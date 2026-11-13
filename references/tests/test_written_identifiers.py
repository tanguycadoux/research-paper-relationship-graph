from copy import deepcopy
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from references.models import CitedReference, Publication
from references.services.imports.parser import parse_publication
from references.services.imports.written_identifiers import (
    link_written_identifiers,
    written_doi,
)
from references.services.sources.external_records import Source, has_record
from references.tests.helpers import with_crossref
from references.tests.test_candidates import JACOW, JACOW_DOI, JACOW_RECORD, datacite_record

# Bibliography of « Deep learning » (10.1038/nature14539), as Crossref gives it (#266).
SZEGEDY = {
    "key": "szegedy",
    "unstructured": "Szegedy, C. et al. Going deeper with convolutions. Preprint at "
    "http://arxiv.org/abs/1409.4842 (2014).",
}
HE = {
    "key": "he",
    "unstructured": "He, K., Zhang, X., Ren, S. and Sun, J. Deep residual learning for image "
    "recognition. arXiv preprint arXiv:1512.03385 (2015).",
}
MALDACENA = {
    "key": "maldacena",
    "unstructured": "J. Maldacena, The large N limit of superconformal field theories and "
    "supergravity, arXiv:hep-th/9711200.",
}
NO_IDENTIFIER = {"key": "wilson", "unstructured": "Wilson, M. Superconducting Magnets (1983)."}

SZEGEDY_DOI = "10.48550/arxiv.1409.4842"
HE_DOI = "10.48550/arxiv.1512.03385"
MALDACENA_DOI = "10.48550/arxiv.hep-th/9711200"
SZEGEDY_RECORD = datacite_record(SZEGEDY_DOI, "Going Deeper with Convolutions", "Szegedy", 2014)
HE_RECORD = datacite_record(HE_DOI, "Deep Residual Learning for Image Recognition", "He", 2015)
MALDACENA_RECORD = datacite_record(
    MALDACENA_DOI,
    "The Large N Limit of Superconformal Field Theories and Supergravity",
    "Maldacena",
    1997,
)
RECORDS = {SZEGEDY_DOI: SZEGEDY_RECORD, HE_DOI: HE_RECORD, MALDACENA_DOI: MALDACENA_RECORD}

PUBLISHED_DOI = "10.1109/cvpr.2015.7298594"
PUBLISHED = {
    "message": {
        "DOI": PUBLISHED_DOI,
        "type": "proceedings-article",
        "title": ["Going deeper with convolutions"],
        "issued": {"date-parts": [[2015, 6]]},
    }
}


def declaring_its_version(record, doi):
    """The DataCite record of a preprint whose authors declare the published version."""
    record = deepcopy(record)
    record["data"]["attributes"]["relatedIdentifiers"] = [
        {"relationType": "IsVersionOf", "relatedIdentifierType": "DOI", "relatedIdentifier": doi}
    ]
    return record


@patch("references.services.imports.preprints.fetch_crossref_works", return_value={})
@patch("references.services.imports.written_identifiers.fetch_datacite_works")
class WrittenArxivIdentifierTests(TestCase):
    def setUp(self):
        self.source = Publication.objects.create(doi="10.1038/nature14539")
        references = [SZEGEDY, HE, MALDACENA, NO_IDENTIFIER, JACOW]
        with_crossref(
            self.source, {"message": {"title": ["Deep learning"], "reference": references}}
        )
        parse_publication(self.source)

    def ref(self, key):
        return CitedReference.objects.get(source=self.source, key=key)

    def test_written_forms(self, _works, _crossref):
        self.assertEqual(written_doi(self.ref("szegedy")), SZEGEDY_DOI)
        self.assertEqual(written_doi(self.ref("he")), HE_DOI)
        self.assertEqual(written_doi(self.ref("maldacena")), MALDACENA_DOI)
        self.assertEqual(written_doi(self.ref("wilson")), "")
        self.assertEqual(written_doi(self.ref(JACOW["key"])), JACOW_DOI)

    def test_linked_once_datacite_confirms(self, works, _crossref):
        works.return_value = RECORDS | {JACOW_DOI: JACOW_RECORD}
        report = link_written_identifiers(self.source)
        self.assertEqual((report.found, report.linked, report.replaced), (4, 4, 0))
        target = self.ref("szegedy").target
        self.assertEqual(target.doi, SZEGEDY_DOI)
        self.assertTrue(has_record(target, Source.DATACITE))
        self.assertFalse(self.ref("szegedy").resolved_manually)
        self.assertEqual(self.ref("maldacena").target.doi, MALDACENA_DOI)
        self.assertIsNone(self.ref("wilson").target)

    def test_one_datacite_request_for_jacow_and_arxiv(self, works, _crossref):
        works.return_value = {}
        link_written_identifiers(self.source)
        works.assert_called_once_with(sorted([SZEGEDY_DOI, HE_DOI, MALDACENA_DOI, JACOW_DOI]))

    def test_unknown_to_datacite_creates_nothing(self, works, _crossref):
        works.return_value = dict.fromkeys(RECORDS)
        count = Publication.objects.count()
        self.assertEqual(link_written_identifiers(self.source).linked, 0)
        self.assertEqual(Publication.objects.count(), count)

    def test_other_title_creates_nothing(self, works, _crossref):
        works.return_value = {SZEGEDY_DOI: datacite_record(SZEGEDY_DOI, "Another work", "X", 2014)}
        count = Publication.objects.count()
        link_written_identifiers(self.source)
        self.assertIsNone(self.ref("szegedy").target)
        self.assertEqual(Publication.objects.count(), count)

    def test_known_preprint_linked_without_request(self, works, _crossref):
        published = Publication.objects.create(
            doi=PUBLISHED_DOI, preprint_doi=SZEGEDY_DOI, title="Going deeper with convolutions"
        )
        works.return_value = {}
        link_written_identifiers(self.source)
        self.assertEqual(self.ref("szegedy").target, published)
        self.assertNotIn(SZEGEDY_DOI, works.call_args.args[0])

    def test_preprint_replaced_by_its_published_version(self, works, crossref):
        works.return_value = {SZEGEDY_DOI: declaring_its_version(SZEGEDY_RECORD, PUBLISHED_DOI)}
        crossref.return_value = {PUBLISHED_DOI: PUBLISHED}
        report = link_written_identifiers(self.source)
        self.assertEqual(report.replaced, 1)
        target = self.ref("szegedy").target
        self.assertEqual((target.doi, target.preprint_doi), (PUBLISHED_DOI, SZEGEDY_DOI))
        self.assertEqual(target.title, "Going deeper with convolutions")

    def test_command_links_the_bibliographies_already_imported(self, works, _crossref):
        works.return_value = RECORDS
        out = StringIO()
        call_command("link_written_identifiers", stdout=out)
        self.assertIn("Références qui écrivent un identifiant : 4", out.getvalue())
        self.assertIn("Références reliées à leur publication : 3", out.getvalue())
        self.assertEqual(self.ref("he").target.doi, HE_DOI)
