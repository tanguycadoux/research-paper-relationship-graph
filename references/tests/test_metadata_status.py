from django.test import TestCase
from django.urls import reverse

from references.models import Publication
from references.services.external_records import (
    METADATA_MISSING,
    METADATA_UNKNOWN,
    Source,
    metadata_status,
    store_record,
    with_metadata_status,
)


class MetadataStatusTests(TestCase):
    """Publications whose metadata is missing stand out (#124)."""

    @classmethod
    def setUpTestData(cls):
        cls.known = Publication.objects.create(doi="10.1000/known", title="Connue")
        store_record(cls.known, Source.CROSSREF, {"message": {}})
        store_record(cls.known, Source.OPENALEX, None)
        cls.unknown = Publication.objects.create(doi="10.1000/unknown", title="Inconnue")
        store_record(cls.unknown, Source.CROSSREF, None)
        store_record(cls.unknown, Source.DATACITE, None)
        cls.missing = Publication.objects.create(isbn="9780262035613", title="Jamais demandée")
        cls.manual = Publication.objects.create(title="Saisie à la main")

    def test_status(self):
        expected = {
            "Connue": "",
            "Inconnue": METADATA_UNKNOWN,
            "Jamais demandée": METADATA_MISSING,
            "Saisie à la main": "",
        }
        annotated = dict(
            with_metadata_status(Publication.objects).values_list("title", "metadata_status")
        )
        self.assertEqual(annotated, expected)
        for pub in Publication.objects.all():
            with self.subTest(pub=pub.title):
                self.assertEqual(metadata_status(pub), expected[pub.title])

    def test_badges_in_the_publication_list(self):
        response = self.client.get(reverse("publication_list"))
        self.assertContains(response, "métadonnées à récupérer", count=1)
        self.assertContains(response, "inconnue des sources", count=1)

    def test_alert_on_the_detail_page(self):
        for pub, text in (
            (self.missing, "n'ont pas encore été récupérées"),
            (self.unknown, "ne connaît cette publication"),
        ):
            with self.subTest(pub=pub.title):
                self.assertContains(
                    self.client.get(reverse("publication_detail", args=[pub.pk])), text
                )
        response = self.client.get(reverse("publication_detail", args=[self.known.pk]))
        self.assertNotContains(response, "récupérées")
