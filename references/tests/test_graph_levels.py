"""The levels of the citation graphs (#451): level 2, a publication developed or reduced."""

from django.contrib.auth import get_user_model
from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, Publication, UserPublication
from references.services.corpus import tags
from references.services.display.graph import corpus_graph, publication_graph
from references.services.display.graph_levels import Expansion, missing_bibliographies


def cite(source, target, position=0):
    CitedReference.objects.create(source=source, target=target, position=position)


class LevelTests(TestCase):
    """
    start cites ref, which cites old and is cited by other; citer cites start and far;
    ref of level 1 and citer of level 1; old, other and far of level 2.
    """

    @classmethod
    def setUpTestData(cls):
        cls.start, cls.ref, cls.citer, cls.old, cls.other, cls.far = (
            Publication.objects.create(title=title)
            for title in ("Départ", "Réf", "Citant", "Ancienne", "Autre", "Loin")
        )
        cite(cls.start, cls.ref)
        cite(cls.ref, cls.old)
        cite(cls.other, cls.ref)
        cite(cls.citer, cls.start)
        cite(cls.citer, cls.far, position=1)

    def labels(self, graph):
        return {node["data"]["label"]: node["data"] for node in graph["nodes"]}

    def test_level_one_by_default(self):
        nodes = self.labels(publication_graph(self.start))
        self.assertEqual(set(nodes), {"Départ", "Réf", "Citant"})
        self.assertEqual(nodes["Départ"]["level"], 0)
        self.assertEqual(nodes["Réf"]["level"], 1)
        self.assertFalse(nodes["Réf"]["expanded"])
        self.assertNotIn("tooltip", nodes["Réf"])

    def test_level_two_follows_both_ways(self):
        graph = publication_graph(self.start, Expansion(level=2), QueryDict("niveau=2"))
        nodes = self.labels(graph)
        self.assertEqual(set(nodes), {"Départ", "Réf", "Citant", "Ancienne", "Autre", "Loin"})
        self.assertEqual(nodes["Ancienne"]["level"], 2)
        self.assertEqual(nodes["Autre"]["level"], 2)
        self.assertEqual(nodes["Autre"]["role"], "cited")
        self.assertTrue(nodes["Réf"]["expanded"])
        self.assertEqual(nodes["Ancienne"]["tooltip"], "Ancienne\nNiveau 2")
        self.assertEqual(len(graph["edges"]), 5)

    def test_level_two_costs_one_query_more(self):
        with self.assertNumQueries(4):
            publication_graph(self.start, Expansion(level=2))

    def test_one_publication_developed(self):
        expansion = Expansion.of(QueryDict(f"developper={self.ref.pk}"))
        nodes = self.labels(publication_graph(self.start, expansion))
        self.assertEqual(set(nodes), {"Départ", "Réf", "Citant", "Ancienne", "Autre"})
        self.assertTrue(nodes["Réf"]["expanded"])
        self.assertFalse(nodes["Citant"]["expanded"])

    def test_one_publication_reduced_at_level_two(self):
        expansion = Expansion.of(QueryDict(f"niveau=2&reduire={self.ref.pk}"))
        nodes = self.labels(publication_graph(self.start, expansion))
        self.assertEqual(set(nodes), {"Départ", "Réf", "Citant", "Loin"})
        self.assertFalse(nodes["Réf"]["expanded"])

    def test_a_publication_of_level_two_is_not_developed(self):
        expansion = Expansion.of(QueryDict(f"developper={self.old.pk}"))
        nodes = self.labels(publication_graph(self.start, expansion))
        self.assertEqual(set(nodes), {"Départ", "Réf", "Citant"})

    def test_toggle_queries(self):
        query = QueryDict("vue=reseau")
        nodes = self.labels(publication_graph(self.start, Expansion.of(query), query))
        develop = QueryDict(nodes["Réf"]["toggle"])
        self.assertEqual(develop["developper"], str(self.ref.pk))
        self.assertEqual(develop["noeud"], str(self.ref.pk))
        self.assertEqual(develop["vue"], "reseau")
        # Developed, the same link reduces it again.
        nodes = self.labels(publication_graph(self.start, Expansion.of(develop), develop))
        self.assertNotIn("developper", QueryDict(nodes["Réf"]["toggle"]))
        level_two = QueryDict("niveau=2")
        nodes = self.labels(publication_graph(self.start, Expansion.of(level_two), level_two))
        reduce = QueryDict(nodes["Réf"]["toggle"])
        self.assertEqual(reduce["reduire"], str(self.ref.pk))
        self.assertNotIn("toggle", nodes["Ancienne"])
        self.assertNotIn("toggle", nodes["Départ"])

    def test_corpus_at_level_two(self):
        user = get_user_model().objects.create_user("alice")
        UserPublication.objects.create(user=user, publication=self.start)
        level_one = self.labels(corpus_graph(user))
        self.assertEqual(set(level_one), {"Départ", "Réf"})
        level_two = self.labels(corpus_graph(user, expansion=Expansion(level=2)))
        # The references of the references and the publications citing them.
        self.assertEqual(set(level_two), {"Départ", "Réf", "Ancienne", "Autre"})

    def test_missing_bibliographies(self):
        self.ref.doi = "10.1/ref"
        self.ref.save()
        nobody = Publication.objects.create(title="Sans bibliographie", doi="10.1/vide")
        cite(self.start, nobody, position=1)
        # ref has a bibliography: only nobody lacks one, at level 2 only.
        self.assertEqual(missing_bibliographies(publication_graph(self.start)), [])
        graph = publication_graph(self.start, Expansion(level=2))
        self.assertEqual(missing_bibliographies(graph), [(2, 1)])


class LevelPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("bob")
        make = Publication.objects.create
        cls.start, cls.ref = make(title="Départ"), make(title="Réf")
        cls.old = make(title="Ancienne", doi="10.1/ancienne")
        cls.lacking = make(title="Sans bibliographie", doi="10.1/vide")
        cite(cls.start, cls.ref)
        cite(cls.ref, cls.old)
        cite(cls.start, cls.lacking, position=1)
        entry = UserPublication.objects.create(user=cls.user, publication=cls.start)
        tags.tag_entry(entry, "Projet")

    def test_level_choice_in_the_panel(self):
        response = self.client.get(reverse("publication_graph", args=[self.start.pk]))
        self.assertContains(response, "Niveau</span>")
        self.assertContains(response, '<a href="?niveau=2"')
        self.assertContains(response, 'aria-current="true">1</a>')
        self.assertContains(response, 'data-card="develop"')
        self.assertNotContains(response, "Niveau 2 : reliée")

    def test_level_two_page(self):
        response = self.client.get(
            reverse("publication_graph", args=[self.start.pk]), {"niveau": "2"}
        )
        self.assertEqual(len(response.context["graph"]["nodes"]), 4)
        self.assertContains(response, 'aria-current="true">2</a>')
        self.assertContains(response, "Niveau 2 : reliée à une publication du niveau 1")

    def test_changing_the_level_forgets_the_developed_publications(self):
        response = self.client.get(
            reverse("publication_graph", args=[self.start.pk]),
            {"developper": self.ref.pk, "noeud": self.ref.pk},
        )
        self.assertContains(response, '<a href="?niveau=2"')

    def test_missing_bibliographies_and_their_request(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("corpus_graph"), {"tag": "Projet", "niveau": "2"})
        self.assertContains(response, "1 bibliographie manque pour le niveau 2.")
        url = reverse("bibliography_request") + "?depth=2&amp;tag=Projet"
        self.assertContains(response, f'href="{url}"')
        # The tag form keeps the level.
        self.assertContains(response, '<input type="hidden" name="niveau" value="2">', html=True)

    def test_anonymous_sees_the_missing_bibliographies_without_the_request(self):
        response = self.client.get(
            reverse("publication_graph", args=[self.start.pk]), {"niveau": "2"}
        )
        self.assertContains(response, "1 bibliographie manque pour le niveau 2.")
        self.assertNotContains(response, "Récupérer les bibliographies")

    def test_the_base_graph_has_no_level(self):
        response = self.client.get(reverse("base_graph"))
        self.assertNotContains(response, "Niveau</span>")
        self.assertNotContains(response, 'data-card="develop"')
