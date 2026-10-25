from datetime import date

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import Author, AuthorPublication, Publication, UserPublication
from references.services.sorting import AUTHORS, PUBLICATIONS, Sort


class SortingTests(SimpleTestCase):
    def test_read(self):
        self.assertEqual(PUBLICATIONS.read("title"), Sort("title", False))
        self.assertEqual(PUBLICATIONS.read("-title"), Sort("title", True))
        # Nothing, or no such column: the default sort.
        for value in (None, "", "-", "pk", "-doi"):
            with self.subTest(value=value):
                self.assertEqual(PUBLICATIONS.read(value), Sort("year", True))

    def test_a_click_reverses_the_sorted_column(self):
        self.assertEqual(PUBLICATIONS.next_sort(Sort("year", True), "year"), Sort("year", False))
        self.assertEqual(PUBLICATIONS.next_sort(Sort("year", False), "year"), Sort("year", True))

    def test_a_click_on_another_column_starts_with_its_first_direction(self):
        self.assertEqual(PUBLICATIONS.next_sort(Sort("year", True), "title"), Sort("title", False))
        self.assertEqual(PUBLICATIONS.next_sort(Sort("title", False), "year"), Sort("year", True))


class PublicationSortTests(TestCase):
    """Server side, before the pagination, in the URL (#115)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")
        cls.eclair = Publication.objects.create(title="Éclair", publication_date=date(2021, 1, 1))
        cls.dune = Publication.objects.create(title="dune", publication_date=date(2023, 1, 1))
        cls.faisceau = Publication.objects.create(title="Faisceau")
        for pub, author in (
            (cls.eclair, Author.objects.create(first_name="Zoé", last_name="Ångström")),
            (cls.dune, Author.objects.create(first_name="Ada", last_name="Lovelace")),
        ):
            AuthorPublication.objects.create(author=author, publication=pub, order=0)
        for pub in (cls.eclair, cls.dune, cls.faisceau):
            UserPublication.objects.create(user=cls.user, publication=pub)

    def listed(self, url_name="publication_list", **params):
        return list(self.client.get(reverse(url_name), params).context["publications"])

    def test_default_is_the_most_recent_first_undated_last(self):
        self.assertEqual(self.listed(), [self.dune, self.eclair, self.faisceau])

    def test_years_from_the_oldest_undated_still_last(self):
        self.assertEqual(self.listed(sort="year"), [self.eclair, self.dune, self.faisceau])

    def test_titles_ignore_case_and_accents(self):
        self.assertEqual(self.listed(sort="title"), [self.dune, self.eclair, self.faisceau])
        self.assertEqual(self.listed(sort="-title"), [self.faisceau, self.eclair, self.dune])

    def test_first_author_by_family_name_without_author_last(self):
        self.assertEqual(self.listed(sort="author"), [self.eclair, self.dune, self.faisceau])
        self.assertEqual(self.listed(sort="-author"), [self.dune, self.eclair, self.faisceau])

    def test_corpus_and_search_are_sorted_too(self):
        self.client.force_login(self.user)
        self.assertEqual(
            self.listed("corpus", sort="title"), [self.dune, self.eclair, self.faisceau]
        )
        self.assertEqual(
            self.listed("search", q="année:2020..", sort="title"), [self.dune, self.eclair]
        )

    def test_headers(self):
        response = self.client.get(reverse("publication_list"), {"page": "1"})
        # Sorted by year, newest first: a click reverses it; the page starts over.
        self.assertRegex(
            response.content.decode(),
            r'<th scope="col" aria-sort="descending">\s*<a href="\?sort=year"',
        )
        self.assertContains(response, 'href="?sort=title"')
        self.assertContains(response, 'href="?sort=author"')
        self.assertContains(response, '<th scope="col" class="hidden xl:table-cell">Identifiant')

    def test_headers_keep_the_search(self):
        response = self.client.get(reverse("search"), {"q": "dune", "sort": "title"})
        self.assertContains(response, 'aria-sort="ascending"')
        self.assertContains(response, 'href="?q=dune&amp;sort=-title"')

    def test_tables_without_sorting_keep_plain_headers(self):
        author = Author.objects.get(last_name="Lovelace")
        response = self.client.get(reverse("author_detail", args=[author.pk]))
        self.assertContains(response, '<th scope="col">Titre</th>', html=True)
        self.assertNotContains(response, "?sort=")


class AuthorSortTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.zoe = Author.objects.create(first_name="Zoé", last_name="Émery")
        cls.ada = Author.objects.create(first_name="Ada", last_name="Lovelace")

    def listed(self, **params):
        return list(self.client.get(reverse("author_list"), params).context["authors"])

    def test_family_names_ignore_accents(self):
        self.assertEqual(self.listed(), [self.zoe, self.ada])

    def test_given_names(self):
        self.assertEqual(self.listed(sort="first_name"), [self.ada, self.zoe])
        response = self.client.get(reverse("author_list"), {"sort": "first_name"})
        self.assertContains(response, 'aria-sort="ascending"')
        self.assertContains(response, 'href="?sort=-first_name"')
        self.assertEqual(AUTHORS.read("orcid"), AUTHORS.default)
