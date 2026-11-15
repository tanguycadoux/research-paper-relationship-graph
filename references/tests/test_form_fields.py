from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Publication


class FormFieldTests(TestCase):
    """{% field %}: one way to show a field, on every form (#337)."""

    def test_labels_have_no_colon_and_help_comes_after_the_input(self):
        html = self.client.get(reverse("register")).content.decode()
        label = html.split('<label for="id_username">')[1].split("</label>")[0]
        self.assertFalse(label.rstrip().endswith(":"))
        username = html.split('id="id_username"')[1]
        self.assertLess(username.index("id_username-help"), username.index('for="id_password1"'))
        self.assertIn('aria-describedby="id_username-help"', html)

    def test_errors_under_the_field_and_pointed_to(self):
        response = self.client.post(
            reverse("register"), {"username": "", "password1": "a", "password2": "b"}
        )
        self.assertContains(response, 'id="id_username-errors"')
        self.assertContains(response, 'aria-invalid="true"')

    def test_the_title_of_a_publication_is_three_rows_high(self):
        self.client.force_login(get_user_model().objects.create_user("lea"))
        pub = Publication.objects.create(title="Titre")
        response = self.client.get(reverse("publication_edit", args=[pub.pk]))
        self.assertContains(response, 'rows="3"')

    def test_errors_of_the_whole_form_are_alerts(self):
        self.client.force_login(get_user_model().objects.create_user("max"))
        response = self.client.post(reverse("publication_create"), {})
        self.assertContains(response, "Indiquez au moins un DOI, un ISBN ou un titre.")
        self.assertContains(response, 'role="alert"')
