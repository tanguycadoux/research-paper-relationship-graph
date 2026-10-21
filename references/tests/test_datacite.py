import json
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase

from references.models import Publication
from references.services.datacite_api import fetch_datacite_json, fetch_datacite_works
from references.services.external_records import Source
from references.services.importer import import_publication
from references.services.metadata_formats import datacite_message
from references.tests.helpers import crossref_record, without_openalex

FIXTURE = Path(__file__).parent / "fixtures" / "datacite_jacow_ecris2016_tuao05.json"
JACOW_DOI = "10.18429/jacow-ecris2016-tuao05"
JACOW = json.loads(FIXTURE.read_text(encoding="utf-8"))


def response(payload, status_code=200):
    return Mock(status_code=status_code, headers={}, json=Mock(return_value=payload))


@patch("references.services.http._get_session")
class DataciteApiTests(SimpleTestCase):
    def call(self, get_session, responses, function, *args):
        get_session.return_value.get.side_effect = responses
        with self.assertLogs("references.services", level="INFO"):
            return function(*args)

    def test_single_doi(self, get_session):
        result = self.call(get_session, [response(JACOW)], fetch_datacite_json, JACOW_DOI)
        self.assertEqual(result, JACOW)
        url = get_session.return_value.get.call_args.args[0]
        self.assertEqual(url, f"https://api.datacite.org/dois/{JACOW_DOI}")

    def test_unknown_doi(self, get_session):
        result = self.call(get_session, [response({}, 404)], fetch_datacite_json, JACOW_DOI)
        self.assertIsNone(result)

    def test_batch(self, get_session):
        payload = {"data": [dict(JACOW["data"], id="10.18429/JACoW-ECRIS2016-TUAO05")]}
        works = self.call(
            get_session, [response(payload)], fetch_datacite_works, [JACOW_DOI, "10.1000/ghost"]
        )
        self.assertEqual(works[JACOW_DOI]["data"]["attributes"]["publicationYear"], 2016)
        self.assertIsNone(works["10.1000/ghost"])
        params = get_session.return_value.get.call_args.kwargs["params"]
        self.assertEqual(params["ids"], f"{JACOW_DOI},10.1000/ghost")

    def test_failed_batch_is_absent(self, get_session):
        works = self.call(get_session, [response({}, 404)], fetch_datacite_works, [JACOW_DOI])
        self.assertEqual(works, {})


class DataciteMessageTests(SimpleTestCase):
    def test_real_jacow_record(self):
        message = datacite_message(JACOW)
        self.assertEqual(message["title"], ["First Plasma of the PHOENIX V3 ECR Ion Source"])
        self.assertEqual(message["issued"], {"date-parts": [[2016]]})
        self.assertEqual(message["author"][0], {"given": "Thomas", "family": "Thuillier"})
        self.assertEqual(message["reference"], [])

    def test_orcid_and_references(self):
        record = {
            "data": {
                "attributes": {
                    "titles": [{"title": "Dataset"}],
                    "dates": [{"date": "2020-03-04", "dateType": "Issued"}],
                    "creators": [
                        {
                            "givenName": "Ada",
                            "familyName": "Lovelace",
                            "nameIdentifiers": [
                                {
                                    "nameIdentifier": "https://orcid.org/0000-0001",
                                    "nameIdentifierScheme": "ORCID",
                                }
                            ],
                        },
                        {"name": "CERN", "nameType": "Organizational"},
                    ],
                    "relatedIdentifiers": [
                        {
                            "relationType": "References",
                            "relatedIdentifierType": "DOI",
                            "relatedIdentifier": "10.1000/cited",
                        },
                        {
                            "relationType": "IsPartOf",
                            "relatedIdentifierType": "ISBN",
                            "relatedIdentifier": "978-3-95450-186-1",
                        },
                    ],
                }
            }
        }
        message = datacite_message(record)
        self.assertEqual(message["issued"], {"date-parts": [[2020, 3, 4]]})
        self.assertEqual(message["author"][0]["ORCID"], "https://orcid.org/0000-0001")
        self.assertEqual(message["author"][1], {"given": "", "family": "CERN"})
        self.assertEqual(message["reference"], [{"key": "datacite-0", "DOI": "10.1000/cited"}])


@without_openalex
@patch("references.services.importer.fetch_datacite_json", return_value=JACOW)
@patch("references.services.importer.fetch_crossref_json", return_value=None)
class SingleDoiTests(TestCase):
    def test_doi_unknown_to_crossref_is_found_in_datacite(self, crossref, datacite):
        pub = Publication.objects.create(doi=JACOW_DOI)
        self.assertTrue(import_publication(pub))
        self.assertEqual(pub.title, "First Plasma of the PHOENIX V3 ECR Ion Source")
        self.assertEqual(pub.authorpublication_set.count(), 10)
        self.assertEqual(pub.external_records.get().source, Source.DATACITE)

    def test_crossref_answer_is_used_first(self, crossref, datacite):
        crossref.return_value = {"message": {"title": ["Article Crossref"]}}
        pub = Publication.objects.create(doi="10.1000/x")
        import_publication(pub)
        datacite.assert_not_called()


def source_with_references(dois):
    references = [{"key": f"r{i}", "DOI": doi} for i, doi in enumerate(dois)]
    return {"message": {"title": ["Source"], "reference": references}}


@without_openalex
class CitedDoisTests(TestCase):
    def import_source(self, crossref_works, datacite_works):
        source = Publication.objects.create(doi="10.1000/source")
        dois = ["10.1000/in-crossref", JACOW_DOI, "10.1000/ghost"]
        with (
            patch(
                "references.services.importer.fetch_crossref_json",
                return_value=source_with_references(dois),
            ),
            patch("references.services.importer.fetch_crossref_works", side_effect=crossref_works),
            patch("references.services.importer.fetch_datacite_works", side_effect=datacite_works),
        ):
            import_publication(source, with_references=True)

    def test_dois_missing_from_crossref_are_asked_to_datacite_in_one_batch(self):
        datacite_calls = []

        def datacite_works(dois):
            datacite_calls.append(sorted(dois))
            return {doi: JACOW if doi == JACOW_DOI else None for doi in dois}

        self.import_source(
            lambda dois: {
                doi: {"message": {"title": ["Crossref"]}} if doi == "10.1000/in-crossref" else None
                for doi in dois
            },
            datacite_works,
        )
        self.assertEqual(datacite_calls, [sorted([JACOW_DOI, "10.1000/ghost"])])
        jacow = Publication.objects.get(doi=JACOW_DOI)
        self.assertEqual(jacow.title, "First Plasma of the PHOENIX V3 ECR Ion Source")
        ghost = Publication.objects.get(doi="10.1000/ghost")
        self.assertEqual(ghost.external_records.exclude(source="openalex").count(), 2)
        self.assertFalse(ghost.external_records.filter(data__isnull=False).exists())

    def test_doi_is_not_marked_unknown_when_datacite_fails(self):
        self.import_source(lambda dois: {doi: None for doi in dois}, lambda dois: {})
        self.assertIsNone(crossref_record(Publication.objects.get(doi="10.1000/ghost")))
