from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from references.models import Publication, UserPublication


# Both return the publication imported.
@patch("references.views.publications.import_publication", side_effect=lambda pub, **_: pub)
@patch("references.views.corpus.add_identified", side_effect=lambda user, pub, status="": pub)
class StateChangingActionsTests(TestCase):
    """Actions that change the database answer only to POST (#19)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")
        cls.pub = Publication.objects.create(title="Un article")

    def setUp(self):
        self.client.force_login(self.user)

    def actions(self):
        return [
            reverse(name, args=[self.pub.pk])
            for name in (
                "corpus_add",
                "corpus_remove",
                "corpus_reading_status",
                "publication_refresh",
            )
        ]

    def test_get_is_refused(self, add_to_corpus, import_publication):
        UserPublication.objects.create(user=self.user, publication=self.pub)
        for url in self.actions():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)
        add_to_corpus.assert_not_called()
        import_publication.assert_not_called()
        self.assertTrue(UserPublication.objects.filter(user=self.user).exists())

    def test_add_returns_to_the_publication(self, add_to_corpus, import_publication):
        response = self.client.post(reverse("corpus_add", args=[self.pub.pk]))
        self.assertRedirects(response, reverse("publication_detail", args=[self.pub.pk]))
        add_to_corpus.assert_called_once_with(self.user, self.pub, "")

    def test_remove_returns_to_the_page_holding_the_button(self, add_to_corpus, import_publication):
        UserPublication.objects.create(user=self.user, publication=self.pub)
        response = self.client.post(
            reverse("corpus_remove", args=[self.pub.pk]),
            {"next": reverse("publication_list")},
        )
        self.assertRedirects(response, reverse("publication_list"))
        self.assertFalse(UserPublication.objects.filter(user=self.user).exists())

    def test_external_next_url_is_ignored(self, add_to_corpus, import_publication):
        response = self.client.post(
            reverse("corpus_add", args=[self.pub.pk]),
            {"next": "https://example.org/"},
        )
        self.assertRedirects(response, reverse("publication_detail", args=[self.pub.pk]))

    def test_refresh_imports_again(self, add_to_corpus, import_publication):
        self.client.post(reverse("publication_refresh", args=[self.pub.pk]))
        import_publication.assert_called_once()

    def test_pages_hold_forms_instead_of_links(self, add_to_corpus, import_publication):
        add_url = reverse("corpus_add", args=[self.pub.pk])
        for name, args in (("publication_detail", [self.pub.pk]), ("publication_list", [])):
            with self.subTest(page=name):
                response = self.client.get(reverse(name, args=args))
                self.assertContains(response, f'action="{add_url}"')
                self.assertContains(response, 'method="post"')
                self.assertNotContains(response, f'href="{add_url}"')


class PublicationDeletionTests(TestCase):
    """Publications are shared: only administrators delete them, from the admin site (#77)."""

    def test_no_deletion_page(self):
        with self.assertRaises(NoReverseMatch):
            reverse("publication_delete", args=[1])

    def test_detail_has_no_delete_button(self):
        pub = Publication.objects.create(title="Un article")
        self.client.force_login(get_user_model().objects.create_user("alice"))
        response = self.client.get(reverse("publication_detail", args=[pub.pk]))
        self.assertNotContains(response, "Supprimer")
