import json
import logging
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from references.models import CitedReference, FetchRequest, Publication
from references.services.imports import batch_import, fetch_queue
from references.services.imports.batch_import import Item, import_publications
from references.services.sources import api_log_summary as summary
from references.tests.helpers import crossref_record
from references.tests.sources import simulated_sources
from references.tests.test_importer import CITED_DOI, SOURCE_DOI, crossref_json

Action = FetchRequest.Action
Status = FetchRequest.Status
OTHER_DOI = "10.1000/other"
CROSSREF = {
    SOURCE_DOI: crossref_json("Source", [{"key": "r1", "DOI": CITED_DOI}, {"key": "r2"}]),
    OTHER_DOI: crossref_json("Other", [{"key": "o1", "DOI": CITED_DOI}]),
    CITED_DOI: crossref_json("Cited"),
}
SOURCES = simulated_sources(crossref=CROSSREF)


@SOURCES
class BatchImportTests(TestCase):
    """The steps of the import, each for all the publications of the batch (#381)."""

    def items(self, *dois, with_references=True):
        return [Item(Publication.objects.create(doi=doi), with_references) for doi in dois]

    def test_one_crossref_batch_for_all(self):
        items = import_publications(self.items(SOURCE_DOI, OTHER_DOI))
        self.assertEqual(SOURCES.single("crossref"), [])
        # The two publications, then the cited one once, shared by both.
        self.assertEqual(
            [sorted(batch) for batch in SOURCES.batches("crossref")],
            [sorted([SOURCE_DOI, OTHER_DOI]), [CITED_DOI]],
        )
        self.assertEqual([item.result.title for item in items], ["Source", "Other"])
        self.assertEqual([item.error for item in items], ["", ""])
        cited = Publication.objects.get(doi=CITED_DOI)
        self.assertEqual(cited.title, "Cited")
        self.assertEqual(CitedReference.objects.filter(target=cited).count(), 2)

    def test_a_single_publication_is_asked_alone(self):
        import_publications(self.items(SOURCE_DOI, with_references=False))
        self.assertEqual(SOURCES.single("crossref"), [SOURCE_DOI])
        self.assertEqual(SOURCES.batches("crossref"), [])

    def test_an_unknown_doi_fails_its_item_only(self):
        known, unknown = import_publications(self.items(SOURCE_DOI, "10.1000/unknown"))
        self.assertEqual((known.error, known.result.title), ("", "Source"))
        self.assertEqual((unknown.error, unknown.result), (batch_import.UNKNOWN, None))
        self.assertIsNone(crossref_record(unknown.pub))

    def test_without_references(self):
        import_publications(self.items(SOURCE_DOI, OTHER_DOI, with_references=False))
        self.assertFalse(CitedReference.objects.exists())
        self.assertFalse(Publication.objects.filter(doi=CITED_DOI).exists())

    def test_a_stored_answer_is_not_asked_again(self):
        items = self.items(SOURCE_DOI, OTHER_DOI, with_references=False)
        import_publications(items)
        SOURCES.forget()
        import_publications([Item(item.pub, False) for item in items])
        self.assertEqual(SOURCES.batches("crossref"), [])


@SOURCES
class WorkerBatchTests(TestCase):
    """The worker takes the imports that wait together (#381)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")

    def enqueue(self, doi, with_references=True):
        pub = Publication.objects.get_or_create_doi(doi)
        return fetch_queue.enqueue(pub, self.user, with_references=with_references)

    def run_worker(self):
        out = StringIO()
        call_command("fetch_worker", "--once", stdout=out)
        return out.getvalue()

    def test_the_imports_that_wait_go_together(self):
        first, second = self.enqueue(SOURCE_DOI), self.enqueue(OTHER_DOI)
        out = self.run_worker()
        self.assertIn("2 imports", out)
        self.assertEqual(SOURCES.single("crossref"), [])
        for request in (first, second):
            request.refresh_from_db()
            self.assertEqual((request.status, request.error), (Status.DONE, ""))
            self.assertIsNotNone(request.started_at)

    def test_the_other_actions_wait_their_turn(self):
        first = self.enqueue(SOURCE_DOI)
        refresh = fetch_queue.enqueue_action(
            Action.REFRESH, self.user, publication=Publication.objects.create(doi=OTHER_DOI)
        )
        self.assertEqual(fetch_queue.claim_next(), first)
        self.assertEqual(fetch_queue.claim_companions(10), [])
        refresh.refresh_from_db()
        self.assertEqual(refresh.status, Status.PENDING)

    def test_at_most_a_batch(self):
        for index in range(fetch_queue.BATCH_SIZE + 3):
            self.enqueue(f"10.1000/n{index}", with_references=False)
        first = fetch_queue.claim_next()
        done = fetch_queue.process_claimed(first)
        self.assertEqual(len(done), fetch_queue.BATCH_SIZE)
        self.assertEqual(FetchRequest.objects.filter(status=Status.PENDING).count(), 3)

    def test_two_requests_for_one_publication(self):
        without = self.enqueue(SOURCE_DOI, with_references=False)
        with_references = self.enqueue(SOURCE_DOI, with_references=True)
        self.run_worker()
        self.assertTrue(CitedReference.objects.filter(source__doi=SOURCE_DOI).exists())
        self.assertEqual(set(FetchRequest.objects.values_list("status", flat=True)), {Status.DONE})
        self.assertNotEqual(without, with_references)

    def test_a_book_without_doi_is_imported_alone(self):
        book = Publication.objects.create(isbn="9780262035613")
        request = fetch_queue.enqueue(book, self.user, with_references=False)
        self.assertFalse(fetch_queue.batchable(request))

    def test_the_journal_says_the_batch(self):
        self.enqueue(SOURCE_DOI), self.enqueue(OTHER_DOI)
        logger = "references.api"
        with (
            patch.object(logging.getLogger(logger), "disabled", False),
            self.assertLogs(logger, "INFO") as logs,
        ):
            self.run_worker()
        lines = [json.loads(record.getMessage()) for record in logs.records]
        files = [line for line in lines if line["event"] == "file"]
        self.assertEqual([line["batch"] for line in files], [2, 2])
        self.assertEqual({line["references"] for line in files}, {1, 2})
        # The requests of the batch are shared out between its lines in the summary.
        stats = summary.summarize(files)["by_action"]["import_with_references"]
        self.assertEqual(stats.per_request(), files[0]["api_requests"] / 2)
