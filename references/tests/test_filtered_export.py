"""Export of a tag, or of the publications the filters of « Mon corpus » show (#285)."""

import json
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Publication, Tag, UserPublication
from references.services.corpus import tags
from references.services.corpus.corpus_transfer import import_corpus
from references.tests.helpers import with_crossref
from references.tests.sources import simulated_sources
from references.views.pagination import PAGE_SIZE


def exported_dois(response):
    return [entry["doi"] for entry in json.loads(response.content)["publications"]]


class FilteredExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice")
        cls.bob = User.objects.create_user("bob")
        cls.pubs = {}
        for name, year, tag, status in (
            ("a", 2021, "Projet/Groupe", "read"),
            ("b", 2018, "Projet", ""),
            ("c", 2022, "Autre", ""),
        ):
            pub = Publication.objects.create(
                doi=f"10.1000/{name}", title=f"Titre {name}", publication_date=date(year, 1, 1)
            )
            with_crossref(pub, {"message": {}})
            entry = UserPublication.objects.create(
                user=cls.alice, publication=pub, reading_status=status
            )
            tags.tag_entry(entry, tag)
            cls.pubs[name] = pub
        # Shown in the table, left out of the exports.
        without_identifier = Publication.objects.create(title="Sans identifiant")
        entry = UserPublication.objects.create(user=cls.alice, publication=without_identifier)
        tags.tag_entry(entry, "Projet")
        # Bob tags « Projet » a publication alice tagged « Autre », and has one of his own.
        bob_entry = UserPublication.objects.create(user=cls.bob, publication=cls.pubs["c"])
        tags.tag_entry(bob_entry, "Projet")
        own = Publication.objects.create(doi="10.1000/bob", title="De Bob")
        tags.tag_entry(UserPublication.objects.create(user=cls.bob, publication=own), "Projet")

    def setUp(self):
        self.client.force_login(self.alice)

    def export(self, name="corpus_export_json", **params):
        return self.client.get(reverse(name), params)

    def test_without_filter_the_whole_corpus(self):
        response = self.export()
        self.assertEqual(exported_dois(response), ["10.1000/a", "10.1000/b", "10.1000/c"])
        self.assertRegex(response["Content-Disposition"], r'filename="corpus-[\d-]+\.json"')

    def test_tag_with_its_subtags(self):
        response = self.export(tag="Projet")
        self.assertEqual(exported_dois(response), ["10.1000/a", "10.1000/b"])
        self.assertRegex(response["Content-Disposition"], r'filename="corpus-projet-[\d-]+\.json"')

    def test_subtag_alone(self):
        self.assertEqual(exported_dois(self.export(tag="Projet/Groupe")), ["10.1000/a"])
        response = self.export("corpus_export_bibtex", tag="Projet/Groupe")
        self.assertIn("10.1000/a", response.content.decode())
        self.assertNotIn("10.1000/b", response.content.decode())
        self.assertIn('filename="corpus-projet-groupe-', response["Content-Disposition"])

    def test_combined_filters(self):
        self.assertEqual(exported_dois(self.export(tag="Projet", year_from="2020")), ["10.1000/a"])
        self.assertEqual(exported_dois(self.export(tag="Projet", status="none")), ["10.1000/b"])
        response = self.export(title="titre", year_to="2021")
        self.assertEqual(exported_dois(response), ["10.1000/a", "10.1000/b"])
        self.assertIn('filename="corpus-selection-', response["Content-Disposition"])

    def test_filter_without_result(self):
        self.assertEqual(exported_dois(self.export(title="introuvable")), [])
        bibtex = self.export("corpus_export_bibtex", title="introuvable").content.decode()
        self.assertEqual(bibtex.strip(), "")

    def test_never_the_corpus_of_another_user(self):
        # Bob's tag « Projet » on c, and his own publication, stay out of alice's export.
        self.assertNotIn("10.1000/c", exported_dois(self.export(tag="Projet")))
        self.assertNotIn("10.1000/bob", exported_dois(self.export(tag="Projet")))
        self.client.force_login(self.bob)
        self.assertEqual(exported_dois(self.export(tag="Projet")), ["10.1000/bob", "10.1000/c"])
        self.assertEqual(exported_dois(self.export(tag="Autre")), [])

    def test_sort_and_page_are_ignored(self):
        response = self.export(tag="Projet", sort="-added", page="2")
        self.assertEqual(exported_dois(response), ["10.1000/a", "10.1000/b"])

    @simulated_sources()
    def test_a_filtered_export_imports_again(self):
        data = json.loads(self.export(tag="Projet").content)
        carol = get_user_model().objects.create_user("carol")
        report = import_corpus(carol, data)
        self.assertEqual(len(report.already_there) + len(report.added), 2)
        entries = UserPublication.objects.filter(user=carol)
        self.assertEqual(
            sorted(entries.values_list("publication__doi", flat=True)), ["10.1000/a", "10.1000/b"]
        )
        names = Tag.objects.filter(user=carol).values_list("name", flat=True)
        self.assertEqual(sorted(names), ["Projet", "Projet/Groupe"])


class ExportButtonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = get_user_model().objects.create_user("alice")
        for number in range(PAGE_SIZE + 5):
            pub = Publication.objects.create(doi=f"10.1000/{number}", title=f"Titre {number}")
            entry = UserPublication.objects.create(user=cls.alice, publication=pub)
            if number % 2 == 0:
                tags.tag_entry(entry, "Pair")
        UserPublication.objects.create(
            user=cls.alice, publication=Publication.objects.create(title="Sans identifiant")
        )

    def setUp(self):
        self.client.force_login(self.alice)

    def corpus(self, **params):
        return self.client.get(reverse("corpus"), params)

    def test_without_filter_the_labels_of_the_whole_corpus(self):
        response = self.corpus()
        self.assertContains(response, "JSON (réimportable)")
        self.assertContains(response, f'href="{reverse("corpus_export_bibtex")}"')
        self.assertNotContains(response, "publications affichées")
        self.assertNotContains(response, "reprennent les filtres")
        self.assertContains(response, "1 publication sans DOI ni ISBN")

    def test_filtered_labels_count_every_page(self):
        response = self.corpus(title="titre", sort="-added", page="2")
        shown = PAGE_SIZE + 5
        self.assertContains(response, f"JSON des {shown} publications affichées")
        self.assertContains(response, f"BibTeX des {shown} publications affichées")
        self.assertContains(response, f'href="{reverse("corpus_export_bibtex")}?title=titre"')
        self.assertContains(response, "reprennent les filtres")
        self.assertNotContains(response, "sans DOI ni ISBN")

    def test_tag_labels_and_publications_left_out(self):
        response = self.corpus(tag="Pair")
        self.assertContains(response, "BibTeX des 28 publications affichées")
        self.assertContains(response, f'href="{reverse("corpus_export_json")}?tag=Pair"')

    def test_one_publication_shown(self):
        response = self.corpus(title="Titre 54")
        self.assertContains(response, "BibTeX de la publication affichée")

    def test_filter_without_result_disables_the_buttons(self):
        response = self.corpus(title="introuvable")
        self.assertContains(response, "BibTeX : aucune publication affichée")
        self.assertRegex(
            response.content.decode(), r"disabled[^<]*>\s*<svg[^>]*>.*?</svg>\s*BibTeX : aucune"
        )
        self.assertNotContains(response, "export/bibtex/?")
