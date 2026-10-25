from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, Publication, UserPublication
from references.services.corpus import add_to_corpus, change_reading_status
from references.services.corpus_transfer import EXPORT_FORMAT, import_corpus
from references.tests.helpers import without_doi_org

TO_READ = UserPublication.ReadingStatus.TO_READ
READ = UserPublication.ReadingStatus.READ


def imported(pub, **_):
    return pub


@without_doi_org
@patch("references.services.corpus.import_publication", side_effect=imported)
class LightToReadTests(TestCase):
    """A publication « à lire » enters the corpus without its bibliography (#234)."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice")
        cls.bob = User.objects.create_user("bob")
        cls.pub = Publication.objects.create(doi="10.1000/a", title="Un article")

    def setUp(self):
        self.client.force_login(self.alice)

    def entry(self, user=None):
        return UserPublication.objects.get(user=user or self.alice, publication=self.pub)

    def test_to_read_is_added_without_its_references(self, import_publication):
        add_to_corpus(self.alice, self.pub, TO_READ)
        import_publication.assert_called_once_with(self.pub, with_references=False)
        self.assertEqual(self.entry().reading_status, TO_READ)

    def test_other_additions_import_the_references(self, import_publication):
        add_to_corpus(self.alice, self.pub)
        import_publication.assert_called_once_with(self.pub, with_references=True)

    def test_status_is_only_given_to_a_new_entry(self, import_publication):
        UserPublication.objects.create(user=self.alice, publication=self.pub, reading_status=READ)
        add_to_corpus(self.alice, self.pub, TO_READ)
        self.assertEqual(self.entry().reading_status, READ)
        import_publication.assert_called_once_with(self.pub, with_references=True)

    def test_leaving_to_read_imports_the_references(self, import_publication):
        entry = UserPublication.objects.create(
            user=self.alice, publication=self.pub, reading_status=TO_READ
        )
        self.assertEqual(change_reading_status(entry, "reading"), self.pub)
        import_publication.assert_called_once_with(self.pub, with_references=True)

    def test_other_changes_import_nothing(self, import_publication):
        entry = UserPublication.objects.create(user=self.alice, publication=self.pub)
        # None → lu → à lire → à lire: never from « à lire » to another status.
        for status in (READ, TO_READ, TO_READ):
            with self.subTest(status=status):
                self.assertIs(change_reading_status(entry, status), False)
        import_publication.assert_not_called()

    def test_book_without_doi_has_no_bibliography_to_import(self, import_publication):
        book = Publication.objects.create(isbn="9780262035613", title="Un livre")
        entry = UserPublication.objects.create(
            user=self.alice, publication=book, reading_status=TO_READ
        )
        self.assertIs(change_reading_status(entry, READ), False)
        import_publication.assert_not_called()

    def test_references_are_parsed_unless_every_entry_is_to_read(self, _import):
        UserPublication.objects.create(
            user=self.alice, publication=self.pub, reading_status=TO_READ
        )
        self.assertFalse(self.pub.parse_references)
        UserPublication.objects.create(user=self.bob, publication=self.pub)
        self.assertTrue(self.pub.parse_references)

    def test_add_buttons_on_the_publication_page_and_in_tables(self, _import):
        for url in (reverse("publication_detail", args=[self.pub.pk]), reverse("publication_list")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, 'name="status"')
                self.assertContains(response, 'value="to_read"')

    def test_add_view_with_the_to_read_button(self, import_publication):
        url = reverse("corpus_add", args=[self.pub.pk])
        response = self.client.post(url, {"status": "to_read"}, follow=True)
        self.assertEqual(self.entry().reading_status, TO_READ)
        self.assertContains(response, "à lire : sa bibliographie sera importée")
        import_publication.assert_called_once_with(self.pub, with_references=False)

    def test_add_by_identifier_with_the_to_read_button(self, import_publication):
        self.client.post(
            reverse("corpus_add_by_identifier"), {"identifier": "10.1000/a", "status": "to_read"}
        )
        self.assertEqual(self.entry().reading_status, TO_READ)

    def test_status_change_reports_the_references_imported(self, _import):
        UserPublication.objects.create(
            user=self.alice, publication=self.pub, reading_status=TO_READ
        )
        CitedReference.objects.create(source=self.pub, position=0, unstructured="Réf.")
        url = reverse("corpus_reading_status", args=[self.pub.pk])
        response = self.client.post(url, {"status": "reading"}, follow=True)
        self.assertContains(response, "Sa bibliographie a été importée : 1 référence(s).")

    def test_status_change_reports_a_failed_import(self, import_publication):
        import_publication.side_effect = None
        import_publication.return_value = None
        UserPublication.objects.create(
            user=self.alice, publication=self.pub, reading_status=TO_READ
        )
        url = reverse("corpus_reading_status", args=[self.pub.pk])
        response = self.client.post(url, {"status": "read"}, follow=True)
        self.assertContains(response, "Sa bibliographie n&#x27;a pas pu être récupérée")
        self.assertEqual(self.entry().reading_status, READ)


@without_doi_org
@patch("references.services.corpus.import_publication", side_effect=imported)
class ImportAsToReadTests(TestCase):
    """The box « importer comme à lire » of the file import (#234)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")
        cls.new = Publication.objects.create(doi="10.1000/new", title="Nouvelle")
        cls.read = Publication.objects.create(doi="10.1000/read", title="Lue")
        cls.there = Publication.objects.create(doi="10.1000/there", title="Déjà là")
        UserPublication.objects.create(user=cls.user, publication=cls.there)

    def status(self, pub):
        return UserPublication.objects.get(user=self.user, publication=pub).reading_status

    def test_new_entries_without_status_become_to_read(self, import_publication):
        data = {
            "format": EXPORT_FORMAT,
            "version": 2,
            "publications": [
                {"doi": "10.1000/new"},
                {"doi": "10.1000/read", "status": "read"},
                {"doi": "10.1000/there"},
            ],
        }
        import_corpus(self.user, data, TO_READ)
        self.assertEqual(self.status(self.new), TO_READ)
        self.assertEqual(self.status(self.read), READ)
        # An entry already there keeps its own status, even none.
        self.assertEqual(self.status(self.there), "")
        import_publication.assert_any_call(self.new, with_references=False)
        import_publication.assert_any_call(self.read, with_references=True)

    def test_box_of_the_import_form(self, import_publication):
        self.client.force_login(self.user)
        upload = SimpleUploadedFile("zotero.bib", b"@article{a, doi = {10.1000/new}}")
        self.client.post(reverse("corpus_import"), {"file": upload, "to_read": "1"})
        self.assertEqual(self.status(self.new), TO_READ)
        response = self.client.get(reverse("corpus"))
        self.assertContains(response, 'name="to_read"')
