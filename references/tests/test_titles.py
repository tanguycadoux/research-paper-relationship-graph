from django.test import SimpleTestCase, TestCase

from references.models import Publication
from references.services.parser import cited_publications, parse_title
from references.services.titles import clean_title


class CleanTitleTests(SimpleTestCase):
    def test_entities_are_decoded(self):
        self.assertEqual(clean_title("An R&amp;D Program"), "An R&D Program")

    def test_jats_and_mathml_markup_is_removed(self):
        self.assertEqual(
            clean_title("Growth of <i>E. coli</i> in H<sub>2</sub>O <scp>at</scp> 4 K"),
            "Growth of E. coli in H2O at 4 K",
        )
        self.assertEqual(
            clean_title('A <mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML">x</mml:math>'),
            "A x",
        )

    def test_latex_is_kept(self):
        title = r"Towards ${\rm Nb}_{3}{\rm Sn}$ Accelerator Magnets"
        self.assertEqual(clean_title(title), title)

    def test_a_lone_less_than_sign_is_text(self):
        self.assertEqual(clean_title("When T < 4 K and T > 2 K"), "When T < 4 K and T > 2 K")

    def test_spaces_are_collapsed(self):
        self.assertEqual(clean_title("  A\n   title "), "A title")


class ParsedTitlesTests(TestCase):
    def test_publication_title_is_cleaned(self):
        pub = Publication()
        parse_title(pub, {"title": ["An R&amp;D Program for <i>Nb</i>"]})
        self.assertEqual(pub.title, "An R&D Program for Nb")

    def test_cited_publication_title_is_cleaned(self):
        pubs = cited_publications(["10.1000/x"], [{"article-title": "R&amp;D <b>now</b>"}])
        self.assertEqual(pubs["10.1000/x"].title, "R&D now")
