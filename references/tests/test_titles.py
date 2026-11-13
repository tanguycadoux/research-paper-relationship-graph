from django.test import SimpleTestCase, TestCase

from references.models import Publication
from references.services.imports.parser import cited_publications, parse_title
from references.services.imports.titles import clean_title


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

    def test_markup_escaped_twice_is_removed(self):
        # Crossref title of 10.1109/tasc.2015.2510508, as deposited by IEEE (#263).
        raw = (
            "Development of MQXF: The Nb&lt;sub&gt;3&lt;/sub&gt;Sn Low-&lt;inline-formula&gt; "
            '&lt;tex-math notation="LaTeX"&gt;$\\beta$&lt;/tex-math&gt;&lt;/inline-formula&gt; '
            "Quadrupole for the HiLumi LHC"
        )
        self.assertEqual(
            clean_title(raw),
            "Development of MQXF: The Nb3Sn Low- $\\beta$ Quadrupole for the HiLumi LHC",
        )

    def test_entity_escaped_twice_is_decoded(self):
        self.assertEqual(clean_title("An R&amp;amp;D Program"), "An R&D Program")

    def test_a_lone_less_than_sign_escaped_is_text(self):
        self.assertEqual(clean_title("When T &lt; 4 K"), "When T < 4 K")

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


class StoredTitlesMigrationTests(TestCase):
    """Migration 0029 (#263): titles stored with the markup of a title escaped twice."""

    def run_migration(self):
        from importlib import import_module

        from django.apps import apps

        import_module("references.migrations.0029_clean_double_escaped_titles").clean_titles(
            apps, None
        )

    def test_markup_left_in_a_stored_title_is_removed(self):
        pub = Publication.objects.create(title="The Nb<sub>3</sub>Sn Low-<inline-formula> x")
        self.run_migration()
        pub.refresh_from_db()
        self.assertEqual(pub.title, "The Nb3Sn Low- x")

    def test_a_title_corrected_by_hand_is_kept(self):
        pub = Publication.objects.create(title="My <sub>own</sub> title", title_edited=True)
        self.run_migration()
        pub.refresh_from_db()
        self.assertEqual(pub.title, "My <sub>own</sub> title")
