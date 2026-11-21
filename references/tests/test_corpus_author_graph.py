"""The graph of the authors of a corpus or of a tag (#422)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Author, CitedReference, UserPublication
from references.services.corpus import tags
from references.services.display.author_graph import LARGE_COLLABORATION, corpus_authors_graph
from references.services.display.author_groups import probable_groups
from references.tests.test_author_graph import links, nodes, publish


class CorpusAuthorsGraphTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice")
        cls.bob = User.objects.create_user("bob")
        cls.ada, cls.alan, cls.grace, cls.edsger, cls.short = (
            Author.objects.create(first_name=first, last_name=last)
            for first, last in [
                ("Ada", "Lovelace"),
                ("Alan", "Turing"),
                ("Grace", "Hopper"),
                ("Edsger", "Dijkstra"),
                ("A", "Lovelace"),
            ]
        )
        cls.project = publish("Projet", cls.ada, cls.alan)
        cls.group = publish("Groupe", cls.short, cls.alan)
        cls.untagged = publish("Sans tag", cls.ada, cls.grace)
        # Only cited by the corpus, and outside it: left out.
        cited = publish("Citée", cls.ada, cls.edsger)
        publish("Ailleurs", cls.alan, cls.edsger)
        CitedReference.objects.create(source=cls.project, target=cited, position=0)
        entries = {
            pub: UserPublication.objects.create(user=cls.alice, publication=pub)
            for pub in (cls.project, cls.group, cls.untagged)
        }
        tags.tag_entry(entries[cls.project], "Projet")
        tags.tag_entry(entries[cls.group], "Projet/Groupe")
        UserPublication.objects.create(user=cls.bob, publication=cited)

    def test_the_authors_of_the_corpus_only(self):
        graph = corpus_authors_graph(self.alice, grouped=False)
        self.assertEqual(
            set(nodes(graph)), {"Ada Lovelace", "A Lovelace", "Alan Turing", "Grace Hopper"}
        )
        # Sizes and links through the publications of the corpus only.
        self.assertEqual(nodes(graph)["Ada Lovelace"]["publications"], 2)
        self.assertEqual(nodes(graph)["Alan Turing"]["publications"], 2)
        self.assertEqual(len(links(graph)), 3)
        self.assertNotIn(frozenset({"Alan Turing", "Edsger Dijkstra"}), links(graph))

    def test_a_tag_and_its_subtags(self):
        graph = corpus_authors_graph(self.alice, "Projet", grouped=False)
        self.assertEqual(set(nodes(graph)), {"Ada Lovelace", "A Lovelace", "Alan Turing"})
        graph = corpus_authors_graph(self.alice, "Projet/Groupe", grouped=False)
        self.assertEqual(set(nodes(graph)), {"A Lovelace", "Alan Turing"})

    def test_another_corpus(self):
        graph = corpus_authors_graph(self.bob)
        self.assertEqual(set(nodes(graph)), {"Ada Lovelace", "Edsger Dijkstra"})

    def test_the_probable_duplicates_gathered(self):
        graph = corpus_authors_graph(self.alice, groups=probable_groups())
        self.assertEqual(graph["groups"], 1)
        ada = nodes(graph)["Ada Lovelace"]
        self.assertEqual(ada["publications"], 3)
        self.assertEqual(
            [(v["label"], v["publications"]) for v in ada["variants"]],
            [("Ada Lovelace", 2), ("A Lovelace", 1)],
        )
        self.assertEqual(links(graph)[frozenset({"Ada Lovelace", "Alan Turing"})], (2.0, 2))

    def test_the_authors_of_large_collaborations_only_are_left_out(self):
        crowd = [Author.objects.create(last_name=f"Auteur {i}") for i in range(LARGE_COLLABORATION)]
        large = publish("Collaboration", self.ada, self.alan, *crowd)
        UserPublication.objects.create(user=self.alice, publication=large)
        graph = corpus_authors_graph(self.alice, grouped=False)
        self.assertNotIn("Auteur 0", nodes(graph))
        self.assertEqual(graph["excluded"], 1)
        self.assertEqual(nodes(graph)["Ada Lovelace"]["publications"], 3)
        self.assertEqual(links(graph)[frozenset({"Ada Lovelace", "Alan Turing"})], (1.0, 1))


class CorpusAuthorsGraphPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = get_user_model().objects.create_user("alice")
        ada = Author.objects.create(first_name="Ada", last_name="Lovelace")
        short = Author.objects.create(first_name="A", last_name="Lovelace")
        alan = Author.objects.create(first_name="Alan", last_name="Turing")
        entries = [
            UserPublication.objects.create(user=cls.alice, publication=publish(title, *people))
            for title, people in [("Projet", (ada, alan)), ("Groupe", (short, alan))]
        ]
        tags.tag_entry(entries[0], "Projet")
        tags.tag_entry(entries[1], "Projet/Groupe")
        cls.url = reverse("corpus_authors_graph")

    def setUp(self):
        self.client.force_login(self.alice)

    def test_logged_in_only(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_the_whole_corpus_gathered(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Les auteurs des publications de mon corpus")
        self.assertContains(response, "2 auteurs, 1 lien de coautorat")
        self.assertContains(response, "Regrouper les doublons probables (1)")
        self.assertContains(response, "Doublons probables regroupés (1)")
        self.assertContains(response, "Auteur du corpus")
        self.assertContains(response, "Taille : nombre de publications dans le corpus")
        self.assertContains(response, 'data-scope="dans le corpus"')
        self.assertContains(response, 'data-graph-export="graphe-auteurs-corpus"')
        self.assertContains(response, 'id="graph-tag"')
        # Mon graphe stays the current entry of the navigation.
        self.assertContains(response, f'href="{reverse("corpus_graph")}"')
        self.assertContains(response, 'aria-current="page">Auteurs</a>')

    def test_a_tag(self):
        response = self.client.get(self.url, {"tag": "Projet"})
        self.assertContains(response, "du tag « Projet » (sous-tags compris)")
        self.assertContains(response, "Auteur du tag")
        self.assertContains(response, 'data-scope="dans ce tag"')
        self.assertContains(response, 'data-graph-export="graphe-auteurs-corpus-tag-projet"')
        self.assertContains(response, f'href="{reverse("corpus_graph")}?tag=Projet"')
        self.assertContains(response, 'href="?tag=Projet&amp;doublons=separes"')

    def test_the_base_as_it_is_keeps_the_tag(self):
        response = self.client.get(self.url, {"tag": "Projet", "doublons": "separes"})
        self.assertContains(response, "3 auteurs, 2 liens de coautorat")
        self.assertContains(response, 'href="?tag=Projet"')
        # The tag selector keeps the choice.
        self.assertContains(response, 'name="doublons" value="separes"')
        self.assertContains(
            response, 'data-graph-export="graphe-auteurs-corpus-tag-projet-doublons-separes"'
        )

    def test_without_any_link_the_choices_stay(self):
        response = self.client.get(self.url, {"tag": "Projet/Groupe", "doublons": "separes"})
        self.assertContains(response, "2 auteurs, 1 lien")
        UserPublication.objects.filter(user=self.alice).delete()
        response = self.client.get(self.url)
        self.assertContains(response, "Aucun coautorat : rien à afficher.")
        self.assertContains(response, 'aria-label="Graphe du corpus"')

    def test_mon_graphe_leads_to_the_authors_of_its_tag(self):
        response = self.client.get(reverse("corpus_graph"), {"tag": "Projet"})
        self.assertContains(response, 'aria-label="Graphe du corpus"')
        self.assertContains(response, f'href="{self.url}?tag=Projet"')
        self.assertContains(response, 'aria-current="page">Publications</a>')

    def test_the_publications_of_the_base_on_the_other_graphs(self):
        response = self.client.get(reverse("authors_graph"))
        self.assertContains(response, 'data-scope="dans la base"')
        self.assertContains(response, "Auteur de la base")
        self.assertNotContains(response, 'aria-label="Graphe du corpus"')
