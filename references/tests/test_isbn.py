from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.forms import IdentifyReferenceForm, PublicationForm
from references.models import CitedReference, Publication, UserPublication
from references.services.identifiers.isbn import is_valid_isbn, normalize_isbn
from references.services.imports.books import find_or_import_book
from references.services.sources.metadata_formats import openlibrary_message
from references.services.sources.openlibrary_api import fetch_openlibrary_book
from references.tests.helpers import with_openlibrary
from references.tests.sources import active_sources, simulated_sources

DEEP_LEARNING = "9780262035613"
OPENLIBRARY_DOC = {
    "title": "Deep Learning",
    "author_name": ["Ian Goodfellow", "Yoshua Bengio", "Aaron Courville"],
    "first_publish_year": 2016,
}
CROSSREF_BOOK = {
    "message": {"DOI": "10.7551/DL", "title": ["Deep Learning"], "ISBN": [DEEP_LEARNING]}
}


class IsbnNormalizationTests(SimpleTestCase):
    def test_hyphens_and_spaces_are_removed(self):
        self.assertEqual(normalize_isbn("978-0-262-03561-3"), DEEP_LEARNING)
        self.assertEqual(normalize_isbn(" 978 0262035613 "), DEEP_LEARNING)

    def test_isbn10_is_converted(self):
        self.assertEqual(normalize_isbn("0-262-03561-8"), DEEP_LEARNING)
        self.assertEqual(normalize_isbn("080442957X"), "9780804429573")

    def test_validation(self):
        self.assertTrue(is_valid_isbn(DEEP_LEARNING))
        for isbn in ("", "9780262035614", "12345", normalize_isbn("0262035619")):
            with self.subTest(isbn=isbn):
                self.assertFalse(is_valid_isbn(isbn))


class OpenLibraryTests(SimpleTestCase):
    def test_search_by_isbn_in_one_request(self):
        with simulated_sources(openlibrary={DEEP_LEARNING: OPENLIBRARY_DOC}) as sources:
            self.assertEqual(fetch_openlibrary_book(DEEP_LEARNING), OPENLIBRARY_DOC)
        self.assertEqual(sources.asked("openlibrary"), [DEEP_LEARNING])

    def test_message_conversion(self):
        message = openlibrary_message(dict(OPENLIBRARY_DOC, subtitle="Adaptive Computation"))
        self.assertEqual(message["title"], ["Deep Learning: Adaptive Computation"])
        self.assertEqual(message["issued"], {"date-parts": [[2016]]})
        self.assertEqual(message["author"][0], {"given": "Ian", "family": "Goodfellow"})


@simulated_sources()
class FindOrImportBookTests(TestCase):
    def test_crossref_first(self):
        active_sources().add(crossref=[CROSSREF_BOOK])
        pub, imported = find_or_import_book(DEEP_LEARNING)
        self.assertTrue(imported)
        self.assertEqual(
            (pub.doi, pub.isbn, pub.title), ("10.7551/dl", DEEP_LEARNING, "Deep Learning")
        )
        self.assertEqual(active_sources().to("openlibrary"), [])

    def test_crossref_book_goes_to_the_publication_of_its_doi(self):
        existing = Publication.objects.create(doi="10.7551/dl")
        active_sources().add(crossref=[CROSSREF_BOOK])
        pub, _ = find_or_import_book(DEEP_LEARNING)
        self.assertEqual(pub, existing)
        self.assertEqual(Publication.objects.count(), 1)

    def test_then_open_library_with_authors(self):
        active_sources().add(openlibrary={DEEP_LEARNING: OPENLIBRARY_DOC})
        pub, imported = find_or_import_book(DEEP_LEARNING)
        self.assertTrue(imported)
        self.assertEqual((pub.title, str(pub.publication_date)), ("Deep Learning", "2016-01-01"))
        families = [slot.published_family_name for slot in pub.authorpublication_set.all()]
        self.assertEqual(families, ["Goodfellow", "Bengio", "Courville"])

    def test_unknown_everywhere(self):
        pub, imported = find_or_import_book(DEEP_LEARNING)
        self.assertFalse(imported)
        self.assertEqual(pub.isbn, DEEP_LEARNING)

    def test_stored_metadata_is_not_fetched_again(self):
        with_openlibrary(Publication.objects.create(isbn=DEEP_LEARNING), OPENLIBRARY_DOC)
        find_or_import_book(DEEP_LEARNING)
        self.assertEqual(active_sources().requests, [])

    def test_publication_without_metadata_is_retried(self):
        existing = Publication.objects.create(isbn=DEEP_LEARNING)
        active_sources().add(openlibrary={DEEP_LEARNING: OPENLIBRARY_DOC})
        pub, imported = find_or_import_book(DEEP_LEARNING)
        self.assertEqual(pub, existing)
        self.assertTrue(imported)


class IsbnModelAndFormTests(TestCase):
    def test_isbn_is_unique_when_set(self):
        Publication.objects.create(title="A")
        Publication.objects.create(title="B")
        Publication.objects.create(isbn=DEEP_LEARNING)
        with self.assertRaises(IntegrityError):
            Publication.objects.create(isbn="0-262-03561-8")

    def test_publication_form_accepts_hyphenated_isbn10(self):
        form = PublicationForm({"isbn": "0-262-03561-8"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["isbn"], DEEP_LEARNING)

    def test_publication_form_rejects_invalid_isbn(self):
        self.assertIn("isbn", PublicationForm({"isbn": "9780262035614"}).errors)

    def test_identify_form_requires_a_valid_isbn(self):
        self.assertIn("isbn", IdentifyReferenceForm({"method": "isbn", "isbn": "123"}).errors)


@simulated_sources(openlibrary={DEEP_LEARNING: OPENLIBRARY_DOC})
class IdentifyByIsbnViewTests(TestCase):
    def test_reference_is_linked_to_the_book(self):
        source = Publication.objects.create(title="Source")
        ref = CitedReference.objects.create(source=source, position=0, unstructured="Goodfellow…")
        self.client.force_login(get_user_model().objects.create_user("alice"))
        self.client.post(
            reverse("reference_identify", args=[source.pk, 0]),
            {"method": "isbn", "isbn": "978-0-262-03561-3"},
        )
        ref.refresh_from_db()
        self.assertEqual(ref.target.title, "Deep Learning")
        self.assertTrue(ref.resolved_manually)


BOOK_SOURCES = simulated_sources(openlibrary={DEEP_LEARNING: OPENLIBRARY_DOC})


@BOOK_SOURCES
class AddByIsbnViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        self.client.force_login(self.user)

    def add(self, identifier):
        url = reverse("corpus_add_by_identifier")
        return self.client.post(url, {"identifier": identifier}, follow=True)

    def test_book_is_added_by_isbn10_with_hyphens(self):
        self.add("0-262-03561-8")
        book = Publication.objects.get(isbn=DEEP_LEARNING)
        self.assertEqual(book.title, "Deep Learning")
        self.assertTrue(UserPublication.objects.filter(user=self.user, publication=book).exists())
        self.assertEqual(BOOK_SOURCES.single("crossref"), [])

    def test_unknown_isbn_is_added_without_data(self):
        BOOK_SOURCES.openlibrary.clear()  # restored when the test ends
        response = self.add(DEEP_LEARNING)
        self.assertContains(response, "ISBN inconnu de Crossref et d&#x27;Open Library")
        self.assertTrue(UserPublication.objects.filter(publication__isbn=DEEP_LEARNING).exists())
        self.assertEqual(BOOK_SOURCES.single("crossref"), [])

    def test_invalid_identifier_names_both_formats(self):
        response = self.add("9780262035614")
        self.assertContains(response, "un identifiant ou un lien arXiv")
        self.assertFalse(Publication.objects.exists())
