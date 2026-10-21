from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import CitedReference, Publication
from references.services.publication_details import abstract_paragraphs, crossref_details
from references.tests.helpers import with_crossref

MESSAGE = {
    "title": ["Stress analysis"],
    "container-title": ["IEEE Transactions on Applied Superconductivity"],
    "is-referenced-by-count": 12,
    "subject": [],
    "funder": [
        {"name": "French &#x201C;Agence Nationale de la Recherche", "award": ["21-ESRE-0018"]},
        {"name": "CEA"},
    ],
    "license": [
        {"URL": "https://example.org/license", "content-version": "vor"},
        {"URL": "https://example.org/license", "content-version": "am"},
    ],
    "abstract": "<jats:title>Abstract</jats:title><jats:p>First <jats:italic>part</jats:italic>."
    "</jats:p><jats:p>Second &amp; last.</jats:p>",
}


class AbstractTests(SimpleTestCase):
    def test_paragraphs_without_title_tags_or_entities(self):
        self.assertEqual(
            abstract_paragraphs(MESSAGE["abstract"]), ["First part.", "Second & last."]
        )

    def test_empty(self):
        self.assertEqual(abstract_paragraphs(""), [])


class CrossrefDetailsTests(TestCase):
    def test_details(self):
        pub = with_crossref(Publication.objects.create(title="A"), {"message": MESSAGE})
        details = crossref_details(pub)
        self.assertEqual(details["venue"], "IEEE Transactions on Applied Superconductivity")
        self.assertEqual(details["citation_count"], 12)
        self.assertEqual(
            details["funders"],
            ["French “Agence Nationale de la Recherche (21-ESRE-0018)", "CEA"],
        )
        self.assertEqual(details["licenses"], ["https://example.org/license"])
        self.assertEqual(details["subjects"], [])

    def test_without_crossref_answer(self):
        self.assertIsNone(crossref_details(Publication.objects.create(title="A")))

    def test_detail_page(self):
        pub = with_crossref(Publication.objects.create(title="A"), {"message": MESSAGE})
        response = self.client.get(reverse("publication_detail", args=[pub.pk]))
        self.assertContains(response, "IEEE Transactions on Applied Superconductivity")
        self.assertContains(response, "<dd>12 (selon Crossref)</dd>", html=True)
        self.assertContains(response, "Second &amp; last.")
        self.assertNotContains(response, "Disciplines")


class ReferenceLabelTests(SimpleTestCase):
    def label(self, raw, unstructured=""):
        return CitedReference(raw=raw, key=raw.get("key", ""), unstructured=unstructured).label

    def test_unstructured_text_first(self):
        self.assertEqual(
            self.label({"key": "r1", "year": "1965"}, "Smith J. 1965."), "Smith J. 1965."
        )

    def test_composed_from_the_crossref_fields(self):
        raw = {
            "key": "r2",
            "first-page": "287",
            "volume": "69C",
            "year": "1965",
            "journal-title": "NBS J. Res.",
        }
        self.assertEqual(self.label(raw), "NBS J. Res. 69C, p. 287 (1965)")

    def test_with_author_and_title(self):
        raw = {"key": "r3", "author": "Arp", "year": "1977", "article-title": "Stresses"}
        self.assertEqual(self.label(raw), "Arp (1977). Stresses")

    def test_never_the_technical_key(self):
        self.assertEqual(
            self.label({"key": "2024020419552444200_r1"}), "Référence sans description"
        )
