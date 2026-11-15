from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.http import urlencode

from references.models import Author
from references.views.authors import MERGE_PAGE_SIZE


class AuthorMergeSelectTests(TestCase):
    """Choose the authors to merge by a search, the choice kept on top (#271)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("olga")
        cls.ada = Author.objects.create(first_name="Ada", last_name="Lovelace", orcid="0000-0001")
        cls.initial = Author.objects.create(first_name="A.", last_name="Lovelace")
        cls.alan = Author.objects.create(first_name="Alan", last_name="Turing")
        Author.objects.bulk_create(
            Author(first_name=f"P{i}", last_name=f"Zed{i:03d}") for i in range(MERGE_PAGE_SIZE)
        )

    def setUp(self):
        self.client.force_login(self.user)

    def get(self, **params):
        return self.client.get(reverse("author_merge_select"), params)

    def test_without_search_one_page_only(self):
        response = self.get()
        self.assertEqual(len(response.context["authors"]), MERGE_PAGE_SIZE)
        self.assertEqual(response.context["page_obj"].paginator.count, MERGE_PAGE_SIZE + 3)

    def test_search_by_name_or_orcid(self):
        names = lambda response: [a.pk for a in response.context["authors"]]  # noqa: E731
        self.assertEqual(
            sorted(names(self.get(q="lovelace"))), sorted([self.ada.pk, self.initial.pk])
        )
        self.assertEqual(names(self.get(q="0000-0001")), [self.ada.pk])

    def test_the_selection_stays_on_top_and_out_of_the_results(self):
        response = self.get(q="lovelace", selected=f"{self.ada.pk}")
        self.assertEqual(response.context["selected"], [self.ada])
        self.assertEqual([a.pk for a in response.context["authors"]], [self.initial.pk])
        # Adding keeps the search and the selection.
        self.assertContains(
            response, f'href="?q=lovelace&amp;selected={self.ada.pk}%2C{self.initial.pk}"'
        )

    def test_two_authors_lead_to_the_confirmation(self):
        response = self.get(selected=f"{self.ada.pk}")
        self.assertEqual(response.context["confirm_url"], "")
        self.assertContains(response, "disabled")
        response = self.get(selected=f"{self.ada.pk},{self.initial.pk}")
        confirm = reverse("author_merge_confirm", args=[f"{self.ada.pk},{self.initial.pk}"])
        self.assertEqual(response.context["confirm_url"], f"{confirm}?next=%2Fauthors%2Fmerge%2F")

    def test_removing_from_the_selection(self):
        response = self.get(selected=f"{self.ada.pk},{self.initial.pk}")
        self.assertContains(response, f'href="?selected={self.initial.pk}"')

    def test_the_page_of_an_author_starts_a_selection(self):
        response = self.client.get(reverse("author_detail", args=[self.ada.pk]))
        self.assertContains(response, f"{reverse('author_merge_select')}?selected={self.ada.pk}")

    def test_nothing_changes_on_a_get(self):
        self.get(selected=f"{self.ada.pk},{self.initial.pk}")
        self.assertEqual(Author.objects.count(), MERGE_PAGE_SIZE + 3)


class MergeComesBackTests(TestCase):
    """After the merge, back to the page it started from (#388)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("olga")

    def setUp(self):
        self.client.force_login(self.user)
        self.ada = Author.objects.create(first_name="Ada", last_name="Lovelace")
        self.initial = Author.objects.create(first_name="A.", last_name="Lovelace")
        self.ids = f"{self.ada.pk},{self.initial.pk}"

    def confirm_url(self, **params):
        url = reverse("author_merge_confirm", args=[self.ids])
        return f"{url}?{urlencode(params)}" if params else url

    def test_the_search_is_kept_without_the_selection(self):
        response = self.client.get(
            reverse("author_merge_select"), {"q": "lovelace", "selected": self.ids, "page": 2}
        )
        back = reverse("author_merge_select") + "?q=lovelace"
        self.assertEqual(response.context["confirm_url"], self.confirm_url(next=back))

    def test_from_the_duplicates_with_their_page(self):
        back = reverse("author_duplicates") + "?page=2"
        response = self.client.post(
            reverse("author_merge_select"),
            {"authors": [self.ada.pk, self.initial.pk], "next": back},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith(f"/?{urlencode({'next': back})}"))

    def test_the_merge_comes_back(self):
        back = reverse("author_duplicates") + "?page=2"
        page = self.client.get(self.confirm_url(next=back))
        self.assertContains(page, f'href="{back}"')  # « Annuler »
        response = self.client.post(self.confirm_url(next=back), page.context["form"].initial)
        self.assertRedirects(response, back, fetch_redirect_response=False)
        self.assertEqual(Author.objects.count(), 1)

    def test_another_site_is_refused(self):
        page = self.client.get(self.confirm_url(next="https://example.org/"))
        response = self.client.post(
            self.confirm_url(next="https://example.org/"), page.context["form"].initial
        )
        self.assertRedirects(response, reverse("author_merge_select"))
