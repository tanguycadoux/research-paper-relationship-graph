from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.forms import PublicationForm
from references.models import CitedReference, Publication, UserPublication
from references.services.corpus import add_to_corpus
from references.services.external_records import Source, store_record
from references.services.importer import import_publication
from references.services.preprints import (
    declared_version,
    is_published_version,
    similar_titles,
)
from references.tests.helpers import with_crossref, without_doi_org, without_openalex, without_orcid

ARXIV = "10.48550/arxiv.2403.00171"
JOURNAL = "10.1109/tasc.2024.3358777"
TITLE = "Quench Performance of the First Pre-series AUP Cryo-assembly"
CITING = "10.1000/citing"


def datacite(title=TITLE, related=JOURNAL, relation="IsVersionOf"):
    """An arXiv record at DataCite, declaring its published version."""
    related_identifiers = (
        [{"relationType": relation, "relatedIdentifier": related, "relatedIdentifierType": "DOI"}]
        if related
        else []
    )
    return {
        "data": {
            "attributes": {
                "titles": [{"title": title}],
                "publicationYear": 2024,
                "creators": [{"givenName": "Ada", "familyName": "Lovelace"}],
                "relatedIdentifiers": related_identifiers,
            }
        }
    }


def crossref(doi=JOURNAL, title=TITLE, kind="journal-article", references=()):
    return {
        "message": {
            "DOI": doi,
            "type": kind,
            "title": [title],
            "issued": {"date-parts": [[2024, 2]]},
            "author": [{"given": "Ada", "family": "Lovelace"}],
            "reference": list(references),
        }
    }


class DeclarationTests(SimpleTestCase):
    def test_declared_version(self):
        self.assertEqual(declared_version(datacite()), JOURNAL)
        self.assertEqual(declared_version(datacite(relation="IsPreprintOf")), JOURNAL)

    def test_other_relations_declare_nothing(self):
        self.assertIsNone(declared_version(datacite(relation="References")))
        self.assertIsNone(declared_version(datacite(related=None)))
        # Another arXiv DOI is not a published version.
        self.assertIsNone(declared_version(datacite(related="10.48550/arXiv.2401.00001")))
        self.assertIsNone(declared_version(None))

    def test_titles(self):
        self.assertTrue(similar_titles(TITLE, TITLE.upper() + ": first results"))
        self.assertTrue(similar_titles("Quench performance of AUP cryo-assemblies", TITLE))
        self.assertFalse(similar_titles(TITLE, "Deep residual learning for image recognition"))
        self.assertFalse(similar_titles(TITLE, ""))

    def test_published_types_only(self):
        self.assertTrue(is_published_version(TITLE, crossref()))
        self.assertTrue(is_published_version(TITLE, crossref(kind="proceedings-article")))
        # Copies of arXiv preprints registered elsewhere (10.65215…).
        self.assertFalse(is_published_version(TITLE, crossref(kind="posted-content")))
        self.assertFalse(is_published_version(TITLE, None))


@without_doi_org
@without_orcid
@without_openalex
class ReplacementTests(TestCase):
    """An arXiv preprint is replaced by the published version its authors declare (#227)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")

    def sources(self, datacite_record=None, journal=None):
        """Crossref knows the journal version only; DataCite knows the preprint."""
        datacite_record = datacite_record or datacite()
        journal = journal if journal is not None else crossref()
        patches = [
            patch("references.services.importer.fetch_crossref_json", new=lambda doi: None),
            patch(
                "references.services.importer.fetch_datacite_json",
                new=lambda doi: datacite_record if doi == ARXIV else None,
            ),
            patch(
                "references.services.preprints.fetch_crossref_json",
                new=lambda doi: journal if doi == JOURNAL else None,
            ),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_preprint_becomes_its_published_version(self):
        self.sources()
        pub = Publication.objects.create(doi=ARXIV)
        UserPublication.objects.create(user=self.user, publication=pub)
        self.assertEqual(import_publication(pub), pub)
        pub.refresh_from_db()
        self.assertEqual((pub.doi, pub.preprint_doi), (JOURNAL, ARXIV))
        self.assertEqual(pub.title, TITLE)
        sources = set(pub.external_records.values_list("source", flat=True))
        self.assertIn(Source.CROSSREF, sources)
        self.assertNotIn(Source.DATACITE, sources)
        self.assertTrue(UserPublication.objects.filter(publication=pub).exists())

    def test_the_preprint_doi_finds_the_publication_again(self):
        self.sources()
        pub = Publication.objects.create(doi=ARXIV)
        import_publication(pub)
        self.assertEqual(Publication.objects.get_or_create_doi(ARXIV), pub)
        self.assertEqual(Publication.objects.count(), 1)

    def test_no_published_type_no_replacement(self):
        self.sources(journal=crossref(kind="posted-content"))
        pub = Publication.objects.create(doi=ARXIV)
        import_publication(pub)
        pub.refresh_from_db()
        self.assertEqual((pub.doi, pub.preprint_doi), (ARXIV, ""))

    def test_another_title_no_replacement(self):
        self.sources(journal=crossref(title="Deep residual learning for image recognition"))
        pub = Publication.objects.create(doi=ARXIV)
        import_publication(pub)
        pub.refresh_from_db()
        self.assertEqual(pub.doi, ARXIV)

    def test_published_version_already_in_the_base(self):
        self.sources()
        published = with_crossref(Publication.objects.create(doi=JOURNAL, title=TITLE), crossref())
        preprint = Publication.objects.create(doi=ARXIV)
        citing = Publication.objects.create(doi=CITING)
        CitedReference.objects.create(source=citing, position=0, doi=ARXIV, target=preprint)
        UserPublication.objects.create(user=self.user, publication=preprint)
        self.assertEqual(add_to_corpus(self.user, preprint), published)
        self.assertFalse(Publication.objects.filter(doi=ARXIV).exists())
        published.refresh_from_db()
        self.assertEqual(published.preprint_doi, ARXIV)
        self.assertEqual(CitedReference.objects.get(source=citing).target, published)
        self.assertTrue(UserPublication.objects.filter(publication=published).exists())

    def test_adding_by_doi_says_so(self):
        self.sources()
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("corpus_add_by_identifier"), {"identifier": ARXIV}, follow=True
        )
        self.assertContains(response, f"La prépublication arXiv {ARXIV} a été remplacée")
        self.assertEqual(Publication.objects.get().doi, JOURNAL)

    def test_form_refuses_the_doi_of_a_replaced_preprint(self):
        Publication.objects.create(doi=JOURNAL, preprint_doi=ARXIV, title=TITLE)
        form = PublicationForm(data={"doi": ARXIV, "isbn": "", "title": "", "publication_date": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("doi", form.errors)


@without_orcid
@without_openalex
class CitedPreprintTests(TestCase):
    """Cited preprints, imported in batch, are replaced too."""

    def setUp(self):
        reference = {"key": "ref1", "DOI": ARXIV, "unstructured": "Lovelace, arXiv 2024"}
        self.citing = with_crossref(
            Publication.objects.create(doi=CITING),
            crossref(CITING, "Citing", references=[reference]),
        )
        patches = [
            patch(
                "references.services.importer.fetch_crossref_works",
                new=lambda dois: dict.fromkeys(dois),
            ),
            patch(
                "references.services.importer.fetch_datacite_works",
                new=lambda dois: {doi: datacite() if doi == ARXIV else None for doi in dois},
            ),
            patch(
                "references.services.preprints.fetch_crossref_works",
                new=lambda dois: {doi: crossref() if doi == JOURNAL else None for doi in dois},
            ),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_cited_preprint_is_replaced(self):
        import_publication(self.citing, with_references=True)
        ref = CitedReference.objects.get(source=self.citing)
        self.assertEqual((ref.target.doi, ref.target.preprint_doi), (JOURNAL, ARXIV))
        self.assertEqual(ref.target.title, TITLE)
        # Parsed again, the reference still leads to the published version.
        import_publication(self.citing, with_references=True)
        self.assertEqual(CitedReference.objects.get(source=self.citing).target.doi, JOURNAL)
        self.assertEqual(Publication.objects.count(), 2)


@without_orcid
@without_openalex
class StoredPreprintTests(TestCase):
    def test_command_replaces_the_preprints_in_the_base(self):
        pub = Publication.objects.create(doi=ARXIV)
        store_record(pub, Source.DATACITE, datacite())
        other = Publication.objects.create(doi="10.48550/arxiv.1706.03762")
        store_record(other, Source.DATACITE, datacite(related=None))
        out = StringIO()
        with patch("references.services.preprints.fetch_crossref_json", return_value=crossref()):
            call_command("replace_preprints", stdout=out)
        pub.refresh_from_db()
        self.assertEqual((pub.doi, pub.preprint_doi), (JOURNAL, ARXIV))
        self.assertIn("Prépublications remplacées : 1", out.getvalue())

    def test_detail_shows_the_preprint(self):
        pub = Publication.objects.create(doi=JOURNAL, preprint_doi=ARXIV, title=TITLE)
        response = self.client.get(reverse("publication_detail", args=[pub.pk]))
        self.assertContains(response, "Prépublication")
        self.assertContains(response, f'href="https://doi.org/{ARXIV}"')
