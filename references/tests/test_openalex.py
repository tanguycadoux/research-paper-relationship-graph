from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase, override_settings

from references.models import CitedReference, Publication
from references.services.imports.enrichment import (
    complete_cited_with_openalex,
    complete_with_openalex,
)
from references.services.sources.external_records import Source
from references.services.sources.openalex_api import fetch_openalex_work, fetch_openalex_works
from references.tests.sources import simulated_sources

WORK = {"doi": "https://doi.org/10.1038/NATURE14539", "authorships": []}


def response(payload, status_code=200):
    return Mock(status_code=status_code, headers={}, json=Mock(return_value=payload))


@override_settings(CROSSREF_MAILTO="someone@example.org")
@patch("references.services.sources.http._get_session")
class OpenalexApiTests(SimpleTestCase):
    def call(self, get_session, responses, function, *args):
        get_session.return_value.get.side_effect = responses
        with self.assertLogs("references.services", level="INFO"):
            return function(*args)

    def test_single_work(self, get_session):
        self.assertEqual(
            self.call(get_session, [response(WORK)], fetch_openalex_work, "10.1/a"), WORK
        )
        call = get_session.return_value.get.call_args
        self.assertEqual(call.args[0], "https://api.openalex.org/works/doi:10.1/a")
        self.assertEqual(call.kwargs["params"], {"mailto": "someone@example.org"})

    def test_unknown_work(self, get_session):
        self.assertIsNone(
            self.call(get_session, [response({}, 404)], fetch_openalex_work, "10.1/a")
        )

    def test_batch(self, get_session):
        dois = ["10.1038/nature14539", "10.1000/ghost"]
        works = self.call(get_session, [response({"results": [WORK]})], fetch_openalex_works, dois)
        self.assertEqual(works, {"10.1038/nature14539": WORK, "10.1000/ghost": None})
        params = get_session.return_value.get.call_args.kwargs["params"]
        self.assertEqual(params["filter"], "doi:10.1038/nature14539|10.1000/ghost")
        self.assertEqual(params["per-page"], 2)

    def test_failed_batch_is_absent(self, get_session):
        works = self.call(get_session, [response({}, 404)], fetch_openalex_works, ["10.1/a"])
        self.assertEqual(works, {})


OPENALEX = simulated_sources(openalex=[WORK])


@OPENALEX
class CompleteWithOpenalexTests(TestCase):
    def test_work_is_stored_and_not_fetched_again(self):
        pub = Publication.objects.create(doi="10.1038/nature14539")
        complete_with_openalex(pub)
        complete_with_openalex(pub)
        self.assertEqual(OPENALEX.single("openalex"), ["10.1038/nature14539"])
        self.assertEqual(pub.external_records.get(source=Source.OPENALEX).data, WORK)

    def test_refresh_fetches_again(self):
        pub = Publication.objects.create(doi="10.1038/nature14539")
        complete_with_openalex(pub)
        complete_with_openalex(pub, force_fetch=True)
        self.assertEqual(len(OPENALEX.single("openalex")), 2)

    def test_unknown_or_failed_is_not_stored(self):
        pub = Publication.objects.create(doi="10.1000/ghost")
        complete_with_openalex(pub)
        self.assertFalse(pub.external_records.exists())

    def test_publication_without_doi(self):
        complete_with_openalex(Publication.objects.create(title="Sans DOI"))
        self.assertEqual(OPENALEX.requests, [])


class CompleteCitedWithOpenalexTests(TestCase):
    def setUp(self):
        self.source = Publication.objects.create(title="Source")
        for position, doi in enumerate(["10.1038/nature14539", "10.1000/ghost", ""]):
            target = Publication.objects.create(doi=doi, title=f"Cited {position}")
            CitedReference.objects.create(source=self.source, target=target, position=position)

    def complete(self):
        with OPENALEX:
            complete_cited_with_openalex(self.source)
        return [sorted(batch) for batch in OPENALEX.batches("openalex")]

    def test_one_batch_for_the_cited_dois(self):
        self.assertEqual(self.complete(), [["10.1000/ghost", "10.1038/nature14539"]])
        known = Publication.objects.get(doi="10.1038/nature14539")
        self.assertEqual(known.external_records.get(source=Source.OPENALEX).data, WORK)

    def test_dois_already_asked_are_not_asked_again(self):
        self.complete()
        self.assertEqual(self.complete(), [])
