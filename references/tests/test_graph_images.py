from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from references.models import (
    Author,
    AuthorPublication,
    CitedReference,
    GraphImage,
    Publication,
)
from references.services.display import graph_images

Kind = GraphImage.Kind


def at_once(function, *args):
    """Instead of a thread: the test sees the result at once."""
    function(*args)


@patch("references.services.display.graph_images.run_in_background", at_once)
@patch("references.services.display.graph_images.LARGE_GRAPH", 2)
class GraphImageTests(TestCase):
    """Graphs too large for the page: their full image, computed in the background (#328)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("paul")
        pubs = [Publication.objects.create(title=f"Article {i}") for i in range(4)]
        CitedReference.objects.create(source=pubs[0], target=pubs[1], position=0)
        CitedReference.objects.create(source=pubs[0], target=pubs[2], position=1)
        people = [
            Author.objects.create(first_name="A", last_name=name)
            for name in ("Lovelace", "Turing", "<Hopper>", "Seule")
        ]
        for order, person in enumerate(people[:3]):
            AuthorPublication.objects.create(publication=pubs[0], author=person, order=order)
        AuthorPublication.objects.create(publication=pubs[3], author=people[3], order=0)

    def generate(self, kind):
        self.client.force_login(self.user)
        return self.client.post(reverse("graph_image_generate", args=[kind]), follow=True)

    def test_a_large_graph_is_not_drawn_but_offered_as_an_image(self):
        for name, kind in (("authors_graph", Kind.AUTHORS), ("base_graph", Kind.BASE)):
            with self.subTest(kind=kind):
                response = self.client.get(reverse(name))
                self.assertNotIn("graph", response.context)
                self.assertEqual(response.context["large_graph"]["kind"], kind)
                self.assertContains(response, "trop pour être dessiné")

    def test_the_image_is_computed_and_served(self):
        response = self.generate(Kind.AUTHORS)
        self.assertRedirects(response, reverse("authors_graph"))
        image = GraphImage.objects.get(kind=Kind.AUTHORS)
        self.assertEqual((image.status, image.nodes, image.edges), ("done", 4, 3))
        self.assertContains(response, "Ouvrir l'image complète")
        svg = self.client.get(reverse("graph_image_svg", args=[Kind.AUTHORS]))
        self.assertEqual(svg["Content-Type"], "image/svg+xml; charset=utf-8")
        self.assertIn("default-src 'none'", svg["Content-Security-Policy"])
        content = svg.content.decode()
        self.assertTrue(content.startswith("<svg"))
        # Each node links to its page; names are escaped.
        self.assertIn(
            f'href="{reverse("author_detail", args=[Author.objects.get(last_name="Turing").pk])}"',
            content,
        )
        self.assertIn("&lt;Hopper&gt;", content)
        self.assertNotIn("<Hopper>", content)
        # The author without link is in the grid, under its caption.
        self.assertIn("1 auteur sans lien", content)

    def test_the_image_comes_with_the_list_of_its_nodes(self):
        self.generate(Kind.AUTHORS)
        listed = self.client.get(reverse("graph_image_nodes", args=[Kind.AUTHORS])).json()
        names = [node[0] for node in listed["nodes"]]
        self.assertCountEqual(names, ["A Lovelace", "A Turing", "A <Hopper>", "A Seule"])
        turing = listed["nodes"][names.index("A Turing")]
        author = Author.objects.get(last_name="Turing")
        self.assertEqual(turing[1:3], [1, reverse("author_detail", args=[author.pk])])
        # The three co-authors of the first article, linked two by two.
        self.assertEqual(len(listed["edges"]), 6)
        content = self.client.get(reverse("graph_image_svg", args=[Kind.AUTHORS])).content
        # Each circle is the node of its rank in the list, at its place.
        rank = names.index("A Turing")
        x, y, r = turing[3:]
        self.assertIn(
            f'data-node="{rank}" cx="{x - 40:.1f}" cy="{y - 80:.1f}" r="{r:.1f}"', content.decode()
        )

    def test_the_page_that_browses_the_image(self):
        self.generate(Kind.AUTHORS)
        response = self.client.get(reverse("graph_image_viewer", args=[Kind.AUTHORS]))
        self.assertContains(response, "<title>Image complète · Graphe des auteurs · Base commune")
        self.assertContains(response, reverse("graph_image_nodes", args=[Kind.AUTHORS]))
        self.assertContains(response, "references/graph/image_viewer.js")
        self.assertContains(response, "Chercher parmi les auteurs")
        # The selection, above the list of all the nodes: empty, its button disabled.
        content = response.content.decode()
        self.assertLess(content.index("data-image-selection"), content.index("data-image-search"))
        self.assertContains(response, "Aucune sélection")
        self.assertRegex(content, r"<button[^>]*\sdisabled[^>]*>\s*Tout désélectionner\s*</button>")
        # The name of a row selects its node: no link to its page in the list.
        self.assertNotIn("data-row-name href", content)
        # The page fits in the window from lg; the other pages grow with their content.
        self.assertContains(response, "lg:h-dvh")
        page = self.client.get(reverse("authors_graph"))
        self.assertNotContains(page, "h-dvh")
        # The graph page leads to it.
        self.assertContains(page, reverse("graph_image_viewer", args=[Kind.AUTHORS]))

    def test_an_image_drawn_before_the_list_cannot_be_browsed(self):
        self.generate(Kind.BASE)
        GraphImage.objects.filter(kind=Kind.BASE).update(node_list="")
        response = self.client.get(reverse("graph_image_viewer", args=[Kind.BASE]))
        self.assertContains(response, "recalculez-la")
        self.assertNotContains(response, "image_viewer.js")
        self.assertContains(response, reverse("graph_image_svg", args=[Kind.BASE]))

    def test_the_graph_of_the_base_too(self):
        self.generate(Kind.BASE)
        image = GraphImage.objects.get(kind=Kind.BASE)
        self.assertEqual((image.status, image.nodes, image.edges), ("done", 4, 2))

    def test_an_image_is_old_once_the_base_changes(self):
        self.generate(Kind.BASE)
        self.assertFalse(graph_images.image_state(Kind.BASE)["outdated"])
        Publication.objects.create(title="Nouvelle")
        self.assertTrue(graph_images.image_state(Kind.BASE)["outdated"])

    def test_a_computation_is_not_started_twice(self):
        GraphImage.objects.create(kind=Kind.BASE, status="pending", requested_at=timezone.now())
        self.assertFalse(graph_images.request_image(Kind.BASE, self.user))
        # Unless it died with its thread long ago.
        GraphImage.objects.filter(kind=Kind.BASE).update(
            requested_at=timezone.now() - graph_images.STUCK_AFTER * 2
        )
        self.assertTrue(graph_images.request_image(Kind.BASE, self.user))

    def test_while_computing_the_page_asks_for_the_state(self):
        GraphImage.objects.create(kind=Kind.BASE, status="pending", requested_at=timezone.now())
        response = self.client.get(reverse("base_graph"))
        self.assertContains(response, "js/graph_image.js")
        self.assertContains(response, reverse("graph_image_status", args=[Kind.BASE]))
        state = self.client.get(reverse("graph_image_status", args=[Kind.BASE])).json()
        self.assertEqual(state, {"pending": True})

    def test_a_failure_is_shown(self):
        with patch("references.services.display.graph_images.render", side_effect=ValueError("x")):
            response = self.generate(Kind.BASE)
        self.assertContains(response, "Le calcul de l&#x27;image a échoué : ValueError : x")

    def test_visitors_see_the_image_but_cannot_start_it(self):
        response = self.client.post(reverse("graph_image_generate", args=[Kind.BASE]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(GraphImage.objects.exists())
        self.assertContains(self.client.get(reverse("base_graph")), "Connectez-vous")

    def test_unknown_kinds_and_missing_images(self):
        self.assertEqual(self.client.get("/graph/image/rien.svg").status_code, 404)
        for name in ("graph_image_svg", "graph_image_viewer", "graph_image_nodes"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name, args=[Kind.BASE]))
                self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get("/graph/image/rien/").status_code, 404)


class SmallGraphTests(TestCase):
    def test_a_small_graph_is_still_drawn_in_the_page(self):
        Publication.objects.create(title="Seule")
        response = self.client.get(reverse("base_graph"))
        self.assertIn("graph", response.context)
        self.assertNotIn("large_graph", response.context)
