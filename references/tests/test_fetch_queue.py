import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from references.models import (
    CitedReference,
    FetchRequest,
    FetchWorker,
    Publication,
    UserPublication,
)
from references.services.imports import fetch_actions, fetch_queue
from references.tests.helpers import with_crossref, with_openlibrary, without_other_sources
from references.tests.test_corpus_transfer import export_of
from references.tests.test_importer import with_mocked_crossref

Status = FetchRequest.Status
Action = FetchRequest.Action
BOOK_ISBN = "9780262035613"


def worker_seen(seconds_ago=0):
    FetchWorker.objects.update_or_create(
        pk=1, defaults={"seen_at": timezone.now() - timedelta(seconds=seconds_ago)}
    )


def run_worker():
    call_command("fetch_worker", "--once", stdout=StringIO())


class WorkerAliveTests(TestCase):
    def test_a_worker_counts_for_thirty_seconds(self):
        self.assertFalse(fetch_queue.worker_alive())
        worker_seen(seconds_ago=29)
        self.assertTrue(fetch_queue.worker_alive())
        worker_seen(seconds_ago=31)
        self.assertFalse(fetch_queue.worker_alive())

    def test_a_worker_that_stops_says_so(self):
        fetch_queue.signal_alive()
        fetch_queue.signal_stopped()
        self.assertFalse(fetch_queue.worker_alive())


class EnqueueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice, cls.bob = User.objects.create_user("alice"), User.objects.create_user("bob")
        cls.pub = Publication.objects.create(doi="10.1000/source")

    def test_a_second_requester_joins_the_same_request(self):
        first = fetch_queue.enqueue(self.pub, self.alice, with_references=True)
        second = fetch_queue.enqueue(self.pub, self.bob, with_references=True)
        self.assertEqual(first, second)
        self.assertEqual(FetchRequest.objects.count(), 1)
        self.assertEqual(set(first.requesters.all()), {self.alice, self.bob})
        self.assertEqual(first.identifier, "10.1000/source")

    def test_a_running_request_is_joined_too(self):
        first = fetch_queue.enqueue(self.pub, self.alice, with_references=False)
        self.assertEqual(fetch_queue.claim_next(), first)
        self.assertEqual(fetch_queue.enqueue(self.pub, self.bob, with_references=False), first)

    def test_other_action_or_finished_request_makes_a_new_one(self):
        first = fetch_queue.enqueue(self.pub, self.alice, with_references=False)
        with_references = fetch_queue.enqueue(self.pub, self.alice, with_references=True)
        self.assertNotEqual(first, with_references)
        FetchRequest.objects.filter(pk=first.pk).update(status=Status.DONE)
        self.assertNotEqual(fetch_queue.enqueue(self.pub, self.alice, with_references=False), first)

    def test_requests_are_claimed_in_order(self):
        other = Publication.objects.create(doi="10.1000/other")
        first = fetch_queue.enqueue(self.pub, self.alice, with_references=False)
        second = fetch_queue.enqueue(other, self.alice, with_references=False)
        self.assertEqual(fetch_queue.claim_next(), first)
        self.assertEqual(fetch_queue.claim_next(), second)
        self.assertIsNone(fetch_queue.claim_next())
        first.refresh_from_db()
        self.assertEqual(first.status, Status.RUNNING)
        self.assertIsNotNone(first.started_at)

    def test_interrupted_requests_go_back_to_the_queue(self):
        request = fetch_queue.enqueue(self.pub, self.alice, with_references=False)
        fetch_queue.claim_next()
        # The worker starts by taking them back.
        self.assertEqual(fetch_queue.recover_interrupted(), 1)
        request.refresh_from_db()
        self.assertEqual((request.status, request.started_at), (Status.PENDING, None))


@without_other_sources
@with_mocked_crossref
class WorkerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")

    def test_the_worker_imports_with_the_bibliography(self, fetch, fetch_works):
        pub = Publication.objects.create(doi="10.1000/source")
        request = fetch_queue.enqueue(pub, self.user, with_references=True)
        run_worker()
        request.refresh_from_db()
        pub.refresh_from_db()
        self.assertEqual((request.status, request.error), (Status.DONE, ""))
        self.assertIsNotNone(request.finished_at)
        self.assertEqual(pub.title, "Source")
        self.assertTrue(CitedReference.objects.filter(source=pub).exists())

    def test_without_the_bibliography(self, fetch, fetch_works):
        pub = Publication.objects.create(doi="10.1000/source")
        fetch_queue.enqueue(pub, self.user, with_references=False)
        run_worker()
        self.assertFalse(CitedReference.objects.filter(source=pub).exists())

    def test_a_failure_is_kept_with_its_error(self, fetch, fetch_works):
        pub = Publication.objects.create(doi="10.1000/unknown")
        request = fetch_queue.enqueue(pub, self.user, with_references=False)
        run_worker()
        request.refresh_from_db()
        self.assertEqual(request.status, Status.FAILED)
        self.assertIn("DOI inconnu", request.error)

    def test_an_exception_fails_the_request_and_the_worker_goes_on(self, fetch, fetch_works):
        broken = fetch_queue.enqueue(
            Publication.objects.create(doi="10.1000/broken"), self.user, with_references=False
        )
        next_one = fetch_queue.enqueue(
            Publication.objects.create(doi="10.1000/source"), self.user, with_references=False
        )
        real = fetch_actions.import_publication

        def import_publication(pub, **kwargs):
            if pub.doi == "10.1000/broken":
                raise RuntimeError("panne")
            return real(pub, **kwargs)

        with (
            patch.object(fetch_actions, "import_publication", side_effect=import_publication),
            self.assertLogs("references.services.imports.fetch_queue", "ERROR"),
        ):
            run_worker()
        broken.refresh_from_db()
        next_one.refresh_from_db()
        self.assertEqual(broken.status, Status.FAILED)
        self.assertIn("panne", broken.error)
        self.assertEqual(next_one.status, Status.DONE)


@without_other_sources
class QueuedBookTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")

    @patch("references.services.imports.books.fetch_crossref_by_isbn", return_value=None)
    @patch(
        "references.services.imports.books.fetch_openlibrary_book",
        return_value={"title": "Un livre", "publish_date": "2016"},
    )
    def test_a_book_from_open_library(self, _openlibrary, _crossref):
        book = Publication.objects.create(isbn=BOOK_ISBN)
        request = fetch_queue.enqueue(book, self.user, with_references=False)
        run_worker()
        request.refresh_from_db()
        self.assertEqual(request.status, Status.DONE)
        self.assertEqual(request.identifier, BOOK_ISBN)

    @patch(
        "references.services.imports.books.fetch_crossref_by_isbn",
        return_value={"message": {"DOI": "10.1000/book", "title": ["Le livre"]}},
    )
    def test_the_doi_of_a_book_already_in_the_base_takes_its_place(self, _crossref):
        holder = with_crossref(Publication.objects.create(doi="10.1000/book"), {"message": {}})
        placeholder = Publication.objects.create(isbn=BOOK_ISBN)
        UserPublication.objects.create(user=self.user, publication=placeholder)
        request = fetch_queue.enqueue(placeholder, self.user, with_references=False)
        with patch.object(fetch_actions, "import_publication", side_effect=lambda pub, **_: pub):
            run_worker()
        request.refresh_from_db()
        holder.refresh_from_db()
        self.assertFalse(Publication.objects.filter(pk=placeholder.pk).exists())
        self.assertEqual(holder.isbn, BOOK_ISBN)
        self.assertEqual((request.status, request.publication), (Status.DONE, holder))
        self.assertTrue(UserPublication.objects.filter(user=self.user, publication=holder).exists())

    @patch("references.services.imports.books.fetch_crossref_by_isbn", return_value=None)
    @patch("references.services.imports.books.fetch_openlibrary_book", return_value=None)
    def test_an_unknown_isbn_fails(self, _openlibrary, _crossref):
        request = fetch_queue.enqueue(
            Publication.objects.create(isbn=BOOK_ISBN), self.user, with_references=False
        )
        run_worker()
        request.refresh_from_db()
        self.assertEqual(request.status, Status.FAILED)
        self.assertIn("ISBN inconnu", request.error)


@without_other_sources
@with_mocked_crossref
class AddWithWorkerTests(TestCase):
    """With a worker, adding answers at once and leaves the retrieval to the queue."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        self.client.force_login(self.user)
        worker_seen()

    def add(self, identifier, **extra):
        return self.client.post(
            reverse("corpus_add_by_identifier"), {"identifier": identifier, **extra}, follow=True
        )

    def test_the_doi_is_queued_without_any_request(self, fetch, fetch_works):
        response = self.add("10.1000/source")
        fetch.assert_not_called()
        pub = Publication.objects.get(doi="10.1000/source")
        self.assertTrue(UserPublication.objects.filter(user=self.user, publication=pub).exists())
        request = FetchRequest.objects.get()
        self.assertEqual(
            (request.publication, request.action), (pub, Action.IMPORT_WITH_REFERENCES)
        )
        self.assertEqual(list(request.requesters.all()), [self.user])
        self.assertContains(response, "ses données sont en file de récupération")

    def test_to_read_leaves_the_bibliography_aside(self, fetch, fetch_works):
        response = self.add("10.1000/source", status=UserPublication.ReadingStatus.TO_READ)
        self.assertEqual(FetchRequest.objects.get().action, Action.IMPORT)
        self.assertContains(response, "à votre corpus, à lire ; ses données")

    @patch("references.services.corpus.entries.find_or_import_book")
    def test_an_isbn_is_not_looked_up_by_the_page(self, find_book, fetch, fetch_works):
        self.add("978-0-262-03561-3")
        find_book.assert_not_called()
        request = FetchRequest.objects.get()
        self.assertEqual((request.identifier, request.action), (BOOK_ISBN, Action.IMPORT))

    def test_a_book_with_its_metadata_is_not_queued(self, fetch, fetch_works):
        with_openlibrary(Publication.objects.create(isbn=BOOK_ISBN), {"title": "Un livre"})
        response = self.add(BOOK_ISBN)
        self.assertFalse(FetchRequest.objects.exists())
        self.assertContains(response, "a été ajouté à votre corpus.")

    def test_without_worker_the_page_fetches_itself(self, fetch, fetch_works):
        FetchWorker.objects.update(seen_at=timezone.now() - timedelta(minutes=1))
        response = self.add("10.1000/source")
        fetch.assert_called_once_with("10.1000/source")
        self.assertFalse(FetchRequest.objects.exists())
        self.assertContains(response, "« Source » a été ajouté à votre corpus.")

    def test_the_file_import_queues_its_entries(self, fetch, fetch_works):
        content = json.dumps(export_of({"doi": "10.1000/source"}, {"doi": "10.1000/other"}))
        upload = SimpleUploadedFile("corpus.json", content.encode(), "application/json")
        response = self.client.post(reverse("corpus_import"), {"file": upload}, follow=True)
        fetch.assert_not_called()
        self.assertEqual(FetchRequest.objects.count(), 2)
        self.assertEqual(UserPublication.objects.filter(user=self.user).count(), 2)
        self.assertContains(response, "Import enregistré : 2 publications en file de récupération.")
        self.assertEqual(response.context["import_report"]["queued"]["count"], 2)
        self.assertContains(response, "2</strong> publications en file de récupération")


class ProgressTests(TestCase):
    """The toast of the requests in the queue (#379)."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice, cls.bob = User.objects.create_user("alice"), User.objects.create_user("bob")

    def request(self, user, doi, status=Status.PENDING):
        pub = Publication.objects.get_or_create_doi(doi)
        request = fetch_queue.enqueue(pub, user, with_references=False)
        FetchRequest.objects.filter(pk=request.pk).update(status=status)
        return request

    def test_nothing_without_an_active_request(self):
        self.request(self.alice, "10.1000/old", Status.DONE)
        self.assertIsNone(fetch_queue.progress(self.alice))
        self.client.force_login(self.alice)
        self.assertNotContains(self.client.get(reverse("corpus")), "data-fetch-progress-toast")

    def test_counts_since_the_oldest_active_request(self):
        self.request(self.alice, "10.1000/a", Status.DONE)
        FetchRequest.objects.update(requested_at=timezone.now() - timedelta(hours=1))
        self.request(self.alice, "10.1000/b", Status.DONE)
        self.request(self.alice, "10.1000/c", Status.FAILED)
        FetchRequest.objects.exclude(identifier="10.1000/a").update(
            requested_at=timezone.now() - timedelta(minutes=1)
        )
        self.request(self.alice, "10.1000/d")
        self.request(self.alice, "10.1000/e", Status.RUNNING)
        # a, b and c were asked before the oldest active request: an earlier batch.
        state = fetch_queue.progress(self.alice)
        self.assertEqual((state.total, state.done, state.failed), (2, 0, 0))
        self.assertEqual(fetch_queue.progress_text(state), "0 publication récupérée sur 2.")

    def test_a_followed_batch_keeps_its_start(self):
        first = self.request(self.alice, "10.1000/a")
        since = fetch_queue.progress(self.alice).start
        self.request(self.alice, "10.1000/b")
        FetchRequest.objects.exclude(pk=first.pk).update(requested_at=since + timedelta(seconds=1))
        # a finished while b was waiting: the same batch.
        FetchRequest.objects.filter(pk=first.pk).update(
            status=Status.DONE, finished_at=since + timedelta(seconds=3)
        )
        state = fetch_queue.progress(self.alice, since=since)
        self.assertEqual((state.total, state.done, state.active), (2, 1, True))

    def test_a_batch_over_long_ago_is_not_followed_any_more(self):
        old = self.request(self.alice, "10.1000/old")
        since = fetch_queue.progress(self.alice).start
        FetchRequest.objects.filter(pk=old.pk).update(
            status=Status.DONE, finished_at=since + timedelta(seconds=5)
        )
        self.request(self.alice, "10.1000/new")
        FetchRequest.objects.exclude(pk=old.pk).update(requested_at=since + timedelta(days=2))
        state = fetch_queue.progress(self.alice, since=since)
        self.assertEqual((state.total, state.done), (1, 0))

    def test_requests_of_others_before_mine(self):
        self.request(self.bob, "10.1000/bob1")
        self.request(self.bob, "10.1000/bob2", Status.RUNNING)
        mine = self.request(self.alice, "10.1000/mine")
        self.request(self.bob, "10.1000/bob3")
        state = fetch_queue.progress(self.alice)
        self.assertEqual(state.ahead, 2)
        self.assertEqual(state.publications, {mine.publication_id})
        self.assertEqual(
            fetch_queue.progress_text(state),
            "Récupération de « 10.1000/mine »… 2 demandes avant la vôtre.",
        )

    def test_a_joined_request_is_not_ahead(self):
        shared = self.request(self.bob, "10.1000/shared")
        shared.requesters.add(self.alice)
        self.assertEqual(fetch_queue.progress(self.alice).ahead, 0)

    def test_outcome_of_a_batch_once_over(self):
        first = self.request(self.alice, "10.1000/a")
        since = fetch_queue.progress(self.alice).start
        self.request(self.alice, "10.1000/b")
        FetchRequest.objects.filter(pk=first.pk).update(status=Status.DONE)
        FetchRequest.objects.exclude(pk=first.pk).update(status=Status.FAILED)
        state = fetch_queue.progress(self.alice, since=since)
        self.assertFalse(state.active)
        self.assertEqual(
            fetch_queue.progress_text(state),
            "Récupération terminée : 1 publication récupérée, 1 échec.",
        )

    def test_toast_on_every_page_and_json(self):
        self.request(self.alice, "10.1000/a", Status.DONE)
        self.request(self.alice, "10.1000/b")
        FetchRequest.objects.filter(identifier="10.1000/a").update(
            requested_at=timezone.now() + timedelta(seconds=1)
        )
        self.client.force_login(self.alice)
        for name in ("index", "corpus", "publication_list"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertContains(response, "data-fetch-progress-toast")
                self.assertContains(response, "1 publication récupérée sur 2.")
                self.assertContains(response, "js/fetch_progress.js")
        data = self.client.get(reverse("fetch_progress")).json()
        self.assertEqual((data["active"], data["text"]), (True, "1 publication récupérée sur 2."))

    def test_json_once_over(self):
        self.client.force_login(self.alice)
        data = self.client.get(reverse("fetch_progress"), {"since": "pas une date"}).json()
        self.assertEqual(data, {"active": False, "text": ""})

    def test_the_page_of_a_publication_in_the_queue(self):
        request = self.request(self.bob, "10.1000/a")
        self.client.force_login(self.alice)
        url = reverse("publication_detail", args=[request.publication_id])
        response = self.client.get(url)
        self.assertContains(response, "Données en cours de récupération")
        self.assertContains(response, f'data-fetch-pending-publication="{request.publication_id}"')
        self.assertContains(response, "js/fetch_progress.js")
        data = self.client.get(
            reverse("fetch_progress"), {"publication": request.publication_id}
        ).json()
        self.assertTrue(data["publication_pending"])
        FetchRequest.objects.update(status=Status.DONE)
        self.assertNotContains(self.client.get(url), "Données en cours de récupération")
        data = self.client.get(
            reverse("fetch_progress"), {"publication": request.publication_id}
        ).json()
        self.assertFalse(data["publication_pending"])

    def test_visitors_see_nothing(self):
        request = self.request(self.bob, "10.1000/a")
        response = self.client.get(reverse("publication_detail", args=[request.publication_id]))
        self.assertNotContains(response, "Données en cours de récupération")
        self.assertNotContains(response, "fetch_progress.js")


class BatchOutcomeTests(TestCase):
    """Once a batch is over, the next page says how it went, once (#379)."""

    @classmethod
    def setUpTestData(cls):
        cls.alice = get_user_model().objects.create_user("alice")

    def setUp(self):
        self.client.force_login(self.alice)
        self.request = fetch_queue.enqueue(
            Publication.objects.create(doi="10.1000/a"), self.alice, with_references=False
        )
        self.client.get(reverse("corpus"))  # the batch is followed from now on

    def finish(self):
        FetchRequest.objects.update(status=Status.DONE)

    def test_the_next_page_says_it_once(self):
        self.finish()
        response = self.client.get(reverse("corpus"))
        self.assertContains(response, "« 10.1000/a » récupérée.")
        self.assertContains(response, "data-toast-autohide")
        self.assertNotContains(response, "fetch_progress.js")
        self.assertNotContains(self.client.get(reverse("corpus")), "récupérée.")

    def test_not_again_once_the_toast_said_it(self):
        self.finish()
        data = self.client.get(reverse("fetch_progress")).json()
        self.assertEqual(data["text"], "« 10.1000/a » récupérée.")
        self.assertNotContains(self.client.get(reverse("corpus")), "récupérée.")

    def test_the_page_that_reloads_says_it(self):
        self.finish()
        pk = self.request.publication_id
        data = self.client.get(reverse("fetch_progress"), {"publication": pk}).json()
        self.assertFalse(data["publication_pending"])
        response = self.client.get(reverse("publication_detail", args=[pk]))
        self.assertContains(response, "« 10.1000/a » récupérée.")

    def test_the_pending_page_does_not_offer_to_refresh(self):
        response = self.client.get(
            reverse("publication_detail", args=[self.request.publication_id])
        )
        self.assertContains(response, "Données en cours de récupération")
        self.assertNotContains(response, "pas encore été récupérées")


class SingleRequestTextTests(TestCase):
    """A batch of one request says what it does, not « 1 publication » (#380)."""

    @classmethod
    def setUpTestData(cls):
        cls.alice = get_user_model().objects.create_user("alice")
        cls.pub = Publication.objects.create(doi="10.1000/a", title="Article")

    def text(self):
        return fetch_queue.progress_text(fetch_queue.progress(self.alice, since=self.since))

    def setUp(self):
        self.request = fetch_queue.enqueue(self.pub, self.alice, with_references=True)
        self.since = fetch_queue.progress(self.alice).start

    def test_its_bibliography_while_it_waits(self):
        self.assertEqual(self.text(), "Récupération de « Article » et de sa bibliographie…")

    def test_the_references_it_brought(self):
        for position in range(3):
            CitedReference.objects.create(source=self.pub, position=position)
        FetchRequest.objects.update(status=Status.DONE)
        self.assertEqual(self.text(), "« Article » récupérée avec sa bibliographie : 3 références.")

    def test_its_error(self):
        FetchRequest.objects.update(status=Status.FAILED, error="Crossref injoignable.")
        self.assertEqual(
            self.text(), "Échec de la récupération de « Article » : Crossref injoignable."
        )

    def test_a_refresh(self):
        FetchRequest.objects.all().delete()
        fetch_queue.enqueue_action(Action.REFRESH, self.alice, publication=self.pub)
        self.since = None
        self.assertEqual(self.text(), "Rafraîchissement des métadonnées de « Article »…")

    def test_several_requests_are_counted(self):
        fetch_queue.enqueue(
            Publication.objects.create(doi="10.1000/b"), self.alice, with_references=True
        )
        self.assertEqual(self.text(), "0 publication récupérée sur 2.")
