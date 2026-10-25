from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Author, AuthorPublication, CitedReference, Publication
from references.services.publication_table import for_publication_table


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
        self.assertContains(response, "DOI&nbsp;10.1234/untitled")

    def test_identifier_column_falls_back_to_the_isbn(self):
        response = self.client.get(reverse("publication_list"))
        # Hidden when the content is narrow (#150).
        self.assertRegex(
            response.content.decode(),
            r'<th scope="col" class="hidden xl:table-cell">\s*<div[^>]*>\s*Identifiant',
        )
        self.assertContains(response, "ISBN&nbsp;9782070368228")

    def test_first_author_et_al(self):
        alan = Author.objects.create(first_name="Alan", last_name="Turing")
        AuthorPublication.objects.create(author=alan, publication=self.book, order=2)
        CitedReference.objects.create(source=self.book, position=1, unstructured="Exposé")
        pub = for_publication_table(Publication.objects.filter(pk=self.book.pk)).get()
        self.assertEqual((pub.first_author, pub.author_count), ("Ada Lovelace", 2))
        # The author slots do not multiply the other counts.
        self.assertEqual(pub.to_identify, 2)
        response = self.client.get(reverse("publication_list"))
        # A sortable column (#115).
        self.assertContains(response, 'href="?sort=author"')
        self.assertContains(response, "Ada Lovelace&nbsp;et&nbsp;al.")

    def test_single_author_without_et_al(self):
        pub = for_publication_table(Publication.objects.filter(pk=self.book.pk)).get()
        # Two slots of the same person: one author.
        self.assertEqual((pub.first_author, pub.author_count), ("Ada Lovelace", 1))
        self.assertNotContains(self.client.get(reverse("publication_list")), "et&nbsp;al.")

    def test_author_page_uses_the_shared_table(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("author_detail", args=[self.author.pk]))
        self.assertTemplateUsed(response, "references/_publication_table.html")
        self.assertEqual(list(response.context["publications"]), [self.book])
        # Counted once despite the two slots.
        self.assertContains(response, "1 à identifier")
        self.assertContains(response, "Ajouter à mes références")
        # Its own name on every row would say nothing.
        self.assertNotContains(response, '<th scope="col">Auteurs</th>', html=True)

    def test_author_without_publication(self):
        author = Author.objects.create(last_name="Seule")
        response = self.client.get(reverse("author_detail", args=[author.pk]))
        self.assertContains(response, "Aucune publication.")
        self.assertTemplateNotUsed(response, "references/_publication_table.html")
