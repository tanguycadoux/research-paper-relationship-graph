from django.test import TestCase
from django.urls import reverse

from references.models import Author, AuthorPublication, Publication

NOTE = "Ordre des auteurs incertain"


class JacowAuthorOrderTests(TestCase):
    """DataCite's order of the authors of JACoW papers may differ from the article's (#250)."""

    def publication(self, doi, authors=2):
        pub = Publication.objects.create(doi=doi, title="NEWGAIN")
        for order in range(authors):
            author = Author.objects.create(last_name=f"Auteur {order}")
            AuthorPublication.objects.create(publication=pub, author=author, order=order)
        return self.client.get(reverse("publication_detail", args=[pub.pk]))

    def test_jacow_paper_says_so_and_links_its_page(self):
        response = self.publication("10.18429/jacow-ipac2023-tupa193")
        self.assertContains(response, NOTE)
        self.assertContains(response, "https://doi.org/10.18429/jacow-ipac2023-tupa193")

    def test_nothing_for_a_single_author_or_another_doi(self):
        self.assertNotContains(self.publication("10.18429/jacow-ipac2023-mopa001", 1), NOTE)
        self.assertNotContains(self.publication("10.1103/physrevab.1.1"), NOTE)
