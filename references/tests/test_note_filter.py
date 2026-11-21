import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Publication, UserPublication


class NoteFilterTests(TestCase):
    """« Mon corpus » filtered on my notes (#443): a text, with a note, without."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice")
        bob = User.objects.create_user("bob")
        for name, note in (
            ("Aimants", "Bon résumé sur les AIMANTS supraconducteurs"),
            ("Sources", "Source ECR à relire"),
            ("Muette", ""),
        ):
            pub = Publication.objects.create(doi=f"10.1000/{name.lower()}", title=name)
            UserPublication.objects.create(user=cls.alice, publication=pub, note=note)
            UserPublication.objects.create(user=bob, publication=pub, note="aimant de bob")
        cls.tagged = Publication.objects.get(title="Sources")
        entry = UserPublication.objects.get(user=cls.alice, publication=cls.tagged)
        entry.tags.create(user=cls.alice, name="Projet")

    def setUp(self):
        self.client.force_login(self.alice)

    def get(self, **params):
        return self.client.get(reverse("corpus"), params)

    def titles(self, response):
        return sorted(pub.title for pub in response.context["publications"])

    def test_text_ignores_case_and_accents(self):
        self.assertEqual(self.titles(self.get(note="aimant")), ["Aimants"])
        self.assertEqual(self.titles(self.get(note="a relire")), ["Sources"])

    def test_only_my_notes(self):
        """Bob's note on every publication says « bob »: not mine."""
        self.assertEqual(self.titles(self.get(note="bob")), [])

    def test_with_and_without_a_note(self):
        self.assertEqual(self.titles(self.get(has_note="1")), ["Aimants", "Sources"])
        self.assertEqual(self.titles(self.get(has_note="0")), ["Muette"])
        self.assertEqual(len(self.titles(self.get(has_note="oui"))), 3)

    def test_the_text_wins_over_with_or_without(self):
        self.assertEqual(self.titles(self.get(note="ecr", has_note="0")), ["Sources"])

    def test_combines_with_the_other_filters(self):
        self.assertEqual(self.titles(self.get(note="source", title="aimants")), [])
        self.assertEqual(self.titles(self.get(has_note="1", tag="Projet")), ["Sources"])

    def test_summary(self):
        self.assertContains(self.get(note="aimant"), "Note contient « aimant »")
        self.assertContains(self.get(has_note="1"), "Note renseignée")
        self.assertContains(self.get(has_note="0"), "Note absente")

    def test_the_field_keeps_the_other_parameters(self):
        response = self.get(tag="Projet", note="ecr", page="2")
        self.assertContains(response, 'name="tag" value="Projet"', html=False)
        self.assertNotContains(response, 'name="page"')
        self.assertContains(response, 'value="ecr"')
        self.assertContains(response, 'href="?tag=Projet&amp;has_note=1"')

    def test_the_link_on_is_not_a_link(self):
        response = self.get(has_note="0")
        self.assertContains(response, '<span aria-current="true"', html=False)
        self.assertNotContains(response, 'href="?has_note=0"')

    def test_the_export_keeps_the_filter(self):
        response = self.get(note="aimant")
        self.assertContains(response, f'href="{reverse("corpus_export_json")}?note=aimant"')
        exported = self.client.get(reverse("corpus_export_json"), {"note": "aimant"})
        dois = [entry["doi"] for entry in json.loads(exported.content)["publications"]]
        self.assertEqual(dois, ["10.1000/aimants"])
