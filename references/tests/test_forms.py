from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.forms import AuthorMergeSelectForm
from references.models import Author


class AuthorMergeSelectFormTests(TestCase):
    def test_choice_labels_include_orcid_when_known(self):
        Author.objects.create(first_name="Ada", last_name="Lovelace", orcid="0000-0001")
        Author.objects.create(first_name="Alan", last_name="Turing", orcid="")
        labels = [choice.choice_label for choice in AuthorMergeSelectForm()["authors"]]
        self.assertEqual(labels, ["Ada Lovelace (ORCID : 0000-0001)", "Alan Turing"])

    def test_requires_a_selection(self):
        self.assertFalse(AuthorMergeSelectForm(data={}).is_valid())

    def test_merge_select_page_renders_labels(self):
        Author.objects.create(first_name="Ada", last_name="Lovelace", orcid="0000-0001")
        self.client.force_login(get_user_model().objects.create_user("alice", password="secret"))
        response = self.client.get(reverse("authors_merge_select"))
        self.assertContains(response, "Ada Lovelace (ORCID : 0000-0001)")
