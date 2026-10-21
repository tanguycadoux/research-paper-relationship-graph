import json
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from references.models import Author, AuthorPublication, Publication, UserPublication
from references.services.corpus_transfer import (
    EXPORT_FORMAT,
    EXPORT_VERSION,
    InvalidExport,
    corpus_bibtex,
    export_corpus,
    import_corpus,
)
from references.tests.helpers import with_crossref, without_other_sources
from references.tests.test_importer import with_mocked_crossref


def export_of(*entries):
    return {"format": EXPORT_FORMAT, "version": EXPORT_VERSION, "publications": list(entries)}


class ExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice")
        bob = User.objects.create_user("bob")
        for pub in (
            Publication.objects.create(doi="10.1000/a", title="Article"),
            Publication.objects.create(isbn="9780262035613", title="Livre"),
            Publication.objects.create(title="Sans identifiant"),
        ):
            UserPublication.objects.create(user=cls.alice, publication=pub)
        other = Publication.objects.create(doi="10.1000/bob")
        UserPublication.objects.create(user=bob, publication=other)

    def test_json_holds_the_identifiers_of_my_corpus(self):
        data = export_corpus(self.alice)
        self.assertEqual((data["format"], data["version"]), (EXPORT_FORMAT, EXPORT_VERSION))
        self.assertEqual(
            data["publications"],
            [
                {"doi": "10.1000/a", "isbn": "", "title": "Article"},
                {"doi": "", "isbn": "9780262035613", "title": "Livre"},
            ],
        )

    def test_downloads(self):
        self.client.force_login(self.alice)
        for name, extension in (("corpus_export_json", "json"), ("corpus_export_bibtex", "bib")):
            with self.subTest(export=name):
                response = self.client.get(reverse(name))
                self.assertIn(f'.{extension}"', response["Content-Disposition"])
                self.assertIn("attachment", response["Content-Disposition"])

    def test_page_reports_the_publications_left_out(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("corpus"))
        self.assertContains(response, "1 publication sans DOI ni ISBN")


@without_other_sources
@with_mocked_crossref
class ImportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("bob")

    def test_known_publication_is_added_without_any_request(self, fetch, fetch_works):
        pub = with_crossref(Publication.objects.create(doi="10.1000/known"), {"message": {}})
        report = import_corpus(self.user, export_of({"doi": "10.1000/known"}))
        self.assertEqual(report.added, [pub])
        self.assertTrue(UserPublication.objects.filter(user=self.user, publication=pub).exists())
        fetch.assert_not_called()

    def test_unknown_doi_is_fetched(self, fetch, fetch_works):
        report = import_corpus(self.user, export_of({"doi": "https://doi.org/10.1000/SOURCE"}))
        self.assertEqual([pub.title for pub in report.added], ["Source"])
        fetch.assert_called_once_with("10.1000/source")

    def test_publications_already_in_the_corpus_are_counted(self, fetch, fetch_works):
        pub = with_crossref(Publication.objects.create(doi="10.1000/known"), {"message": {}})
        UserPublication.objects.create(user=self.user, publication=pub)
        report = import_corpus(
            self.user, export_of({"doi": "10.1000/known"}, {"doi": "10.1000/known"})
        )
        self.assertEqual((report.added, report.already_there), ([], [pub, pub]))

    def test_entries_without_valid_identifier_are_ignored(self, fetch, fetch_works):
        report = import_corpus(self.user, export_of({"doi": "pas un DOI"}, {"title": "X"}, "texte"))
        self.assertEqual(report.ignored, 2)
        self.assertFalse(UserPublication.objects.exists())

    def test_book_without_metadata_is_never_sent_to_the_doi_sources(self, fetch, fetch_works):
        book = Publication.objects.create(isbn="9780262035613")
        with patch(
            "references.services.corpus_transfer.find_or_import_book", return_value=(book, False)
        ):
            report = import_corpus(self.user, export_of({"isbn": "978-0-262-03561-3"}))
        self.assertEqual(report.without_metadata, [book])
        self.assertTrue(UserPublication.objects.filter(user=self.user, publication=book).exists())
        fetch.assert_not_called()

    def test_other_files_are_refused(self, fetch, fetch_works):
        for data in ({"publications": []}, [], {**export_of(), "version": 99}):
            with self.subTest(data=data), self.assertRaises(InvalidExport):
                import_corpus(self.user, data)

    def test_round_trip_between_two_users(self, fetch, fetch_works):
        alice = get_user_model().objects.create_user("alice")
        pub = with_crossref(Publication.objects.create(doi="10.1000/known"), {"message": {}})
        UserPublication.objects.create(user=alice, publication=pub)
        import_corpus(self.user, json.loads(json.dumps(export_corpus(alice))))
        self.assertEqual(list(Publication.objects.filter(userpublication__user=self.user)), [pub])


@without_other_sources
@with_mocked_crossref
class ImportViewTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("bob"))

    def post(self, content):
        upload = SimpleUploadedFile("corpus.json", content, content_type="application/json")
        return self.client.post(reverse("corpus_import"), {"file": upload}, follow=True)

    def test_report_is_shown(self, fetch, fetch_works):
        with_crossref(Publication.objects.create(doi="10.1000/known"), {"message": {}})
        response = self.post(json.dumps(export_of({"doi": "10.1000/known"})).encode())
        self.assertContains(response, "1 publication(s) ajoutée(s), 0 déjà dans votre corpus")

    def test_invalid_file_is_reported(self, fetch, fetch_works):
        self.assertContains(self.post(b"\x00 pas du json"), "pas un JSON valide")
        self.assertContains(self.post(b"{}"), "pas un export de corpus")

    def test_get_is_refused(self, fetch, fetch_works):
        self.assertEqual(self.client.get(reverse("corpus_import")).status_code, 405)


class BibtexTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")

    def add(self, crossref=None, **fields):
        pub = Publication.objects.create(**fields)
        if crossref:
            with_crossref(pub, {"message": crossref})
        UserPublication.objects.create(user=self.user, publication=pub)
        return pub

    def test_article_entry(self):
        pub = self.add(
            {"type": "journal-article", "container-title": ["IEEE Trans. Appl. Supercond."]},
            doi="10.1109/x",
            title="An R&D Program Towards ${\\rm Nb}_{3}{\\rm Sn}$ Magnets",
            publication_date=date(2012, 6, 1),
        )
        for order, (first, last) in enumerate((("Ada", "Lovelace"), ("", "Turing"))):
            author = Author.objects.create(first_name=first, last_name=last)
            AuthorPublication.objects.create(publication=pub, author=author, order=order)
        self.assertEqual(
            corpus_bibtex(self.user),
            "@article{lovelace2012,\n"
            "  title = {{An R\\&D Program Towards ${\\rm Nb}_{3}{\\rm Sn}$ Magnets}},\n"
            "  author = {Lovelace, Ada and Turing},\n"
            "  year = {2012},\n"
            "  doi = {10.1109/x},\n"
            "  journal = {IEEE Trans. Appl. Supercond.},\n"
            "}\n",
        )

    def test_book_without_crossref_and_unique_keys(self):
        self.add(isbn="9780262035613", title="Deep learning", publication_date=date(2016, 1, 1))
        self.add(doi="10.1000/y", title="Deep thoughts", publication_date=date(2016, 1, 1))
        bibtex = corpus_bibtex(self.user)
        self.assertIn("@book{deep2016,", bibtex)
        self.assertIn("@misc{deep2016a,", bibtex)
        self.assertIn("isbn = {9780262035613}", bibtex)
