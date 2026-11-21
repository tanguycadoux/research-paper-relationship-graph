from django.conf import settings
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
                ("publication_list", []),
                ("publication_detail", [self.pub.pk]),
                ("publication_graph", [self.pub.pk]),
                ("author_list", []),
                ("author_detail", [self.author.pk]),
                ("login", []),
                ("register", []),
            ]
        )

    def test_every_page_declares_the_site_icon(self):
        # Without it, browsers ask for /favicon.ico, a 404 on each first visit (#347).
        response = self.client.get(reverse("index"))
        self.assertContains(response, 'rel="icon" type="image/svg+xml" href="/static/favicon.svg"')
        self.assertTrue((settings.BASE_DIR / "static" / "favicon.svg").is_file())

    def test_every_page_loads_the_busy_buttons(self):
        # #339: a form sent to the sources disables its buttons and shows a spinner.
        response = self.client.get(reverse("index"))
        self.assertContains(response, 'src="/static/js/busy.js" defer')
        script = (settings.BASE_DIR / "static" / "js" / "busy.js").read_text()
        self.assertIn('form.method.toLowerCase() !== "post"', script)
        self.assertIn("setTimeout", script)  # after the clicked button's value is read

    def test_pages_for_logged_in_user(self):
        self.client.force_login(self.user)
        self.assert_pages_render(
            [
                ("publication_create", []),
                ("publication_edit", [self.pub.pk]),
                ("corpus", []),
                ("corpus_graph", []),
            ]
        )

    def test_private_pages_redirect_anonymous_users_to_login(self):
        response = self.client.get(reverse("corpus"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('corpus')}")

    def test_detail_lists_resolved_and_unresolved_references(self):
        response = self.client.get(reverse("publication_detail", args=[self.pub.pk]))
        self.assertContains(response, "Article cité")
        self.assertContains(response, "Smith J. Some book. 1999.")

    def test_metadata_page_lists_the_records_of_each_source(self):
        with_crossref(self.pub, {"message": {"title": ["Un article"]}})
        self.client.force_login(self.user)
        url = reverse("publication_metadata", args=[self.pub.pk])
        data = self.client.get(url, {"format": "json"}).json()
        self.assertEqual(data["crossref"]["data"], {"message": {"title": ["Un article"]}})
        # The page shows it indented, wrapped to its width (#413).
        response = self.client.get(url)
        self.assertContains(response, "<h1>Métadonnées brutes</h1>", html=True)
        self.assertContains(response, "whitespace-pre-wrap wrap-anywhere")
        self.assertContains(
            response, "\n      &quot;title&quot;: [\n        &quot;Un article&quot;"
        )
        self.assertContains(response, f'href="{url}?format=json"')
