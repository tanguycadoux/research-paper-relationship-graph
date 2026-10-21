from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import Publication, UserPublication
from references.services.doi import is_valid_doi, normalize_doi


class NormalizeDoiTests(SimpleTestCase):
    def test_strips_resolver_prefixes(self):
        for raw in (
            "https://doi.org/10.1000/ABC",
            "http://doi.org/10.1000/ABC",
            "https://dx.doi.org/10.1000/ABC",
            "doi:10.1000/ABC",
            "DOI: 10.1000/ABC",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_doi(raw), "10.1000/abc")

    def test_strips_spaces_and_lowercases(self):
        self.assertEqual(normalize_doi("  10.1000/AbC.D  "), "10.1000/abc.d")

    def test_empty_values(self):
        self.assertEqual(normalize_doi(""), "")
        self.assertEqual(normalize_doi(None), "")


class IsValidDoiTests(SimpleTestCase):
    def test_valid(self):
        self.assertTrue(is_valid_doi("10.1000/abc"))
        self.assertTrue(is_valid_doi("10.1103/physrevlett.116.061102"))

    def test_invalid(self):
        for doi in ("", "abc", "10.10/abc", "10.1000/", "10.1000/a b", "isbn:123"):
            with self.subTest(doi=doi):
                self.assertFalse(is_valid_doi(doi))


@patch("references.services.importer.fetch_crossref_json", return_value=None)
class DoiPersistenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="secret")
        self.client.force_login(self.user)

    def test_model_saves_normalized_doi(self, _fetch):
        pub = Publication.objects.create(doi="https://doi.org/10.1000/ABC")
        self.assertEqual(pub.doi, "10.1000/abc")

    def test_add_by_doi_reuses_existing_publication(self, _fetch):
        existing = Publication.objects.create(doi="10.1000/abc")
        url = reverse("add_publication_to_user_refs_by_doi")
        self.client.post(url, {"doi": "https://doi.org/10.1000/ABC"})
        self.assertEqual(Publication.objects.count(), 1)
        self.assertTrue(UserPublication.objects.filter(publication=existing).exists())

    def test_add_by_doi_rejects_invalid_doi(self, _fetch):
        url = reverse("add_publication_to_user_refs_by_doi")
        self.client.post(url, {"doi": "not a doi"})
        self.assertFalse(Publication.objects.exists())
