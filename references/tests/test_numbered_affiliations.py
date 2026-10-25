from django.test import TestCase
from django.urls import reverse

from references.models import Author, AuthorPublication, Organization, Publication
from references.services.organizations import numbered_affiliations


class NumberedAffiliationsTests(TestCase):
    """#155: affiliations numbered once, as in an article."""

    @classmethod
    def setUpTestData(cls):
        cls.cea = Organization.objects.create(name="CEA", ror="00jjx8s55")
        cls.saclay = Organization.objects.create(name="CEA Paris-Saclay")
        cls.saclay.ancestors.add(cls.cea)
        cls.irfu = Organization.objects.create(name="IRFU")
        cls.irfu.ancestors.add(cls.cea, cls.saclay)
        cls.ganil = Organization.objects.create(name="GANIL")
        cls.pub = Publication.objects.create(title="ASTERICS")
        cls.slots = [
            cls.sign(0, "Damien", "Simon", [cls.cea, cls.saclay, cls.irfu, cls.ganil]),
            cls.sign(1, "Hélène", "Felice", [cls.irfu]),
            cls.sign(2, "Ada", "Lovelace", []),
            cls.sign(3, "Thomas", "Thuillier", [cls.cea]),
        ]

    @classmethod
    def sign(cls, order, first_name, last_name, organizations):
        author = Author.objects.create(first_name=first_name, last_name=last_name)
        slot = AuthorPublication.objects.create(publication=cls.pub, author=author, order=order)
        slot.organizations.set(organizations)
        return slot

    def numbered(self):
        slots = self.pub.authorpublication_set.prefetch_related("organizations__ancestors")
        return numbered_affiliations(slots.order_by("order"))

    def test_most_precise_organizations_numbered_in_order_of_appearance(self):
        result = self.numbered()
        self.assertEqual(result["affiliations"], [self.ganil, self.irfu, self.cea])
        self.assertEqual([a["numbers"] for a in result["authors"]], [[1, 2], [2], [], [3]])

    def test_detail_page(self):
        response = self.client.get(reverse("publication_detail", args=[self.pub.pk]))
        self.assertContains(
            response,
            '<a href="/authors/'
            f'{self.slots[0].author.pk}/">Damien Simon</a><sup>'
            '<a href="#affiliation-1" aria-label="affiliation 1">1</a>,'
            '<a href="#affiliation-2" aria-label="affiliation 2">2</a></sup>',
        )
        self.assertContains(response, '<li id="affiliation-2">', count=1)
        self.assertContains(response, "https://ror.org/00jjx8s55")
        self.assertNotContains(response, "CEA Paris-Saclay")
