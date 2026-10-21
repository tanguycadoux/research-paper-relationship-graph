from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import (
    Author,
    AuthorPublication,
    CitedReference,
    Publication,
    UserPublication,
)
from references.tests.helpers import with_crossref


class PageSmokeTests(TestCase):
    """Every page renders: protects refactorings of views, URLs and templates."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")
        cls.pub = Publication.objects.create(title="Un article")
        cls.author = Author.objects.create(first_name="Ada", last_name="Lovelace")
        AuthorPublication.objects.create(publication=cls.pub, author=cls.author, order=0)
        UserPublication.objects.create(user=cls.user, publication=cls.pub)
        cited = Publication.objects.create(title="Article cité")
        CitedReference.objects.create(source=cls.pub, target=cited, position=0)
        CitedReference.objects.create(
            source=cls.pub, position=1, unstructured="Smith J. Some book. 1999."
        )

    def assert_pages_render(self, names):
        for name, args in names:
            with self.subTest(page=name):
                response = self.client.get(reverse(name, args=args))
                self.assertEqual(response.status_code, 200)

    def test_public_pages(self):
        self.assert_pages_render(
            [
                ("index", []),
                ("publications_list", []),
                ("publication_detail", [self.pub.pk]),
                ("publication_graph", [self.pub.pk]),
                ("authors_list", []),
                ("author_detail", [self.author.pk]),
                ("login", []),
                ("register", []),
            ]
        )

    def test_pages_for_logged_in_user(self):
        self.client.force_login(self.user)
        self.assert_pages_render(
            [
                ("publication_add", []),
                ("publication_edit", [self.pub.pk]),
                ("my_references", []),
                ("my_refs_graph", []),
            ]
        )

    def test_private_pages_redirect_anonymous_users_to_login(self):
        response = self.client.get(reverse("my_references"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('my_references')}")

    def test_detail_lists_resolved_and_unresolved_references(self):
        response = self.client.get(reverse("publication_detail", args=[self.pub.pk]))
        self.assertContains(response, "Article cité")
        self.assertContains(response, "Smith J. Some book. 1999.")

    def test_metadata_page_lists_the_records_of_each_source(self):
        with_crossref(self.pub, {"message": {"title": ["Un article"]}})
        self.client.force_login(self.user)
        data = self.client.get(reverse("publication_metadata", args=[self.pub.pk])).json()
        self.assertEqual(data["crossref"]["data"], {"message": {"title": ["Un article"]}})
