from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import Author
from references.services.author_duplicates import compatible_given_names, duplicate_groups


class CompatibleGivenNamesTests(SimpleTestCase):
    def test_compatible(self):
        for first, second in [
            ("A.", "Ada"),
            ("J.-L.", "Jean Luc"),
            ("J. S.", "Josiah Stinkney"),
            ("J.C.", "Juan Carlos"),
            ("Juan C.", "Juan Carlos"),
            ("S. O.", "Soren"),
            ("Francois", "François"),
            ("T", "T."),
        ]:
            with self.subTest(first=first, second=second):
                self.assertTrue(compatible_given_names(first, second))

    def test_incompatible(self):
        for first, second in [("Jean Luc", "Jean Pierre"), ("John", "James"), ("A.", "B.")]:
            with self.subTest(first=first, second=second):
                self.assertFalse(compatible_given_names(first, second))


def names(group):
    return [str(author) for author in group]


class DuplicateGroupsTests(TestCase):
    def author(self, first_name, last_name, orcid=""):
        return Author.objects.create(first_name=first_name, last_name=last_name, orcid=orcid)

    def test_same_family_and_compatible_given_names(self):
        self.author("Ada", "Lovelace")
        self.author("A.", "LOVELACE")
        self.author("Alan", "Turing")
        self.assertEqual(
            [sorted(names(g)) for g in duplicate_groups()], [["A. LOVELACE", "Ada Lovelace"]]
        )

    def test_accents_are_ignored_in_family_names(self):
        self.author("Jose", "Pérez")
        self.author("J.", "Perez")
        self.assertEqual(len(duplicate_groups()), 1)

    def test_different_orcids_are_never_grouped(self):
        self.author("Ada", "Lovelace", "0000-0001")
        self.author("A.", "Lovelace", "0000-0002")
        self.assertEqual(duplicate_groups(), [])

    def test_an_initial_is_not_a_bridge_between_two_given_names(self):
        self.author("John", "Smith")
        self.author("James", "Smith")
        self.author("J.", "Smith")
        groups = duplicate_groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 2)

    def test_groups_form_around_the_author_with_an_orcid(self):
        self.author("J.", "Smith")
        self.author("John", "Smith", "0000-0001")
        self.assertEqual(duplicate_groups()[0][0].orcid, "0000-0001")

    def test_groups_with_one_orcid_come_first(self):
        self.author("A.", "Lovelace")
        self.author("Ada", "Lovelace")
        self.author("C.", "Babbage")
        self.author("Charles", "Babbage", "0000-0003")
        self.assertEqual(duplicate_groups()[0][0].last_name, "Babbage")

    def test_authors_without_given_name_are_ignored(self):
        self.author("", "CERN")
        self.author("", "CERN")
        self.assertEqual(duplicate_groups(), [])


class DuplicatesPageTests(TestCase):
    def setUp(self):
        self.ada = Author.objects.create(first_name="Ada", last_name="Lovelace", orcid="0000-0001")
        self.initial = Author.objects.create(first_name="A.", last_name="Lovelace")
        self.client.force_login(get_user_model().objects.create_user("alice"))

    def test_page_lists_the_groups(self):
        response = self.client.get(reverse("author_duplicates"))
        self.assertContains(response, "Ada Lovelace")
        self.assertContains(response, f'value="{self.initial.pk}"')

    def test_group_form_leads_to_the_merge_confirmation(self):
        response = self.client.post(
            reverse("author_merge_select"), {"authors": [self.ada.pk, self.initial.pk]}
        )
        ids = response.url.rstrip("/").rsplit("/", 1)[-1]
        self.assertEqual(sorted(ids.split(",")), sorted([str(self.ada.pk), str(self.initial.pk)]))
        self.assertEqual(self.client.get(response.url).status_code, 200)


class SameOrcidTests(TestCase):
    def test_same_orcid_is_grouped_whatever_the_given_names(self):
        Author.objects.create(first_name="Helene", last_name="Felice", orcid="0000-0002")
        Author.objects.create(first_name="Hélène M.", last_name="Felice", orcid="0000-0002")
        Author.objects.create(first_name="Harry", last_name="Felice", orcid="0000-0002")
        self.assertEqual(len(duplicate_groups()[0]), 3)

    def test_hyphens_in_family_names_are_ignored(self):
        Author.objects.create(first_name="R.", last_name="Correia-Machado", orcid="0000-0001")
        Author.objects.create(first_name="R.", last_name="Correia Machado")
        self.assertEqual(len(duplicate_groups()), 1)
