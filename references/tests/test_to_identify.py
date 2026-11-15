from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, Publication, UserPublication
from references.services.corrections.identification import with_references_to_identify
from references.templatetags.ui import BUTTON_VARIANTS


class ReferencesToIdentifyTests(TestCase):
    """Publications with cited references linked to nothing stand out (#95)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")
        cls.cited = Publication.objects.create(title="Article cité")
        cls.pub = Publication.objects.create(title="Article à trier")
        CitedReference.objects.create(source=cls.pub, target=cls.cited, position=0)
        for position in (1, 2):
            CitedReference.objects.create(source=cls.pub, position=position, unstructured="?")
        UserPublication.objects.create(user=cls.user, publication=cls.pub)

    def test_annotation_counts_only_unresolved_references(self):
        counts = dict(
            with_references_to_identify(Publication.objects).values_list("title", "to_identify")
        )
        self.assertEqual(counts, {"Article à trier": 2, "Article cité": 0})

    def test_badge_in_the_tables(self):
        self.client.force_login(self.user)
        for name in ("publication_list", "corpus"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertContains(response, "2 à identifier")
                self.assertNotContains(response, "0 à identifier")

    def test_badge_in_cited_by(self):
        CitedReference.objects.create(source=self.pub, target=self.pub, position=3)
        response = self.client.get(reverse("publication_detail", args=[self.pub.pk]))
        self.assertEqual(response.context["citing_publications"][0].to_identify, 2)

    def test_summary_on_the_detail_page(self):
        response = self.client.get(reverse("publication_detail", args=[self.pub.pk]))
        self.assertEqual(response.context["references_to_identify"], 2)
        self.assertContains(response, "2 références sur 3")
        self.assertContains(response, "ne sont reliées")
        self.assertContains(response, "border-amber-400", count=2)

    def test_one_full_button_and_amber_row_buttons(self):
        # #282: « Identifier les 2 références en série »; the rows to identify an amber icon
        # button, as their line and badge (#384), the others a secondary one.
        self.client.force_login(get_user_model().objects.create_user("zoe"))
        response = self.client.get(reverse("publication_detail", args=[self.pub.pk]))
        self.assertContains(response, "Identifier les 2 références en série")
        self.assertContains(response, BUTTON_VARIANTS["warning-light"], count=2)

    def test_corpus_actions_on_identified_references(self):
        # #385: the buttons of the publication tables, for a reference that has a target.
        zoe = get_user_model().objects.create_user("zoe")
        self.client.force_login(zoe)
        url = reverse("publication_detail", args=[self.pub.pk])
        add_url = reverse("corpus_add", args=[self.cited.pk])
        response = self.client.get(url)
        self.assertContains(response, f'action="{add_url}"', count=1)
        self.assertContains(response, f'value="{url}#reference-1"')
        self.assertContains(response, "Ajouter à mon corpus, à lire")
        UserPublication.objects.create(user=zoe, publication=self.cited)
        response = self.client.get(url)
        self.assertNotContains(response, f'action="{add_url}"')
        self.assertContains(response, f'action="{reverse("corpus_remove", args=[self.cited.pk])}"')

    def test_adding_a_reference_comes_back_to_its_line(self):
        self.client.force_login(get_user_model().objects.create_user("zoe"))
        back = reverse("publication_detail", args=[self.pub.pk]) + "#reference-1"
        with patch("references.views.corpus.add_identified", return_value=self.cited):
            response = self.client.post(reverse("corpus_add", args=[self.cited.pk]), {"next": back})
        self.assertRedirects(response, back, fetch_redirect_response=False)

    def test_summary_when_everything_is_linked(self):
        response = self.client.get(reverse("publication_detail", args=[self.cited.pk]))
        self.assertNotContains(response, "à identifier :")
