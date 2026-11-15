import re

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import Publication
from references.services.display.search import filter_publications, parse
from references.services.imports.parser import cited_publications, parse_title
from references.services.imports.titles import clean_title, readable_title

# Titles of the base written in LaTeX by their publisher (#264).
LATEX_TITLES = {
    r"An R&D Program Towards ${\rm Nb}_{3}{\rm Sn}$ Accelerator Magnets": (
        "An R&D Program Towards Nb₃Sn Accelerator Magnets"
    ),
    r"Mechanical Behavior of HQ01, a ${\hbox{Nb}}_{3}\hbox{Sn}$ Accelerator-Quality "
    r"Quadrupole": "Mechanical Behavior of HQ01, a Nb₃Sn Accelerator-Quality Quadrupole",
    r"Mechanical Performance of the LARP Nb$_{3}$Sn Quadrupole Magnet LQS01": (
        "Mechanical Performance of the LARP Nb₃Sn Quadrupole Magnet LQS01"
    ),
    # 10.1109/tasc.2015.2510508, once its markup escaped twice is removed (#263).
    r"Development of MQXF: The Nb3Sn Low- $\beta$ Quadrupole for the HiLumi LHC": (
        "Development of MQXF: The Nb3Sn Low- β Quadrupole for the HiLumi LHC"
    ),
}


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


class ReadableTitleTests(SimpleTestCase):
    def test_titles_of_the_base(self):
        for title, readable in LATEX_TITLES.items():
            with self.subTest(title=title):
                self.assertEqual(readable_title(title), readable)

    def test_title_without_latex_is_unchanged(self):
        for title in ("Deep learning", "Cost of $100 magnets", ""):
            with self.subTest(title=title):
                self.assertEqual(readable_title(title), title)

    def test_scripts_symbols_and_text_commands(self):
        self.assertEqual(readable_title(r"MgB$_2$ wires at $10^{-3}$ Pa"), "MgB₂ wires at 10⁻³ Pa")
        self.assertEqual(readable_title(r"A $90^\circ$ bend, $\pm 5\%$"), "A 90° bend, ± 5%")
        self.assertEqual(readable_title(r"The \textit{in situ} method"), "The in situ method")
        self.assertEqual(readable_title(r"$\Delta T \sim 2$ K"), "Δ T ∼ 2 K")

    def test_formula_that_cannot_be_rendered_whole_is_kept(self):
        for title in (
            r"A $\sqrt{x}$ formula",  # unknown command
            r"T$_c$ of a superconductor",  # no subscript c in Unicode
            r"B$^*$ mesons",  # no superscript star
            r"\'Etude des aimants",  # accent outside the known commands
        ):
            with self.subTest(title=title):
                self.assertEqual(readable_title(title), title)


class TitleMarkupLeftTests(SimpleTestCase):
    """Markup left after #264 (#345)."""

    def test_each_formula_on_its_own(self):
        self.assertEqual(
            readable_title(
                r"$J_{C}(B,T,\varepsilon)$ Parameterization for the ITER ${\rm Nb}_{3}{\rm Sn}$ "
                "Production"
            ),
            r"$J_{C}(B,T,\varepsilon)$ Parameterization for the ITER Nb₃Sn Production",
        )
        self.assertEqual(
            readable_title(r"A $\sqrt{x}$ formula with $\beta$"), r"A $\sqrt{x}$ formula with β"
        )

    def test_commands_without_their_backslash_and_spaces_dropped(self):
        self.assertEqual(
            readable_title("a 90 mm$hboxNb_3hboxSn$Model Quadrupole"),
            "a 90 mm Nb₃Sn Model Quadrupole",
        )
        self.assertEqual(
            readable_title("Installation of the LHC Low-$beta$Triplets"),
            "Installation of the LHC Low-β Triplets",
        )

    def test_a_subscript_stays_inside_its_word(self):
        self.assertEqual(readable_title(r"La$_{2-x}$Sr$_x$CuO$_4$ films"), "La₂₋ₓSrₓCuO₄ films")
        self.assertEqual(readable_title(r"LARP Nb$_{3}$Sn Quadrupole"), "LARP Nb₃Sn Quadrupole")

    def test_old_ieee_markup(self):
        self.assertEqual(
            readable_title("the MQXA series of LHC low-/spl beta/ insertion quadrupoles"),
            "the MQXA series of LHC low-β insertion quadrupoles",
        )
        self.assertEqual(readable_title("YBa/sub 2/Cu/sub 3/O/sub 7/ tapes"), "YBa₂Cu₃O₇ tapes")
        self.assertEqual(readable_title("Fields of 10/sup 3/ T"), "Fields of 10³ T")

    def test_a_greek_word_outside_a_formula_is_text(self):
        self.assertEqual(
            readable_title(r"The beta function at $10^{3}$ T"), "The beta function at 10³ T"
        )


class ReadableTitleFieldTests(TestCase):
    TITLE = r"Mechanical Performance of the LARP Nb$_{3}$Sn Quadrupole Magnet LQS01"
    READABLE = "Mechanical Performance of the LARP Nb₃Sn Quadrupole Magnet LQS01"

    def test_filled_on_save_and_shown(self):
        pub = Publication.objects.create(title=self.TITLE)
        self.assertEqual(pub.readable_title, self.READABLE)
        self.assertEqual(str(pub), self.READABLE)
        pub.title = "Plain"
        pub.save(update_fields=["title"])
        pub.refresh_from_db()
        self.assertEqual(pub.readable_title, "Plain")

    def test_filled_by_bulk_writes(self):
        cited = cited_publications(["10.1000/x"], [{"article-title": self.TITLE}])["10.1000/x"]
        cited.refresh_from_db()
        self.assertEqual(cited.readable_title, self.READABLE)
        cited.title = r"MgB$_2$"
        Publication.objects.bulk_update([cited], ["title"])
        cited.refresh_from_db()
        self.assertEqual(cited.readable_title, "MgB₂")

    def test_source_title_kept_for_editing(self):
        pub = Publication.objects.create(title=self.TITLE)
        user = get_user_model().objects.create_user("u", password="p")
        self.client.force_login(user)
        page = self.client.get(reverse("publication_detail", args=[pub.pk])).content.decode()
        # Only the BibTeX entry of « Citer » keeps the LaTeX, which BibTeX reads (#286).
        self.assertIn("Nb$_{3}$Sn", re.search(r'<pre id="citation-bibtex".*?</pre>', page, re.S)[0])
        page = re.sub(r'<pre id="citation-bibtex".*?</pre>', "", page, flags=re.S)
        self.assertIn(self.READABLE, page)
        self.assertNotIn("$_{3}$", page)
        edit = self.client.get(reverse("publication_edit", args=[pub.pk])).content.decode()
        self.assertIn("Nb$_{3}$Sn", edit)

    def test_search_finds_every_form_of_nb3sn(self):
        expected = {Publication.objects.create(title=title) for title in LATEX_TITLES}
        Publication.objects.create(title="Deep learning")
        found = set(filter_publications(Publication.objects.all(), parse("Nb3Sn")))
        self.assertEqual(found, expected)


class ReadableTitlesMigrationTests(TestCase):
    """Migration 0031 (#264): the readable title of the publications already in base."""

    def test_readable_titles_are_filled(self):
        from importlib import import_module

        from django.apps import apps

        pub = Publication.objects.create(title=r"${\rm Nb}_{3}{\rm Sn}$ magnets")
        Publication.objects.filter(pk=pub.pk).update(readable_title="")
        import_module("references.migrations.0031_publication_readable_title").fill_readable_titles(
            apps, None
        )
        pub.refresh_from_db()
        self.assertEqual(pub.readable_title, "Nb₃Sn magnets")


class ReadableTitlesAgainMigrationTests(TestCase):
    """Migration 0034 (#345): the readable titles computed again."""

    def test_readable_titles_are_computed_again(self):
        from importlib import import_module

        from django.apps import apps

        pub = Publication.objects.create(title="a 90 mm$hboxNb_3hboxSn$Model Quadrupole")
        plain = Publication.objects.create(title="Deep learning")
        Publication.objects.update(readable_title="old")
        import_module("references.migrations.0034_readable_titles_again").refill_readable_titles(
            apps, None
        )
        pub.refresh_from_db()
        plain.refresh_from_db()
        self.assertEqual(pub.readable_title, "a 90 mm Nb₃Sn Model Quadrupole")
        self.assertEqual(plain.readable_title, "old")  # not touched: no markup
