from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Publication, UserPublication
from references.services.corpus.corpus_transfer import (
    EXPORT_FORMAT,
    bibtex_note,
    corpus_bibtex,
    export_corpus,
    import_corpus,
)
from references.services.display.publication_table import corpus_ids
from references.services.display.search import filter_publications, parse
from references.tests.helpers import without_doi_org


class NoteTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice")
        cls.bob = User.objects.create_user("bob")
        cls.pub = Publication.objects.create(doi="10.1000/noted", title="Annotée")
        cls.other = Publication.objects.create(doi="10.1000/other", title="Autre")
        cls.entry = UserPublication.objects.create(
            user=cls.alice, publication=cls.pub, note="Méthode de l'aimant pulsé, § 3."
        )
        UserPublication.objects.create(user=cls.alice, publication=cls.other)
        UserPublication.objects.create(user=cls.bob, publication=cls.pub, note="Note de Bob")


class NoteOnThePageTests(NoteTestCase):
    """A free note per entry of my corpus, on the page of the publication (#283)."""

    def detail(self, pub):
        return self.client.get(reverse("publication_detail", args=[pub.pk]))

    def test_the_owner_sees_and_edits_her_note(self):
        self.client.force_login(self.alice)
        response = self.detail(self.pub)
        self.assertContains(response, "Ma note")
        self.assertContains(response, "Méthode de l&#x27;aimant pulsé, § 3.")
        self.assertContains(response, reverse("corpus_note", args=[self.pub.pk]))
        self.assertNotContains(response, "Note de Bob")

    def test_no_note_outside_my_corpus_nor_for_a_visitor(self):
        self.assertNotContains(self.detail(self.pub), "Ma note")
        carol = get_user_model().objects.create_user("carol")
        self.client.force_login(carol)
        self.assertNotContains(self.detail(self.pub), "Ma note")

    def test_save_and_erase(self):
        self.client.force_login(self.alice)
        url = reverse("corpus_note", args=[self.other.pk])
        response = self.client.post(url, {"note": "  À relire  "}, follow=True)
        self.assertContains(response, "Note enregistrée.")
        self.assertRedirects(
            response, reverse("publication_detail", args=[self.other.pk]) + "#note"
        )
        entry = UserPublication.objects.get(user=self.alice, publication=self.other)
        self.assertEqual(entry.note, "À relire")
        response = self.client.post(url, {"note": ""}, follow=True)
        self.assertContains(response, "Note effacée.")
        entry.refresh_from_db()
        self.assertEqual(entry.note, "")

    def test_only_an_entry_of_my_corpus(self):
        carol = get_user_model().objects.create_user("carol")
        self.client.force_login(carol)
        url = reverse("corpus_note", args=[self.pub.pk])
        self.assertEqual(self.client.post(url, {"note": "x"}).status_code, 404)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_too_long(self):
        self.client.force_login(self.alice)
        url = reverse("corpus_note", args=[self.pub.pk])
        self.client.post(url, {"note": "x" * 20001})
        self.entry.refresh_from_db()
        self.assertTrue(self.entry.note.startswith("Méthode"))

    def test_the_removal_says_the_note_is_lost(self):
        self.client.force_login(self.alice)
        self.assertEqual(corpus_ids(self.alice).with_note, {self.pub.pk})
        self.assertContains(self.detail(self.pub), "Sa note sera perdue.")
        self.assertNotContains(self.detail(self.other), "Sa note sera perdue.")
        self.entry.reading_status = UserPublication.ReadingStatus.READ
        self.entry.save()
        response = self.client.post(reverse("corpus_remove", args=[self.pub.pk]), follow=True)
        self.assertContains(
            response, "a été retiré de votre corpus, avec son statut « Lu » et sa note."
        )


class NoteSearchTests(NoteTestCase):
    """note: looks in the notes of my own corpus only."""

    def found(self, text, user):
        return set(filter_publications(Publication.objects.all(), parse(text), user))

    def test_parse(self):
        query = parse('note:"aimant pulsé" magnet')
        self.assertEqual(query.notes, ["aimant pulsé"])
        self.assertEqual(query.terms, ["magnet"])
        self.assertTrue(query.about_publications_only)

    def test_my_notes_case_and_accents_ignored(self):
        self.assertEqual(self.found("note:AIMANT", self.alice), {self.pub})
        self.assertEqual(self.found("note:aimant", self.bob), set())
        self.assertEqual(self.found("note:bob", self.alice), set())

    def test_visitor(self):
        response = self.client.get(reverse("search"), {"q": "note:aimant"})
        self.assertContains(response, "connectez-vous")
        self.assertEqual(response.context["page_obj"].paginator.count, 0)

    def test_search_page(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("search"), {"q": "note:pulse"})
        self.assertEqual(list(response.context["publications"]), [self.pub])
        self.assertContains(response, "<code>note:</code>")


class FreeTextInNotesTests(NoteTestCase):
    """Free text also looks in my notes, never in those of others (#416)."""

    def search(self, text, user=None, **params):
        if user:
            self.client.force_login(user)
        return self.client.get(reverse("search"), {"q": text, **params})

    def found_in_note(self, response):
        return {pub: pub.found_in_note for pub in response.context["publications"]}

    def test_my_note_case_and_accents_ignored(self):
        response = self.search("PULSE", self.alice)
        self.assertEqual(self.found_in_note(response), {self.pub: True})
        self.assertContains(response, "trouvée dans votre note")

    def test_not_the_notes_of_others(self):
        self.assertEqual(list(self.search("pulsé", self.bob).context["publications"]), [])
        self.assertEqual(list(self.search("bob", self.alice).context["publications"]), [])

    def test_visitor(self):
        response = self.search("pulsé")
        self.assertEqual(list(response.context["publications"]), [])
        self.assertNotContains(response, "connectez-vous")

    def test_found_by_title_and_note_once_without_badge(self):
        self.entry.note = "Annotée avec soin"
        self.entry.save()
        response = self.search("annotee", self.alice)
        self.assertEqual(self.found_in_note(response), {self.pub: False})
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertNotContains(response, "trouvée dans votre note")

    def test_one_word_in_the_note_only(self):
        # « annotée » is in the title, « aimant » in the note alone: the note was needed.
        response = self.search("annotée aimant", self.alice)
        self.assertEqual(self.found_in_note(response), {self.pub: True})

    def test_help_under_the_bar(self):
        self.assertContains(self.search("x"), "Cherche aussi dans vos notes.")

    def test_sort_and_pages_unchanged(self):
        for number in range(55):
            pub = Publication.objects.create(doi=f"10.1000/p{number}", title=f"Étude {number:02}")
            UserPublication.objects.create(
                user=self.alice, publication=pub, note="aimant" if number % 2 else ""
            )
        response = self.search("etude", self.alice, sort="-title")
        self.assertEqual(response.context["page_obj"].paginator.count, 55)
        titles = [pub.title for pub in response.context["publications"]]
        self.assertEqual(len(titles), 50)
        self.assertEqual(titles, sorted(titles, reverse=True))
        last = self.search("etude", self.alice, sort="-title", page=2).context["publications"]
        self.assertEqual([pub.title for pub in last], [f"Étude {n:02}" for n in range(4, -1, -1)])
        self.assertFalse(any(pub.found_in_note for pub in last))


@without_doi_org
class NoteTransferTests(NoteTestCase):
    """The note in the JSON export (version 3) and the BibTeX export."""

    def test_json_export(self):
        data = export_corpus(self.alice)
        self.assertEqual(data["version"], 3)
        notes = {entry["doi"]: entry["note"] for entry in data["publications"]}
        self.assertEqual(
            notes, {"10.1000/noted": "Méthode de l'aimant pulsé, § 3.", "10.1000/other": ""}
        )

    def import_into_bob(self, version, **entry):
        data = {"format": EXPORT_FORMAT, "version": version, "publications": [entry]}
        return import_corpus(self.bob, data)

    def note_of_bob(self, pub):
        return UserPublication.objects.get(user=self.bob, publication=pub).note

    def test_import_fills_an_empty_note_only(self):
        UserPublication.objects.create(user=self.bob, publication=self.other)
        self.import_into_bob(3, doi=self.other.doi, note=" Lue en 2025 ")
        self.assertEqual(self.note_of_bob(self.other), "Lue en 2025")
        self.import_into_bob(3, doi=self.pub.doi, note="Remplacée ?")
        self.assertEqual(self.note_of_bob(self.pub), "Note de Bob")

    def test_versions_1_and_2_still_import(self):
        UserPublication.objects.create(user=self.bob, publication=self.other)
        for version in (1, 2):
            with self.subTest(version=version):
                report = self.import_into_bob(version, doi=self.other.doi, note=42)
                self.assertEqual(report.already_there, [self.other])
                self.assertEqual(self.note_of_bob(self.other), "")

    def test_bibtex_annote(self):
        bibtex = corpus_bibtex(self.alice)
        self.assertIn("annote = {Méthode de l'aimant pulsé, § 3.},", bibtex)
        self.assertEqual(bibtex.count("annote ="), 1)

    def test_bibtex_note_escaped_and_balanced(self):
        self.assertEqual(bibtex_note("50 % de {gain}"), "50 \\% de {gain}")
        self.assertEqual(bibtex_note("a } b {"), "a  b ")
        self.assertEqual(bibtex_note("{a"), "a")
