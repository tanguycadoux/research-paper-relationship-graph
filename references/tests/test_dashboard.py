from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from references.models import Author, CitedReference, MetadataConflict, Publication, UserPublication
from references.services import dashboard


class DashboardTests(TestCase):
    """The home page (#151)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("frank")
        cls.older = Publication.objects.create(title="Plus ancienne")
        cls.newer = Publication.objects.create(title="Plus récente")
        cited = Publication.objects.create(title="Citée")
        for pub in (cls.older, cls.newer):
            UserPublication.objects.create(user=cls.user, publication=pub)
        CitedReference.objects.create(source=cls.older, target=cited, position=0)
        CitedReference.objects.create(source=cls.older, position=1, unstructured="À trouver")
        Author.objects.create(first_name="Ada", last_name="Lovelace")
        Author.objects.create(first_name="A.", last_name="Lovelace")

    def test_base_figures(self):
        self.assertEqual(
            dashboard.base_figures(), {"publications": 3, "authors": 2, "citations": 1}
        )

    def test_corpus_latest_first(self):
        figures = dashboard.corpus_figures(self.user)
        self.assertEqual(figures["count"], 2)
        self.assertEqual(figures["latest"], [self.newer, self.older])

    def test_to_do(self):
        MetadataConflict.objects.create(
            kind="orcid",
            publication=self.older,
            field="orcid",
            current_value="a",
            proposed_value="b",
            source="crossref",
        )
        self.assertEqual(
            dashboard.to_do(self.user), {"to_identify": 1, "conflicts": 1, "duplicates": 1}
        )

    def home_page_queries(self):
        with CaptureQueriesContext(connection) as queries:
            self.client.get(reverse("index"))
        return len(queries)

    def test_query_count_does_not_depend_on_size(self):
        self.client.force_login(self.user)
        before = self.home_page_queries()
        for i in range(10):
            pub = Publication.objects.create(title=f"P{i}")
            UserPublication.objects.create(user=self.user, publication=pub)
            CitedReference.objects.create(source=pub, target=self.older, position=0)
        self.assertEqual(self.home_page_queries(), before)

    def test_dashboard_of_a_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("index"))
        self.assertContains(response, "Mon corpus")
        self.assertContains(response, "À faire")
        self.assertContains(response, "Plus récente")
        self.assertContains(response, "Base commune")

    def test_presentation_for_a_visitor(self):
        response = self.client.get(reverse("index"))
        self.assertNotContains(response, "Mon corpus")
        self.assertNotContains(response, "À faire")
        self.assertContains(response, "Base commune")
        self.assertContains(response, reverse("base_graph"))
