import json
from pathlib import Path

from django.test import TestCase

from references.models import CitedReference, Publication
from references.services.parser import parse_publication

FIXTURE = Path(__file__).parent / "fixtures" / "crossref_nature14539.json"


class RealCrossrefResponseTests(TestCase):
    """Parse a real Crossref response, frozen on 2026-10-21 (LeCun et al., Nature 2015)."""

    @classmethod
    def setUpTestData(cls):
        cls.pub = Publication.objects.create(doi="10.1038/nature14539")
        cls.pub.crossref_json = json.loads(FIXTURE.read_text(encoding="utf-8"))
        parse_publication(cls.pub)
        cls.pub.refresh_from_db()

    def test_metadata(self):
        self.assertEqual(self.pub.title, "Deep learning")
        self.assertEqual(str(self.pub.publication_date), "2015-05-27")

    def test_authors_in_order(self):
        names = [slot.author.last_name for slot in self.pub.authorpublication_set.all()]
        self.assertEqual(names, ["LeCun", "Bengio", "Hinton"])

    def test_references(self):
        refs = CitedReference.objects.filter(source=self.pub)
        self.assertEqual(refs.count(), 103)
        self.assertEqual(refs.exclude(target=None).count(), 37)
        self.assertTrue(all(ref.label for ref in refs))
