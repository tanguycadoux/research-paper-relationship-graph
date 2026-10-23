import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse

from references.models import (
    Author,
    AuthorPublication,
    CitedReference,
    Publication,
    UserPublication,
)
from references.services.external_records import Source, store_record
from references.services.graph import base_graph, corpus_graph, publication_graph


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
        self.assertEqual(nodes["Source"]["role"], "source")
        self.assertEqual(nodes["Source"]["date"], "2020-01-01")
        self.assertEqual(nodes["Cité"]["role"], "cited")
        self.assertIsNone(nodes["Cité"]["date"])
        self.assertEqual(nodes["Cité"]["citedBy"], 2)
        self.assertEqual(nodes["Cité"]["url"], reverse("publication_detail", args=[self.cited.pk]))

    def test_node_data_for_the_information_card(self):
        self.source.doi = "10.1000/source"
        self.source.save()
        ada, alan, grace, edsger = (
            Author.objects.create(first_name=first, last_name=last)
            for first, last in [
                ("Ada", "Lovelace"),
                ("Alan", "Turing"),
                ("Grace", "Hopper"),
                ("Edsger", "Dijkstra"),
            ]
        )
        for order, author in enumerate([ada, alan, grace, ada, edsger]):
            AuthorPublication.objects.create(publication=self.source, author=author, order=order)
        nodes = self.nodes_by_label(publication_graph(self.source))
        # « Ada Lovelace et al. »: each person counted once (merged slots).
        self.assertEqual(nodes["Source"]["firstAuthor"], "Ada Lovelace")
        self.assertEqual(nodes["Source"]["authorCount"], 4)
        self.assertEqual(nodes["Cité"]["firstAuthor"], "")

    def test_node_venue_from_crossref_then_datacite(self):
        store_record(
            self.source, Source.CROSSREF, {"message": {"container-title": ["IEEE Trans. &amp; Co"]}}
        )
        store_record(
            self.cited,
            Source.DATACITE,
            {"data": {"attributes": {"container": {"title": "Proc. ECRIS 2016"}}}},
        )
        with self.assertNumQueries(3):
            nodes = self.nodes_by_label(publication_graph(self.source))
        self.assertEqual(nodes["Source"]["venue"], "IEEE Trans. & Co")
        self.assertEqual(nodes["Cité"]["venue"], "Proc. ECRIS 2016")

    def test_node_without_venue(self):
        nodes = self.nodes_by_label(publication_graph(self.source))
        self.assertEqual(nodes["Source"]["venue"], "")

    def test_corpus_graph_merges_the_corpus_publications(self):
        user = get_user_model().objects.create_user("alice")
        UserPublication.objects.create(user=user, publication=self.source)
        UserPublication.objects.create(user=user, publication=self.other)
        graph = corpus_graph(user)
        self.assertEqual(set(self.nodes_by_label(graph)), {"Source", "Autre source", "Cité"})
        self.assertEqual(len(graph["edges"]), 2)

    def test_graph_query_count_does_not_depend_on_size(self):
        with self.assertNumQueries(3):
            publication_graph(self.source)

    def test_graph_page_embeds_data_and_local_library(self):
        response = self.client.get(reverse("publication_graph", args=[self.source.pk]))
        self.assertContains(response, 'id="citation-graph-data"')
        self.assertContains(response, "vendor/cytoscape/cytoscape.min.js")
        # The year axis is drawn outside the canvas, to stay in view (#62).
        self.assertContains(response, 'id="citation-graph-axis"')
        # The information card of a selected publication, filled by the script (#61).
        self.assertContains(response, 'id="citation-graph-card"')

    def test_publication_graph_contains_the_citing_publications(self):
        graph = publication_graph(self.cited)
        nodes = self.nodes_by_label(graph)
        self.assertEqual(set(nodes), {"Cité", "Source", "Autre source"})
        self.assertEqual(nodes["Cité"]["role"], "source")
        self.assertEqual(nodes["Source"]["role"], "citing")
        self.assertEqual(nodes["Autre source"]["role"], "citing")
        self.assertEqual(
            {(e["data"]["source"], e["data"]["target"]) for e in graph["edges"]},
            {(str(self.source.pk), str(self.cited.pk)), (str(self.other.pk), str(self.cited.pk))},
        )

    def test_corpus_graph_does_not_add_the_citing_publications(self):
        user = get_user_model().objects.create_user("bob")
        UserPublication.objects.create(user=user, publication=self.cited)
        self.assertEqual(corpus_graph(user)["edges"], [])

    def test_legend_follows_the_kind_of_graph(self):
        response = self.client.get(reverse("publication_graph", args=[self.cited.pk]))
        self.assertContains(response, "Cette publication")
        self.assertContains(response, "Publication qui la cite")
        user = get_user_model().objects.create_user("carol")
        UserPublication.objects.create(user=user, publication=self.source)
        self.client.force_login(user)
        response = self.client.get(reverse("corpus_graph"))
        self.assertContains(response, "Publication de mon corpus")
        self.assertNotContains(response, "Publication qui la cite")

    def test_graph_page_of_a_cited_publication_is_not_empty(self):
        response = self.client.get(reverse("publication_graph", args=[self.cited.pk]))
        self.assertContains(response, 'id="citation-graph-data"')

    def test_graph_page_without_citations(self):
        alone = Publication.objects.create(title="Seule")
        response = self.client.get(reverse("publication_graph", args=[alone.pk]))
        self.assertContains(response, "Aucune citation identifiée")


class BaseGraphTests(TestCase):
    """The graph of the whole base (#131)."""

    @classmethod
    def setUpTestData(cls):
        cls.source = Publication.objects.create(title="Source")
        cls.cited = Publication.objects.create(title="Cité")
        cls.alone = Publication.objects.create(title="Seule")
        CitedReference.objects.create(source=cls.source, target=cls.cited, position=0)
        CitedReference.objects.create(source=cls.source, position=1, unstructured="Sans DOI")
        cls.user = get_user_model().objects.create_user("dave")
        UserPublication.objects.create(user=cls.user, publication=cls.cited)

    def roles(self, graph):
        return {node["data"]["label"]: node["data"]["role"] for node in graph["nodes"]}

    def test_every_publication_and_every_resolved_citation(self):
        graph = base_graph(AnonymousUser())
        # Publications without identified citations are shown too.
        self.assertEqual(set(self.roles(graph)), {"Source", "Cité", "Seule"})
        self.assertEqual(
            [(e["data"]["source"], e["data"]["target"]) for e in graph["edges"]],
            [(str(self.source.pk), str(self.cited.pk))],
        )

    def test_the_corpus_of_the_user_stands_out(self):
        self.assertEqual(
            self.roles(base_graph(self.user)),
            {"Source": "other", "Cité": "source", "Seule": "other"},
        )
        self.assertEqual(set(self.roles(base_graph(AnonymousUser())).values()), {"other"})

    def test_query_count_does_not_depend_on_size(self):
        with self.assertNumQueries(3):
            base_graph(AnonymousUser())
        # And the corpus of the user.
        with self.assertNumQueries(4):
            base_graph(self.user)

    def test_a_publication_citing_another_twice_gives_one_edge(self):
        CitedReference.objects.create(source=self.source, target=self.cited, position=2)
        self.assertEqual(len(base_graph(AnonymousUser())["edges"]), 1)
        self.assertEqual(len(publication_graph(self.source)["edges"]), 1)

    def test_page_is_public(self):
        response = self.client.get(reverse("base_graph"))
        self.assertContains(response, 'id="citation-graph-data"')
        self.assertContains(response, 'data-graph-export="graphe-base"')
        self.assertContains(response, "Publication de la base")
        self.assertNotContains(response, "Publication de mon corpus")
        self.assertNotContains(response, "Publication qui la cite")

    def test_legend_with_a_corpus(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("base_graph"))
        self.assertContains(response, "Publication de mon corpus")
        self.assertContains(response, "Autre publication de la base")
