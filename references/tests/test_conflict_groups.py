from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import MetadataConflict, Publication
from references.views.conflicts import GROUP_SIZE

Kind = MetadataConflict.Kind


class ConflictGroupsTests(TestCase):
    """The conflicts grouped by type, each explained once (#335)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("noe")
        for i in range(GROUP_SIZE + 2):
            cls.conflict(Kind.AUTHORS_MISMATCH, f"Liste {i}")
        cls.conflict(Kind.ORCID, "Orcid", current_value="a", proposed_value="b")

    @classmethod
    def conflict(cls, kind, title, **values):
        return MetadataConflict.objects.create(
            kind=kind,
            publication=Publication.objects.create(title=title),
            field="x",
            source="openalex",
            **values,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_one_section_per_type_with_its_explanation_once(self):
        response = self.client.get(reverse("conflict_list"))
        self.assertEqual(
            [group["kind"] for group in response.context["groups"]],
            [Kind.AUTHORS_MISMATCH, Kind.ORCID],
        )
        self.assertContains(response, "Les sources ne donnent pas la même liste d'auteurs", count=1)
        self.assertContains(response, "À trancher")
        self.assertEqual(response.context["open_count"], GROUP_SIZE + 3)

    def test_a_long_type_is_cut_with_a_link_to_all_of_it(self):
        response = self.client.get(reverse("conflict_list"))
        group = response.context["groups"][0]
        self.assertEqual(len(group["conflicts"]), GROUP_SIZE)
        self.assertContains(response, f'href="?type={Kind.AUTHORS_MISMATCH}"')
        self.assertContains(response, f"Voir les {GROUP_SIZE + 2} conflits de ce type")

    def test_one_type_alone_in_pages(self):
        url = reverse("conflict_list")
        response = self.client.get(url, {"type": Kind.AUTHORS_MISMATCH, "page": "2"})
        groups = response.context["groups"]
        self.assertEqual([group["kind"] for group in groups], [Kind.AUTHORS_MISMATCH])
        self.assertEqual(len(groups[0]["conflicts"]), 2)
        self.assertContains(response, "Tous les types")

    def test_an_unknown_type_shows_them_all(self):
        response = self.client.get(reverse("conflict_list"), {"type": "nimporte"})
        self.assertEqual(len(response.context["groups"]), 2)
