from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Publication, UserPublication
from references.services.corpus.corpus_transfer import import_corpus
from references.services.sources.doi_registration import (
    BATCH_SIZE,
    registered_dois,
    unregistered_dois,
)
from references.tests.helpers import with_crossref
from references.tests.sources import simulated_sources
from references.tests.test_corpus_transfer import export_of
from references.tests.test_importer import CROSSREF_SOURCES

ACM_DOI = "10.5555/2627435.2670313"


class RegisteredDoisTests(TestCase):
    def test_answers_of_doi_org(self):
        # doi.org writes the DOI as it was registered, in capitals here.
        answers = {"10.1038/NATURE14539": True, ACM_DOI: False}
        with simulated_sources(doi_org=answers) as sources:
            self.assertEqual(
                registered_dois(["10.1038/nature14539", ACM_DOI]),
                {"10.1038/nature14539": True, ACM_DOI: False},
            )
        self.assertIn("/ra/10.1038/nature14539,10.5555/", sources.to("doi.org")[0].url)

    def test_unanswered(self):
        with simulated_sources(unreachable=["doi.org"]):
            self.assertEqual(registered_dois([ACM_DOI]), {ACM_DOI: None})

    def test_by_batches(self):
        with simulated_sources() as sources:
            registered_dois([f"10.1000/{n}" for n in range(BATCH_SIZE + 1)])
        self.assertEqual([len(batch) for batch in sources.batches("doi.org")], [BATCH_SIZE, 1])


class UnregisteredDoisTests(TestCase):
    def test_doi_of_a_publication_with_metadata_is_not_asked(self):
        with_crossref(Publication.objects.create(doi="10.1000/known"), {"message": {}})
        with simulated_sources(doi_org={ACM_DOI: False}) as sources:
            self.assertEqual(unregistered_dois(["10.1000/known", ACM_DOI]), {ACM_DOI})
        self.assertEqual(sources.batches("doi.org"), [[ACM_DOI]])

    def test_empty_publication_does_not_vouch_for_its_doi(self):
        Publication.objects.create(doi=ACM_DOI)  # left by a former identification
        with simulated_sources(doi_org=False):
            self.assertEqual(unregistered_dois([ACM_DOI]), {ACM_DOI})

    def test_unanswered_doi_is_accepted(self):
        with simulated_sources(unreachable=["doi.org"]):
            self.assertEqual(unregistered_dois([ACM_DOI]), set())


@CROSSREF_SOURCES
class CorpusRefusesUnregisteredDoiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")

    def test_add_by_identifier(self):
        self.client.force_login(self.user)
        CROSSREF_SOURCES.add(doi_org=False)
        response = self.client.post(
            reverse("corpus_add_by_identifier"),
            {"identifier": f"https://doi.org/{ACM_DOI}"},
            follow=True,
        )
        self.assertContains(response, "n&#x27;est enregistré nulle part")
        self.assertContains(response, "Rien n&#x27;a été ajouté")
        self.assertFalse(Publication.objects.exists())

    def test_import_drops_the_entry(self):
        CROSSREF_SOURCES.add(doi_org=False)
        report = import_corpus(self.user, export_of({"doi": ACM_DOI, "title": "Dropout"}))
        self.assertEqual(report.unregistered, ["Dropout"])
        self.assertFalse(Publication.objects.exists())
        self.assertEqual(CROSSREF_SOURCES.single("crossref"), [])

    def test_import_falls_back_on_the_isbn(self):
        book = Publication.objects.create(isbn="9780262035613")
        CROSSREF_SOURCES.add(doi_org=False)
        with patch(
            "references.services.corpus.entries.find_or_import_book", return_value=(book, False)
        ):
            report = import_corpus(self.user, export_of({"doi": ACM_DOI, "isbn": "9780262035613"}))
        self.assertEqual(report.unregistered, [])
        self.assertTrue(UserPublication.objects.filter(user=self.user, publication=book).exists())
