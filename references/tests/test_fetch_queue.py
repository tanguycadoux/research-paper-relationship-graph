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
from references.services.imports import fetch_queue
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
        real = fetch_queue.import_publication

        def import_publication(pub, **kwargs):
            if pub.doi == "10.1000/broken":
                raise RuntimeError("panne")
            return real(pub, **kwargs)

        with (
            patch.object(fetch_queue, "import_publication", side_effect=import_publication),
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
        with patch.object(fetch_queue, "import_publication", side_effect=lambda pub, **_: pub):
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
