import datetime

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import Author, MetadataConflict
from references.services.conflicts import compare_names
from references.services.names import same_words_up_to_initials

Kind = MetadataConflict.Kind


def name_conflict(current, proposed, author=None):
    return MetadataConflict(
        kind=Kind.ORCID_NAME,
        author=author,
        field="name",
        current_value=current,
        proposed_value=proposed,
        source="orcid",
    )


class SameWordsTests(SimpleTestCase):
    def test_same_words(self):
        for first, second in (
            ("Thomas Thuillier", "Thuillier Thomas"),
            ("E. Fernandez Mora", "Elena Fernandez Mora"),
            ("Jean-Luc Flambard", "Flambard J. L."),
        ):
            with self.subTest(first=first):
                self.assertTrue(same_words_up_to_initials(first, second))

    def test_different_words(self):
        for first, second in (
            ("Thomas Thuillier", "Thomas Simon"),
            ("E. Mora", "Elena Fernandez Mora"),
            ("T. Thuillier", "Elena Thuillier"),
        ):
            with self.subTest(first=first):
                self.assertFalse(same_words_up_to_initials(first, second))


class CompareNamesTests(SimpleTestCase):
    def test_given_name_first(self):
        names = compare_names(name_conflict("Mora, E. Fernandez", "Fernandez Mora, Elena"))
        self.assertEqual((names.current.given, names.current.family), ("E. Fernandez", "Mora"))
        self.assertEqual((names.proposed.given, names.proposed.family), ("Elena", "Fernandez Mora"))

    def test_split_differently(self):
        for current, proposed in (
            ("Mora, E. Fernandez", "Fernandez Mora, Elena"),
            ("Thomas, Thuillier", "Thuillier, Thomas"),
        ):
            with self.subTest(current=current):
                names = compare_names(name_conflict(current, proposed))
                self.assertTrue(names.split_differently)

    def test_another_name(self):
        names = compare_names(name_conflict("Thuillier, Thomas", "Simon, Thomas"))
        self.assertFalse(names.split_differently)


class ConflictsPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        self.client.force_login(self.user)
        author = Author.objects.create(first_name="E. Fernandez", last_name="Mora")
        self.conflict = name_conflict("Mora, E. Fernandez", "Fernandez Mora, Elena", author)
        self.conflict.save()

    def test_names_in_a_table_given_name_first(self):
        response = self.client.get(reverse("conflict_list"))
        self.assertContains(response, '<th scope="col">Prénom</th>', html=True)
        self.assertContains(response, "<td>Fernandez Mora</td>", html=True)
        self.assertContains(response, "Mêmes mots, répartis autrement")
        self.assertNotContains(response, "Fernandez Mora, Elena")

    def test_decision_time_to_the_second(self):
        resolved_at = datetime.datetime(2026, 7, 1, 16, 42, 7, tzinfo=datetime.UTC)
        MetadataConflict.objects.filter(pk=self.conflict.pk).update(
            status=MetadataConflict.Status.KEPT, resolved_at=resolved_at
        )
        response = self.client.get(reverse("conflict_list"))
        self.assertContains(response, "1 juillet 2026 à 18:42:07")  # Paris summer time
