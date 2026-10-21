from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, Publication, UserPublication
from references.services import identification
from references.services.parser import parse_publication
from references.services.publication_merge import (
    find_merge_target,
    merge_publication,
    merge_summary,
)

BOOK_REF = {"key": "ref1", "unstructured": "Goodfellow et al. Deep Learning. 2016."}


class MergeTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        self.other_user = get_user_model().objects.create_user("bob")
        self.source = Publication.objects.create(title="Source")
        self.source.crossref_json = {"message": {"title": ["Source"], "reference": [BOOK_REF]}}
        parse_publication(self.source)
        self.ref = CitedReference.objects.get(source=self.source)
        self.duplicate = identification.identify_without_identifier(
            self.ref, "Deep learning (sans identifiant)", 2016, self.user
        )
        self.book = Publication.objects.create(isbn="9780262035613", title="Deep Learning")


class MergeServiceTests(MergeTestCase):
    def test_citations_point_to_the_target_and_are_kept_on_reimport(self):
        merge_publication(self.duplicate, self.book, self.user)
        self.ref.refresh_from_db()
        self.assertEqual(self.ref.target, self.book)
        self.assertTrue(self.ref.resolved_manually)

        parse_publication(self.source)
        self.assertEqual(CitedReference.objects.get(source=self.source).target, self.book)

    def test_duplicate_is_deleted(self):
        merge_publication(self.duplicate, self.book, self.user)
        self.assertFalse(Publication.objects.filter(pk=self.duplicate.pk).exists())

    def test_corpus_entries_are_moved_without_duplicates(self):
        UserPublication.objects.create(user=self.user, publication=self.duplicate)
        UserPublication.objects.create(user=self.other_user, publication=self.duplicate)
        UserPublication.objects.create(user=self.other_user, publication=self.book)
        merge_publication(self.duplicate, self.book, self.user)
        owners = UserPublication.objects.filter(publication=self.book).values_list(
            "user__username", flat=True
        )
        self.assertEqual(sorted(owners), ["alice", "bob"])

    def test_summary(self):
        UserPublication.objects.create(user=self.user, publication=self.duplicate)
        summary = merge_summary(self.duplicate)
        self.assertEqual((summary["citations"], summary["corpus_entries"]), (1, 1))

    def test_identified_publication_cannot_be_merged(self):
        with self.assertRaises(ValueError):
            merge_publication(self.book, self.duplicate, self.user)

    def test_publication_cannot_be_merged_into_itself(self):
        with self.assertRaises(ValueError):
            merge_publication(self.duplicate, self.duplicate, self.user)


@patch("references.services.importer.fetch_crossref_json", return_value=None)
class FindMergeTargetTests(MergeTestCase):
    def test_by_existing_doi_without_calling_crossref(self, fetch):
        article = Publication.objects.create(doi="10.1000/x", crossref_json={"message": {}})
        self.assertEqual(find_merge_target("https://doi.org/10.1000/X"), article)
        fetch.assert_not_called()

    def test_by_isbn(self, _fetch):
        self.assertEqual(find_merge_target("978-0-262-03561-3"), self.book)

    def test_by_publication_url(self, _fetch):
        url = f"http://127.0.0.1:8000/publications/{self.book.pk}/"
        self.assertEqual(find_merge_target(url), self.book)

    def test_nothing_found(self, _fetch):
        self.assertIsNone(find_merge_target("n'importe quoi"))


class MergeViewTests(MergeTestCase):
    def url(self, pub):
        return reverse("publication_merge", args=[pub.pk])

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_preview_does_not_merge(self):
        response = self.client.post(self.url(self.duplicate), {"target": self.book.isbn})
        self.assertContains(response, "Confirmer la fusion")
        self.assertTrue(Publication.objects.filter(pk=self.duplicate.pk).exists())

    def test_confirmation_merges(self):
        response = self.client.post(
            self.url(self.duplicate), {"target": self.book.isbn, "confirm": "True"}
        )
        self.assertRedirects(response, reverse("publication_detail", args=[self.book.pk]))
        self.assertFalse(Publication.objects.filter(pk=self.duplicate.pk).exists())

    def test_unknown_target_shows_an_error(self):
        response = self.client.post(self.url(self.duplicate), {"target": "rien"})
        self.assertContains(response, "Aucune publication trouvée")

    def test_identified_publication_is_refused(self):
        response = self.client.get(self.url(self.book))
        self.assertRedirects(response, reverse("publication_detail", args=[self.book.pk]))

    def test_detail_page_offers_the_merge_only_without_identifier(self):
        detail = reverse("publication_detail", args=[self.duplicate.pk])
        self.assertContains(self.client.get(detail), self.url(self.duplicate))
        book_detail = reverse("publication_detail", args=[self.book.pk])
        self.assertNotContains(self.client.get(book_detail), self.url(self.book))


@patch("references.services.importer.fetch_crossref_json")
class FindMergeTargetImportTests(TestCase):
    def test_unknown_doi_is_imported(self, fetch):
        fetch.return_value = {"message": {"title": ["Nouvel article"]}}
        target = find_merge_target("10.1000/new")
        self.assertEqual(target.title, "Nouvel article")
        fetch.assert_called_once_with("10.1000/new")
