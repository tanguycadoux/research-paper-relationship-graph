import math
from itertools import combinations

from django.test import SimpleTestCase

from references.services.display.large_graph_layout import NODE_GAP, positions


def star_and_clique():
    """A node cited by 30 leaves and linked to a clique of 5, plus a pair and a lonely node."""
    edges = [(0, leaf, 1) for leaf in range(1, 31)]
    clique = range(31, 36)
    edges += [(a, b, 1 + (a + b) % 3) for a, b in combinations(clique, 2)]
    edges += [(0, 31, 1), (36, 37, 1)]
    return 39, edges, [6] + [3] * 38


class LargeGraphLayoutTests(SimpleTestCase):
    """The layout of the images of the large graphs (#420)."""

    def test_the_leaves_ring_their_node(self):
        count, edges, radii = star_and_clique()
        points, *_ = positions(count, edges, radii)
        distances = sorted(math.dist(points[0], points[leaf]) for leaf in range(1, 31))
        # In rings: a few distinct distances, the first beyond the node.
        self.assertLessEqual(len({round(distance) for distance in distances}), 3)
        self.assertGreater(distances[0], radii[0] + radii[1])

    def test_no_two_nodes_overlap(self):
        count, edges, radii = star_and_clique()
        points, *_ = positions(count, edges, radii)
        for a, b in combinations(range(count), 2):
            with self.subTest(a=a, b=b):
                self.assertGreater(math.dist(points[a], points[b]), radii[a] + radii[b])

    def test_the_heart_keeps_clear_of_the_crown(self):
        count, edges, radii = star_and_clique()
        points, *_ = positions(count, edges, radii)
        crown = max(math.dist(points[0], points[leaf]) for leaf in range(1, 31))
        for node in range(31, 36):
            self.assertGreater(math.dist(points[0], points[node]), crown + NODE_GAP / 2)

    def test_the_same_graph_gives_the_same_image(self):
        count, edges, radii = star_and_clique()
        self.assertEqual(positions(count, edges, radii), positions(count, edges, radii))

    def test_the_drawing_fits_in_the_image(self):
        count, edges, radii = star_and_clique()
        points, width, height, caption, alone = positions(count, edges, radii)
        self.assertEqual(alone, 1)
        self.assertIsNotNone(caption)
        for (x, y), radius in zip(points, radii, strict=True):
            self.assertTrue(0 <= x - radius and x + radius <= width)
            self.assertTrue(0 <= y - radius <= height)
