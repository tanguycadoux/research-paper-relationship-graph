import datetime
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import CitedReference, Organization, Publication
from references.services.affiliations import attach_affiliations, organization_periods
from references.services.enrichment import complete_cited_with_openalex
from references.services.external_records import Source, store_record
from references.services.names import same_person_name
from references.services.parser import parse_publication
from references.tests.helpers import with_crossref

LPSC = {
    "id": "https://openalex.org/I4210141222",
    "display_name": "Laboratoire de Physique Subatomique et de Cosmologie",
    "ror": "https://ror.org/03f0apy98",
    "country_code": "FR",
}
CERN = {
    "id": "https://openalex.org/I67311998",
    "display_name": "CERN",
    "ror": "",
    "country_code": "CH",
}


def authorship(raw_name, *institutions):
    return {"raw_author_name": raw_name, "institutions": list(institutions)}


def publication(title, authors, authorships, date=None):
    pub = Publication.objects.create(title=title, publication_date=date)
    with_crossref(pub, {"message": {"title": [title], "author": authors}})
    store_record(pub, Source.OPENALEX, {"authorships": authorships})
    parse_publication(pub)  # attaches the affiliations
    return pub


THUILLIER = {"given": "Thomas", "family": "Thuillier"}
ANGOT = {"given": "Julien", "family": "Angot"}


class SamePersonNameTests(SimpleTestCase):
    def test_same_words_in_any_order(self):
        self.assertTrue(same_person_name("Thomas Thuillier", "Thuillier, Thomas"))
        self.assertTrue(same_person_name("Jean-Luc Flambard", "Flambard, Jean Luc"))
        self.assertTrue(same_person_name("Francois Juster", "François JUSTER"))

    def test_different_names(self):
        self.assertFalse(same_person_name("T. Thuillier", "Thomas Thuillier"))


class AttachAffiliationsTests(TestCase):
    def organizations(self, pub):
        return [
            [str(org) for org in slot.organizations.all()]
            for slot in pub.authorpublication_set.order_by("order")
        ]

    def test_institutions_are_attached_by_position_and_published_name(self):
        pub = publication(
            "First Plasma",
            [THUILLIER, ANGOT],
            [authorship("Thuillier, Thomas", LPSC), authorship("Angot, Julien", LPSC, CERN)],
        )
        self.assertEqual(
            self.organizations(pub), [[LPSC["display_name"]], ["CERN", LPSC["display_name"]]]
        )
        lpsc = Organization.objects.get(name=LPSC["display_name"])
        self.assertEqual(
            (lpsc.ror, lpsc.openalex_id, lpsc.country_code), ("03f0apy98", "I4210141222", "FR")
        )

    def test_organizations_are_shared_between_publications(self):
        publication("A", [THUILLIER], [authorship("Thomas Thuillier", LPSC)])
        publication("B", [ANGOT], [authorship("Julien Angot", LPSC)])
        self.assertEqual(Organization.objects.count(), 1)

    def test_organization_recognized_by_its_ror_under_a_new_openalex_id(self):
        publication("A", [THUILLIER], [authorship("Thomas Thuillier", LPSC)])
        merged = dict(LPSC, id="https://openalex.org/I999")
        publication("B", [ANGOT], [authorship("Julien Angot", merged)])
        self.assertEqual(Organization.objects.count(), 1)

    def test_nothing_attached_when_the_number_of_authors_differs(self):
        pub = publication("A", [THUILLIER, ANGOT], [authorship("Thomas Thuillier", LPSC)])
        self.assertEqual(self.organizations(pub), [[], []])
        self.assertFalse(attach_affiliations(pub))

    def test_nothing_attached_when_a_published_name_differs(self):
        pub = publication(
            "A",
            [THUILLIER, ANGOT],
            [authorship("Thomas Thuillier", LPSC), authorship("Someone Else", LPSC)],
        )
        self.assertEqual(self.organizations(pub), [[], []])

    def test_without_openalex(self):
        pub = Publication.objects.create(title="A")
        with_crossref(pub, {"message": {"title": ["A"], "author": [THUILLIER]}})
        parse_publication(pub)
        self.assertFalse(attach_affiliations(pub))

    def test_affiliations_survive_a_new_parse(self):
        pub = publication("A", [THUILLIER], [authorship("Thomas Thuillier", LPSC)])
        parse_publication(pub)
        self.assertEqual(self.organizations(pub), [[LPSC["display_name"]]])

    def test_cited_publications_are_attached_after_the_openalex_batch(self):
        source = Publication.objects.create(title="Source")
        cited = Publication.objects.create(doi="10.1000/cited", title="Cited")
        with_crossref(cited, {"message": {"title": ["Cited"], "author": [THUILLIER]}})
        parse_publication(cited)
        CitedReference.objects.create(source=source, target=cited, position=0)
        work = {"authorships": [authorship("Thomas Thuillier", LPSC)]}
        with patch(
            "references.services.enrichment.fetch_openalex_works",
            return_value={"10.1000/cited": work},
        ):
            complete_cited_with_openalex(source)
        self.assertEqual(self.organizations(cited), [[LPSC["display_name"]]])


class OrganizationPeriodsTests(TestCase):
    def test_period_and_count_from_the_publications(self):
        first = publication(
            "A", [THUILLIER], [authorship("Thomas Thuillier", LPSC)], datetime.date(2012, 5, 1)
        )
        publication(
            "B", [THUILLIER], [authorship("Thomas Thuillier", LPSC)], datetime.date(2016, 1, 1)
        )
        publication(
            "C", [THUILLIER], [authorship("Thomas Thuillier", CERN)], datetime.date(2019, 1, 1)
        )
        author = first.authorpublication_set.get().author
        periods = {
            o.name: (o.first_date.year, o.last_date.year, o.publication_count)
            for o in organization_periods(author)
        }
        self.assertEqual(periods, {LPSC["display_name"]: (2012, 2016, 2), "CERN": (2019, 2019, 1)})

    def test_pages_show_the_organizations(self):
        pub = publication(
            "A", [THUILLIER], [authorship("Thomas Thuillier", LPSC)], datetime.date(2016, 1, 1)
        )
        self.assertContains(
            self.client.get(reverse("publication_detail", args=[pub.pk])), LPSC["display_name"]
        )
        author = pub.authorpublication_set.get().author
        response = self.client.get(reverse("author_detail", args=[author.pk]))
        self.assertContains(response, "https://ror.org/03f0apy98")
        self.assertContains(response, "2016")
