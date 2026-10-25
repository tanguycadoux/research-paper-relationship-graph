from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, Publication
from references.services import candidates
from references.services.external_records import Source, has_record
from references.services.jacow import link_jacow_references, written_jacow_doi
from references.services.parser import parse_publication
from references.tests.helpers import with_crossref, without_other_sources

DYER = {
    "key": "dyer",
    "unstructured": "Chris Dyer, Adhiguna Kuncoro, Miguel Ballesteros, and Noah A. Smith. "
    "Recurrent neural network grammars. In Proc. of NAACL, 2016.",
}
JACOW = {
    "key": "ref2",
    "author": "Di Giacomo",
    "year": "2019",
    "volume-title": "RF Commissioning of the SPIRAL2 RFQ in CW Mode and Beyond Nominal Field. "
    "JACoW-IPAC2019-WEPRB007",
}
WILSON = {
    "key": "ref11",
    "author": "Wilson",
    "year": "1983",
    "volume-title": "Superconducting Magnets",
}


def crossref_item(doi, title, family, year, kind="proceedings-article"):
    return {
        "DOI": doi,
        "title": [title],
        "author": [{"family": family}],
        "issued": {"date-parts": [[year]]},
        "type": kind,
    }


def datacite_record(doi, title, family, year):
    return {
        "data": {
            "id": doi,
            "attributes": {
                "doi": doi,
                "titles": [{"title": title}],
                "creators": [{"familyName": family, "givenName": "A."}],
                "publicationYear": year,
            },
        }
    }


RNNG = crossref_item("10.18653/v1/N16-1024", "Recurrent Neural Network Grammars", "Dyer", 2016)
RNNG_ARXIV = datacite_record(
    "10.48550/arxiv.1602.07776", "Recurrent Neural Network Grammars", "Dyer", 2016
)
JACOW_DOI = "10.18429/jacow-ipac2019-weprb007"
JACOW_RECORD = datacite_record(
    JACOW_DOI,
    "RF Commissioning of the SPIRAL2 RFQ in CW Mode and Beyond Nominal Field",
    "Di Giacomo",
    2019,
)


class CandidateTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        self.source = Publication.objects.create(title="Source")
        with_crossref(
            self.source, {"message": {"title": ["Source"], "reference": [DYER, JACOW, WILSON]}}
        )
        parse_publication(self.source)

    def ref(self, position):
        return CitedReference.objects.get(source=self.source, position=position)


class CitedReferenceReadingTests(CandidateTestCase):
    def test_title_after_the_authors_despite_initials(self):
        self.assertEqual(candidates.cited_title(self.ref(0)), "Recurrent neural network grammars")

    def test_title_of_a_structured_reference_without_its_jacow_code(self):
        self.assertEqual(
            candidates.cited_title(self.ref(1)),
            "RF Commissioning of the SPIRAL2 RFQ in CW Mode and Beyond Nominal Field",
        )

    def test_year_from_the_text(self):
        self.assertEqual(candidates.cited_year(self.ref(0)), 2016)

    def test_jacow_doi(self):
        self.assertEqual(written_jacow_doi("p. 2804, JACoW-IPAC2019-WEPRB007."), JACOW_DOI)
        self.assertEqual(written_jacow_doi("JACoW-IPAC2019"), "")  # a whole volume
        self.assertEqual(written_jacow_doi("IPAC2019, WEPRB007"), "")


class SelectionTests(CandidateTestCase):
    def select(self, position, *candidate_list):
        return candidates.select(self.ref(position), list(candidate_list))

    def test_same_title_and_subtitle_accepted_closest_first(self):
        subtitle = candidates.Candidate(
            title="Recurrent Neural Network Grammars for parsing", doi="10.1/b", authors=("Dyer",)
        )
        same = candidates.Candidate(title="Recurrent Neural Network Grammars", doi="10.1/a")
        self.assertEqual([c.doi for c in self.select(0, subtitle, same)], ["10.1/a", "10.1/b"])

    def test_longer_title_on_the_same_topic_rejected(self):
        other = candidates.Candidate(
            title="End fields of CBA superconducting magnets", doi="10.2172/6306309", year=1983
        )
        self.assertEqual(self.select(2, other), [])

    def test_contradicting_year_rejected(self):
        later = candidates.Candidate(
            title="Recurrent Neural Network Grammars", doi="10.1/a", year=2020
        )
        self.assertEqual(self.select(0, later), [])

    def test_close_title_needs_its_first_author(self):
        close = candidates.Candidate(
            title="Recurrent Neural Network Grammars Learn Syntax",
            doi="10.1/c",
            authors=("Nobody",),
        )
        self.assertEqual(self.select(0, close), [])

    def test_researchgate_copies_ignored(self):
        copy = candidates.Candidate(title="Recurrent Neural Network Grammars", doi="10.13140/rg.2")
        self.assertEqual(self.select(0, copy), [])

    def test_doi_in_the_base_and_linked_publication(self):
        pub = Publication.objects.create(doi="10.1/a", title="Recurrent Neural Network Grammars")
        found = self.select(0, candidates.Candidate(title=pub.title, doi="10.1/a"))
        self.assertEqual(found[0].publication, pub)
        CitedReference.objects.filter(pk=self.ref(0).pk).update(target=pub)
        self.assertEqual(self.select(0, candidates.Candidate(title=pub.title, doi="10.1/a")), [])


@patch("references.services.candidates.fetch_datacite_works", return_value={})
@patch("references.services.candidates.search_datacite_title", return_value=[RNNG_ARXIV])
@patch("references.services.candidates.search_crossref", return_value=[RNNG])
class SourcesTests(CandidateTestCase):
    def test_both_sources_cached(self, crossref, datacite, _works):
        found, failed = candidates.candidates_for(self.ref(0))
        self.assertFalse(failed)
        self.assertEqual(
            [c.doi for c in found], ["10.18653/v1/n16-1024", "10.48550/arxiv.1602.07776"]
        )
        self.assertEqual(found[1].kind, "Prépublication arXiv")
        datacite.assert_called_once_with("Recurrent neural network grammars")
        candidates.candidates_for(self.ref(0))
        crossref.assert_called_once()

    def test_failed_source_not_cached(self, crossref, _datacite, _works):
        crossref.return_value = None
        found, failed = candidates.candidates_for(self.ref(0))
        self.assertTrue(failed)
        self.assertEqual(len(found), 1)  # DataCite answered
        self.assertIsNone(self.ref(0).candidates)

    def test_forget(self, crossref, _datacite, _works):
        candidates.candidates_for(self.ref(0))
        candidates.forget_candidates(self.ref(0))
        candidates.candidates_for(self.ref(0))
        self.assertEqual(crossref.call_count, 2)

    def test_jacow_code_first(self, crossref, datacite, works):
        works.return_value = {JACOW_DOI: JACOW_RECORD}
        crossref.return_value, datacite.return_value = [], []
        found, _failed = candidates.candidates_for(self.ref(1))
        self.assertEqual([(c.doi, c.kind) for c in found], [(JACOW_DOI, "Actes JACoW")])

    def test_publication_of_the_base(self, crossref, datacite, _works):
        crossref.return_value, datacite.return_value = [], []
        pub = Publication.objects.create(title="Recurrent neural network grammars")
        found, _failed = candidates.candidates_for(self.ref(0))
        self.assertEqual([c.publication for c in found], [pub])


@patch("references.services.jacow.fetch_datacite_works")
class JacowLinkTests(CandidateTestCase):
    def test_linked_once_datacite_confirms(self, works):
        works.return_value = {JACOW_DOI: JACOW_RECORD}
        self.assertEqual(link_jacow_references(self.source), 1)
        target = self.ref(1).target
        self.assertEqual(target.doi, JACOW_DOI)
        self.assertTrue(target.title.startswith("RF Commissioning"))
        self.assertTrue(has_record(target, Source.DATACITE))
        self.assertFalse(self.ref(1).resolved_manually)

    def test_unknown_doi_creates_nothing(self, works):
        works.return_value = {JACOW_DOI: None}
        count = Publication.objects.count()
        self.assertEqual(link_jacow_references(self.source), 0)
        self.assertEqual(Publication.objects.count(), count)

    def test_other_title_creates_nothing(self, works):
        works.return_value = {JACOW_DOI: datacite_record(JACOW_DOI, "Another paper", "X", 2019)}
        count = Publication.objects.count()
        self.assertEqual(link_jacow_references(self.source), 0)
        self.assertEqual(Publication.objects.count(), count)

    def test_publication_of_the_base_linked_without_request(self, works):
        Publication.objects.create(
            doi=JACOW_DOI, title=JACOW_RECORD["data"]["attributes"]["titles"][0]["title"]
        )
        self.assertEqual(link_jacow_references(self.source), 1)
        works.assert_not_called()


@without_other_sources
@patch("references.services.importer.fetch_crossref_json", return_value=None)
@patch("references.services.candidates.fetch_datacite_works", return_value={})
@patch("references.services.candidates.search_datacite_title", return_value=[])
@patch("references.services.candidates.search_crossref", return_value=[RNNG])
class CandidateViewTests(CandidateTestCase):
    def url(self, name, position=0):
        return reverse(name, args=[self.source.pk, position])

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_page_shows_the_candidates(self, *_mocks):
        response = self.client.get(self.url("reference_identify"))
        self.assertContains(response, "Publications candidates")
        self.assertContains(response, "10.18653/v1/n16-1024")
        self.assertContains(response, "Titre identique")

    def test_choose_a_doi(self, *_mocks):
        response = self.client.post(
            self.url("reference_candidate"), {"doi": "10.18653/v1/N16-1024"}
        )
        self.assertRedirects(response, reverse("publication_detail", args=[self.source.pk]))
        ref = self.ref(0)
        self.assertEqual(ref.target.doi, "10.18653/v1/n16-1024")
        self.assertTrue(ref.resolved_manually)

    def test_choose_a_publication_of_the_base(self, *_mocks):
        pub = Publication.objects.create(title="Recurrent neural network grammars")
        self.client.post(self.url("reference_candidate"), {"publication": pub.pk})
        self.assertEqual(self.ref(0).target, pub)

    def test_invalid_candidate(self, *_mocks):
        response = self.client.post(self.url("reference_candidate"), {"doi": "pas un DOI"})
        self.assertRedirects(response, self.url("reference_identify"))
        self.assertIsNone(self.ref(0).target)

    def test_search_again(self, crossref, *_mocks):
        self.client.get(self.url("reference_identify"))
        self.client.post(self.url("reference_search_again"))
        self.assertIsNone(self.ref(0).candidates)

    def test_manual_title_prefilled_from_the_text(self, *_mocks):
        response = self.client.get(self.url("reference_identify"))
        self.assertContains(response, 'value="Recurrent neural network grammars"')
