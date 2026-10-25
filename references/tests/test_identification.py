from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.forms import IdentifyReferenceForm
from references.models import CitedReference, Publication, UserPublication
from references.services import identification
from references.services.parser import parse_publication
from references.tests.helpers import (
    doi_org_answers,
    with_crossref,
    without_candidate_search,
    without_other_sources,
)

BOOK = {"key": "ref1", "unstructured": "Goodfellow I. Deep Learning. MIT Press, 2016."}
NO_KEY = {"unstructured": "Private communication."}
WITH_DOI = {"key": "ref3", "DOI": "10.1000/crossref"}


def source_json(references):
    return {"message": {"title": ["Source"], "reference": references}}


class IdentificationTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        self.source = Publication.objects.create(title="Source")
        self.parse([BOOK, NO_KEY, WITH_DOI])

    def parse(self, references):
        with_crossref(self.source, source_json(references))
        parse_publication(self.source)

    def ref(self, position):
        return CitedReference.objects.get(source=self.source, position=position)


class ManualResolutionSurvivesReimportTests(IdentificationTestCase):
    def test_identification_is_traced(self):
        pub = identification.identify_without_identifier(
            self.ref(0), "Deep Learning", 2016, self.user
        )
        ref = self.ref(0)
        self.assertEqual(ref.target, pub)
        self.assertTrue(ref.resolved_manually)
        self.assertEqual(ref.resolved_by, self.user)
        self.assertIsNotNone(ref.resolved_at)
        self.assertEqual(str(pub.publication_date), "2016-01-01")
        self.assertEqual(pub.formatted_publication_date, "2016")

    def test_kept_by_crossref_key(self):
        pub = identification.identify_without_identifier(
            self.ref(0), "Deep Learning", 2016, self.user
        )
        self.parse([NO_KEY, BOOK, WITH_DOI])  # the book moved to position 1
        self.assertEqual(self.ref(1).target, pub)
        self.assertTrue(self.ref(1).resolved_manually)
        self.assertIsNone(self.ref(0).target)

    def test_kept_by_position_without_key(self):
        pub = identification.identify_without_identifier(self.ref(1), "Lettre", None, self.user)
        self.parse([BOOK, NO_KEY, WITH_DOI])
        self.assertEqual(self.ref(1).target, pub)

    def test_manual_identification_takes_precedence_over_crossref(self):
        other = Publication.objects.create(title="Le bon article")
        identification.resolve(self.ref(2), other, self.user)
        self.parse([BOOK, NO_KEY, WITH_DOI])
        self.assertEqual(self.ref(2).target, other)


@without_other_sources
@patch("references.services.importer.fetch_crossref_json")
class IdentifyByDoiTests(IdentificationTestCase):
    def test_existing_publication_is_reused_without_calling_crossref(self, fetch):
        existing = with_crossref(Publication.objects.create(doi="10.1000/book"), {"message": {}})
        pub, imported = identification.identify_by_doi(self.ref(0), "10.1000/book", self.user)
        self.assertEqual(pub, existing)
        self.assertTrue(imported)
        fetch.assert_not_called()

    def test_new_doi_is_imported(self, fetch):
        fetch.return_value = {"message": {"title": ["Deep Learning"]}}
        pub, imported = identification.identify_by_doi(self.ref(0), "10.1000/book", self.user)
        self.assertTrue(imported)
        self.assertEqual(pub.title, "Deep Learning")
        self.assertEqual(self.ref(0).target, pub)

    def test_unknown_doi_is_linked_anyway(self, fetch):
        fetch.return_value = None
        pub, imported = identification.identify_by_doi(self.ref(0), "10.1000/ghost", self.user)
        self.assertFalse(imported)
        self.assertEqual(self.ref(0).target, pub)


class IdentifyReferenceFormTests(TestCase):
    def test_doi_is_normalized(self):
        form = IdentifyReferenceForm({"method": "doi", "doi": "https://doi.org/10.1000/ABC"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["doi"], "10.1000/abc")

    def test_invalid_doi(self):
        form = IdentifyReferenceForm({"method": "doi", "doi": "pas un DOI"})
        self.assertIn("doi", form.errors)

    def test_title_required_without_identifier(self):
        form = IdentifyReferenceForm({"method": "none", "title": ""})
        self.assertIn("title", form.errors)


@without_candidate_search
@without_other_sources
@patch("references.services.importer.fetch_crossref_json", return_value=None)
class IdentifyReferenceViewTests(IdentificationTestCase):
    def url(self, position):
        return reverse("reference_identify", args=[self.source.pk, position])

    def test_login_required(self, _fetch):
        response = self.client.get(self.url(0))
        self.assertEqual(response.status_code, 302)

    def test_form_shows_the_reference_text(self, _fetch):
        self.client.force_login(self.user)
        response = self.client.get(self.url(0))
        self.assertContains(response, "Goodfellow I. Deep Learning")
        self.assertContains(response, "Telle que donnée par Crossref")

    def test_identify_without_identifier(self, _fetch):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url(0), {"method": "none", "title": "Deep Learning", "year": "2016"}
        )
        self.assertRedirects(response, reverse("publication_detail", args=[self.source.pk]))
        self.assertEqual(self.ref(0).target.title, "Deep Learning")

    def test_detail_page_links_to_identification(self, _fetch):
        self.client.force_login(self.user)
        response = self.client.get(reverse("publication_detail", args=[self.source.pk]))
        self.assertContains(response, self.url(0))


@without_candidate_search
@without_other_sources
@patch("references.services.importer.fetch_crossref_json", return_value=None)
class UnregisteredDoiTests(IdentificationTestCase):
    """A DOI that doi.org does not know is refused, not linked to an empty publication (#240)."""

    ACM_DOI = "10.5555/2627435.2670313"

    def post_doi(self, doi, registered):
        self.client.force_login(self.user)
        with doi_org_answers(registered):
            return self.client.post(
                reverse("reference_identify", args=[self.source.pk, 0]),
                {"method": "doi", "doi": doi},
            )

    def test_unregistered_doi_is_refused(self, _fetch):
        response = self.post_doi(self.ACM_DOI, registered=False)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "n&#x27;est enregistré nulle part")
        self.assertContains(response, "ACM Digital Library")
        self.assertIsNone(self.ref(0).target)
        self.assertFalse(Publication.objects.filter(doi=self.ACM_DOI).exists())

    def test_doi_linked_when_doi_org_cannot_answer(self, _fetch):
        response = self.post_doi("10.1000/ghost", registered=None)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.ref(0).target.doi, "10.1000/ghost")


class OrphanTargetTests(IdentificationTestCase):
    def reidentify(self, first_target):
        identification.resolve(self.ref(0), first_target, self.user)
        identification.resolve(self.ref(0), Publication.objects.create(title="La bonne"), self.user)
        return Publication.objects.filter(pk=first_target.pk).exists()

    def test_empty_unused_previous_target_is_deleted(self):
        self.assertFalse(self.reidentify(Publication.objects.create(isbn="9783954501861")))

    def test_previous_target_with_metadata_is_kept(self):
        kept = with_crossref(Publication.objects.create(doi="10.1000/kept"), {"message": {}})
        self.assertTrue(self.reidentify(kept))

    def test_previous_target_still_cited_is_kept(self):
        cited = Publication.objects.create(title="Citée ailleurs")
        CitedReference.objects.create(source=self.source, target=cited, position=99)
        self.assertTrue(self.reidentify(cited))

    def test_previous_target_in_a_corpus_is_kept(self):
        in_corpus = Publication.objects.create(title="Dans un corpus")
        UserPublication.objects.create(user=self.user, publication=in_corpus)
        self.assertTrue(self.reidentify(in_corpus))
