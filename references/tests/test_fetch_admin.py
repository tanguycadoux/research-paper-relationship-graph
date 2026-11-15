from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from references.models import FetchRequest, FetchWorker, Publication
from references.services.imports import fetch_admin, fetch_queue
from references.tests.test_navigation import render_navigation

Status = FetchRequest.Status
Action = FetchRequest.Action
URL = reverse("fetch_queue_admin")


def worker_seen(seconds_ago=0):
    FetchWorker.objects.update_or_create(
        pk=1, defaults={"seen_at": timezone.now() - timedelta(seconds=seconds_ago)}
    )


def failed_request(pub, error="DOI inconnu de Crossref et de DataCite."):
    return FetchRequest.objects.create(
        publication=pub,
        identifier=pub.doi,
        action=Action.IMPORT,
        status=Status.FAILED,
        finished_at=timezone.now(),
        error=error,
    )


class FetchAdminAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user("alice")
        cls.admin = User.objects.create_user("root", is_staff=True)
        cls.failed = failed_request(Publication.objects.create(doi="10.1000/failed"))

    def test_visitors_are_sent_to_the_login_page(self):
        response = self.client.get(URL)
        self.assertRedirects(response, f"{reverse('login')}?next={URL}")
        retry = reverse("fetch_request_retry", args=[self.failed.pk])
        self.assertEqual(self.client.post(retry).status_code, 302)
        self.failed.refresh_from_db()
        self.assertEqual(self.failed.status, Status.FAILED)

    def test_users_who_are_not_administrators_are_refused(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(URL).status_code, 403)
        retry = reverse("fetch_request_retry", args=[self.failed.pk])
        self.assertEqual(self.client.post(retry).status_code, 403)
        cancel = reverse("fetch_request_cancel", args=[self.failed.pk])
        self.assertEqual(self.client.post(cancel).status_code, 403)
        self.failed.refresh_from_db()
        self.assertEqual(self.failed.status, Status.FAILED)

    def test_administrators_see_the_page(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(URL), "<h1>File des récupérations</h1>", html=True)

    def test_actions_are_posted(self):
        self.client.force_login(self.admin)
        retry = reverse("fetch_request_retry", args=[self.failed.pk])
        self.assertEqual(self.client.get(retry).status_code, 405)

    def test_the_menu_link_is_for_administrators_only(self):
        self.assertNotIn(URL, render_navigation("/", self.user))
        self.assertNotIn(URL, render_navigation("/", AnonymousUser()))
        html = render_navigation(URL, self.admin)
        self.assertIn("File des récupérations", html)
        self.assertIn("File des récupérations", html.split('aria-current="page"')[1])


class FetchAdminPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user("root", is_staff=True)
        cls.alice, cls.bob = User.objects.create_user("alice"), User.objects.create_user("bob")
        cls.waiting = Publication.objects.create(doi="10.1000/waiting", title="En file")
        cls.pending = fetch_queue.enqueue(cls.waiting, cls.alice, with_references=True)
        fetch_queue.enqueue(cls.waiting, cls.bob, with_references=True)
        cls.other = fetch_queue.enqueue(
            Publication.objects.create(doi="10.1000/other"), cls.bob, with_references=False
        )
        cls.done = Publication.objects.create(doi="10.1000/done", title="Récupérée")
        FetchRequest.objects.create(
            publication=cls.done,
            identifier=cls.done.doi,
            action=Action.IMPORT,
            status=Status.DONE,
            finished_at=timezone.now(),
        )
        cls.failed = failed_request(Publication.objects.create(doi="10.1000/failed"))

    def setUp(self):
        self.client.force_login(self.admin)

    def test_the_requests_of_each_state(self):
        response = self.client.get(URL)
        queue = response.context["queue"]
        self.assertEqual(queue.pending, [self.pending, self.other])
        self.assertEqual(queue.running, [])
        self.assertEqual([r.identifier for r in queue.done], ["10.1000/done"])
        self.assertEqual(queue.failed, [self.failed])
        self.assertContains(response, "Importer avec la bibliographie")
        self.assertContains(response, reverse("publication_detail", args=[self.waiting.pk]))
        self.assertContains(response, "alice,")
        self.assertContains(response, "DOI inconnu de Crossref et de DataCite.")
        self.assertContains(response, reverse("fetch_request_retry", args=[self.failed.pk]))
        self.assertContains(response, reverse("fetch_request_cancel", args=[self.pending.pk]))

    def test_pending_requests_by_action(self):
        response = self.client.get(URL)
        self.assertContains(response, "Importer : 1")
        self.assertContains(response, "Importer avec la bibliographie : 1")

    def test_a_request_whose_publication_is_gone(self):
        FetchRequest.objects.filter(pk=self.failed.pk).update(publication=None)
        self.assertContains(self.client.get(URL), "(publication disparue)")

    def test_a_warning_when_requests_wait_without_a_worker(self):
        response = self.client.get(URL)
        self.assertContains(response, "lancez « python manage.py fetch_worker »")
        self.assertContains(response, "Aucun signe de vie connu.")
        worker_seen(seconds_ago=5)
        response = self.client.get(URL)
        self.assertNotContains(response, "lancez « python manage.py fetch_worker »")
        self.assertContains(response, "Actif")
        self.assertContains(response, "Dernier signe de vie")

    def test_no_warning_without_pending_requests(self):
        FetchRequest.objects.filter(status=Status.PENDING).update(status=Status.DONE)
        worker_seen(seconds_ago=120)
        response = self.client.get(URL)
        self.assertContains(response, "Arrêté")
        self.assertNotContains(response, "lancez « python manage.py fetch_worker »")

    def test_a_constant_number_of_queries(self):
        with CaptureQueriesContext(connection) as before:
            self.client.get(URL)
        for number in range(5):
            pub = Publication.objects.create(doi=f"10.1000/more{number}")
            fetch_queue.enqueue(pub, self.alice, with_references=False)
            failed_request(Publication.objects.create(doi=f"10.1000/failed{number}"))
        with self.assertNumQueries(len(before)):
            self.client.get(URL)


class RetryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_user("root", is_staff=True)
        cls.pub = Publication.objects.create(doi="10.1000/failed")

    def setUp(self):
        self.client.force_login(self.admin)
        self.failed = failed_request(self.pub)

    def post(self, name, request):
        return self.client.post(reverse(name, args=[request.pk]), follow=True)

    def test_a_failed_request_goes_back_to_the_end_of_the_queue(self):
        earlier = fetch_queue.enqueue(
            Publication.objects.create(doi="10.1000/earlier"), None, with_references=False
        )
        response = self.post("fetch_request_retry", self.failed)
        self.assertRedirects(response, URL)
        self.assertContains(response, "Demande relancée : 10.1000/failed")
        self.failed.refresh_from_db()
        self.assertEqual(self.failed.status, Status.PENDING)
        self.assertEqual((self.failed.error, self.failed.finished_at), ("", None))
        self.assertEqual(fetch_queue.claim_next(), earlier)
        self.assertEqual(fetch_queue.claim_next(), self.failed)

    def test_not_twice_when_the_same_request_is_already_active(self):
        active = fetch_queue.enqueue(self.pub, None, with_references=False)
        response = self.post("fetch_request_retry", self.failed)
        self.assertContains(response, "Une demande identique est déjà en file")
        self.failed.refresh_from_db()
        self.assertEqual(self.failed.status, Status.FAILED)
        self.assertEqual(
            list(FetchRequest.objects.filter(status__in=FetchRequest.ACTIVE)), [active]
        )

    def test_another_action_does_not_block(self):
        fetch_queue.enqueue(self.pub, None, with_references=True)
        self.post("fetch_request_retry", self.failed)
        self.failed.refresh_from_db()
        self.assertEqual(self.failed.status, Status.PENDING)

    def test_without_publication_the_identifier_is_compared(self):
        FetchRequest.objects.filter(pk=self.failed.pk).update(publication=None)
        self.failed.refresh_from_db()
        twin = failed_request(self.pub)
        FetchRequest.objects.filter(pk=twin.pk).update(publication=None, status=Status.PENDING)
        with self.assertRaises(fetch_admin.NotRetried):
            fetch_admin.retry(self.failed)

    def test_only_a_failed_request_is_retried(self):
        FetchRequest.objects.filter(pk=self.failed.pk).update(status=Status.DONE)
        response = self.post("fetch_request_retry", self.failed)
        self.assertContains(response, "Seule une demande échouée peut être relancée.")
        self.failed.refresh_from_db()
        self.assertEqual(self.failed.status, Status.DONE)


class CancelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_user("root", is_staff=True)
        cls.alice = get_user_model().objects.create_user("alice")

    def setUp(self):
        self.client.force_login(self.admin)
        self.pub = Publication.objects.create(doi="10.1000/waiting")
        self.pending = fetch_queue.enqueue(self.pub, self.alice, with_references=False)

    def cancel(self):
        url = reverse("fetch_request_cancel", args=[self.pending.pk])
        return self.client.post(url, follow=True)

    def test_a_pending_request_is_cancelled_and_kept_as_failed(self):
        response = self.cancel()
        self.assertRedirects(response, URL)
        self.assertContains(response, "Demande annulée : 10.1000/waiting")
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, Status.FAILED)
        self.assertEqual(self.pending.error, "Annulée par root.")
        self.assertFalse(fetch_queue.publication_pending(self.pub))
        self.assertIsNone(fetch_queue.claim_next())

    def test_a_running_request_is_not_cancelled(self):
        fetch_queue.claim_next()
        response = self.cancel()
        self.assertContains(response, "Seule une demande en attente peut être annulée.")
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, Status.RUNNING)

    def test_a_cancelled_request_can_be_retried(self):
        self.cancel()
        self.pending.refresh_from_db()
        fetch_admin.retry(self.pending)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, Status.PENDING)
