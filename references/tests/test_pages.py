from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from references.models import Author, AuthorPublication, Publication, UserPublication


class PageSmokeTests(TestCase):
    """Every page renders: protects refactorings of views, URLs and templates."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("alice", password="secret")
        cls.pub = Publication.objects.create(title="Un article")
        cls.author = Author.objects.create(first_name="Ada", last_name="Lovelace")
        AuthorPublication.objects.create(publication=cls.pub, author=cls.author, order=0)
        UserPublication.objects.create(user=cls.user, publication=cls.pub)

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
                ("publication_delete", [self.pub.pk]),
                ("my_references", []),
                ("my_refs_graph", []),
            ]
        )

    def test_private_pages_redirect_anonymous_users_to_login(self):
        response = self.client.get(reverse("my_references"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('my_references')}")
