from django.test import TestCase
from django.urls import reverse

from references.models import Author, AuthorPublication, Publication
from references.services.display.author_graph import (
    LARGE_COLLABORATION,
    all_authors_graph,
    author_graph,
)


def publish(title, *authors):
    publication = Publication.objects.create(title=title)
    for order, author in enumerate(authors):
        AuthorPublication.objects.create(publication=publication, author=author, order=order)
    return publication


def nodes(graph):
    return {node["data"]["label"]: node["data"] for node in graph["nodes"]}


def links(graph):
    """{frozenset of two names: (weight, shared publications)}."""
    names = {node["data"]["id"]: node["data"]["label"] for node in graph["nodes"]}
    return {
        frozenset((names[e["data"]["source"]], names[e["data"]["target"]])): (
            e["data"]["weight"],
            e["data"]["shared"],
        )
        for e in graph["edges"]
    }


class CoauthorshipWeightTests(TestCase):
    """Newman's weighting: each publication of n authors adds 1/(n - 1) to each pair."""

    @classmethod
    def setUpTestData(cls):
        cls.ada, cls.alan, cls.grace, cls.edsger = (
            Author.objects.create(first_name=first, last_name=last)
            for first, last in [
                ("Ada", "Lovelace"),
                ("Alan", "Turing"),
                ("Grace", "Hopper"),
                ("Edsger", "Dijkstra"),
            ]
        )

    def test_two_authors_weigh_one(self):
        publish("À deux", self.ada, self.alan)
        self.assertEqual(
            links(all_authors_graph()), {frozenset({"Ada Lovelace", "Alan Turing"}): (1.0, 1)}
        )

    def test_three_authors_weigh_a_half_per_pair(self):
        publish("À trois", self.ada, self.alan, self.grace)
        graph_links = links(all_authors_graph())
        self.assertEqual(len(graph_links), 3)
        self.assertEqual(set(graph_links.values()), {(0.5, 1)})

    def test_shared_publications_add_up_in_one_edge(self):
        publish("À deux", self.ada, self.alan)
        publish("À trois", self.ada, self.alan, self.grace)
        publish("À quatre", self.ada, self.alan, self.grace, self.edsger)
        graph = all_authors_graph()
        self.assertEqual(len(graph["edges"]), 6)
        graph_links = links(graph)
        self.assertEqual(
            graph_links[frozenset({"Ada Lovelace", "Alan Turing"})],
            (round(1 + 1 / 2 + 1 / 3, 4), 3),
        )
        self.assertEqual(
            graph_links[frozenset({"Grace Hopper", "Edsger Dijkstra"})], (round(1 / 3, 4), 1)
        )

    def test_merged_slots_count_one_person(self):
        # After a merge, one author can hold two slots of a publication.
        publish("Fusion", self.ada, self.alan, self.ada)
        self.assertEqual(
            links(all_authors_graph()), {frozenset({"Ada Lovelace", "Alan Turing"}): (1.0, 1)}
        )
        self.assertEqual(nodes(all_authors_graph())["Ada Lovelace"]["publications"], 1)

    def test_node_data(self):
        publish("À deux", self.ada, self.alan)
        publish("Seule", self.ada)
        ada = nodes(all_authors_graph())["Ada Lovelace"]
        self.assertEqual(ada["publications"], 2)
        self.assertEqual(ada["shortLabel"], "Lovelace")
        self.assertEqual(ada["role"], "other")
        self.assertEqual(ada["url"], reverse("author_detail", args=[self.ada.pk]))

    def test_authors_without_publication_are_left_out(self):
        publish("À deux", self.ada, self.alan)
        self.assertEqual(set(nodes(all_authors_graph())), {"Ada Lovelace", "Alan Turing"})


class LargeCollaborationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.crowd = [
            Author.objects.create(last_name=f"Auteur {i}") for i in range(LARGE_COLLABORATION + 1)
        ]
        cls.first, cls.second = cls.crowd[:2]

    def test_a_large_collaboration_creates_no_link_but_counts_in_sizes(self):
        publish("Collaboration", *self.crowd)
        publish("À deux", self.first, self.second)
        graph = all_authors_graph()
        self.assertEqual(links(graph), {frozenset({"Auteur 0", "Auteur 1"}): (1.0, 1)})
        self.assertEqual(graph["excluded"], 1)
        self.assertEqual(nodes(graph)["Auteur 0"]["publications"], 2)
        self.assertEqual(nodes(graph)["Auteur 50"]["publications"], 1)

    def test_fifty_authors_still_link(self):
        publish("Cinquante", *self.crowd[:LARGE_COLLABORATION])
        graph = all_authors_graph()
        self.assertEqual(graph["excluded"], 0)
        self.assertEqual(len(graph["edges"]), LARGE_COLLABORATION * (LARGE_COLLABORATION - 1) // 2)

    def test_the_author_graph_leaves_out_coauthors_of_large_collaborations(self):
        publish("Collaboration", *self.crowd)
        graph = author_graph(self.first)
        self.assertEqual(set(nodes(graph)), {"Auteur 0"})
        self.assertEqual(graph["edges"], [])
        self.assertEqual(graph["excluded"], 0)

    def test_the_author_graph_counts_large_collaborations_between_its_authors(self):
        publish("Collaboration", *self.crowd)
        publish("À deux", self.first, self.second)
        graph = author_graph(self.first)
        self.assertEqual(set(nodes(graph)), {"Auteur 0", "Auteur 1"})
        self.assertEqual(graph["excluded"], 1)

    def test_the_page_says_how_many_publications_are_set_aside(self):
        publish("Collaboration", *self.crowd)
        publish("À deux", self.first, self.second)
        response = self.client.get(reverse("authors_graph"))
        self.assertContains(response, "1 publication de plus de 50 auteurs ne crée aucun lien")


class AuthorGraphTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ada, cls.alan, cls.grace, cls.edsger, cls.barbara = (
            Author.objects.create(first_name=first, last_name=last)
            for first, last in [
                ("Ada", "Lovelace"),
                ("Alan", "Turing"),
                ("Grace", "Hopper"),
                ("Edsger", "Dijkstra"),
                ("Barbara", "Liskov"),
            ]
        )
        publish("Ada et Alan", cls.ada, cls.alan)
        publish("Ada et Grace", cls.ada, cls.grace)
        # Between two coauthors of Ada, without her: in the graph of Ada.
        publish("Alan et Grace", cls.alan, cls.grace)
        # A coauthor of a coauthor: not in the graph of Ada.
        publish("Grace et Edsger", cls.grace, cls.edsger)
        publish("Barbara seule", cls.barbara)

    def test_the_author_their_coauthors_and_the_links_between_them(self):
        graph = author_graph(self.ada)
        self.assertEqual(set(nodes(graph)), {"Ada Lovelace", "Alan Turing", "Grace Hopper"})
        self.assertEqual(
            set(links(graph)),
            {
                frozenset({"Ada Lovelace", "Alan Turing"}),
                frozenset({"Ada Lovelace", "Grace Hopper"}),
                frozenset({"Alan Turing", "Grace Hopper"}),
            },
        )

    def test_the_author_stands_out_and_comes_first(self):
        graph = author_graph(self.grace)
        self.assertEqual(graph["nodes"][0]["data"]["label"], "Grace Hopper")
        roles = {label: data["role"] for label, data in nodes(graph).items()}
        self.assertEqual(roles.pop("Grace Hopper"), "source")
        self.assertEqual(set(roles.values()), {"other"})

    def test_sizes_count_every_publication_in_the_base(self):
        # Edsger is not in the graph of Ada: Grace has her three publications all the same.
        self.assertEqual(nodes(author_graph(self.ada))["Grace Hopper"]["publications"], 3)

    def test_an_author_without_coauthor(self):
        graph = author_graph(self.barbara)
        self.assertEqual(set(nodes(graph)), {"Barbara Liskov"})
        self.assertEqual(graph["edges"], [])

    def test_constant_number_of_queries(self):
        with self.assertNumQueries(2):
            author_graph(self.ada)
        with self.assertNumQueries(2):
            all_authors_graph()
        for i in range(10):
            people = [Author.objects.create(last_name=f"Nouveau {i} {j}") for j in range(3)]
            publish(f"Nouvelle {i}", self.ada, *people)
        with self.assertNumQueries(2):
            author_graph(self.ada)
        with self.assertNumQueries(2):
            all_authors_graph()


class AuthorGraphPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ada = Author.objects.create(first_name="Ada", last_name="Lovelace")
        cls.alan = Author.objects.create(first_name="Alan", last_name="Turing")
        cls.barbara = Author.objects.create(first_name="Barbara", last_name="Liskov")
        publish("Ada et Alan", cls.ada, cls.alan)

    def test_the_author_page_links_to_their_graph_for_everyone(self):
        response = self.client.get(reverse("author_detail", args=[self.ada.pk]))
        self.assertContains(response, reverse("author_graph", args=[self.ada.pk]))

    def test_the_graph_of_an_author_is_public(self):
        response = self.client.get(reverse("author_graph", args=[self.ada.pk]))
        self.assertContains(response, 'id="citation-graph-data"')
        self.assertContains(response, "references/graph/coauthors.js")
        self.assertContains(response, f'data-graph-export="graphe-auteur-{self.ada.pk}"')
        self.assertContains(response, "Cet auteur")
        self.assertContains(response, "2 auteurs, 1 lien de coautorat")

    def test_the_graph_of_all_authors_is_public(self):
        response = self.client.get(reverse("authors_graph"))
        self.assertContains(response, 'data-graph-export="graphe-auteurs"')
        self.assertNotContains(response, "Cet auteur")
        self.assertNotContains(response, "data-graph-excluded")

    def test_the_list_of_authors_links_to_the_graph(self):
        response = self.client.get(reverse("author_list"))
        self.assertContains(response, reverse("authors_graph"))

    def test_an_author_without_coauthor_has_nothing_to_draw(self):
        response = self.client.get(reverse("author_graph", args=[self.barbara.pk]))
        self.assertContains(response, "Aucun coautorat : rien à afficher.")
        self.assertNotContains(response, "coauthors.js")

    def test_unknown_author(self):
        response = self.client.get(reverse("author_graph", args=[0]))
        self.assertEqual(response.status_code, 404)
