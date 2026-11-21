from django.template import Context, Template
from django.test import SimpleTestCase

from references.services.corpus.bulk import BulkAddition, BulkTagging
from references.services.corpus.import_reports import headline, in_background
from references.services.display.wording import count, suffix
from references.views.corpus_bulk import addition_report


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


class SuffixTests(SimpleTestCase):
    """Django's pluralize puts 0 in the plural: « 0 publications » (#411)."""

    def test_zero_and_one_take_the_singular(self):
        for number, expected in ((0, ""), (1, ""), (2, "s")):
            with self.subTest(number=number):
                self.assertEqual(suffix(number), expected)

    def test_given_endings(self):
        self.assertEqual(suffix(0, "nt"), "")
        self.assertEqual(suffix(3, "nt"), "nt")
        self.assertEqual(suffix(1, "a,ont"), "a")
        self.assertEqual(suffix(2, "a,ont"), "ont")

    def test_the_filter(self):
        source = (
            "{% load ui %}{{ n }} publication{{ n|pluralize_fr }} ser{{ n|pluralize_fr:'a,ont' }}"
        )
        for number, expected in ((0, "0 publication sera"), (2, "2 publications seront")):
            with self.subTest(number=number):
                self.assertEqual(Template(source).render(Context({"n": number})), expected)
        listed = Template("{% load ui %}{{ items|pluralize_fr }}").render(
            Context({"items": [1, 2]})
        )
        self.assertEqual(listed, "s")


class ImportHeadlineTests(SimpleTestCase):
    """The first line of the import report, without counts at 0 (#411)."""

    def test_queued_publications_are_added(self):
        self.assertEqual(
            headline(2, 2, 0),
            "2 publications ajoutées à votre corpus ; leurs données arrivent en arrière-plan.",
        )
        self.assertEqual(
            headline(1, 1, 0),
            "1 publication ajoutée à votre corpus ; ses données arrivent en arrière-plan.",
        )

    def test_some_queued(self):
        self.assertEqual(
            in_background(3, 1), " ; les données de l'une d'elles arrivent en arrière-plan"
        )
        self.assertEqual(
            in_background(3, 2), " ; les données de 2 d'entre elles arrivent en arrière-plan"
        )

    def test_already_there(self):
        self.assertEqual(
            headline(1, 0, 2),
            "1 publication ajoutée à votre corpus. 2 autres étaient déjà dans votre corpus.",
        )
        self.assertEqual(
            headline(0, 0, 1),
            "Aucune publication ajoutée. 1 publication était déjà dans votre corpus.",
        )
        self.assertEqual(headline(0, 0, 0), "Aucune publication ajoutée.")


class AdditionReportTests(SimpleTestCase):
    """The toast of the bulk addition to the corpus: one sentence (#411)."""

    def test_added_to_read_and_tagged(self):
        result = BulkAddition(added=2, queued=2, tagging=BulkTagging("Essai", tagged=2))
        self.assertEqual(
            addition_report(result, "to_read"),
            "2 publications ajoutées, à lire, taguées « Essai ».",
        )

    def test_read_is_agreed(self):
        one, three = BulkAddition(added=1), BulkAddition(added=3)
        self.assertEqual(addition_report(one, "read"), "1 publication ajoutée, lue.")
        self.assertEqual(addition_report(three, "read"), "3 publications ajoutées, lues.")

    def test_some_covered(self):
        result = BulkAddition(added=2, tagging=BulkTagging("A › B", tagged=1, covered=1))
        self.assertEqual(
            addition_report(result, ""),
            "2 publications ajoutées ; 1 publication taguée « A › B » ; "
            "1 autre avait déjà un tag plus précis.",
        )
