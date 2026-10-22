import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, Publication, UserPublication
from references.services.graph import corpus_graph, publication_graph


class CitationGraphTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = Publication.objects.create(
            title="Source", publication_date=datetime.date(2020, 1, 1)
        )
        cls.cited = Publication.objects.create(title="Cité")
        cls.other = Publication.objects.create(title="Autre source")
        CitedReference.objects.create(source=cls.source, target=cls.cited, position=0)
        CitedReference.objects.create(source=cls.source, position=1, unstructured="Sans DOI")
        CitedReference.objects.create(source=cls.other, target=cls.cited, position=0)

    def nodes_by_label(self, graph):
        return {node["data"]["label"]: node["data"] for node in graph["nodes"]}

    def test_publication_graph_contains_source_and_resolved_citations(self):
        graph = publication_graph(self.source)
        nodes = self.nodes_by_label(graph)
        self.assertEqual(set(nodes), {"Source", "Cité"})
        self.assertEqual(
            graph["edges"],
            [
                {
                    "data": {
                        "id": f"{self.source.pk}-{self.cited.pk}",
                        "source": str(self.source.pk),
                        "target": str(self.cited.pk),
                    }
                }
            ],
        )

    def test_node_data(self):
        nodes = self.nodes_by_label(publication_graph(self.source))
        self.assertTrue(nodes["Source"]["isSource"])
        self.assertEqual(nodes["Source"]["date"], "2020-01-01")
        self.assertFalse(nodes["Cité"]["isSource"])
        self.assertIsNone(nodes["Cité"]["date"])
        self.assertEqual(nodes["Cité"]["citedBy"], 2)
        self.assertEqual(nodes["Cité"]["url"], reverse("publication_detail", args=[self.cited.pk]))

    def test_corpus_graph_merges_the_corpus_publications(self):
        user = get_user_model().objects.create_user("alice")
        UserPublication.objects.create(user=user, publication=self.source)
        UserPublication.objects.create(user=user, publication=self.other)
        graph = corpus_graph(user)
        self.assertEqual(set(self.nodes_by_label(graph)), {"Source", "Autre source", "Cité"})
        self.assertEqual(len(graph["edges"]), 2)

    def test_graph_query_count_does_not_depend_on_size(self):
        with self.assertNumQueries(2):
            publication_graph(self.source)

    def test_graph_page_embeds_data_and_local_library(self):
        response = self.client.get(reverse("publication_graph", args=[self.source.pk]))
        self.assertContains(response, 'id="citation-graph-data"')
        self.assertContains(response, "vendor/cytoscape/cytoscape.min.js")
        # The year axis is drawn outside the canvas, to stay in view (#62).
        self.assertContains(response, 'id="citation-graph-axis"')

    def test_graph_page_without_citations(self):
        response = self.client.get(reverse("publication_graph", args=[self.cited.pk]))
        self.assertContains(response, "Aucune référence identifiée")
