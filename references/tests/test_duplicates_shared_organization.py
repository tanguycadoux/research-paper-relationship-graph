from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Author, AuthorPublication, Organization, Publication
from references.services.author_duplicates import duplicate_groups


def organization(name, *ancestors):
    org = Organization.objects.create(name=name, openalex_id=f"I-{name}")
    org.ancestors.set(ancestors)
    return org


def author(first_name, last_name, *organizations):
    person = Author.objects.create(first_name=first_name, last_name=last_name)
    slot = AuthorPublication.objects.create(
        publication=Publication.objects.create(title=f"{first_name} {last_name}"),
        author=person,
        order=0,
    )
    slot.organizations.set(organizations)
    return person


class SharedOrganizationTests(TestCase):
    def setUp(self):
        self.cea = organization("CEA")
        self.irfu = organization("IRFU", self.cea)
        self.saclay = organization("CEA Paris-Saclay", self.cea)
        self.cnrs = organization("CNRS")

    def test_shared_top_level_organization_through_the_hierarchy(self):
        author("Helene", "Felice", self.irfu)
        author("H.", "Felice", self.saclay)
        self.assertEqual([str(o) for o in duplicate_groups()[0].shared_organizations], ["CEA"])

    def test_different_organizations_never_separate_authors(self):
        author("Helene", "Felice", self.irfu)
        author("H.", "Felice", self.cnrs)
        groups = duplicate_groups()
        self.assertEqual(len(groups[0]), 2)
        self.assertEqual(groups[0].shared_organizations, [])

    def test_groups_with_a_shared_organization_come_first(self):
        author("Alan", "Turing", self.cnrs)
        author("A.", "Turing")
        author("Helene", "Felice", self.irfu)
        author("H.", "Felice", self.saclay)
        self.assertEqual(duplicate_groups()[0][0].last_name, "Felice")

    def test_duplicates_page_shows_the_shared_organization(self):
        author("Helene", "Felice", self.irfu)
        author("H.", "Felice", self.saclay)
        self.client.force_login(get_user_model().objects.create_user("alice"))
        response = self.client.get(reverse("author_duplicates"))
        self.assertContains(response, "Tutelle commune à plusieurs d'entre eux : CEA")
