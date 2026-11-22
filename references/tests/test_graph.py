import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse

from references.models import (
    Author,
    AuthorPublication,
    CitedReference,
    Publication,
    UserPublication,
)
from references.services.corpus import tags
from references.services.display.graph import base_graph, corpus_graph, publication_graph
from references.services.display.graph_variants import graph_layout, kept_params
from references.services.sources.external_records import Source, store_record


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
        # Short label of an exported image (#289): family name and year.
        self.assertEqual(nodes["Source"]["shortLabel"], "Lovelace 2020")

    def test_short_label_without_author_or_date(self):
        self.cited.title = "A very long title about superconducting magnets and their quench"
        self.cited.save()
        nodes = {
            node["data"]["id"]: node["data"] for node in publication_graph(self.source)["nodes"]
        }
        # No author: the start of the title, cut at a word; no date: no year.
        self.assertEqual(nodes[str(self.cited.pk)]["shortLabel"], "A very long title about…")
        self.assertEqual(nodes[str(self.source.pk)]["shortLabel"], "Source 2020")

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
        # The information card of a selected publication, filled by the script (#61). It is
        # beside the graph, not over it (#291), and keeps its place with a hint.
        self.assertContains(response, 'id="citation-graph-card"')
        self.assertContains(response, "Cliquez sur un article du graphe pour le décrire ici.")

    def test_panel_holds_commands_summary_and_legend(self):
        """
        The panel beside the graph (#291): the commands, out of the frame, then what the
        graph shows, then the legend; in this order, so that nothing moves on selection.
        """
        response = self.client.get(reverse("publication_graph", args=[self.cited.pk]))
        html = response.content.decode()
        panel = html[html.index('aria-label="Informations et commandes du graphe"') :]
        positions = [
            panel.index(marker)
            for marker in (
                "data-graph-show-all",
                "data-graph-export",
                'id="citation-graph-card"',
                'id="citation-graph-legend"',
            )
        ]
        self.assertEqual(positions, sorted(positions))
        # Three publications, two citations.
        self.assertContains(response, "3 publications, 2 citations")
        # The commands are no longer over the graph.
        frame = html[html.index('id="citation-graph-axis"') : html.index("<aside")]
        self.assertNotIn("data-graph-export", frame)

    def test_help_is_behind_a_button(self):
        """
        #415: the legend stays in the panel, the help is in a popover opened by « ? » at
        the end of the commands, without JavaScript.
        """
        response = self.client.get(reverse("publication_graph", args=[self.cited.pk]))
        html = response.content.decode()
        self.assertContains(response, 'popovertarget="graph-help"', count=2)
        self.assertContains(response, 'aria-label="Aide du graphe"')
        # The help is written once, in the popover, which is in frosted glass.
        popover = html[html.index('id="graph-help"') : html.index('id="citation-graph-card"')]
        self.assertIn("backdrop-blur-md", popover)
        self.assertIn("Survolez un article", popover)
        self.assertIn("Axe horizontal : date de publication", popover)
        self.assertEqual(html.count("Survolez"), 1)

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
            {"Source": "base", "Cité": "source", "Seule": "base"},
        )
        # The others in a neutral grey, not in the green of the past (#477).
        self.assertEqual(set(self.roles(base_graph(AnonymousUser())).values()), {"base"})

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
        # Its publications in the neutral grey, not in the green of the past (#477).
        self.assertContains(response, "bg-graph-base")
        self.assertNotContains(response, "border-graph-cited-border bg-graph-cited")
        # The groups of distance of a selection, in the card of every graph (#477).
        self.assertContains(response, "data-distance-groups", count=1)
        self.assertContains(response, "Distance à la sélection")

    def test_legend_with_a_corpus(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("base_graph"))
        self.assertContains(response, "Publication de mon corpus")
        self.assertContains(response, "Autre publication de la base")


class TagGraphTests(TestCase):
    """The graph of a tag of the corpus, its subtags included (#290)."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice")
        cls.bob = User.objects.create_user("bob")
        cls.project = Publication.objects.create(title="Projet")
        cls.group = Publication.objects.create(title="Groupe")
        cls.untagged = Publication.objects.create(title="Sans tag")
        cls.cited = Publication.objects.create(title="Cité")
        cls.cited_elsewhere = Publication.objects.create(title="Cité ailleurs")
        CitedReference.objects.create(source=cls.project, target=cls.cited, position=0)
        CitedReference.objects.create(source=cls.untagged, target=cls.cited_elsewhere, position=0)
        entries = {
            pub: UserPublication.objects.create(user=cls.alice, publication=pub)
            for pub in (cls.project, cls.group, cls.untagged)
        }
        tags.tag_entry(entries[cls.project], "Projet")
        tags.tag_entry(entries[cls.group], "Projet/Groupe")
        # Bob's tag of the same name does not count for Alice.
        bob_entry = UserPublication.objects.create(user=cls.bob, publication=cls.untagged)
        tags.tag_entry(bob_entry, "Projet")

    def labels(self, graph):
        return {node["data"]["label"] for node in graph["nodes"]}

    def test_a_tag_shows_its_publications_and_those_of_its_subtags(self):
        graph = corpus_graph(self.alice, "Projet")
        self.assertEqual(self.labels(graph), {"Projet", "Groupe", "Cité"})
        self.assertEqual(len(graph["edges"]), 1)

    def test_a_subtag_shows_only_its_own(self):
        self.assertEqual(self.labels(corpus_graph(self.alice, "Projet/Groupe")), {"Groupe"})

    def test_without_tag_the_whole_corpus(self):
        self.assertEqual(
            self.labels(corpus_graph(self.alice)),
            {"Projet", "Groupe", "Sans tag", "Cité", "Cité ailleurs"},
        )

    def test_the_tag_of_another_user_is_not_mine(self):
        self.assertEqual(
            self.labels(corpus_graph(self.bob, "Projet")), {"Sans tag", "Cité ailleurs"}
        )

    def test_page_with_a_tag(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("corpus_graph"), {"tag": "Projet"})
        self.assertContains(response, "du tag « Projet » (sous-tags compris)")
        self.assertContains(
            response, '<option value="Projet" selected>Projet (2)</option>', html=True
        )
        self.assertContains(response, "Projet › Groupe (1)")
        self.assertContains(response, 'data-graph-export="graphe-corpus-tag-projet"')
        nodes = response.context["graph"]["nodes"]
        self.assertEqual({node["data"]["label"] for node in nodes}, {"Projet", "Groupe", "Cité"})

    def test_exported_image_names_a_subtag_with_a_hyphen(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("corpus_graph"), {"tag": "Projet/Groupe"})
        # The name of the exported image (graphe-corpus-tag-…, _citation_graph.html).
        self.assertEqual(response.context["active_tag_slug"], "projet-groupe")
        # Without any citation, no graph, but the selector stays to choose another tag.
        self.assertContains(response, "rien à afficher")
        self.assertContains(response, 'id="graph-tag"')

    def test_an_unknown_tag_falls_back_to_the_whole_corpus(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("corpus_graph"), {"tag": "Disparu"})
        self.assertContains(response, "Le tag « Disparu » n&#x27;existe plus : tout le corpus.")
        self.assertEqual(len(response.context["graph"]["nodes"]), 5)
        self.assertContains(response, 'data-graph-export="graphe-corpus"')

    def test_without_tags_no_selector(self):
        user = get_user_model().objects.create_user("carol")
        UserPublication.objects.create(user=user, publication=self.project)
        self.client.force_login(user)
        response = self.client.get(reverse("corpus_graph"))
        self.assertNotContains(response, 'id="graph-tag"')

    def test_anonymous_is_sent_to_the_login_page(self):
        response = self.client.get(reverse("corpus_graph"), {"tag": "Projet"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_my_references_filtered_by_a_tag_link_to_its_graph(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("corpus"), {"tag": "Projet"})
        self.assertContains(response, reverse("corpus_graph") + "?tag=Projet")


class GraphViewTests(TestCase):
    """The view of a graph chosen in the URL (#195): timeline by default, or network."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("erin")
        cls.source = Publication.objects.create(
            title="Source", publication_date=datetime.date(2020, 1, 1)
        )
        cls.cited = Publication.objects.create(title="Cité")
        CitedReference.objects.create(source=cls.source, target=cls.cited, position=0)
        entry = UserPublication.objects.create(user=cls.user, publication=cls.source)
        tags.tag_entry(entry, "Projet")

    def corpus_page(self, **params):
        self.client.force_login(self.user)
        return self.client.get(reverse("corpus_graph"), params)

    def test_variants_from_the_query_string(self):
        self.assertEqual(graph_layout(QueryDict("")), {"vue": "frise"})
        self.assertEqual(graph_layout(QueryDict("vue=reseau")), {"vue": "reseau"})
        self.assertEqual(kept_params(QueryDict("vue=frise&tag=Projet")), {})
        self.assertEqual(kept_params(QueryDict("vue=reseau&tag=Projet")), {"vue": "reseau"})

    def test_timeline_by_default(self):
        response = self.client.get(reverse("publication_graph", args=[self.source.pk]))
        self.assertEqual(response.context["graph_layout"], {"vue": "frise"})
        self.assertContains(response, 'id="citation-graph-layout"')
        self.assertContains(response, 'id="citation-graph-axis"')
        self.assertContains(response, 'id="citation-graph-band"')
        self.assertContains(response, "Axe horizontal : date de publication")
        self.assertContains(response, '<a href="?vue=reseau"', count=1)
        self.assertContains(response, f'data-graph-export="graphe-publication-{self.source.pk}"')

    def test_network_has_no_time_axis(self):
        response = self.client.get(
            reverse("publication_graph", args=[self.source.pk]), {"vue": "reseau"}
        )
        self.assertEqual(response.context["graph_layout"], {"vue": "reseau"})
        self.assertNotContains(response, 'id="citation-graph-axis"')
        self.assertNotContains(response, 'id="citation-graph-band"')
        self.assertContains(response, "la position ne suit pas la date")
        self.assertContains(
            response, f'data-graph-export="graphe-publication-{self.source.pk}-reseau"'
        )
        # The current choice is marked, the other one leads back to the timeline.
        self.assertContains(response, 'aria-current="true">Réseau</a>')
        self.assertContains(response, '<a href="?vue=frise"', count=1)

    def test_waiting_message_and_tooltip_of_large_graphs(self):
        # #202, #323: both views may be laid out in a Web Worker, with a message in the
        # frame, hidden until then; the hover tooltip is in both views.
        network = self.client.get(
            reverse("publication_graph", args=[self.source.pk]), {"vue": "reseau"}
        )
        timeline = self.client.get(reverse("publication_graph", args=[self.source.pk]))
        for response in (network, timeline):
            self.assertContains(response, "data-graph-waiting", count=1)
            self.assertContains(response, "Disposition du graphe…</p>")
            self.assertContains(response, 'role="status"')
            self.assertContains(response, "data-graph-tooltip", count=1)
            self.assertContains(response, "pointer-events-none absolute z-10")
            # Frosted glass, shared by what floats over the content (ui.GLASS_CLASSES).
            self.assertContains(response, "backdrop-blur-md")

    def test_layout_time_field(self):
        # #323: the time given to the layout, in seconds, in both views, with what says a
        # new layout is being computed.
        for params in ({}, {"vue": "reseau"}):
            response = self.client.get(reverse("publication_graph", args=[self.source.pk]), params)
            self.assertContains(response, '<label for="graph-layout-time"')
            self.assertContains(response, 'min="0.1"')
            self.assertContains(response, 'max="10"')
            self.assertContains(response, 'value="0.1"')
            self.assertContains(response, "data-graph-computing", count=1)
            self.assertContains(response, "Calcul en cours…")

    def test_an_invalid_view_falls_back_to_the_timeline(self):
        response = self.client.get(reverse("base_graph"), {"vue": "cercle"})
        self.assertEqual(response.context["graph_layout"], {"vue": "frise"})
        self.assertContains(response, 'id="citation-graph-axis"')
        self.assertContains(response, 'aria-current="true">Frise</a>')
        self.assertEqual(response.context["graph_kept_params"], {})

    def test_the_links_keep_the_other_parameters(self):
        response = self.corpus_page(tag="Projet")
        self.assertContains(response, 'href="?tag=Projet&amp;vue=reseau"')
        self.assertContains(response, 'href="?tag=Projet&amp;vue=frise"')
        self.assertContains(response, 'data-graph-export="graphe-corpus-tag-projet"')

    def test_the_tag_form_keeps_the_network(self):
        response = self.corpus_page(tag="Projet", vue="reseau")
        self.assertContains(response, '<input type="hidden" name="vue" value="reseau">', html=True)
        self.assertContains(response, 'data-graph-export="graphe-corpus-tag-projet-reseau"')
        self.assertNotContains(self.corpus_page(tag="Projet"), 'type="hidden" name="vue"')


class BaseGraphPlaceTests(TestCase):
    """The graph of the base under « Publications », as that of the authors (#391)."""

    def test_reached_from_the_list_of_publications(self):
        response = self.client.get(reverse("publication_list"))
        self.assertContains(response, f'href="{reverse("base_graph")}"')
        self.assertContains(response, "Graphe des publications")
        self.assertEqual(reverse("base_graph"), "/publications/graph/")

    def test_former_address_redirects(self):
        response = self.client.get("/graph/")
        self.assertRedirects(response, reverse("base_graph"), status_code=301)
