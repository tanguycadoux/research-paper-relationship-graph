from unittest.mock import patch

from django.db import IntegrityError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from references.models import Author, AuthorPublication, CitedReference, Publication
from references.services.parser import parse_publication
from references.tests.helpers import with_crossref, without_other_sources


def crossref_message(authors=(), references=()):
    return {
        "message": {
            "title": ["Un article"],
            "issued": {"date-parts": [[2020, 5]]},
            "author": list(authors),
            "reference": list(references),
        }
    }


ADA = {"given": "Ada", "family": "Lovelace"}
ADA_INITIAL = {"given": "A.", "family": "Lovelace"}
TURING = {"given": "Alan", "family": "Turing", "ORCID": "https://orcid.org/0000-0001-2345-6789"}
REF_WITH_DOI = {"key": "ref1", "DOI": "10.1000/ABC", "article-title": "Cited article"}
REF_WITHOUT_DOI = {"key": "ref2", "unstructured": "Smith J. Some book. 1999."}


@without_other_sources
@patch("references.services.importer.fetch_crossref_json", return_value=None)
class ParsePublicationTests(TestCase):
    def make_publication(self, json_data):
        pub = Publication.objects.create(title="")
        with_crossref(pub, json_data)
        parse_publication(pub)
        return pub

    def test_title_and_date(self, _fetch):
        pub = self.make_publication(crossref_message())
        pub.refresh_from_db()
        self.assertEqual(pub.title, "Un article")
        self.assertEqual(str(pub.publication_date), "2020-05-01")
        self.assertEqual(pub.publication_date_precision, Publication.DatePrecision.MONTH)

    def test_date_precision_follows_the_source(self, _fetch):
        """#147: a missing month or day is stored as 1, but not shown."""
        cases = [([2020], "year", "2020"), ([2020, 5, 3], "day", "3 mai 2020")]
        for parts, precision, shown in cases:
            with self.subTest(parts=parts):
                message = crossref_message()
                message["message"]["issued"] = {"date-parts": [parts]}
                pub = self.make_publication(message)
                pub.refresh_from_db()
                self.assertEqual(pub.publication_date_precision, precision)
                self.assertEqual(pub.formatted_publication_date, shown)

    def test_published_names_are_kept(self, _fetch):
        pub = self.make_publication(crossref_message(authors=[ADA, TURING]))
        slots = list(pub.authorpublication_set.all())
        self.assertEqual([s.published_family_name for s in slots], ["Lovelace", "Turing"])
        self.assertEqual(slots[1].published_orcid, "0000-0001-2345-6789")

    def test_reference_with_doi_is_resolved(self, _fetch):
        pub = self.make_publication(crossref_message(references=[REF_WITH_DOI]))
        ref = CitedReference.objects.get(source=pub)
        self.assertEqual(ref.doi, "10.1000/abc")
        self.assertEqual(ref.target.doi, "10.1000/abc")
        self.assertEqual(ref.target.title, "Cited article")

    def test_reference_without_doi_creates_no_publication(self, _fetch):
        pub = self.make_publication(crossref_message(references=[REF_WITHOUT_DOI]))
        ref = CitedReference.objects.get(source=pub)
        self.assertIsNone(ref.target)
        self.assertEqual(ref.label, "Smith J. Some book. 1999.")
        self.assertEqual(Publication.objects.count(), 1)

    def test_reparse_does_not_duplicate(self, _fetch):
        json_data = crossref_message(references=[REF_WITH_DOI, REF_WITHOUT_DOI])
        pub = self.make_publication(json_data)
        parse_publication(pub)
        self.assertEqual(CitedReference.objects.filter(source=pub).count(), 2)
        self.assertEqual(Publication.objects.count(), 2)

    def test_merge_survives_reparse(self, _fetch):
        pub = self.make_publication(crossref_message(authors=[ADA, ADA_INITIAL]))
        ada, ada_initial = (slot.author for slot in pub.authorpublication_set.all())
        ada.merge_with([ada_initial])

        parse_publication(pub)
        other = self.make_publication(crossref_message(authors=[ADA_INITIAL]))

        self.assertEqual(Author.objects.count(), 1)
        self.assertEqual(other.authorpublication_set.get().author, ada)

    def test_orcid_identifies_the_author(self, _fetch):
        self.make_publication(crossref_message(authors=[TURING]))
        renamed = dict(TURING, given="A. M.")
        self.make_publication(crossref_message(authors=[renamed]))
        self.assertEqual(Author.objects.count(), 1)


class PublicationConstraintTests(TestCase):
    def test_doi_is_unique_when_set(self):
        Publication.objects.create(title="A")
        Publication.objects.create(title="B")
        with patch("references.services.importer.fetch_crossref_json", return_value=None):
            Publication.objects.create(doi="10.1000/abc")
            with self.assertRaises(IntegrityError):
                Publication.objects.create(doi="https://doi.org/10.1000/ABC")

    def test_author_slots_allow_the_same_author_twice_after_a_merge(self):
        pub = Publication.objects.create(title="A")
        author = Author.objects.create(last_name="Lovelace")
        AuthorPublication.objects.create(publication=pub, author=author, order=0)
        AuthorPublication.objects.create(publication=pub, author=author, order=1)
        self.assertEqual(pub.authorpublication_set.count(), 2)


class ParserQueryCountTests(TestCase):
    """The number of queries must not grow with the number of authors or references."""

    def parse(self, json_data):
        pub = Publication.objects.create(title="")
        with_crossref(pub, json_data)
        parse_publication(pub)

    def count_queries(self, size):
        authors = [{"given": f"G{i}", "family": f"F{i}", "ORCID": f"0000-{i}"} for i in range(size)]
        refs = [{"key": f"r{i}", "DOI": f"10.1000/q{size}-{i}"} for i in range(size)]
        with CaptureQueriesContext(connection) as context:
            self.parse(crossref_message(authors=authors, references=refs))
        return len(context)

    def test_query_count_does_not_grow_per_row(self):
        # 200 authors and 200 references: per-row queries would mean more than 600.
        # bulk_create only splits large inserts to respect SQLite's parameter limit.
        self.assertLess(self.count_queries(200), 30)
