from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Author, AuthorPublication, Publication, UserPublication
from references.views.pagination import PAGE_SIZE


class PublicationFilterTests(TestCase):
    """The lists filtered with the syntax of the search (#115)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")
        cls.electron = Publication.objects.create(
            title="Faisceaux d'électrons", publication_date=date(2020, 1, 1)
        )
        cls.magnet = Publication.objects.create(title="Magnet", publication_date=date(2023, 1, 1))
        ada = Author.objects.create(first_name="Ada", last_name="Lovelace")
        AuthorPublication.objects.create(author=ada, publication=cls.magnet, order=0)
        UserPublication.objects.create(user=cls.user, publication=cls.electron)
        UserPublication.objects.create(user=cls.user, publication=cls.magnet)

    def get(self, name="publication_list", **params):
        return self.client.get(reverse(name), params)

    def test_filter(self):
        response = self.get(q="ELECTRON")
        self.assertEqual(list(response.context["publications"]), [self.electron])
        self.assertContains(response, 'id="list-filter"')
        self.assertContains(response, 'value="ELECTRON"')
        self.assertEqual(list(self.get(q="auteur:lovelace").context["publications"]), [self.magnet])
        self.assertEqual(list(self.get(q="année:..2021").context["publications"]), [self.electron])

    def test_nothing_matches(self):
        response = self.get(q="absent")
        self.assertContains(response, "Aucune publication ne correspond à ce filtre.")
        # The bar stays, to change the filter.
        self.assertContains(response, 'id="list-filter"')

    def test_sort_is_kept_and_clear_drops_the_filter_only(self):
        response = self.get(q="a", sort="title")
        self.assertContains(response, '<input type="hidden" name="sort" value="title">')
        self.assertContains(response, 'href="?sort=title"')  # Effacer le filtre
        self.assertContains(response, 'href="?q=a&amp;sort=-title"')  # Column header

    def test_default_sort_is_not_repeated(self):
        response = self.get(q="a")
        self.assertNotContains(response, 'type="hidden" name="sort"')
        self.assertContains(response, 'href="/publications/"')  # Effacer le filtre

    def test_wrong_years_are_explained(self):
        self.assertContains(self.get(q="année:vingt"), "écrire 2020, 2020..2024")

    def test_pages_keep_the_filter(self):
        Publication.objects.bulk_create(
            Publication(title=f"Électron {i}") for i in range(PAGE_SIZE)
        )
        self.assertContains(self.get(q="electron"), 'href="?q=electron&amp;page=2" rel="next"')

    def test_corpus(self):
        self.client.force_login(self.user)
        Publication.objects.create(title="Électron hors corpus")
        response = self.get("corpus", q="electron")
        self.assertEqual(list(response.context["publications"]), [self.electron])
        self.assertContains(response, "(1 sur 2)")
        self.assertContains(self.get("corpus"), "(2)")

    def test_no_bar_on_an_empty_list(self):
        Publication.objects.all().delete()
        self.assertNotContains(self.get(), 'id="list-filter"')


class AuthorFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.helene = Author.objects.create(
            first_name="Hélène", last_name="Félice", orcid="0000-0002-1825-0097"
        )
        cls.ada = Author.objects.create(first_name="Ada", last_name="Lovelace")

    def get(self, **params):
        return self.client.get(reverse("author_list"), params)

    def test_name_or_orcid(self):
        self.assertEqual(list(self.get(q="helene").context["authors"]), [self.helene])
        self.assertEqual(list(self.get(q="0000-0002-1825-0097").context["authors"]), [self.helene])
        self.assertContains(self.get(q="absent"), "Aucun auteur ne correspond à ce filtre.")

    def test_publication_operators_are_explained(self):
        response = self.get(q="titre:magnet")
        self.assertContains(response, "ne filtrent que des publications")
        self.assertEqual(len(response.context["authors"]), 2)
