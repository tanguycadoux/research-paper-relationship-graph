from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Author, CitedReference, Publication
from references.services.books import import_book_metadata
from references.services.parser import parse_publication
from references.tests.helpers import crossref_record, with_crossref, without_other_sources


def work(title, year, family="Lovelace", references=()):
    return {
        "message": {
            "title": [title],
            "issued": {"date-parts": [[year]]},
            "author": [{"given": "Ada", "family": family}],
            "reference": list(references),
        }
    }


class ManualEditsTestCase(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("alice"))
        self.pub = with_crossref(
            Publication.objects.create(doi="10.1000/old"), work("Source", 2020)
        )
        parse_publication(self.pub)

    def edit(self, **fields):
        data = {
            "doi": self.pub.doi,
            "isbn": self.pub.isbn,
            "title": self.pub.title,
            "publication_date": self.pub.publication_date.isoformat(),
        }
        data.update(fields)
        response = self.client.post(reverse("publication_edit", args=[self.pub.pk]), data)
        self.pub.refresh_from_db()
        return response


class KeptCorrectionsTests(ManualEditsTestCase):
    """A title or date corrected by hand survives a new reading of the sources (#146)."""

    def test_corrected_title_survives_a_new_parse(self):
        self.edit(title="Titre corrigé")
        self.assertTrue(self.pub.title_edited)
        self.assertFalse(self.pub.date_edited)
        parse_publication(self.pub)
        self.assertEqual(self.pub.title, "Titre corrigé")

    def test_corrected_date_survives_a_new_parse(self):
        self.edit(publication_date="2019-06-15")
        self.assertEqual((self.pub.title_edited, self.pub.date_edited), (False, True))
        detail = self.client.get(reverse("publication_detail", args=[self.pub.pk]))
        # Under the title, with the other corrections: one place for all of them.
        self.assertContains(detail, "Corrigé à la main :")
        self.assertContains(detail, "date.")
        parse_publication(self.pub)
        self.assertEqual(self.pub.publication_date, date(2019, 6, 15))

    def test_an_emptied_title_is_filled_again_by_the_source(self):
        self.edit(title="Titre corrigé")
        self.edit(title="")
        self.assertFalse(self.pub.title_edited)
        parse_publication(self.pub)
        self.assertEqual(self.pub.title, "Source")

    def test_detail_page_shows_the_correction_and_restores_the_sources(self):
        self.edit(title="Titre corrigé")
        detail = self.client.get(reverse("publication_detail", args=[self.pub.pk]))
        self.assertContains(detail, "Corrigé à la main :")
        self.assertContains(detail, "titre.")
        self.assertContains(detail, "Revenir aux valeurs des sources")

        url = reverse("publication_restore_sources", args=[self.pub.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        self.pub.refresh_from_db()
        self.assertEqual((self.pub.title, self.pub.title_edited), ("Source", False))

    @patch("references.services.importer.fetch_crossref_json")
    def test_editing_without_changing_the_identifier_fetches_nothing(self, fetch):
        response = self.edit(title="Titre corrigé")
        self.assertRedirects(response, reverse("publication_detail", args=[self.pub.pk]))
        fetch.assert_not_called()


@without_other_sources
@patch("references.services.importer.fetch_crossref_json")
class IdentifierChangeTests(ManualEditsTestCase):
    """A new DOI or ISBN replaces what was fetched for the old one."""

    def test_new_doi_replaces_the_old_data(self, fetch):
        old_author = self.pub.authors.get()
        CitedReference.objects.create(source=self.pub, position=0, unstructured="Ancienne")
        fetch.return_value = work("Nouvel article", 2024, family="Turing")

        self.edit(doi="10.1000/new")

        fetch.assert_called_once_with("10.1000/new")
        self.assertEqual(self.pub.title, "Nouvel article")
        self.assertEqual(self.pub.publication_date, date(2024, 1, 1))
        self.assertEqual([str(a) for a in self.pub.authors.all()], ["Ada Turing"])
        self.assertFalse(self.pub.cited_references.exists())
        # The author of the old work had no other publication.
        self.assertFalse(Author.objects.filter(pk=old_author.pk).exists())

    def test_a_title_corrected_in_the_same_form_is_kept(self, fetch):
        fetch.return_value = work("Nouvel article", 2024)
        self.edit(doi="10.1000/new", title="Mon titre")
        self.assertEqual(self.pub.title, "Mon titre")

    def test_unknown_new_doi_drops_the_old_data_and_warns(self, fetch):
        fetch.return_value = None
        response = self.edit(doi="10.1000/ghost")
        self.assertIsNone(crossref_record(self.pub))
        self.assertFalse(self.pub.authors.exists())
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertIn("n'ont pas pu être récupérées", messages[0])


@patch("references.services.books.fetch_openlibrary_book")
@patch("references.services.books.fetch_crossref_by_isbn", return_value=None)
class BookIdentifierChangeTests(TestCase):
    def test_new_isbn_is_looked_up_in_open_library(self, _crossref, openlibrary):
        self.client.force_login(get_user_model().objects.create_user("alice"))
        book = Publication.objects.create(title="Livre", isbn="9780262035613")
        openlibrary.return_value = {"title": "Autre livre", "first_publish_year": 2001}
        self.client.post(
            reverse("publication_edit", args=[book.pk]),
            {"isbn": "978-2-07-036822-8", "title": "Livre"},
        )
        book.refresh_from_db()
        openlibrary.assert_called_once_with("9782070368228")
        self.assertEqual(book.publication_date, date(2001, 1, 1))


@patch("references.services.books.fetch_crossref_by_isbn")
class BookFoundInCrossrefTests(TestCase):
    def setUp(self):
        self.book = Publication.objects.create(isbn="9782070368228")

    def crossref_book(self, doi):
        answer = work("Livre de Crossref", 2010)
        answer["message"]["DOI"] = doi
        return answer

    def test_the_doi_of_the_book_is_taken(self, fetch):
        fetch.return_value = self.crossref_book("10.1000/BOOK")
        self.assertTrue(import_book_metadata(self.book))
        self.book.refresh_from_db()
        self.assertEqual((self.book.doi, self.book.title), ("10.1000/book", "Livre de Crossref"))
        self.assertIsNotNone(crossref_record(self.book))

    def test_a_doi_held_by_another_publication_is_not_taken(self, fetch):
        Publication.objects.create(doi="10.1000/book")
        fetch.return_value = self.crossref_book("10.1000/book")
        import_book_metadata(self.book)
        self.book.refresh_from_db()
        self.assertEqual((self.book.doi, self.book.title), ("", "Livre de Crossref"))
