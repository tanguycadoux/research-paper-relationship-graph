from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from references.models import Author, AuthorPublication, OrcidRecord, Publication
from references.services.orcid_api import fetch_orcid_record
from references.services.orcid_profile import orcid_profile

ORCID = "0000-0002-1825-0097"


def work(*dois, relationship="self"):
    return {
        "external-ids": {
            "external-id": [
                {
                    "external-id-type": "doi",
                    "external-id-value": doi,
                    "external-id-relationship": relationship,
                }
                for doi in dois
            ]
        }
    }


RECORD = {
    "person": {
        "name": {
            "given-names": {"value": "Josiah"},
            "family-name": {"value": "Carberry"},
            "credit-name": None,
        },
        "other-names": {
            "other-name": [
                {"content": "Josiah Stinkney Carberry", "display-index": 3},
                {"content": "J. Carberry", "display-index": 1},
            ]
        },
    },
    "activities-summary": {
        "works": {
            "group": [
                work("10.5555/SIGNED"),
                work("https://doi.org/10.5555/unsigned"),
                work("10.5555/unknown"),
                work("10.5555/journal", relationship="part-of"),
                {"external-ids": {"external-id": []}},  # a work without DOI
            ]
        }
    },
}


def response(payload, status_code=200):
    return Mock(status_code=status_code, headers={}, json=Mock(return_value=payload))


@patch("references.services.http._get_session")
class OrcidApiTests(SimpleTestCase):
    def test_record_asked_in_json(self, get_session):
        get_session.return_value.get.return_value = response(RECORD)
        with self.assertLogs("references.services", level="INFO"):
            self.assertEqual(fetch_orcid_record(ORCID), RECORD)
        call = get_session.return_value.get.call_args
        self.assertEqual(call.args[0], f"https://pub.orcid.org/v3.0/{ORCID}/record")
        self.assertEqual(call.kwargs["headers"]["Accept"], "application/json")
        self.assertIn("references-manager", call.kwargs["headers"]["User-Agent"])

    def test_unknown_orcid(self, get_session):
        get_session.return_value.get.return_value = response({}, 404)
        with self.assertLogs("references.services", level="INFO"):
            self.assertIsNone(fetch_orcid_record(ORCID))


class OrcidProfileTests(TestCase):
    """#59: the public ORCID record, asked on demand, informative only."""

    @classmethod
    def setUpTestData(cls):
        cls.author = Author.objects.create(first_name="J.", last_name="Carberry", orcid=ORCID)
        cls.signed = Publication.objects.create(title="Signed", doi="10.5555/signed")
        AuthorPublication.objects.create(publication=cls.signed, author=cls.author, order=0)
        cls.unsigned = Publication.objects.create(title="Unsigned", doi="10.5555/unsigned")
        Publication.objects.create(title="A book")  # no DOI: never matched
        cls.url = reverse("author_detail", args=[cls.author.pk])
        cls.refresh_url = reverse("author_orcid_refresh", args=[cls.author.pk])

    def store(self):
        OrcidRecord.objects.create(orcid=ORCID, data=RECORD, fetched_at=timezone.now())

    def test_profile(self):
        self.store()
        profile = orcid_profile(self.author)
        self.assertEqual(profile["name"], "Josiah Carberry")
        self.assertEqual(profile["credit_name"], "")
        self.assertEqual(profile["other_names"], ["J. Carberry", "Josiah Stinkney Carberry"])
        self.assertEqual(profile["work_count"], 5)
        self.assertEqual(profile["in_base_count"], 2)
        self.assertEqual(list(profile["without_author"]), [self.unsigned])

    def test_no_profile_without_record_or_orcid(self):
        self.assertIsNone(orcid_profile(self.author))
        self.assertIsNone(orcid_profile(Author.objects.create(last_name="Sans ORCID")))

    def test_record_survives_a_merge(self):
        self.store()
        other = Author.objects.create(first_name="Josiah", last_name="Carberry")
        self.author.merge_with([other])
        self.assertIsNotNone(orcid_profile(self.author))

    def test_author_page_shows_the_profile(self):
        self.store()
        response = self.client.get(self.url)
        self.assertContains(response, "Profil ORCID")
        self.assertContains(response, "J. Carberry, Josiah Stinkney Carberry")
        self.assertContains(response, "5, dont 2 dans la base")
        self.assertContains(response, reverse("publication_detail", args=[self.unsigned.pk]))
        self.assertNotContains(response, "Compléter depuis ORCID")  # anonymous

    @patch("references.services.orcid_profile.fetch_orcid_record", return_value=RECORD)
    def test_refresh_stores_the_record(self, fetch):
        self.client.force_login(get_user_model().objects.create_user("alice"))
        self.assertContains(self.client.get(self.url), "Compléter depuis ORCID")
        response = self.client.post(self.refresh_url, follow=True)
        fetch.assert_called_once_with(ORCID)
        self.assertEqual(OrcidRecord.objects.get(orcid=ORCID).data, RECORD)
        self.assertContains(response, "Profil ORCID mis à jour.")
        self.assertContains(response, "Actualiser depuis ORCID")

    @patch("references.services.orcid_profile.fetch_orcid_record", return_value=None)
    def test_failure_keeps_the_stored_record(self, _fetch):
        self.store()
        self.client.force_login(get_user_model().objects.create_user("alice"))
        response = self.client.post(self.refresh_url, follow=True)
        self.assertContains(response, "ORCID n&#x27;a pas répondu")
        self.assertEqual(OrcidRecord.objects.get(orcid=ORCID).data, RECORD)

    @patch("references.services.orcid_profile.fetch_orcid_record")
    def test_refresh_requires_login_and_post(self, fetch):
        self.assertEqual(self.client.post(self.refresh_url).status_code, 302)
        self.client.force_login(get_user_model().objects.create_user("alice"))
        self.assertEqual(self.client.get(self.refresh_url).status_code, 405)
        fetch.assert_not_called()
