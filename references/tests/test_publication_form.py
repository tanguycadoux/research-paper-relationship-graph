from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.forms import PublicationForm
from references.models import Author, Publication


class PublicationFormTests(TestCase):
    def test_empty_publication_is_refused(self):
        form = PublicationForm({"publication_date": "2020-01-01"})
        self.assertFalse(form.is_valid())
        self.assertIn("Indiquez au moins un DOI, un ISBN ou un titre.", form.non_field_errors())

    def test_any_identifier_or_title_is_enough(self):
        for data in ({"doi": "10.1000/x"}, {"isbn": "0-262-03561-8"}, {"title": "Un livre"}):
            with self.subTest(data=data):
                self.assertTrue(PublicationForm(data).is_valid())

    def test_creation_page_refuses_an_empty_form(self):
        self.client.force_login(get_user_model().objects.create_user("alice"))
        response = self.client.post(reverse("publication_create"), {})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Publication.objects.exists())


class ListViewsTests(TestCase):
    def test_publications_are_listed_newest_first_without_untitled_ones(self):
        Publication.objects.create(title="Ancien", publication_date=date(2000, 1, 1))
        Publication.objects.create(title="Récent", publication_date=date(2020, 1, 1))
        Publication.objects.create(doi="10.1000/untitled")
        response = self.client.get(reverse("publication_list"))
        self.assertEqual([str(p) for p in response.context["publications"]], ["Récent", "Ancien"])

    def test_creation_page_is_linked_for_logged_in_users(self):
        url = reverse("publication_create")
        self.assertNotContains(self.client.get(reverse("publication_list")), url)
        self.client.force_login(get_user_model().objects.create_user("alice"))
        self.assertContains(self.client.get(reverse("publication_list")), url)

    def test_authors_are_listed_by_last_name(self):
        Author.objects.create(first_name="Alan", last_name="Turing")
        Author.objects.create(first_name="Ada", last_name="Lovelace")
        response = self.client.get(reverse("author_list"))
        self.assertEqual([a.last_name for a in response.context["authors"]], ["Lovelace", "Turing"])


class PublicationDateInputTests(TestCase):
    def test_date_is_rendered_in_iso_format_whatever_the_locale(self):
        form = PublicationForm(
            instance=Publication(title="Un article", publication_date=date(2026, 8, 1))
        )
        self.assertIn('value="2026-08-01"', str(form["publication_date"]))
