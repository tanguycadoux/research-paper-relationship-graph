from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, Publication
from references.services.corrections import candidates
from references.services.imports.jacow import written_jacow_doi
from references.services.imports.parser import parse_publication
from references.services.imports.written_identifiers import link_written_identifiers
from references.services.sources.external_records import Source, has_record
from references.tests.helpers import with_crossref
from references.tests.sources import active_sources, simulated_sources

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


RNNG_TITLE = "Recurrent neural network grammars"


class SourcesTests(CandidateTestCase):
    def search(self, crossref_found=(RNNG,), datacite_found=(RNNG_ARXIV,), **sources):
        """What the searches of Crossref and DataCite find for the first reference."""
        return self.enterContext(
            simulated_sources(
                crossref_searches={candidates.search_text(self.ref(0)): list(crossref_found)},
                datacite_searches={RNNG_TITLE: list(datacite_found)},
                **sources,
            )
        )

    def test_both_sources_cached(self):
        sources = self.search()
        found, failed = candidates.candidates_for(self.ref(0))
        self.assertFalse(failed)
        self.assertEqual(
            [c.doi for c in found], ["10.18653/v1/n16-1024", "10.48550/arxiv.1602.07776"]
        )
        self.assertEqual(found[1].kind, "Prépublication arXiv")
        self.assertEqual(sources.searches("datacite"), [RNNG_TITLE])
        candidates.candidates_for(self.ref(0))
        self.assertEqual(len(sources.searches("crossref")), 1)

    def test_failed_source_not_cached(self):
        self.search(unreachable=["crossref"])
        found, failed = candidates.candidates_for(self.ref(0))
        self.assertTrue(failed)
        self.assertEqual(len(found), 1)  # DataCite answered
        self.assertIsNone(self.ref(0).candidates)

    def test_forget(self):
        sources = self.search()
        candidates.candidates_for(self.ref(0))
        candidates.forget_candidates(self.ref(0))
        candidates.candidates_for(self.ref(0))
        self.assertEqual(len(sources.searches("crossref")), 2)

    def test_jacow_code_first(self):
        self.search(crossref_found=[], datacite_found=[], datacite=[JACOW_RECORD])
        found, _failed = candidates.candidates_for(self.ref(1))
        self.assertEqual([(c.doi, c.kind) for c in found], [(JACOW_DOI, "Actes JACoW")])

    def test_publication_of_the_base(self):
        self.search(crossref_found=[], datacite_found=[])
        pub = Publication.objects.create(title="Recurrent neural network grammars")
        found, _failed = candidates.candidates_for(self.ref(0))
        self.assertEqual([c.publication for c in found], [pub])


class JacowLinkTests(CandidateTestCase):
    @simulated_sources(datacite=[JACOW_RECORD])
    def test_linked_once_datacite_confirms(self):
        self.assertEqual(link_written_identifiers(self.source).linked, 1)
        target = self.ref(1).target
        self.assertEqual(target.doi, JACOW_DOI)
        self.assertTrue(target.title.startswith("RF Commissioning"))
        self.assertTrue(has_record(target, Source.DATACITE))
        self.assertFalse(self.ref(1).resolved_manually)

    @simulated_sources()
    def test_unknown_doi_creates_nothing(self):
        count = Publication.objects.count()
        self.assertEqual(link_written_identifiers(self.source).linked, 0)
        self.assertEqual(Publication.objects.count(), count)

    @simulated_sources(datacite=[datacite_record(JACOW_DOI, "Another paper", "X", 2019)])
    def test_other_title_creates_nothing(self):
        count = Publication.objects.count()
        self.assertEqual(link_written_identifiers(self.source).linked, 0)
        self.assertEqual(Publication.objects.count(), count)

    def test_publication_of_the_base_linked_without_request(self):
        Publication.objects.create(
            doi=JACOW_DOI, title=JACOW_RECORD["data"]["attributes"]["titles"][0]["title"]
        )
        with simulated_sources() as sources:
            self.assertEqual(link_written_identifiers(self.source).linked, 1)
        self.assertEqual(sources.requests, [])


class CandidateViewTests(CandidateTestCase):
    def url(self, name, position=0):
        return reverse(name, args=[self.source.pk, position])

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        text = candidates.search_text(self.ref(0))
        self.enterContext(simulated_sources(crossref_searches={text: [RNNG]}))

    def test_page_shows_the_candidates(self):
        response = self.client.get(self.url("reference_identify"))
        self.assertContains(response, "Publications candidates")
        self.assertContains(response, "10.18653/v1/n16-1024")
        self.assertContains(response, "Titre identique")

    def test_choose_a_doi(self):
        response = self.client.post(
            self.url("reference_candidate"), {"doi": "10.18653/v1/N16-1024"}
        )
        self.assertRedirects(response, reverse("publication_detail", args=[self.source.pk]))
        ref = self.ref(0)
        self.assertEqual(ref.target.doi, "10.18653/v1/n16-1024")
        self.assertTrue(ref.resolved_manually)

    def test_choose_a_publication_of_the_base(self):
        pub = Publication.objects.create(title="Recurrent neural network grammars")
        self.client.post(self.url("reference_candidate"), {"publication": pub.pk})
        self.assertEqual(self.ref(0).target, pub)

    def test_invalid_candidate(self):
        response = self.client.post(self.url("reference_candidate"), {"doi": "pas un DOI"})
        self.assertRedirects(response, self.url("reference_identify"))
        self.assertIsNone(self.ref(0).target)

    def test_search_again(self):
        self.client.get(self.url("reference_identify"))
        self.client.post(self.url("reference_search_again"))
        self.assertIsNone(self.ref(0).candidates)

    def test_manual_title_prefilled_from_the_text(self):
        response = self.client.get(self.url("reference_identify"))
        self.assertContains(response, 'value="Recurrent neural network grammars"')


ARXIV_DOI = "10.48550/arxiv.1512.03385"
# Its title is abbreviated in the reference: it was not linked at import.
ABBREVIATED = {
    "key": "he",
    "unstructured": "K. He et al. Deep residual learning. CoRR, arXiv:1512.03385, 2015.",
}
# Another title than the one of arXiv: the checks of the candidates would leave it out.
DIFFERENT = {"key": "he2", "unstructured": "He K. Residual nets. CoRR, arXiv:1512.03385, 2015."}
ARXIV_RECORD = datacite_record(
    ARXIV_DOI, "Deep Residual Learning for Image Recognition", "He", 2015
)


@simulated_sources(datacite=[ARXIV_RECORD, JACOW_RECORD])
class WrittenIdentifierCandidateTests(TestCase):
    """The identifier written in a reference is a candidate, whatever its title (#311)."""

    def setUp(self):
        self.source = Publication.objects.create(title="Source")
        with_crossref(
            self.source,
            {"message": {"title": ["Source"], "reference": [ABBREVIATED, JACOW, DIFFERENT]}},
        )
        parse_publication(self.source)

    def ref(self, position):
        return CitedReference.objects.get(source=self.source, position=position)

    def test_an_arxiv_identifier_written(self):
        found, _failed = candidates.candidates_for(self.ref(0))
        self.assertEqual(active_sources().batches("datacite"), [[ARXIV_DOI]])
        self.assertEqual([(c.doi, c.written) for c in found], [(ARXIV_DOI, True)])
        self.assertEqual(found[0].kind, "Prépublication arXiv")

    def test_shown_whatever_its_title(self):
        found, _failed = candidates.candidates_for(self.ref(2))
        self.assertEqual([c.doi for c in found], [ARXIV_DOI])
        self.assertFalse(candidates.is_likely(found[0]))

    def test_a_jacow_code_by_the_same_path(self):
        found, _failed = candidates.candidates_for(self.ref(1))
        self.assertEqual(
            [(c.doi, c.kind, c.written) for c in found], [(JACOW_DOI, "Actes JACoW", True)]
        )

    def test_first_before_the_other_candidates(self):
        item = crossref_item("10.1109/cvpr.2016.90", "Deep residual learning", "He", 2016)
        active_sources().add(crossref_searches={candidates.search_text(self.ref(0)): [item]})
        found, _failed = candidates.candidates_for(self.ref(0))
        self.assertEqual([c.doi for c in found], [ARXIV_DOI, "10.1109/cvpr.2016.90"])

    def test_unknown_to_datacite_it_is_not_proposed(self):
        active_sources().datacite.clear()  # restored when the test ends
        found, _failed = candidates.candidates_for(self.ref(0))
        self.assertEqual(found, [])

    def test_the_page_says_where_it_comes_from(self):
        self.client.force_login(get_user_model().objects.create_user("alice"))
        response = self.client.get(reverse("reference_identify", args=[self.source.pk, 0]))
        self.assertContains(response, "Identifiant écrit dans la référence")
        self.assertContains(response, ARXIV_DOI)
        self.assertFalse(CitedReference.objects.filter(target__isnull=False).exists())
