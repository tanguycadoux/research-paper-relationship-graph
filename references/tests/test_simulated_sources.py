"""The simulated sources answer the real clients, from the URL and the parameters (#299)."""

from django.test import SimpleTestCase

from references.services.sources import (
    arxiv_api,
    crossref_api,
    datacite_api,
    doi_registration,
    openalex_api,
    openlibrary_api,
    orcid_api,
)
from references.services.sources.http import get_json
from references.tests.sources import UnsimulatedRequest, fixture, simulated_sources

CROSSREF = fixture("crossref_e17-2025.json")
CROSSREF_DOI = "10.18653/v1/e17-2025"
DATACITE = fixture("datacite_jacow_ecris2016_tuao05.json")
DATACITE_DOI = "10.18429/jacow-ecris2016-tuao05"
OPENALEX = fixture("openalex_arxiv1706.03762.json")
ARXIV_DOI = "10.48550/arxiv.1706.03762"
ORCID_ENTRIES = fixture("orcid_expanded_search.json")["expanded-result"]

SOURCES = simulated_sources(crossref=[CROSSREF], datacite=[DATACITE], openalex=[OPENALEX])


class CrossrefTests(SimpleTestCase):
    @SOURCES
    def test_a_single_doi(self):
        self.assertEqual(crossref_api.fetch_crossref_json(CROSSREF_DOI), CROSSREF)
        self.assertIsNone(crossref_api.fetch_crossref_json("10.1000/unknown"))
        self.assertEqual(SOURCES.single("crossref"), [CROSSREF_DOI, "10.1000/unknown"])

    @SOURCES
    def test_a_batch_answers_the_known_dois(self):
        works = crossref_api.fetch_crossref_works([CROSSREF_DOI, "10.1000/unknown"])
        self.assertEqual(works[CROSSREF_DOI]["message"], CROSSREF["message"])
        self.assertIsNone(works["10.1000/unknown"])
        self.assertEqual(SOURCES.batches("crossref"), [[CROSSREF_DOI, "10.1000/unknown"]])

    def test_a_doi_given_by_its_answer_or_its_key(self):
        with simulated_sources(crossref={"10.1000/A": {"message": {"title": ["A"]}}}):
            work = crossref_api.fetch_crossref_json("10.1000/a")
            works = crossref_api.fetch_crossref_works(["10.1000/a"])
        self.assertEqual(work["message"], {"DOI": "10.1000/A", "title": ["A"]})
        self.assertEqual(works["10.1000/a"]["message"]["title"], ["A"])

    def test_isbn_and_bibliographic_search(self):
        book = {"message": {"DOI": "10.1000/book", "ISBN": ["978-0-19-854805-8"]}}
        item = {"DOI": "10.1000/found", "title": ["Found"]}
        with simulated_sources(crossref=[book], crossref_searches={"Some text": [item]}):
            self.assertEqual(
                crossref_api.fetch_crossref_by_isbn("9780198548058")["message"], book["message"]
            )
            self.assertIsNone(crossref_api.fetch_crossref_by_isbn("9780000000000"))
            self.assertEqual(crossref_api.search_crossref("Some text"), [item])
            self.assertEqual(crossref_api.search_crossref("Other text"), [])


class DataCiteTests(SimpleTestCase):
    @SOURCES
    def test_single_batch_and_title_search(self):
        self.assertEqual(datacite_api.fetch_datacite_json(DATACITE_DOI), DATACITE)
        works = datacite_api.fetch_datacite_works([DATACITE_DOI, "10.1000/unknown"])
        self.assertEqual(works, {DATACITE_DOI: DATACITE, "10.1000/unknown": None})
        self.assertEqual(datacite_api.search_datacite_title("Unknown title"), [])

    def test_title_search(self):
        with simulated_sources(datacite_searches={"Some title": [DATACITE]}):
            self.assertEqual(datacite_api.search_datacite_title("Some title?"), [DATACITE])


class OpenAlexTests(SimpleTestCase):
    @SOURCES
    def test_a_work_by_each_of_its_dois(self):
        self.assertEqual(openalex_api.fetch_openalex_work(ARXIV_DOI), OPENALEX)
        works = openalex_api.fetch_openalex_works([ARXIV_DOI, "10.1000/unknown"])
        self.assertEqual(works, {ARXIV_DOI: OPENALEX, "10.1000/unknown": None})
        self.assertEqual(SOURCES.single("openalex"), [ARXIV_DOI])
        self.assertEqual(SOURCES.batches("openalex"), [[ARXIV_DOI, "10.1000/unknown"]])

    def test_citing_works_and_institutions(self):
        institution = OPENALEX["authorships"][0]["institutions"][0]
        citing = [{"id": f"https://openalex.org/W{i}"} for i in range(3)]
        with simulated_sources(openalex_citing={"W1": citing}, institutions=[institution]):
            self.assertEqual(
                openalex_api.fetch_citing_works("W1", "cited_by_count:desc", 2), (3, citing[:2])
            )
            self.assertEqual(
                openalex_api.fetch_citing_works("W2", "cited_by_count:desc", 2), (0, [])
            )
            self.assertEqual(
                openalex_api.fetch_openalex_institutions(["I1291425158", "I1"]),
                {"I1291425158": institution},
            )


class OtherSourcesTests(SimpleTestCase):
    @SOURCES
    def test_doi_org_registers_the_dois_known_to_crossref_and_datacite(self):
        answers = doi_registration.registered_dois([CROSSREF_DOI, DATACITE_DOI, "10.1000/x"])
        self.assertEqual(answers, {CROSSREF_DOI: True, DATACITE_DOI: True, "10.1000/x": None})
        self.assertEqual(SOURCES.batches("doi.org"), [[CROSSREF_DOI, DATACITE_DOI, "10.1000/x"]])

    def test_doi_org_answers_as_told(self):
        with simulated_sources(doi_org={"10.1000/x": False}):
            self.assertEqual(doi_registration.registered_dois(["10.1000/x"]), {"10.1000/x": False})
        with simulated_sources(doi_org=True):
            self.assertEqual(doi_registration.registered_dois(["10.1000/x"]), {"10.1000/x": True})

    def test_orcid(self):
        names = {entry["orcid-id"]: entry for entry in ORCID_ENTRIES}
        orcid = ORCID_ENTRIES[0]["orcid-id"]
        with simulated_sources(orcid_names=names, orcid_records={orcid: {"person": {}}}):
            self.assertEqual(
                orcid_api.fetch_orcid_names([orcid, "0000-0000-0000-0000"]),
                {orcid: names[orcid], "0000-0000-0000-0000": None},
            )
            self.assertEqual(orcid_api.fetch_orcid_record(orcid), {"person": {}})
            self.assertIsNone(orcid_api.fetch_orcid_record("0000-0000-0000-0000"))

    def test_open_library_and_arxiv(self):
        doc = fixture("openlibrary_9780198548058.json")["docs"][0]
        with simulated_sources(
            openlibrary={"9780198548058": doc}, eprints={"1706.03762": b"%PDF-1.5"}
        ):
            self.assertEqual(openlibrary_api.fetch_openlibrary_book("9780198548058"), doc)
            self.assertIsNone(openlibrary_api.fetch_openlibrary_book("9780000000000"))
            self.assertIsNone(arxiv_api.fetch_arxiv_eprint("0000.00000"))
            self.assertEqual(arxiv_api.fetch_arxiv_eprint("1706.03762")["source"], "pdf")


class SimulationTests(SimpleTestCase):
    def test_an_unreachable_source_fails_after_its_retries(self):
        with simulated_sources(crossref=[CROSSREF], unreachable=["crossref"]) as sources:
            self.assertIsNone(crossref_api.fetch_crossref_json(CROSSREF_DOI))
            self.assertEqual(crossref_api.fetch_crossref_works([CROSSREF_DOI]), {})
        self.assertEqual(len(sources.to("crossref")), 4)

    def test_an_unsimulated_request_fails_the_test(self):
        url = "https://example.org/api"
        with self.assertRaisesMessage(UnsimulatedRequest, f"requête non simulée : GET {url}"):
            with simulated_sources():
                get_json(url, service="Example", subject="test")

    def test_an_unsimulated_request_caught_by_the_code_still_fails(self):
        with self.assertRaisesMessage(UnsimulatedRequest, "https://api.crossref.org/members"):
            with simulated_sources():
                try:
                    get_json("https://api.crossref.org/members", service="Crossref", subject="x")
                except UnsimulatedRequest:
                    pass

    def test_answers_added_during_a_test_are_forgotten(self):
        with SOURCES:
            SOURCES.add(crossref={"10.1000/added": {"message": {}}})
            self.assertIsNotNone(crossref_api.fetch_crossref_json("10.1000/added"))
        with SOURCES:
            self.assertIsNone(crossref_api.fetch_crossref_json("10.1000/added"))

    def test_the_requests_are_logged_as_usual(self):
        with SOURCES, self.assertLogs("references.services.sources.http", "INFO") as logs:
            crossref_api.fetch_crossref_json(CROSSREF_DOI)
        self.assertIn("Crossref request for DOI 10.18653/v1/e17-2025", logs.output[0])
