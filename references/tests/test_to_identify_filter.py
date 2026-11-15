from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, Publication, UserPublication


class ToIdentifyFilterTests(TestCase):
    """« À identifier »: my corpus filtered on the references to identify (#276)."""

    @classmethod
    def setUpTestData(cls):
        cls.alice = get_user_model().objects.create_user("alice")
        cls.pending = Publication.objects.create(doi="10.1000/pending", title="En attente")
        cls.done = Publication.objects.create(doi="10.1000/done", title="Identifiée")
        cls.none = Publication.objects.create(doi="10.1000/none", title="Sans bibliographie")
        for pub in (cls.pending, cls.done, cls.none):
            UserPublication.objects.create(user=cls.alice, publication=pub)
        CitedReference.objects.create(source=cls.pending, position=0, unstructured="À trouver")
        CitedReference.objects.create(source=cls.pending, position=1, unstructured="Encore")
        # Linked, or declared unidentifiable: nothing left to identify.
        CitedReference.objects.create(source=cls.done, target=cls.pending, position=0)
        CitedReference.objects.create(
            source=cls.done, position=1, unstructured="Rapport", unidentifiable=True
        )

    def setUp(self):
        self.client.force_login(self.alice)

    def get(self, **params):
        return self.client.get(reverse("corpus"), params)

    def titles(self, response):
        return [pub.title for pub in response.context["publications"]]

    def test_only_the_publications_with_references_to_identify(self):
        response = self.get(to_identify="1")
        self.assertEqual(self.titles(response), ["En attente"])
        # Once, though it has two references to identify.
        self.assertContains(response, "Références à identifier")

    def test_any_other_value_is_no_filter(self):
        self.assertEqual(len(self.titles(self.get(to_identify="oui"))), 3)

    def test_the_filter_keeps_the_others(self):
        self.assertEqual(self.titles(self.get(to_identify="1", title="identifiée")), [])

    def test_the_navigation_and_the_dashboard_link_to_it(self):
        url = f'href="{reverse("corpus")}?to_identify=1"'
        self.assertContains(self.get(), url)
        self.assertContains(self.client.get(reverse("index")), url)
