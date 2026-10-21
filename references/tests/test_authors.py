from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Author, Publication
from references.services.parser import parse_publication
from references.tests.helpers import with_crossref

ADA = {"given": "Ada", "family": "Lovelace", "ORCID": "https://orcid.org/0000-0001"}
ADA_INITIAL = {"given": "A.", "family": "Lovelace"}


def article(title, authors):
    pub = Publication.objects.create(title=title)
    with_crossref(pub, {"message": {"title": [title], "author": authors}})
    parse_publication(pub)
    return pub


class AuthorViewsTestCase(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("alice"))


class AuthorEditTests(AuthorViewsTestCase):
    def setUp(self):
        super().setUp()
        self.author = Author.objects.create(first_name="A.", last_name="Lovelace")
        self.url = reverse("author_edit", args=[self.author.pk])

    def test_form_page(self):
        self.assertContains(self.client.get(self.url), 'name="first_name"')

    def test_edit_redirects_to_the_author_with_a_normalized_orcid(self):
        response = self.client.post(
            self.url,
            {"first_name": "Ada", "last_name": "Lovelace", "orcid": "https://orcid.org/0000-0001"},
        )
        self.assertRedirects(response, reverse("author_detail", args=[self.author.pk]))
        self.author.refresh_from_db()
        self.assertEqual((self.author.first_name, self.author.orcid), ("Ada", "0000-0001"))

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)


class AuthorMergeTests(AuthorViewsTestCase):
    def setUp(self):
        super().setUp()
        # The same person, published twice on the same article (#14) and once elsewhere.
        self.pub = article("Note G", [ADA, ADA_INITIAL])
        self.ada, self.ada_initial = (s.author for s in self.pub.authorpublication_set.all())
        self.other = article("Sketch of the Analytical Engine", [ADA_INITIAL])
        self.confirm_url = reverse(
            "author_merge_confirm", args=[f"{self.ada_initial.pk},{self.ada.pk}"]
        )

    def merge(self, **values):
        data = {"first_name": "Ada", "last_name": "Lovelace", "orcid": "0000-0001"} | values
        return self.client.post(self.confirm_url, data)

    def test_select_page_redirects_to_confirmation(self):
        response = self.client.post(
            reverse("authors_merge_select"), {"authors": [self.ada.pk, self.ada_initial.pk]}
        )
        self.assertRedirects(response, self.confirm_url, fetch_redirect_response=False)

    def test_confirmation_page_lists_the_authors_and_the_form(self):
        response = self.client.get(self.confirm_url)
        self.assertContains(response, "A. Lovelace")
        self.assertContains(response, 'name="orcid"')
        self.assertContains(response, 'value="Ada"')  # values of the first created author

    def test_merge_of_coauthors_of_the_same_publication(self):
        response = self.merge()
        self.assertRedirects(response, reverse("author_detail", args=[self.ada.pk]))
        self.assertEqual(Author.objects.count(), 1)
        self.assertEqual(
            [slot.author for slot in self.pub.authorpublication_set.all()], [self.ada, self.ada]
        )

    def test_author_page_lists_each_publication_once(self):
        self.merge()
        response = self.client.get(reverse("author_detail", args=[self.ada.pk]))
        self.assertEqual(response.context["publications"].count(), 2)

    def test_values_chosen_in_the_form_are_kept(self):
        self.merge(first_name="Augusta Ada")
        self.ada.refresh_from_db()
        self.assertEqual(self.ada.first_name, "Augusta Ada")

    def test_merge_survives_reimport_and_new_imports(self):
        self.merge()
        parse_publication(self.pub)
        parse_publication(self.other)
        newer = article("Letters", [ADA_INITIAL])
        self.assertEqual(Author.objects.count(), 1)
        self.assertEqual(newer.authorpublication_set.get().author, self.ada)

    def test_less_than_two_valid_authors(self):
        url = reverse("author_merge_confirm", args=[f"{self.ada.pk},abc"])
        self.assertRedirects(self.client.get(url), reverse("authors_merge_select"))
