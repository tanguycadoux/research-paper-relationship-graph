from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import Author, MetadataConflict, OrcidRecord, Publication
from references.services.corrections import conflicts
from references.services.imports.importer import import_publication
from references.services.imports.orcid_names import complete_names, completed_given_name
from references.services.sources.orcid_api import fetch_orcid_names
from references.tests.sources import simulated_sources
from references.tests.test_orcid_profile import RECORD

ORCID = "0000-0002-6266-8511"


def entry(orcid, given, family):
    return {"orcid-id": orcid, "given-names": given, "family-names": family}


def search(*entries, **sources):
    """Simulate the grouped ORCID search as knowing these entries only."""
    return simulated_sources(orcid_names={e["orcid-id"]: e for e in entries}, **sources)


class CompletedGivenNameTests(SimpleTestCase):
    def test_completion(self):
        cases = [
            ("T.", "Thomas", "Thomas"),
            ("", "Thomas", "Thomas"),
            ("J. S.", "Josiah Stinkney", "Josiah Stinkney"),
            ("J.-L.", "Jean-Luc", "Jean-Luc"),
            ("A. K.", "Angie", "Angie K."),
            ("C.M.", "Claude", "Claude M."),
            ("T.", "Thomas Jean", "Thomas Jean"),
            ("Thomas", "T.", "Thomas"),  # ORCID less complete: kept
            ("Hélène", "Helene", "Hélène"),  # same name: the accents are kept
        ]
        for current, orcid, expected in cases:
            with self.subTest(current=current, orcid=orcid):
                self.assertEqual(completed_given_name(current, orcid), expected)

    def test_different_given_names(self):
        self.assertIsNone(completed_given_name("P.", "Thomas"))
        self.assertIsNone(completed_given_name("Thierry", "Thomas"))


class OrcidSearchApiTests(SimpleTestCase):
    def test_one_request_per_batch(self):
        orcids = [f"0000-0000-0000-{n:04}" for n in range(60)]
        with search(entry(orcids[0], "A", "B")) as sources:
            names = fetch_orcid_names(orcids)
        self.assertEqual(sources.batches("orcid"), [orcids[:50], orcids[50:]])
        self.assertEqual(sources.to("orcid")[0].params["rows"], "50")
        self.assertEqual(names[orcids[0]]["given-names"], "A")
        self.assertIsNone(names[orcids[59]])
        self.assertEqual(len(names), 60)

    def test_failed_batch_is_absent(self):
        with search(unreachable=["orcid"]):
            self.assertEqual(fetch_orcid_names([ORCID]), {})


class CompleteNamesTests(TestCase):
    """#220: names completed from ORCID, never overwritten."""

    def setUp(self):
        self.author = Author.objects.create(first_name="T.", last_name="Thuillier", orcid=ORCID)

    def complete(self, *entries, **kwargs):
        with search(*entries) as sources:
            completed = complete_names(Author.objects.all(), **kwargs)
        self.author.refresh_from_db()
        return completed, sources

    def test_initials_completed_and_family_name_case_kept(self):
        completed, _ = self.complete(entry(ORCID, "thomas", "THUILLIER"))
        self.assertEqual(completed, 1)
        self.assertEqual(str(self.author), "Thomas Thuillier")
        self.assertEqual(OrcidRecord.objects.get(orcid=ORCID).search_data["given-names"], "thomas")
        self.assertFalse(MetadataConflict.objects.exists())

    def test_asked_once_unless_refresh(self):
        Author.objects.create(last_name="Sans ORCID")
        self.complete(entry(ORCID, "Thomas", "Thuillier"))
        _, sources = self.complete(entry(ORCID, "Thomas", "Thuillier"))
        self.assertEqual(sources.requests, [])
        _, sources = self.complete(entry(ORCID, "Thomas", "Thuillier"), refresh=True)
        self.assertEqual(sources.batches("orcid"), [[ORCID]])

    def test_unknown_orcid_is_stored_as_asked(self):
        self.complete()
        self.assertEqual(OrcidRecord.objects.get(orcid=ORCID).search_data, {})
        self.assertEqual(str(self.author), "T. Thuillier")

    def test_different_name_is_a_conflict_that_can_be_accepted(self):
        self.complete(entry(ORCID, "Paul", "Martin"))
        self.assertEqual(str(self.author), "T. Thuillier")
        conflict = MetadataConflict.objects.get(kind=MetadataConflict.Kind.ORCID_NAME)
        self.assertEqual(conflict.current_value, "Thuillier, T.")
        self.assertEqual(conflict.proposed_value, "Martin, Paul")
        self.assertEqual(conflict.source, "orcid")
        conflicts.resolve(conflict, conflicts.Status.ACCEPTED, None)
        self.author.refresh_from_db()
        self.assertEqual(str(self.author), "Paul Martin")

    def test_name_corrected_by_hand_is_never_changed(self):
        self.author.name_edited = True
        self.author.save()
        self.complete(entry(ORCID, "Paul", "Martin"))
        self.assertEqual(str(self.author), "T. Thuillier")
        self.assertFalse(MetadataConflict.objects.exists())

    def test_private_or_incomplete_name_changes_nothing(self):
        self.complete(entry(ORCID, "Thuillier", None))
        self.assertEqual(str(self.author), "T. Thuillier")
        self.assertFalse(MetadataConflict.objects.exists())

    def test_command(self):
        out = StringIO()
        with search(entry(ORCID, "Thomas", "Thuillier")):
            call_command("complete_orcid_names", stdout=out)
        self.assertIn("Noms complétés depuis ORCID : 1", out.getvalue())

    def test_profile_refresh_completes_the_name(self):
        name = {"given-names": {"value": "Thomas"}, "family-name": {"value": "Thuillier"}}
        record = RECORD | {"person": {"name": name}}
        self.client.force_login(get_user_model().objects.create_user("alice"))
        with simulated_sources(orcid_records={ORCID: record}):
            self.client.post(reverse("author_orcid_refresh", args=[self.author.pk]))
        self.author.refresh_from_db()
        self.assertEqual(str(self.author), "Thomas Thuillier")

    def test_edit_form_marks_the_name_as_edited(self):
        self.client.force_login(get_user_model().objects.create_user("alice"))
        url = reverse("author_edit", args=[self.author.pk])
        data = {"first_name": "T.", "last_name": "Thuillier", "orcid": ORCID}
        self.client.post(url, data)
        self.author.refresh_from_db()
        self.assertFalse(self.author.name_edited)  # the name is unchanged
        self.client.post(url, data | {"first_name": "Tom"})
        self.author.refresh_from_db()
        self.assertTrue(self.author.name_edited)


class ImportCompletesNamesTests(TestCase):
    def test_authors_of_the_imported_publication(self):
        pub = Publication.objects.create(doi="10.1000/a")
        crossref = {
            "message": {
                "title": ["A"],
                "author": [
                    {"given": "T.", "family": "Thuillier", "ORCID": f"https://orcid.org/{ORCID}"},
                    {"given": "H.", "family": "Felice"},
                ],
            }
        }
        with search(entry(ORCID, "Thomas", "Thuillier"), crossref={pub.doi: crossref}) as sources:
            import_publication(pub)
        self.assertEqual(sources.batches("orcid"), [[ORCID]])
        self.assertEqual(
            sorted(str(a) for a in Author.objects.all()), ["H. Felice", "Thomas Thuillier"]
        )
