from datetime import date

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from references.models import (
    Author,
    AuthorPublication,
    CitedReference,
    Publication,
    UserPublication,
)
from references.templatetags.ui import page_url
from references.views.pagination import PAGE_SIZE


def publications(count, **fields):
    """count publications of the same date: only the tie-breakers order them."""
    return Publication.objects.bulk_create(
        Publication(title=f"P{i:03}", publication_date=date(2020, 1, 1), **fields)
        for i in range(count)
    )


class PageUrlTests(SimpleTestCase):
    def test_other_parameters_are_kept(self):
        request = RequestFactory().get("/publications/", {"sort": "-year", "page": "3"})
        self.assertEqual(page_url(request, 4), "?sort=-year&page=4")

    def test_first_page_has_no_page_parameter(self):
        request = RequestFactory().get("/publications/", {"sort": "-year", "page": "3"})
        self.assertEqual(page_url(request, 1), "?sort=-year")
        request = RequestFactory().get("/publications/", {"page": "2"})
        self.assertEqual(page_url(request, 1), "/publications/")


class PublicationListPaginationTests(TestCase):
    """Lists in pages of PAGE_SIZE rows, as many queries on any page (#154)."""

    @classmethod
    def setUpTestData(cls):
        cls.pubs = publications(PAGE_SIZE + 1)

    def page(self, **params):
        return self.client.get(reverse("publication_list"), params)

    def test_first_page(self):
        response = self.page()
        self.assertEqual(len(response.context["publications"]), PAGE_SIZE)
        self.assertContains(response, '<nav aria-label="Pagination"')
        self.assertContains(response, f"1&nbsp;à&nbsp;{PAGE_SIZE} sur {PAGE_SIZE + 1}")
        self.assertContains(response, 'href="?page=2" rel="next"')
        self.assertContains(response, '<span aria-current="page"')
        self.assertNotContains(response, 'rel="prev"')

    def test_last_page(self):
        response = self.page(page=2)
        self.assertEqual(len(response.context["publications"]), 1)
        self.assertContains(response, 'href="/publications/" rel="prev"')
        self.assertNotContains(response, 'rel="next"')

    def test_pages_share_out_rows_of_the_same_date(self):
        shown = [*self.page().context["publications"], *self.page(page=2).context["publications"]]
        self.assertCountEqual(shown, self.pubs)

    def test_a_wrong_page_still_lands_on_a_page(self):
        self.assertEqual(self.page(page="abc").context["page_obj"].number, 1)
        # Past the end, as after the last row of a page was removed.
        self.assertEqual(self.page(page=9).context["page_obj"].number, 2)

    def test_single_page_has_no_pagination(self):
        Publication.objects.filter(pk=self.pubs[0].pk).delete()
        self.assertNotContains(self.page(), 'aria-label="Pagination"')

    def queries(self, **params):
        with CaptureQueriesContext(connection) as queries:
            self.page(**params)
        return len(queries)

    def test_queries_do_not_depend_on_the_number_of_rows(self):
        author = Author.objects.create(last_name="Lovelace")
        for pub in self.pubs:
            AuthorPublication.objects.create(author=author, publication=pub, order=0)
            CitedReference.objects.create(source=pub, position=0, unstructured="Rapport")
        # Count, page, corpus of the user (none: anonymous).
        with self.assertNumQueries(2):
            self.page()
        self.assertEqual(self.queries(page=2), self.queries())


class AuthorListPaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Author.objects.bulk_create(Author(last_name="Curie") for _ in range(PAGE_SIZE + 1))

    def test_pages_share_out_authors_of_the_same_name(self):
        first = self.client.get(reverse("author_list"))
        second = self.client.get(reverse("author_list"), {"page": 2})
        self.assertEqual(len(first.context["authors"]), PAGE_SIZE)
        self.assertContains(first, '<nav aria-label="Pagination"')
        self.assertCountEqual(
            [*first.context["authors"], *second.context["authors"]], Author.objects.all()
        )


class CorpusPaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")
        cls.pubs = publications(PAGE_SIZE + 1)
        UserPublication.objects.bulk_create(
            UserPublication(user=cls.user, publication=pub) for pub in cls.pubs
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_heading_counts_the_whole_corpus(self):
        response = self.client.get(reverse("corpus"))
        self.assertEqual(len(response.context["publications"]), PAGE_SIZE)
        self.assertContains(response, f"({PAGE_SIZE + 1})")
        self.assertContains(response, '<nav aria-label="Pagination"')

    def test_removing_the_last_row_of_a_page_goes_back_to_a_page(self):
        last = self.client.get(reverse("corpus"), {"page": 2}).context["publications"][0]
        next_url = reverse("corpus") + "?page=2"
        response = self.client.post(reverse("corpus_remove", args=[last.pk]), {"next": next_url})
        self.assertRedirects(response, next_url)
        page = self.client.get(next_url).context["page_obj"]
        self.assertEqual((page.number, page.paginator.num_pages), (1, 1))
