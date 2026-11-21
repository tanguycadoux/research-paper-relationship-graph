"""The references to identify in the citation graphs (#452)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, Publication, UserPublication
from references.services.display.graph import base_graph, corpus_graph, publication_graph


class ToIdentifyTests(TestCase):
    """
    mine (in the corpus) cites cited and has two references to identify, one declared
    unidentifiable aside; cited (not in the corpus) has one to identify too.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("carol")
        cls.mine = Publication.objects.create(title="Mienne")
        cls.cited = Publication.objects.create(title="Citée")
        UserPublication.objects.create(user=cls.user, publication=cls.mine)
        refs = CitedReference.objects
        refs.create(source=cls.mine, target=cls.cited, position=0)
        refs.create(source=cls.mine, position=3, unstructured="Rapport interne")
        refs.create(source=cls.mine, position=5, unstructured="Exposé")
        refs.create(source=cls.mine, position=1, unstructured="Note", unidentifiable=True)
        # Two citations of cited: its count must not be multiplied by the references.
        cls.other = Publication.objects.create(title="Autre")
        refs.create(source=cls.other, target=cls.cited, position=0)
        refs.create(source=cls.cited, position=0, unstructured="Livre")

    def labels(self, graph):
        return {node["data"]["label"]: node["data"] for node in graph["nodes"]}

    def test_only_the_publications_of_the_corpus_are_marked(self):
        nodes = self.labels(publication_graph(self.mine, user=self.user))
        self.assertEqual(nodes["Mienne"]["toIdentify"], 2)
        self.assertEqual(
            nodes["Mienne"]["identifyUrl"],
            reverse("reference_identify", args=[self.mine.pk, 3]) + "?serie=1",
        )
        self.assertEqual(nodes["Mienne"]["tooltip"], "Mienne\n2 références à identifier")
        self.assertNotIn("toIdentify", nodes["Citée"])
        self.assertNotIn("tooltip", nodes["Citée"])
        self.assertEqual(nodes["Citée"]["citedBy"], 2)

    def test_counted_in_the_query_of_the_nodes(self):
        with self.assertNumQueries(3):
            publication_graph(self.mine, user=self.user)

    def test_without_a_user_nothing_is_marked(self):
        for user in (None, AnonymousUser()):
            nodes = self.labels(publication_graph(self.mine, user=user))
            self.assertNotIn("toIdentify", nodes["Mienne"])

    def test_corpus_and_base_graphs(self):
        self.assertEqual(self.labels(corpus_graph(self.user))["Mienne"]["toIdentify"], 2)
        nodes = self.labels(base_graph(self.user))
        self.assertEqual(nodes["Mienne"]["toIdentify"], 2)
        self.assertNotIn("toIdentify", nodes["Citée"])

    def test_the_legend_explains_the_mark(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("corpus_graph"))
        self.assertTrue(response.context["graph_to_identify"])
        self.assertContains(response, "Références à identifier (mon corpus)")
        self.assertContains(response, "data-graph-warning-icon", count=2)
        self.client.logout()
        response = self.client.get(reverse("publication_graph", args=[self.mine.pk]))
        self.assertNotContains(response, "Références à identifier (mon corpus)")
