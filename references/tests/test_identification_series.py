from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, Publication
from references.tests.helpers import without_candidate_search, without_other_sources


@without_candidate_search
@without_other_sources
class IdentificationSeriesTests(TestCase):
    """The references of a publication left to identify, one after the other (#242)."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        self.client.force_login(self.user)
        self.pub = Publication.objects.create(title="Attention")
        cited = Publication.objects.create(title="Déjà reliée")
        CitedReference.objects.create(source=self.pub, target=cited, position=0)
        for position in (1, 2, 3):
            CitedReference.objects.create(
                source=self.pub, position=position, unstructured=f"Référence {position}"
            )

    def url(self, name, position, series=True):
        url = reverse(name, args=[self.pub.pk, position])
        return f"{url}?serie=1" if series and name == "reference_identify" else url

    def ref(self, position):
        return CitedReference.objects.get(source=self.pub, position=position)

    def detail_url(self):
        return reverse("publication_detail", args=[self.pub.pk])

    def messages_after(self, response):
        return [str(message) for message in response.context["messages"]]

    def test_detail_page_starts_at_the_first_reference_to_identify(self):
        response = self.client.get(self.detail_url())
        self.assertContains(response, "Identifier en série")
        self.assertContains(response, self.url("reference_identify", 1))

    def test_no_series_without_reference_to_identify(self):
        CitedReference.objects.filter(position__gt=0).update(unidentifiable=True)
        self.assertNotContains(self.client.get(self.detail_url()), "Identifier en série")

    def test_progress_and_controls(self):
        response = self.client.get(self.url("reference_identify", 2))
        self.assertEqual(response.context["series"], {"left": 3, "after": 1})
        self.assertContains(response, "dont 1 après celle-ci")
        self.assertContains(response, self.url("reference_skip", 2))
        # Search again and « non identifiable »; each candidate's form has one too.
        self.assertContains(response, 'name="serie" value="1"', count=2)

    def test_no_series_bar_outside_a_series(self):
        response = self.client.get(self.url("reference_identify", 2, series=False))
        self.assertNotContains(response, "Identification en série")
        self.assertNotContains(response, 'name="serie"')

    def test_decision_goes_on_to_the_next_reference(self):
        response = self.client.post(
            self.url("reference_identify", 1), {"method": "none", "title": "Un rapport"}
        )
        self.assertRedirects(response, self.url("reference_identify", 2))
        self.assertEqual(self.ref(1).target.title, "Un rapport")

    def test_candidate_chosen_goes_on_to_the_next_reference(self):
        other = Publication.objects.create(title="La bonne")
        response = self.client.post(
            self.url("reference_candidate", 2), {"publication": other.pk, "serie": "1"}
        )
        self.assertRedirects(response, self.url("reference_identify", 3))

    def test_skipped_reference_stays_to_identify(self):
        response = self.client.get(self.url("reference_skip", 1))
        self.assertRedirects(response, self.url("reference_identify", 2))
        self.assertIsNone(self.ref(1).target)

    def test_end_of_the_series_counts_the_references_left(self):
        response = self.client.post(
            self.url("reference_unidentifiable", 3), {"serie": "1"}, follow=True
        )
        self.assertRedirects(response, self.detail_url())
        self.assertIn(
            "Fin de la série : 2 références restent à identifier.", self.messages_after(response)
        )

    def test_end_of_the_series_when_everything_is_done(self):
        CitedReference.objects.filter(position__in=(1, 2)).update(unidentifiable=True)
        response = self.client.post(
            self.url("reference_unidentifiable", 3), {"serie": "1"}, follow=True
        )
        self.assertIn(
            "Fin de la série : toutes les références sont traitées.",
            self.messages_after(response),
        )

    def test_search_again_stays_in_the_series(self):
        response = self.client.post(self.url("reference_search_again", 2), {"serie": "1"})
        self.assertRedirects(response, self.url("reference_identify", 2))

    def test_outside_a_series_a_decision_goes_back_to_the_publication(self):
        response = self.client.post(
            self.url("reference_identify", 1, series=False),
            {"method": "none", "title": "Un rapport"},
        )
        self.assertRedirects(response, self.detail_url())
