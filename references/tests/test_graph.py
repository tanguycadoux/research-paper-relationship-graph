from django.test import SimpleTestCase

from references.services.graph import map_value


class MapValueTests(SimpleTestCase):
    def test_maps_linearly(self):
        self.assertEqual(map_value(5, 0, 10, 25, 75), 50)

    def test_degenerate_range_returns_the_middle(self):
        self.assertEqual(map_value(1, 1, 1, 25, 75), 50)
