from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from references.models import Publication, UserPublication


class SortByAdditionTests(TestCase):
    """My corpus sorted by date of addition, the latest first (#281)."""

    @classmethod
    def setUpTestData(cls):
        cls.alice = get_user_model().objects.create_user("alice")
        bob = get_user_model().objects.create_user("bob")
        now = timezone.now()
        for days, title, year in (
            (3, "Ancienne", 2024),
            (1, "Récente", 2001),
            (2, "Moyenne", 2010),
        ):
            pub = Publication.objects.create(
                title=title, publication_date=timezone.datetime(year, 1, 1).date()
            )
            entry = UserPublication.objects.create(user=cls.alice, publication=pub)
            UserPublication.objects.filter(pk=entry.pk).update(added_at=now - timedelta(days=days))
            # Bob added them the other way round: his dates must not count.
            other = UserPublication.objects.create(user=bob, publication=pub)
            UserPublication.objects.filter(pk=other.pk).update(
                added_at=now - timedelta(days=9 - days)
            )

    def setUp(self):
        self.client.force_login(self.alice)

    def titles(self, **params):
        response = self.client.get(reverse("corpus"), params)
        return [pub.title for pub in response.context["publications"]], response

    def test_latest_first(self):
        titles, response = self.titles(sort="-added")
        self.assertEqual(titles, ["Récente", "Moyenne", "Ancienne"])
        self.assertContains(response, "trier par année")

    def test_by_year_by_default_with_a_link_to_the_latest_first(self):
        titles, response = self.titles()
        self.assertEqual(titles, ["Ancienne", "Moyenne", "Récente"])
        self.assertContains(response, 'href="?sort=-added"')

    def test_the_link_keeps_the_filters(self):
        _, response = self.titles(title="e", page="1")
        self.assertContains(response, 'href="?title=e&amp;sort=-added"')

    def test_the_home_page_links_to_it(self):
        response = self.client.get(reverse("index"))
        self.assertContains(response, f'href="{reverse("corpus")}?sort=-added"')
