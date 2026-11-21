from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Publication
from references.tests.sources import simulated_sources


class AddPublicationTests(TestCase):
    """One way to add a publication, on the home page, my corpus and Publications (#277)."""

    PAGES = ("index", "corpus", "publication_list")

    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("alice"))

    def test_the_same_form_on_the_three_pages(self):
        action = f'action="{reverse("corpus_add_by_identifier")}"'
        for name in self.PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertContains(response, action)
                self.assertContains(response, "Ajouter à mon corpus")
                self.assertContains(response, "Ajouter à lire")
                self.assertContains(response, f'href="{reverse("publication_create")}"')

    def test_visitors_have_no_form(self):
        self.client.logout()
        for name in ("index", "publication_list"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertNotContains(response, reverse("corpus_add_by_identifier"))

    @simulated_sources()
    @patch("references.views.corpus.add_identified", side_effect=lambda user, pub, status: pub)
    def test_back_to_the_page_holding_the_form(self, _add):
        response = self.client.post(
            reverse("corpus_add_by_identifier"),
            {"identifier": "10.1000/new", "next": reverse("publication_list")},
        )
        self.assertRedirects(response, reverse("publication_list"))
        self.assertTrue(Publication.objects.filter(doi="10.1000/new").exists())

    def test_the_page_typed_by_hand_says_it_is_for_the_base_only(self):
        response = self.client.get(reverse("publication_create"))
        self.assertContains(response, "<h2>Saisir une publication à la main</h2>", html=True)
        self.assertContains(response, "commune seulement, sans bibliographie")
