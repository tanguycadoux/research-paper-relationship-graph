from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Publication, UserPublication
from references.services.corpus_transfer import import_corpus
from references.services.doi_registration import (
    BATCH_SIZE,
    registered_dois,
    unregistered_dois,
)
from references.tests.helpers import doi_org_answers, with_crossref, without_other_sources
from references.tests.test_corpus_transfer import export_of
from references.tests.test_importer import with_mocked_crossref

ACM_DOI = "10.5555/2627435.2670313"


@patch("references.services.doi_registration.get_json")
class RegisteredDoisTests(TestCase):
    def test_answers_of_doi_org(self, get_json):
        get_json.return_value = [
            {"DOI": "10.1038/NATURE14539", "RA": "Crossref"},
            {"DOI": ACM_DOI, "status": "DOI does not exist"},
        ]
        self.assertEqual(
            registered_dois(["10.1038/nature14539", ACM_DOI]),
            {"10.1038/nature14539": True, ACM_DOI: False},
        )
        self.assertIn("10.1038/nature14539,10.5555/", get_json.call_args.args[0])

    def test_unanswered(self, get_json):
        get_json.return_value = None
        self.assertEqual(registered_dois([ACM_DOI]), {ACM_DOI: None})

    def test_by_batches(self, get_json):
        get_json.return_value = []
        registered_dois([f"10.1000/{n}" for n in range(BATCH_SIZE + 1)])
        self.assertEqual(get_json.call_count, 2)


class UnregisteredDoisTests(TestCase):
    def test_doi_of_a_publication_with_metadata_is_not_asked(self):
        with_crossref(Publication.objects.create(doi="10.1000/known"), {"message": {}})
        with patch("references.services.doi_registration.registered_dois") as registered:
            registered.return_value = {ACM_DOI: False}
            self.assertEqual(unregistered_dois(["10.1000/known", ACM_DOI]), {ACM_DOI})
        registered.assert_called_once_with([ACM_DOI])

    def test_empty_publication_does_not_vouch_for_its_doi(self):
        Publication.objects.create(doi=ACM_DOI)  # left by a former identification
        with doi_org_answers(False):
            self.assertEqual(unregistered_dois([ACM_DOI]), {ACM_DOI})

    def test_unanswered_doi_is_accepted(self):
        with doi_org_answers(None):
            self.assertEqual(unregistered_dois([ACM_DOI]), set())


@without_other_sources
@with_mocked_crossref
class CorpusRefusesUnregisteredDoiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")

    def test_add_by_identifier(self, fetch, fetch_works):
        self.client.force_login(self.user)
        with doi_org_answers(False):
            response = self.client.post(
                reverse("corpus_add_by_identifier"),
                {"identifier": f"https://doi.org/{ACM_DOI}"},
                follow=True,
            )
        self.assertContains(response, "n&#x27;est enregistré nulle part")
        self.assertContains(response, "Rien n&#x27;a été ajouté")
        self.assertFalse(Publication.objects.exists())

    def test_import_drops_the_entry(self, fetch, fetch_works):
        with doi_org_answers(False):
            report = import_corpus(self.user, export_of({"doi": ACM_DOI, "title": "Dropout"}))
        self.assertEqual(report.unregistered, ["Dropout"])
        self.assertFalse(Publication.objects.exists())
        fetch.assert_not_called()

    def test_import_falls_back_on_the_isbn(self, fetch, fetch_works):
        book = Publication.objects.create(isbn="9780262035613")
        with (
            doi_org_answers(False),
            patch("references.services.corpus.find_or_import_book", return_value=(book, False)),
        ):
            report = import_corpus(self.user, export_of({"doi": ACM_DOI, "isbn": "9780262035613"}))
        self.assertEqual(report.unregistered, [])
        self.assertTrue(UserPublication.objects.filter(user=self.user, publication=book).exists())
