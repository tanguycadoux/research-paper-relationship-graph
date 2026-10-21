from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Author, AuthorDistinction
from references.services.author_distinctions import declare_distinct, distinct_pairs
from references.services.author_duplicates import duplicate_groups
from references.services.author_merge import merge_authors


def author(first_name, last_name="Smith", orcid=""):
    return Author.objects.create(first_name=first_name, last_name=last_name, orcid=orcid)


class DeclareDistinctTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")

    def test_pairs_are_stored_once_in_order(self):
        john, j = author("John"), author("J.")
        declare_distinct([j, john], self.user)
        declare_distinct([john, j], self.user)
        self.assertEqual(distinct_pairs(), {(john.pk, j.pk)})
        self.assertEqual(AuthorDistinction.objects.get().declared_by, self.user)

    def test_every_pair_of_a_group(self):
        declare_distinct([author("John"), author("J."), author("Jo")], self.user)
        self.assertEqual(AuthorDistinction.objects.count(), 3)

    def test_declared_pair_is_no_longer_suggested(self):
        john, j = author("John"), author("J.")
        self.assertEqual(len(duplicate_groups()), 1)
        declare_distinct([john, j], self.user)
        self.assertEqual(duplicate_groups(), [])

    def test_other_members_can_still_be_grouped(self):
        john, j, jo = author("John"), author("J."), author("J. A.")
        declare_distinct([john, j], self.user)
        groups = duplicate_groups()
        self.assertEqual(len(groups), 1)
        self.assertIn(jo, groups[0])
        self.assertFalse({john, j} <= set(groups[0]))


class MergeTransfersDistinctionsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        self.kept, self.merged, self.other = author("John"), author("J."), author("James")
        declare_distinct([self.merged, self.other], self.user)
        declare_distinct([self.kept, self.merged], self.user)

    def merge(self):
        values = {"first_name": "John", "last_name": "Smith", "orcid": ""}
        merge_authors(self.kept, [self.merged], values)

    def test_distinction_of_a_merged_author_now_applies_to_the_kept_one(self):
        self.merge()
        self.assertEqual(distinct_pairs(), {(self.kept.pk, self.other.pk)})
        self.assertEqual(AuthorDistinction.objects.get().declared_by, self.user)


class DismissViewTests(TestCase):
    def setUp(self):
        self.john, self.j = author("John"), author("J.")
        self.url = reverse("author_duplicates_dismiss")
        self.client.force_login(get_user_model().objects.create_user("alice"))

    def test_dismiss_the_checked_authors(self):
        response = self.client.post(self.url, {"authors": [self.john.pk, self.j.pk]})
        self.assertRedirects(response, reverse("author_duplicates"))
        self.assertEqual(duplicate_groups(), [])

    def test_at_least_two_authors(self):
        response = self.client.post(self.url, {"authors": [self.john.pk]}, follow=True)
        self.assertContains(response, "Cochez au moins deux auteurs")
        self.assertFalse(AuthorDistinction.objects.exists())

    def test_post_only(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_duplicates_page_offers_the_button(self):
        response = self.client.get(reverse("author_duplicates"))
        self.assertContains(response, f'formaction="{self.url}"')
