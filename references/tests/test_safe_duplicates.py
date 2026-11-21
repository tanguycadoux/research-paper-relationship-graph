from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import (
    Author,
    AuthorDistinction,
    AuthorMerge,
    AuthorPublication,
    Organization,
    Publication,
)
from references.services.corrections.author_duplicates import duplicate_groups
from references.services.corrections.safe_duplicates import (
    contradicted,
    merge_safe_groups,
    safe_groups,
)
from references.tests.test_page_titles import Headings


def publication(*authors, organizations=()):
    """A publication signed by the authors, each one declaring the organizations."""
    pub = Publication.objects.create(title=" ".join(str(a) for a in authors))
    for order, author in enumerate(authors):
        slot = AuthorPublication.objects.create(publication=pub, author=author, order=order)
        slot.organizations.set(organizations)
    return pub


def author(first_name, last_name="Abbott", orcid=""):
    return Author.objects.create(first_name=first_name, last_name=last_name, orcid=orcid)


def names(groups):
    return [sorted(str(a) for a in group) for group in groups]


class SafeGroupsTests(TestCase):
    def setUp(self):
        self.coauthor = author("Kip", "Thorne")

    def test_same_names_and_a_shared_coauthor(self):
        first, second = author("B. P."), author("B P")
        publication(first, self.coauthor)
        publication(second, self.coauthor)
        [group] = safe_groups(duplicate_groups())
        self.assertEqual(sorted(str(a) for a in group), ["B P Abbott", "B. P. Abbott"])
        self.assertEqual(group.key, f"{first.pk},{second.pk}")
        self.assertTrue(group.shared_coauthor)
        # The rule of the confirmation of one group: the longest given name.
        self.assertEqual(group.merged_values["first_name"], "B. P.")

    def test_same_names_and_a_shared_organization(self):
        cea = Organization.objects.create(name="CEA")
        irfu = Organization.objects.create(name="IRFU")
        irfu.ancestors.set([cea])
        publication(author("Hélène", "Félice"), organizations=[irfu])
        publication(author("helene", "Felice"), organizations=[cea])
        [group] = safe_groups(duplicate_groups())
        self.assertFalse(group.shared_coauthor)
        self.assertEqual([str(o) for o in group.shared_organizations], ["CEA"])

    def test_namesakes_without_a_tie_are_not_safe(self):
        publication(author("B. P."))
        publication(author("B P"))
        self.assertEqual(len(duplicate_groups()), 1)
        self.assertEqual(safe_groups(duplicate_groups()), [])

    def test_compatible_but_different_names_are_not_safe(self):
        publication(author("B."), self.coauthor)
        publication(author("Barry"), self.coauthor)
        self.assertEqual(safe_groups(duplicate_groups()), [])

    def test_two_signatures_of_the_same_publication_are_not_safe(self):
        first, second = author("B. P."), author("B P")
        publication(first, second, self.coauthor)
        self.assertEqual(safe_groups(duplicate_groups()), [])

    def test_every_author_is_tied_to_the_others(self):
        first, second = author("B. P."), author("B P")
        publication(first, self.coauthor)
        publication(second, self.coauthor)
        publication(author("B.P."))
        self.assertEqual(len(duplicate_groups()[0]), 3)
        self.assertEqual(safe_groups(duplicate_groups()), [])

    def test_ties_from_one_author_to_the_next(self):
        other = author("Rainer", "Weiss")
        first, second, third = author("B. P."), author("B P"), author("B.P.")
        publication(first, self.coauthor)
        publication(second, self.coauthor, other)
        publication(third, other)
        self.assertEqual(
            names(safe_groups(duplicate_groups())), [sorted(str(a) for a in (first, second, third))]
        )

    def test_orcids_and_declared_pairs_contradict_a_group(self):
        first, second = author("B. P.", orcid="0000-0001"), author("B P", orcid="0000-0002")
        self.assertTrue(contradicted([first, second], set()))
        second.orcid = ""
        self.assertFalse(contradicted([first, second], set()))
        self.assertTrue(contradicted([first, second], {(first.pk, second.pk)}))


class MergeSafeGroupsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        coauthor = author("Kip", "Thorne")
        self.first, self.second = author("B P"), author("B. P.", orcid="0000-0001")
        publication(self.first, coauthor)
        publication(self.second, coauthor)

    def test_each_group_is_merged_into_its_oldest_author_with_its_trace(self):
        merged = merge_safe_groups(safe_groups(duplicate_groups()), self.user)
        self.assertEqual(len(merged), 1)
        self.assertFalse(Author.objects.filter(pk=self.second.pk).exists())
        self.first.refresh_from_db()
        self.assertEqual((self.first.first_name, self.first.orcid), ("B. P.", "0000-0001"))
        self.assertEqual(self.first.publications.count(), 2)
        trace = AuthorMerge.objects.get()
        self.assertEqual((trace.kept, trace.merged_by), (self.first, self.user))
        self.assertEqual(trace.reason, AuthorMerge.Reason.MANUAL)
        self.assertEqual(trace.absorbed[0]["first_name"], "B. P.")

    def test_a_group_whose_author_has_gone_is_left_aside(self):
        groups = safe_groups(duplicate_groups())
        self.second.delete()
        self.assertEqual(merge_safe_groups(groups, self.user), [])
        self.assertFalse(AuthorMerge.objects.exists())


class SafeGroupsPageTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("alice"))
        coauthor = author("Kip", "Thorne")
        self.first, self.second = author("B P"), author("B. P.")
        publication(self.first, coauthor)
        publication(self.second, coauthor)
        self.merge_url = reverse("author_duplicates_merge")

    def test_duplicates_page_shows_the_safe_groups_first(self):
        response = self.client.get(reverse("author_duplicates"))
        self.assertContains(response, "Groupes sûrs (1)")
        self.assertContains(response, "<li>B. P. Abbott · B P Abbott</li>", html=True)
        self.assertContains(response, f'href="{self.merge_url}"')
        self.assertContains(response, "Fusionner ce groupe…")

    def test_without_safe_group_the_button_stays_disabled(self):
        AuthorDistinction.objects.create(first=self.first, second=self.second)
        response = self.client.get(reverse("author_duplicates"))
        self.assertContains(response, "Groupes sûrs (0)")
        self.assertContains(response, "Aucun groupe sûr.")
        self.assertNotContains(response, f'href="{self.merge_url}"')

    def test_the_summary_merges_nothing(self):
        response = self.client.get(self.merge_url)
        self.assertContains(response, f'name="groups" value="{self.first.pk},{self.second.pk}"')
        self.assertContains(response, "Coauteur commun")
        self.assertEqual(Author.objects.count(), 3)
        headings = Headings(response.content.decode())
        self.assertEqual(
            headings.headings[:2],
            [(1, "Corrections"), (2, "Fusionner les groupes sûrs (1 groupe)")],
        )
        self.assertTrue(headings.title.startswith("Fusionner les groupes sûrs · Corrections · "))

    def test_the_confirmation_merges_the_groups_shown(self):
        key = f"{self.first.pk},{self.second.pk}"
        response = self.client.post(self.merge_url, {"groups": [key]}, follow=True)
        self.assertRedirects(response, reverse("author_duplicates"))
        self.assertContains(response, "1 groupe fusionné (2 auteurs).")
        self.assertFalse(Author.objects.filter(pk=self.second.pk).exists())
        self.assertEqual(AuthorMerge.objects.get().merged_by.username, "alice")

    def test_a_group_not_shown_is_not_merged(self):
        self.client.post(self.merge_url, {})
        self.client.post(self.merge_url, {"groups": [f"{self.first.pk}"]})
        self.assertEqual(Author.objects.count(), 3)

    def test_a_group_no_longer_safe_is_not_merged(self):
        key = f"{self.first.pk},{self.second.pk}"
        AuthorDistinction.objects.create(first=self.first, second=self.second)
        response = self.client.post(self.merge_url, {"groups": [key]}, follow=True)
        self.assertContains(
            response, "1 groupe non fusionné : il a changé depuis le récapitulatif."
        )
        self.assertEqual(Author.objects.count(), 3)

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.merge_url).status_code, 302)
        self.assertEqual(Author.objects.count(), 3)
