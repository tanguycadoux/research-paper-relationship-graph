from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from references.models import Author, CitedReference, MetadataConflict, Publication, UserPublication
from references.services.display import dashboard
from references.templatetags.ui import BADGE_VARIANTS


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
        figures = dashboard.base_figures()
        self.assertEqual(
            (figures["publications"], figures["authors"], figures["citations"]), (3, 2, 1)
        )

    def test_the_base_shows_what_was_added_to_a_corpus_lately(self):
        # Not « Citée », which entered the base as a cited reference (#278).
        self.assertEqual(dashboard.base_figures()["latest"], [self.newer, self.older])

    def test_corpus_latest_first(self):
        figures = dashboard.corpus_figures(self.user)
        self.assertEqual(figures["count"], 2)
        self.assertEqual(
            [entry.publication for entry in figures["latest"]], [self.newer, self.older]
        )

    def test_next_to_read(self):
        reading, to_read = (
            UserPublication.ReadingStatus.READING,
            UserPublication.ReadingStatus.TO_READ,
        )
        UserPublication.objects.filter(publication=self.older).update(reading_status=to_read)
        UserPublication.objects.filter(publication=self.newer).update(reading_status=reading)
        entries = dashboard.corpus_figures(self.user)["next_to_read"]
        # Being read first, then to read.
        self.assertEqual([entry.publication for entry in entries], [self.newer, self.older])

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

    def test_the_reading_bar_has_one_part_per_status_in_use(self):
        UserPublication.objects.filter(publication=self.older).update(
            reading_status=UserPublication.ReadingStatus.READ
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("index"))
        # One read, one without status; no part for the statuses at zero.
        self.assertContains(response, 'class="bg-blue-800" style="flex-grow: 1"')
        self.assertContains(response, 'class="bg-gray-300" style="flex-grow: 1"')
        self.assertNotContains(response, 'class="bg-blue-300" style=')

    def test_nothing_to_do_is_a_muted_count(self):
        # No open conflict: a 0 aligned with the other counts, without drawing the eye.
        self.client.force_login(self.user)
        response = self.client.get(reverse("index"))
        self.assertContains(response, BADGE_VARIANTS["muted"], count=1)

    def test_presentation_for_a_visitor(self):
        response = self.client.get(reverse("index"))
        self.assertNotContains(response, "Mon corpus")
        self.assertNotContains(response, "À faire")
        self.assertContains(response, "Base commune")
        self.assertContains(response, reverse("base_graph"))
        # One link to each page of the base in the page, not two rows of buttons (#278);
        # the graph has no menu entry any more: it is reached from « Publications ».
        self.assertContains(response, f'href="{reverse("base_graph")}"', count=1)
