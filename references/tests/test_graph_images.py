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
        with patch(
            "references.services.display.graph_images.render_svg", side_effect=ValueError("x")
        ):
            response = self.generate(Kind.BASE)
        self.assertContains(response, "Le calcul de l&#x27;image a échoué : ValueError : x")

    def test_visitors_see_the_image_but_cannot_start_it(self):
        response = self.client.post(reverse("graph_image_generate", args=[Kind.BASE]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(GraphImage.objects.exists())
        self.assertContains(self.client.get(reverse("base_graph")), "Connectez-vous")

    def test_unknown_kinds_and_missing_images(self):
        self.assertEqual(self.client.get("/graph/image/rien.svg").status_code, 404)
        self.assertEqual(
            self.client.get(reverse("graph_image_svg", args=[Kind.BASE])).status_code, 404
        )


class SmallGraphTests(TestCase):
    def test_a_small_graph_is_still_drawn_in_the_page(self):
        Publication.objects.create(title="Seule")
        response = self.client.get(reverse("base_graph"))
        self.assertIn("graph", response.context)
        self.assertNotIn("large_graph", response.context)
