from datetime import date
from unittest.mock import patch

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


class PublicationIdentifierTests(TestCase):
    """#145: identifiers are normalized before the uniqueness check."""

    @classmethod
    def setUpTestData(cls):
        cls.existing = Publication.objects.create(
            doi="10.1109/tasc.2023.1", isbn="9780262035613", title="Existante"
        )

    def test_doi_is_normalized(self):
        form = PublicationForm({"doi": "https://doi.org/10.1000/ABC"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["doi"], "10.1000/abc")

    def test_invalid_doi_is_refused(self):
        form = PublicationForm({"doi": "pas un doi"})
        self.assertFalse(form.is_valid())
        self.assertIn("doi", form.errors)

    def test_known_doi_in_another_form_is_refused_with_a_link(self):
        for doi in ("10.1109/tasc.2023.1", "https://doi.org/10.1109/TASC.2023.1"):
            with self.subTest(doi=doi):
                form = PublicationForm({"doi": doi})
                self.assertFalse(form.is_valid())
                self.assertEqual(len(form.errors["doi"]), 1)
                error = form.errors["doi"][0]
                self.assertIn("Une publication avec ce DOI existe déjà", error)
                self.assertIn(reverse("publication_detail", args=[self.existing.pk]), error)

    def test_known_isbn_is_refused_with_a_link(self):
        form = PublicationForm({"isbn": "0-262-03561-8"})
        self.assertFalse(form.is_valid())
        self.assertIn("Une publication avec cet ISBN existe déjà", form.errors["isbn"][0])

    def test_a_publication_keeps_its_own_identifiers(self):
        data = {"doi": "https://doi.org/10.1109/TASC.2023.1", "isbn": "0-262-03561-8"}
        self.assertTrue(PublicationForm(data, instance=self.existing).is_valid())

    def test_creation_page_answers_a_known_doi_without_error_500(self):
        self.client.force_login(get_user_model().objects.create_user("alice"))
        response = self.client.post(
            reverse("publication_create"), {"doi": "https://doi.org/10.1109/TASC.2023.1"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Une publication avec ce DOI existe déjà")
        self.assertContains(
            response, f'href="{reverse("publication_detail", args=[self.existing.pk])}"'
        )
        self.assertEqual(Publication.objects.count(), 1)

    def test_a_known_doi_has_only_its_own_error(self):
        # Not also « Indiquez au moins un DOI… »: a DOI was given (#272).
        form = PublicationForm({"doi": "10.1109/tasc.2023.1"})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.non_field_errors(), [])

    def test_labels_are_in_french(self):
        labels = [field.label for field in PublicationForm()]
        self.assertEqual(labels, ["DOI", "ISBN", "Titre", "Date de publication"])


class PublicationCreationTests(TestCase):
    """After the creation: the page of the publication, with a message (#272)."""

    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("alice"))

    def create(self, **data):
        return self.client.post(reverse("publication_create"), data, follow=True)

    def test_without_doi(self):
        response = self.create(title="Un livre")
        pub = Publication.objects.get()
        self.assertRedirects(response, reverse("publication_detail", args=[pub.pk]))
        self.assertContains(response, "« Un livre » a été ajoutée à la base.")

    @patch("references.views.publications.import_publication")
    def test_with_a_doi_whose_metadata_is_retrieved(self, import_publication):
        import_publication.side_effect = lambda pub: pub
        response = self.create(doi="10.1000/new")
        pub = Publication.objects.get()
        import_publication.assert_called_once_with(pub)
        self.assertRedirects(response, reverse("publication_detail", args=[pub.pk]))
        self.assertContains(response, "a été ajoutée à la base, avec ses métadonnées.")

    @patch("references.views.publications.import_publication", return_value=None)
    def test_with_a_doi_the_sources_do_not_know(self, _import):
        response = self.create(doi="10.1000/unknown")
        pub = Publication.objects.get()
        self.assertRedirects(response, reverse("publication_detail", args=[pub.pk]))
        self.assertContains(response, "ses métadonnées n&#x27;ont pas pu être récupérées")


class ListViewsTests(TestCase):
    def test_publications_are_listed_newest_first_undated_last(self):
        Publication.objects.create(title="Ancien", publication_date=date(2000, 1, 1))
        Publication.objects.create(title="Récent", publication_date=date(2020, 1, 1))
        Publication.objects.create(doi="10.1000/untitled")
        response = self.client.get(reverse("publication_list"))
        self.assertEqual(
            [str(p) for p in response.context["publications"]],
            ["Récent", "Ancien", "10.1000/untitled"],
        )

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
