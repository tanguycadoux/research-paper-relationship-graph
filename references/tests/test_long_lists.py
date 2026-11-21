from django.test import TestCase
from django.urls import reverse

from references.models import (
    Author,
    AuthorPublication,
    CitedReference,
    Organization,
    Publication,
)
from references.services.display.publication_page import AUTHORS_SHOWN, REFERENCES_SHOWN


class LongListsTests(TestCase):
    """A publication with 1 012 authors or 247 references stays readable (#269)."""

    @classmethod
    def setUpTestData(cls):
        cls.pub = Publication.objects.create(title="Collaboration")
        cls.lab = Organization.objects.create(name="Labo du premier")
        cls.far = Organization.objects.create(name="Labo du trentième")
        for order in range(30):
            author = Author.objects.create(first_name="P", last_name=f"Auteur{order:02d}")
            slot = AuthorPublication.objects.create(publication=cls.pub, author=author, order=order)
            slot.organizations.add(cls.lab if order == 0 else cls.far if order == 25 else cls.lab)
        CitedReference.objects.bulk_create(
            CitedReference(source=cls.pub, position=i, unstructured=f"Réf {i}")
            for i in range(REFERENCES_SHOWN + 7)
        )

    def detail(self, **params):
        return self.client.get(reverse("publication_detail", args=[self.pub.pk]), params)

    def test_the_first_authors_and_the_last(self):
        response = self.detail()
        names = [a["slot"].author.last_name for a in response.context["authors"]["authors"]]
        self.assertEqual(len(names), AUTHORS_SHOWN + 1)
        self.assertEqual(names[-1], "Auteur29")
        self.assertContains(response, "… et 9 autres,")
        self.assertContains(response, "Afficher les 30 auteurs et leurs affiliations")
        # Only the affiliations of the authors shown.
        self.assertNotContains(response, "Labo du trentième")

    def test_all_the_authors_on_demand(self):
        response = self.detail(auteurs="tous")
        self.assertEqual(len(response.context["authors"]["authors"]), 30)
        self.assertContains(response, "Labo du trentième")
        self.assertNotContains(response, "autres,")

    def test_the_first_references(self):
        response = self.detail()
        self.assertEqual(len(response.context["shown_references"]), REFERENCES_SHOWN)
        self.assertContains(response, f"Afficher les {REFERENCES_SHOWN + 7} références")
        # The counts still cover the whole bibliography.
        self.assertEqual(response.context["references_to_identify"], REFERENCES_SHOWN + 7)

    def test_all_the_references_on_demand(self):
        response = self.detail(references="toutes")
        self.assertEqual(len(response.context["shown_references"]), REFERENCES_SHOWN + 7)

    def test_short_lists_are_whole(self):
        short = Publication.objects.create(title="Courte")
        response = self.client.get(reverse("publication_detail", args=[short.pk]))
        self.assertEqual(response.context["authors_hidden"], 0)
        self.assertEqual(response.context["references_hidden"], 0)
