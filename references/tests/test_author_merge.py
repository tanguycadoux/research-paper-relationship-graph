from types import SimpleNamespace

from django.test import SimpleTestCase

from references.forms import AuthorMergeConfirmForm
from references.services.author_merge import (
    candidate_values,
    default_values,
    has_orcid_conflict,
    most_complete_name,
)


def author(first_name="", last_name="", orcid=""):
    return SimpleNamespace(first_name=first_name, last_name=last_name, orcid=orcid)


class CandidateValuesTests(SimpleTestCase):
    def test_distinct_non_empty_values_in_author_order(self):
        authors = [author("A.", "Lovelace"), author("Ada", "Lovelace", "0000-0001"), author("A.")]
        candidates = candidate_values(authors)
        self.assertEqual(candidates["first_name"], ["A.", "Ada"])
        self.assertEqual(candidates["last_name"], ["Lovelace"])
        self.assertEqual(candidates["orcid"], ["0000-0001"])

    def test_orcid_conflict(self):
        self.assertTrue(has_orcid_conflict({"orcid": ["0000-0001", "0000-0002"]}))
        self.assertFalse(has_orcid_conflict({"orcid": ["0000-0001"]}))


class MostCompleteNameTests(SimpleTestCase):
    def test_full_name_is_preferred_to_initials(self):
        self.assertEqual(most_complete_name(["A.", "Ada"]), "Ada")
        self.assertEqual(most_complete_name(["J. S.", "Josiah"]), "Josiah")
        self.assertEqual(most_complete_name(["J.-L.", "Jean Luc"]), "Jean Luc")

    def test_then_not_all_in_capitals(self):
        self.assertEqual(most_complete_name(["FLAMBARD", "Flambard"]), "Flambard")

    def test_then_the_longest(self):
        self.assertEqual(most_complete_name(["Ada", "Augusta Ada"]), "Augusta Ada")
        self.assertEqual(most_complete_name(["A", "B."]), "B.")

    def test_no_value(self):
        self.assertEqual(most_complete_name([]), "")

    def test_defaults(self):
        candidates = {"first_name": ["A.", "Ada"], "last_name": [], "orcid": []}
        self.assertEqual(
            default_values(candidates), {"first_name": "Ada", "last_name": "", "orcid": ""}
        )


CANDIDATES = {"first_name": ["A.", "Ada"], "last_name": ["Lovelace"], "orcid": ["0000-0001"]}


class AuthorMergeConfirmFormTests(SimpleTestCase):
    def form(self, data, **kwargs):
        base = {"first_name": "Ada", "last_name": "Lovelace", "orcid": "0000-0001"}
        return AuthorMergeConfirmForm(base | data, candidates=CANDIDATES, **kwargs)

    def test_choice_of_a_candidate(self):
        form = self.form({"first_name": "A."})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["first_name"], "A.")

    def test_other_value_with_a_normalized_orcid(self):
        form = self.form({"orcid": "__other__", "orcid_other": "https://orcid.org/0000-0009"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["orcid"], "0000-0009")

    def test_no_orcid(self):
        form = self.form({"orcid": ""})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["orcid"], "")

    def test_value_outside_the_candidates_is_refused(self):
        self.assertIn("first_name", self.form({"first_name": "Augusta"}).errors)

    def test_orcid_conflict_requires_the_confirmation(self):
        self.assertIn("confirm_orcid_conflict", self.form({}, orcid_conflict=True).errors)
        confirmed = self.form({"confirm_orcid_conflict": "on"}, orcid_conflict=True)
        self.assertTrue(confirmed.is_valid(), confirmed.errors)
