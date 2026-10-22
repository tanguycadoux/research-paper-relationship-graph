from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Author, AuthorPublication, CitedReference, Publication


class PublicationTablesTests(TestCase):
    """Every publication listed, with its DOI or ISBN; the author page shares the table (#128)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")
        cls.untitled = Publication.objects.create(doi="10.1234/untitled")
        cls.book = Publication.objects.create(title="Un livre", isbn="9782070368228")
        cls.author = Author.objects.create(first_name="Ada", last_name="Lovelace")
        # Two slots of the same publication, as after a merge of coauthors.
        for order in (0, 1):
            AuthorPublication.objects.create(author=cls.author, publication=cls.book, order=order)
        CitedReference.objects.create(source=cls.book, position=0, unstructured="Rapport interne")

    def test_list_shows_publications_without_title(self):
        response = self.client.get(reverse("publication_list"))
        self.assertIn(self.untitled, response.context["publications"])
        self.assertContains(response, "10.1234/untitled")

    def test_identifier_column_falls_back_to_the_isbn(self):
        response = self.client.get(reverse("publication_list"))
        self.assertContains(response, '<th scope="col">Identifiant</th>', html=True)
        self.assertContains(response, "ISBN 9782070368228")

    def test_author_page_uses_the_shared_table(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("author_detail", args=[self.author.pk]))
        self.assertTemplateUsed(response, "references/_publication_table.html")
        self.assertEqual(list(response.context["publications"]), [self.book])
        # Counted once despite the two slots.
        self.assertContains(response, "1 à identifier")
        self.assertContains(response, "Ajouter à mes références")

    def test_author_without_publication(self):
        author = Author.objects.create(last_name="Seule")
        response = self.client.get(reverse("author_detail", args=[author.pk]))
        self.assertContains(response, "Aucune publication.")
        self.assertTemplateNotUsed(response, "references/_publication_table.html")
