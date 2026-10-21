from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, Publication, UserPublication


class CitedByTests(TestCase):
    """The detail page lists the publications of the base that cite it (#93)."""

    @classmethod
    def setUpTestData(cls):
        cls.cited = Publication.objects.create(title="Article cité")
        cls.old = Publication.objects.create(
            title="Ancien citant", publication_date=date(2001, 1, 1)
        )
        cls.new = Publication.objects.create(
            title="Récent citant", publication_date=date(2024, 1, 1)
        )
        for position, source in enumerate((cls.old, cls.new, cls.new)):
            CitedReference.objects.create(source=source, target=cls.cited, position=position)

    def get(self, pub):
        return self.client.get(reverse("publication_detail", args=[pub.pk]))

    def test_citing_publications_newest_first_without_duplicates(self):
        citing = list(self.get(self.cited).context["citing_publications"])
        self.assertEqual(citing, [self.new, self.old])

    def test_section_says_the_list_is_not_exhaustive(self):
        response = self.get(self.cited)
        self.assertContains(response, "Cité par")
        self.assertContains(response, "la liste n'est pas")

    def test_publication_cited_by_nobody(self):
        self.assertContains(self.get(self.old), "Aucune publication de la base ne la cite.")

    def test_citing_publications_can_be_added_to_my_corpus(self):
        user = get_user_model().objects.create_user("alice")
        UserPublication.objects.create(user=user, publication=self.new)
        self.client.force_login(user)
        response = self.get(self.cited)
        self.assertContains(response, reverse("corpus_remove", args=[self.new.pk]))
        self.assertContains(response, reverse("corpus_add", args=[self.old.pk]))
