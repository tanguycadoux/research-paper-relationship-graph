from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Author, CitedReference, Publication, UserPublication


class AccessTests(TestCase):
    """Anonymous visitors read the shared knowledge base; everything else needs a login."""

    @classmethod
    def setUpTestData(cls):
        cls.pub = Publication.objects.create(title="Un article")
        CitedReference.objects.create(source=cls.pub, position=0, unstructured="Smith J. 1999.")
        cls.author = Author.objects.create(first_name="Ada", last_name="Lovelace")
        cls.other_author = Author.objects.create(first_name="A.", last_name="Lovelace")

    def assert_redirects_to_login(self, response, url):
        self.assertRedirects(
            response, f"{reverse('login')}?next={url}", fetch_redirect_response=False
        )

    def test_private_pages_redirect_to_login(self):
        pages = [
            ("publication_create", []),
            ("publication_edit", [self.pub.pk]),
            ("publication_metadata", [self.pub.pk]),
            ("publication_merge", [self.pub.pk]),
            ("reference_identify", [self.pub.pk, 0]),
            ("author_edit", [self.author.pk]),
            ("author_merge_select", []),
            ("author_merge_confirm", [f"{self.author.pk},{self.other_author.pk}"]),
            ("author_duplicates", []),
            ("conflict_list", []),
            ("corpus", []),
            ("corpus_graph", []),
        ]
        for name, args in pages:
            with self.subTest(page=name):
                url = reverse(name, args=args)
                self.assert_redirects_to_login(self.client.get(url), url)

    def test_actions_redirect_to_login_without_changing_anything(self):
        actions = [
            ("corpus_add", [self.pub.pk], {}),
            ("corpus_remove", [self.pub.pk], {}),
            ("corpus_add_by_doi", [], {"doi": "10.1000/new"}),
            ("publication_refresh", [self.pub.pk], {}),
            ("conflict_resolve", [1], {}),
            ("author_duplicates_dismiss", [], {}),
        ]
        for name, args, data in actions:
            with self.subTest(action=name):
                url = reverse(name, args=args)
                self.assert_redirects_to_login(self.client.post(url, data), url)
        self.assertEqual(Publication.objects.count(), 1)
        self.assertFalse(UserPublication.objects.exists())

    def test_unknown_objects_give_404(self):
        for name in ("publication_detail", "publication_graph", "author_detail"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name, args=[999])).status_code, 404)


class CorpusIsolationTests(TestCase):
    """Each user sees only their own corpus."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice")
        bob = User.objects.create_user("bob")
        cls.mine = Publication.objects.create(title="Article d'Alice")
        cls.theirs = Publication.objects.create(title="Article de Bob")
        UserPublication.objects.create(user=cls.alice, publication=cls.mine)
        UserPublication.objects.create(user=bob, publication=cls.theirs)

    def setUp(self):
        self.client.force_login(self.alice)

    def test_my_references_lists_only_my_publications(self):
        response = self.client.get(reverse("corpus"))
        self.assertEqual(list(response.context["publications"]), [self.mine])

    def test_my_references_are_sorted_by_year_newest_first(self):
        UserPublication.objects.create(
            user=self.alice,
            publication=Publication.objects.create(
                title="Récent", publication_date=date(2024, 1, 1)
            ),
        )
        UserPublication.objects.create(
            user=self.alice,
            publication=Publication.objects.create(
                title="Ancien", publication_date=date(1999, 1, 1)
            ),
        )
        response = self.client.get(reverse("corpus"))
        titles = [pub.title for pub in response.context["publications"]]
        self.assertEqual(titles, ["Récent", "Ancien", "Article d'Alice"])

    def test_my_graph_holds_only_my_corpus(self):
        response = self.client.get(reverse("corpus_graph"))
        node_ids = [node["data"]["id"] for node in response.context["graph"]["nodes"]]
        self.assertEqual(node_ids, [str(self.mine.pk)])

    def test_removing_does_not_touch_the_corpus_of_others(self):
        UserPublication.objects.create(user=self.alice, publication=self.theirs)
        self.client.post(reverse("corpus_remove", args=[self.theirs.pk]))
        self.assertEqual(self.theirs.userpublication_set.get().user.username, "bob")


class EditionTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("alice"))

    def test_publication_edition_saves_the_fields(self):
        pub = Publication.objects.create(title="Titre provisoire")
        response = self.client.post(
            reverse("publication_edit", args=[pub.pk]),
            {"title": "Titre corrigé", "publication_date": "2026-08-01"},
        )
        self.assertRedirects(response, reverse("publication_list"))
        pub.refresh_from_db()
        self.assertEqual((pub.title, pub.publication_date), ("Titre corrigé", date(2026, 8, 1)))


class RegistrationTests(TestCase):
    def test_registration_creates_the_account_then_asks_to_log_in(self):
        password = "un-mot-de-passe-solide-42"
        response = self.client.post(
            reverse("register"),
            {"username": "alice", "password1": password, "password2": password},
        )
        self.assertRedirects(response, reverse("login"))
        self.assertTrue(get_user_model().objects.get(username="alice").check_password(password))
