from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from references.models import (
    Author,
    FetchRequest,
    FetchWorker,
    GraphImage,
    MetadataConflict,
    Publication,
    UserPublication,
)
from references.services.display import graph_images
from references.services.imports import fetch_actions, fetch_queue
from references.tests.helpers import with_crossref

Action = FetchRequest.Action
Status = FetchRequest.Status


def worker_seen():
    FetchWorker.objects.update_or_create(pk=1, defaults={"seen_at": timezone.now()})


def run_worker():
    call_command("fetch_worker", "--once", stdout=StringIO())


class QueuedActionsTests(TestCase):
    """With a worker, the long actions of the pages go through the queue (#380)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")
        cls.pub = with_crossref(
            Publication.objects.create(doi="10.1000/a", title="Article"), {"message": {}}
        )

    def setUp(self):
        self.client.force_login(self.user)
        worker_seen()

    def assert_queued(self, action, **target):
        request = FetchRequest.objects.get()
        self.assertEqual(request.action, action)
        for name, value in target.items():
            self.assertEqual(getattr(request, name), value)
        self.assertEqual(list(request.requesters.all()), [self.user])
        return request

    def test_refresh(self):
        response = self.client.post(reverse("publication_refresh", args=[self.pub.pk]), follow=True)
        self.assert_queued(Action.REFRESH, publication=self.pub, identifier="10.1000/a")
        self.assertContains(response, "Rafraîchissement des métadonnées de « Article » en file")
        self.assertContains(response, "Données en cours de récupération")

    def test_import_references(self):
        url = reverse("publication_import_references", args=[self.pub.pk])
        response = self.client.post(url, follow=True)
        self.assert_queued(Action.IMPORT_WITH_REFERENCES, publication=self.pub)
        self.assertContains(response, "Références de « Article » en file de récupération.")

    def test_incoming_citations(self):
        url = reverse("publication_incoming_citations", args=[self.pub.pk])
        response = self.client.post(url, follow=True)
        self.assert_queued(Action.INCOMING_CITATIONS, publication=self.pub)
        self.assertContains(response, "Recherche des publications qui citent « Article » en file")

    def test_leaving_to_read(self):
        UserPublication.objects.create(
            user=self.user,
            publication=self.pub,
            reading_status=UserPublication.ReadingStatus.TO_READ,
        )
        response = self.client.post(
            reverse("corpus_reading_status", args=[self.pub.pk]),
            {"status": UserPublication.ReadingStatus.READING},
            follow=True,
        )
        self.assert_queued(Action.IMPORT_WITH_REFERENCES, publication=self.pub)
        self.assertContains(response, "en cours. Sa bibliographie est en file de récupération.")
        entry = UserPublication.objects.get()
        self.assertEqual(entry.reading_status, UserPublication.ReadingStatus.READING)

    def test_a_status_that_imports_nothing_queues_nothing(self):
        UserPublication.objects.create(user=self.user, publication=self.pub)
        self.client.post(
            reverse("corpus_reading_status", args=[self.pub.pk]),
            {"status": UserPublication.ReadingStatus.READ},
        )
        self.assertFalse(FetchRequest.objects.exists())

    def test_identifier_change(self):
        response = self.client.post(
            reverse("publication_edit", args=[self.pub.pk]),
            {"doi": "10.1000/b", "isbn": "", "title": "Article", "publication_date": ""},
            follow=True,
        )
        self.pub.refresh_from_db()
        self.assertFalse(self.pub.external_records.exists())  # what the old DOI gave
        self.assert_queued(Action.IMPORT, publication=self.pub, identifier="10.1000/b")
        self.assertContains(response, "Identifiant modifié : les données de")

    def test_published_version(self):
        conflict = MetadataConflict.objects.create(
            kind=MetadataConflict.Kind.PUBLISHED_VERSION,
            publication=self.pub,
            field="doi",
            current_value="10.1000/a",
            proposed_value="10.1000/published",
        )
        response = self.client.post(
            reverse("conflict_resolve", args=[conflict.pk]),
            {"decision": MetadataConflict.Status.ACCEPTED},
            follow=True,
        )
        self.assert_queued(
            Action.PUBLISHED_VERSION, publication=self.pub, identifier="10.1000/published"
        )
        self.assertContains(response, "par sa version publiée en file de récupération")
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, MetadataConflict.Status.OPEN)  # decided by the worker

    def test_orcid_profile(self):
        author = Author.objects.create(last_name="Lovelace", orcid="0000-0001")
        response = self.client.post(reverse("author_orcid_refresh", args=[author.pk]), follow=True)
        self.assert_queued(Action.ORCID_PROFILE, author=author, identifier="0000-0001")
        self.assertContains(response, "Profil ORCID en file de récupération.")
        self.assertContains(response, f'data-fetch-pending-author="{author.pk}"')
        data = self.client.get(reverse("fetch_progress"), {"author": author.pk}).json()
        self.assertTrue(data["author_pending"])

    def test_a_second_request_joins_the_first(self):
        url = reverse("publication_refresh", args=[self.pub.pk])
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(FetchRequest.objects.count(), 1)

    def test_graph_image(self):
        with (
            patch.object(graph_images, "is_large", return_value=True),
            patch.object(graph_images, "run_in_background") as thread,
        ):
            graph_images.request_image(GraphImage.Kind.BASE, self.user)
        thread.assert_not_called()
        self.assert_queued(Action.GRAPH_IMAGE, identifier=GraphImage.Kind.BASE)

    def test_only_publications_count_in_the_toast(self):
        author = Author.objects.create(last_name="Lovelace", orcid="0000-0001")
        fetch_queue.enqueue_action(
            Action.ORCID_PROFILE, self.user, author=author, identifier=author.orcid
        )
        self.assertIsNone(fetch_queue.progress(self.user))


class WithoutWorkerTests(TestCase):
    """Without a worker, the pages do the work themselves, as before (#380)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")

    def test_the_graph_image_in_a_thread(self):
        with patch.object(graph_images, "run_in_background") as thread:
            graph_images.request_image(GraphImage.Kind.BASE, self.user)
        thread.assert_called_once()
        self.assertFalse(FetchRequest.objects.exists())

    @patch("references.views.authors.refresh_orcid_record", return_value=True)
    def test_the_orcid_profile(self, refresh):
        self.client.force_login(self.user)
        author = Author.objects.create(last_name="Lovelace", orcid="0000-0001")
        response = self.client.post(reverse("author_orcid_refresh", args=[author.pk]), follow=True)
        refresh.assert_called_once()
        self.assertContains(response, "Profil ORCID mis à jour.")
        self.assertFalse(FetchRequest.objects.exists())


class HandlersTests(TestCase):
    """What the worker does for each action (#380)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")
        cls.pub = Publication.objects.create(doi="10.1000/a", title="Article")

    def outcome(self, request):
        run_worker()
        request.refresh_from_db()
        return request.status, request.error

    def test_refresh_asks_the_sources_again(self):
        request = fetch_queue.enqueue_action(Action.REFRESH, self.user, publication=self.pub)
        with patch.object(fetch_actions, "import_publication", return_value=self.pub) as imp:
            self.assertEqual(self.outcome(request), (Status.DONE, ""))
        imp.assert_called_once_with(self.pub, with_references=False, force_fetch=True)

    def test_a_refresh_without_answer_fails(self):
        request = fetch_queue.enqueue_action(Action.REFRESH, self.user, publication=self.pub)
        with patch.object(fetch_actions, "import_publication", return_value=None):
            status, error = self.outcome(request)
        self.assertEqual(status, Status.FAILED)
        self.assertIn("Les sources n'ont pas répondu", error)

    @patch("references.services.discovery.incoming_citations.openalex_id", return_value=None)
    def test_incoming_citations_error_is_kept(self, _openalex_id):
        request = fetch_queue.enqueue_action(
            Action.INCOMING_CITATIONS, self.user, publication=self.pub
        )
        status, error = self.outcome(request)
        self.assertEqual(
            (status, error), (Status.FAILED, "OpenAlex ne connaît pas cette publication.")
        )

    def test_published_version_no_longer_proposed(self):
        request = fetch_queue.enqueue_action(
            Action.PUBLISHED_VERSION, self.user, publication=self.pub, identifier="10.1000/p"
        )
        status, error = self.outcome(request)
        self.assertEqual(status, Status.FAILED)
        self.assertIn("n'est plus proposée", error)

    @patch("references.services.imports.published_versions.accept_published_version")
    def test_published_version_accepted_by_its_requester(self, accept):
        published = Publication.objects.create(doi="10.1000/p")
        accept.return_value = published
        conflict = MetadataConflict.objects.create(
            kind=MetadataConflict.Kind.PUBLISHED_VERSION,
            publication=self.pub,
            field="doi",
            proposed_value="10.1000/p",
        )
        request = fetch_queue.enqueue_action(
            Action.PUBLISHED_VERSION, self.user, publication=self.pub, identifier="10.1000/p"
        )
        with patch.object(fetch_actions, "import_publication", return_value=published):
            self.assertEqual(self.outcome(request), (Status.DONE, ""))
        accept.assert_called_once_with(conflict, self.user)
        request.refresh_from_db()
        self.assertEqual(request.publication, published)

    @patch("references.services.imports.orcid_profile.refresh_orcid_record", return_value=False)
    def test_orcid_without_answer_fails(self, _refresh):
        author = Author.objects.create(last_name="Lovelace", orcid="0000-0001")
        request = fetch_queue.enqueue_action(
            Action.ORCID_PROFILE, self.user, author=author, identifier=author.orcid
        )
        status, error = self.outcome(request)
        self.assertEqual(status, Status.FAILED)
        self.assertIn("ORCID n'a pas répondu", error)

    def test_graph_image(self):
        GraphImage.objects.create(kind=GraphImage.Kind.BASE, requested_at=timezone.now())
        request = fetch_queue.enqueue_action(
            Action.GRAPH_IMAGE, self.user, identifier=GraphImage.Kind.BASE
        )
        with patch.object(graph_images, "render_svg", return_value="<svg/>"):
            self.assertEqual(self.outcome(request), (Status.DONE, ""))
        self.assertEqual(GraphImage.objects.get().status, GraphImage.Status.DONE)

    def test_a_failed_graph_image_fails_the_request(self):
        GraphImage.objects.create(kind=GraphImage.Kind.BASE, requested_at=timezone.now())
        request = fetch_queue.enqueue_action(
            Action.GRAPH_IMAGE, self.user, identifier=GraphImage.Kind.BASE
        )
        with patch.object(graph_images, "render_svg", side_effect=ValueError("trop grand")):
            status, error = self.outcome(request)
        self.assertEqual(status, Status.FAILED)
        self.assertIn("trop grand", error)
