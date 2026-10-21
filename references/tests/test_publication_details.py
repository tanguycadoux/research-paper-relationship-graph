from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import CitedReference, Publication
from references.services.external_records import Source, store_record
from references.services.publication_details import (
    abstract_paragraphs,
    crossref_details,
    funder_labels,
)
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


class FunderLabelsTests(SimpleTestCase):
    ANR_DOI = "10.13039/501100001665"

    def test_damaged_copies_join_the_identified_funder(self):
        # Real deposit of 10.1109/tasc.2026.3670817
        funders = [
            {"name": "french “Agence Nationale de la Recherche", "award": ["21-ESRE-0018"]},
            {
                "DOI": self.ANR_DOI,
                "name": "Agence Nationale de la Recherche",
                "award": ["21-ESRE-0018"],
            },
            {"name": "Agence Nationale de 308 la Recherche"},
            {"name": "French &#x201C;Agence Nationale de la Recherche", "award": ["21-ESRE-0018"]},
        ]
        self.assertEqual(
            funder_labels(funders), ["Agence Nationale de la Recherche (21-ESRE-0018)"]
        )

    def test_openalex_names_the_funder_of_a_lone_damaged_entry(self):
        # Real deposits: one damaged Crossref entry each, OpenAlex knows the funder.
        openalex = [
            {"display_name": "Agence Nationale de la Recherche", "ror": "https://ror.org/00rbzpz17"}
        ]
        for crossref in (
            [{"name": "french “Agence Nationale de la Recherche", "award": ["21-ESRE-0018"]}],
            [{"name": "Agence Nationale de 308 la Recherche"}],
        ):
            with self.subTest(crossref=crossref):
                label = funder_labels(crossref, openalex)[0]
                self.assertTrue(label.startswith("Agence Nationale de la Recherche"))
                self.assertEqual(len(funder_labels(crossref, openalex)), 1)

    def test_openalex_funders_missing_from_crossref_are_listed(self):
        self.assertEqual(
            funder_labels([{"name": "CEA"}], [{"display_name": "European Commission"}]),
            ["European Commission", "CEA"],
        )

    def test_unidentified_funders_are_merged_by_name(self):
        funders = [
            {"name": "CEA", "award": ["A1"]},
            {"name": "cea", "award": ["A2"]},
            {"name": "Région Normandie"},
        ]
        self.assertEqual(funder_labels(funders), ["CEA (A1, A2)", "Région Normandie"])

    def test_a_name_inside_a_word_is_not_a_match(self):
        funders = [{"DOI": "10.13039/1", "name": "CEA"}, {"name": "Ocean Agency"}]
        self.assertEqual(funder_labels(funders), ["CEA", "Ocean Agency"])

    def test_distinct_identified_funders_stay_apart(self):
        funders = [
            {"DOI": self.ANR_DOI, "name": "Agence Nationale de la Recherche", "award": ["X"]},
            {"DOI": "10.13039/501100004794", "name": "CNRS", "award": ["Y"]},
            {"name": "CNRS", "award": ["Y"]},
        ]
        self.assertEqual(
            funder_labels(funders), ["Agence Nationale de la Recherche (X)", "CNRS (Y)"]
        )


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

    def test_funders_use_the_stored_openalex_answer(self):
        pub = with_crossref(Publication.objects.create(title="A"), {"message": MESSAGE})
        store_record(
            pub,
            Source.OPENALEX,
            {"funders": [{"display_name": "Agence Nationale de la Recherche"}]},
        )
        self.assertEqual(
            crossref_details(pub)["funders"],
            ["Agence Nationale de la Recherche (21-ESRE-0018)", "CEA"],
        )

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
