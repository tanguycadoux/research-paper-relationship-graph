from datetime import date

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from references.models import Author, AuthorPublication, Publication
from references.services.search import (
    filter_publications,
    normalize,
    parse,
    search_authors,
)


class ParseTests(SimpleTestCase):
    """One bar, free text and operators (#153)."""

    def test_normalize_ignores_case_and_accents(self):
        self.assertEqual(normalize("Élodie MÜLLER"), "elodie muller")

    def test_free_text_and_operators(self):
        query = parse('magnet auteur:Felice titre:"champ magnétique" doi:10.1109')
        self.assertEqual(query.terms, ["magnet"])
        self.assertEqual(query.authors, ["Felice"])
        self.assertEqual(query.titles, ["champ magnétique"])
        self.assertEqual(query.identifiers, ["10.1109"])

    def test_operator_names_ignore_case_and_accents(self):
        for text in ("année:2020", "annee:2020", "ANNÉE:2020"):
            with self.subTest(text=text):
                self.assertEqual((parse(text).year_from, parse(text).year_to), (2020, 2020))

    def test_years(self):
        for text, years in (
            ("année:2020..2024", (2020, 2024)),
            ("année:2020..", (2020, None)),
            ("année:..2024", (None, 2024)),
            ("année:2024..2020", (2020, 2024)),
        ):
            with self.subTest(text=text):
                query = parse(text)
                self.assertEqual((query.year_from, query.year_to), years)
                self.assertEqual(query.errors, [])

    def test_wrong_years_are_reported(self):
        for text in ("année:vingt", "année:20202024", "année:.."):
            with self.subTest(text=text):
                query = parse(text)
                self.assertFalse(query.has_years)
                self.assertEqual(len(query.errors), 1)

    def test_unknown_operator_is_plain_text(self):
        self.assertEqual(parse("Re:thinking").terms, ["Re:thinking"])

    def test_unclosed_quote_is_read_as_words(self):
        self.assertEqual(parse('titre:"champ magnétique').titles, ['"champ'])

    def test_empty_query(self):
        self.assertFalse(parse(""))
        self.assertFalse(parse("auteur:"))


class SearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.electron = Publication.objects.create(
            title="Faisceaux d'ÉLECTRONS polarisés",
            doi="10.1109/TASC.2020.1",
            publication_date=date(2020, 5, 1),
        )
        cls.magnet = Publication.objects.create(
            title="Superconducting magnet design",
            isbn="9782070368228",
            publication_date=date(2023, 1, 1),
        )
        cls.ada = Author.objects.create(first_name="Ada", last_name="Lovelace")
        cls.helene = Author.objects.create(
            first_name="Hélène", last_name="Félice", orcid="0000-0002-1825-0097"
        )
        AuthorPublication.objects.create(author=cls.ada, publication=cls.electron, order=0)
        AuthorPublication.objects.create(author=cls.helene, publication=cls.electron, order=1)
        AuthorPublication.objects.create(author=cls.helene, publication=cls.magnet, order=0)

    def found(self, text):
        return set(filter_publications(Publication.objects.all(), parse(text)))

    def test_free_text_ignores_case_and_accents(self):
        self.assertEqual(self.found("electrons"), {self.electron})
        self.assertEqual(self.found("élec POLARISÉS"), {self.electron})

    def test_free_text_looks_in_authors_and_identifiers(self):
        self.assertEqual(self.found("felice"), {self.electron, self.magnet})
        self.assertEqual(self.found("10.1109/tasc"), {self.electron})
        self.assertEqual(self.found("978-2-07-036822-8"), {self.magnet})

    def test_author_words_belong_to_one_author(self):
        self.assertEqual(self.found('auteur:"ada love"'), {self.electron})
        # Ada on one slot, Félice on another: no author holds both names.
        self.assertEqual(self.found('auteur:"ada felice"'), set())
        self.assertEqual(self.found("auteur:ada auteur:felice"), {self.electron})

    def test_title_is_a_phrase(self):
        self.assertEqual(self.found('titre:"magnet design"'), {self.magnet})
        self.assertEqual(self.found('titre:"design magnet"'), set())

    def test_years(self):
        self.assertEqual(self.found("année:2021.."), {self.magnet})
        self.assertEqual(self.found("année:..2020"), {self.electron})
        self.assertEqual(self.found("année:2020"), {self.electron})

    def test_identifiers(self):
        self.assertEqual(self.found("doi:10.1109"), {self.electron})
        self.assertEqual(self.found("isbn:9782070368228"), {self.magnet})

    def test_authors(self):
        self.assertEqual(set(search_authors(parse("helene"))), {self.helene})
        self.assertEqual(set(search_authors(parse("0000-0002-1825-0097"))), {self.helene})
        self.assertEqual(set(search_authors(parse('auteur:"ada lovelace"'))), {self.ada})
        # A title or a year asks about publications only.
        self.assertFalse(search_authors(parse("felice année:2020")).exists())


class SearchPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pub = Publication.objects.create(title="Électron", publication_date=date(2020, 1, 1))
        cls.author = Author.objects.create(first_name="Ada", last_name="Lovelace")
        AuthorPublication.objects.create(author=cls.author, publication=cls.pub, order=0)

    def search(self, text):
        return self.client.get(reverse("search"), {"q": text})

    def test_results(self):
        response = self.search("lovelace")
        self.assertEqual(list(response.context["publications"]), [self.pub])
        self.assertEqual(list(response.context["authors"]), [self.author])
        self.assertTemplateUsed(response, "references/_publication_table.html")
        self.assertContains(response, 'value="lovelace"')

    def test_nothing_found(self):
        self.assertContains(self.search("absent"), "Aucune publication ne correspond")

    def test_without_query_only_the_bar(self):
        response = self.client.get(reverse("search"))
        self.assertNotIn("publications", response.context)
        self.assertContains(response, 'id="search-q"')

    def test_wrong_years_are_explained(self):
        self.assertContains(self.search("année:vingt"), "écrire 2020, 2020..2024")

    def test_queries_do_not_depend_on_the_number_of_results(self):
        def queries():
            with CaptureQueriesContext(connection) as captured:
                self.search("électron")
            return len(captured)

        before = queries()
        for i in range(5):
            pub = Publication.objects.create(title=f"Électron {i}")
            AuthorPublication.objects.create(author=self.author, publication=pub, order=0)
        self.assertEqual(queries(), before)

    def test_bar_in_the_header_of_other_pages(self):
        response = self.client.get(reverse("publication_list"))
        self.assertContains(response, 'id="site-search"')
        self.assertContains(response, 'aria-keyshortcuts="Control+K Meta+K"')
        self.assertContains(response, "js/search.js")

    def test_pages_with_their_own_bar_have_none_in_the_header(self):
        for name, field in (("search", "search-q"), ("index", "home-search")):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertContains(response, f'id="{field}"')
                self.assertNotContains(response, 'id="site-search"')
                self.assertNotContains(response, "data-search-link")
