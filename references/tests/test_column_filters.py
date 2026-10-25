from datetime import date

from django.contrib.auth import get_user_model
from django.http import QueryDict
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import Author, AuthorPublication, Publication, UserPublication
from references.services import filters
from references.views.pagination import PAGE_SIZE


class ReadTests(SimpleTestCase):
    def read(self, text):
        return filters.PUBLICATIONS.read(QueryDict(text))

    def test_values(self):
        active = self.read("title=magnet&author=ada&identifier=doi&year_from=2018")
        self.assertEqual(
            active.values,
            {"title": "magnet", "author": "ada", "identifier": "doi", "year": (2018, None)},
        )

    def test_empty_and_unknown_values_are_no_filter(self):
        self.assertFalse(self.read("title=+&identifier=abc&year_from=&sort=title"))

    def test_years(self):
        self.assertEqual(self.read("year_from=2024&year_to=2018").values, {"year": (2018, 2024)})
        self.assertEqual(self.read("year_to=2020").values, {"year": (None, 2020)})
        active = self.read("year_from=vingt&year_to=2020")
        self.assertEqual(active.values, {"year": (None, 2020)})
        self.assertEqual(len(active.errors), 1)

    def test_descriptions(self):
        years = filters.PUBLICATIONS.columns["year"][1]
        self.assertEqual(years.describe((2018, 2024)), "de 2018 à 2024")
        self.assertEqual(years.describe((2020, 2020)), "2020")
        self.assertEqual(years.describe((2018, None)), "depuis 2018")
        self.assertEqual(years.describe((None, 2024)), "jusqu'à 2024")


class PublicationColumnFilterTests(TestCase):
    """Filters in the column headers, as in a spreadsheet (#115)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")
        cls.electron = Publication.objects.create(
            title="Faisceaux d'ÉLECTRONS", doi="10.1/e", publication_date=date(2020, 1, 1)
        )
        cls.book = Publication.objects.create(
            title="Un livre", isbn="9782070368228", publication_date=date(2023, 1, 1)
        )
        cls.bare = Publication.objects.create(title="Rapport interne")
        ada = Author.objects.create(first_name="Ada", last_name="Lovelace")
        AuthorPublication.objects.create(author=ada, publication=cls.book, order=0)
        for pub in (cls.electron, cls.book):
            UserPublication.objects.create(user=cls.user, publication=pub)

    def get(self, name="publication_list", **params):
        return self.client.get(reverse(name), params)

    def listed(self, name="publication_list", **params):
        return set(self.get(name, **params).context["publications"])

    def test_each_column(self):
        self.assertEqual(self.listed(title="electron"), {self.electron})
        self.assertEqual(self.listed(author="love"), {self.book})
        self.assertEqual(self.listed(identifier="doi"), {self.electron})
        self.assertEqual(self.listed(identifier="isbn"), {self.book})
        self.assertEqual(self.listed(identifier="none"), {self.bare})
        self.assertEqual(self.listed(year_from="2021"), {self.book})
        self.assertEqual(self.listed(year_to="2021"), {self.electron})

    def test_filters_combine(self):
        self.assertEqual(self.listed(title="livre", year_to="2021"), set())
        self.assertEqual(self.listed(title="livre", author="ada"), {self.book})

    def test_headers_open_their_filter(self):
        response = self.get(title="electron", sort="title")
        self.assertContains(response, 'popovertarget="filter-title"')
        self.assertContains(response, 'aria-label="Filtrer la colonne Titre (filtre actif)"')
        self.assertContains(response, 'aria-label="Filtrer la colonne Auteurs"')
        self.assertRegex(response.content.decode(), r'name="title"\s+value="electron"')
        # The form of another column keeps this filter and the sort.
        self.assertContains(response, '<input type="hidden" name="title" value="electron">')
        self.assertContains(response, '<input type="hidden" name="sort" value="title">')

    def test_summary_removes_one_filter(self):
        response = self.get(title="electron", year_from="2018", sort="title", page="1")
        self.assertContains(response, "Titre contient « electron »")
        self.assertContains(response, "Année depuis 2018")
        self.assertContains(response, 'href="?year_from=2018&amp;sort=title"')
        self.assertContains(response, 'href="?sort=title">Retirer tous les filtres')

    def test_nothing_matches_keeps_the_table(self):
        response = self.get(title="absent")
        self.assertContains(response, "Aucune publication ne correspond aux filtres.")
        self.assertContains(response, 'popovertarget="filter-title"')

    def test_wrong_year_is_explained(self):
        self.assertContains(self.get(year_from="vingt"), "pas une année (quatre chiffres)")

    def test_sort_and_pages_keep_the_filters(self):
        Publication.objects.bulk_create(
            Publication(title=f"Électron {i}") for i in range(PAGE_SIZE)
        )
        response = self.get(title="electron")
        self.assertContains(response, 'href="?title=electron&amp;page=2" rel="next"')
        self.assertContains(response, 'href="?title=electron&amp;sort=title"')

    def test_corpus(self):
        self.client.force_login(self.user)
        self.assertEqual(self.listed("corpus", identifier="isbn"), {self.book})
        self.assertContains(self.get("corpus", identifier="isbn"), "(1 sur 2)")
        self.assertContains(self.get("corpus"), "(2)")

    def test_search_and_author_pages_have_no_filters(self):
        self.assertNotContains(self.get("search", q="livre"), "popovertarget")
        author = Author.objects.get(last_name="Lovelace")
        response = self.client.get(reverse("author_detail", args=[author.pk]))
        self.assertNotContains(response, "popovertarget")


class AuthorColumnFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.helene = Author.objects.create(
            first_name="Hélène", last_name="Félice", orcid="0000-0002-1825-0097"
        )
        cls.ada = Author.objects.create(first_name="Ada", last_name="Lovelace")

    def listed(self, **params):
        return set(self.client.get(reverse("author_list"), params).context["authors"])

    def test_columns(self):
        self.assertEqual(self.listed(last_name="felice"), {self.helene})
        self.assertEqual(self.listed(first_name="ADA"), {self.ada})
        self.assertEqual(self.listed(orcid="with"), {self.helene})
        self.assertEqual(self.listed(orcid="without"), {self.ada})

    def test_nothing_matches(self):
        response = self.client.get(reverse("author_list"), {"last_name": "absent"})
        self.assertContains(response, "Aucun auteur ne correspond aux filtres.")
