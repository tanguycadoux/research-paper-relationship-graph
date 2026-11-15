from django.test import SimpleTestCase

from references.services.display.wording import count


class CountTests(SimpleTestCase):
    """Messages agreed with their number, not « publication(s) » (#346)."""

    def test_zero_and_one_take_the_singular(self):
        self.assertEqual(count(0, "publication ajoutée"), "0 publication ajoutée")
        self.assertEqual(count(1, "entrée ignorée"), "1 entrée ignorée")

    def test_the_plural_adds_an_s_to_each_word(self):
        self.assertEqual(count(3, "publication ajoutée"), "3 publications ajoutées")

    def test_a_given_plural(self):
        plural = "publications qui citent"
        self.assertEqual(count(2, "publication qui cite", plural), "2 publications qui citent")
        self.assertEqual(count(1, "publication qui cite", plural), "1 publication qui cite")
