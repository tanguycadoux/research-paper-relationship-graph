from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, Publication, UserPublication
from references.services.identification import with_references_to_identify


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
        self.assertContains(response, 'class="bg-amber-50"', count=2)

    def test_summary_when_everything_is_linked(self):
        response = self.client.get(reverse("publication_detail", args=[self.cited.pk]))
        self.assertNotContains(response, "à identifier :")
