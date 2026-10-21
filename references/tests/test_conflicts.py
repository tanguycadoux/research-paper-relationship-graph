from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import MetadataConflict, Publication
from references.services import conflicts
from references.services.external_records import Source, store_record
from references.services.parser import parse_publication
from references.tests.helpers import with_crossref

THUILLIER = {"given": "Thomas", "family": "Thuillier"}
ANGOT = {"given": "Julien", "family": "Angot"}


def publication_with_openalex(raw_names):
    pub = Publication.objects.create(title="A")
    with_crossref(pub, {"message": {"title": ["A"], "author": [THUILLIER, ANGOT]}})
    authorships = [{"raw_author_name": name, "institutions": []} for name in raw_names]
    store_record(pub, Source.OPENALEX, {"authorships": authorships})
    parse_publication(pub)
    return pub


class NamesSummaryTests(SimpleTestCase):
    def test_summary(self):
        self.assertEqual(conflicts.names_summary(["A B"]), "1 auteur : A B")

    def test_long_lists_are_truncated(self):
        summary = conflicts.names_summary([f"Author {i}" for i in range(1012)])
        self.assertTrue(summary.startswith("1012 auteurs : Author 0; "))
        self.assertTrue(summary.endswith(" ; …"))


class AuthorsMismatchTests(TestCase):
    def test_mismatch_is_reported_once(self):
        pub = publication_with_openalex(["Thomas Thuillier"])
        parse_publication(pub)
        conflict = MetadataConflict.objects.get()
        self.assertEqual(conflict.kind, conflicts.Kind.AUTHORS_MISMATCH)
        self.assertEqual(conflict.publication, pub)
        self.assertEqual(conflict.current_value, "2 auteurs : Thomas Thuillier; Julien Angot")
        self.assertEqual(conflict.proposed_value, "1 auteur : Thomas Thuillier")
        self.assertEqual(conflict.source, Source.OPENALEX)

    def test_a_decided_conflict_is_not_reopened_by_a_new_import(self):
        pub = publication_with_openalex(["Thomas Thuillier"])
        conflicts.resolve(MetadataConflict.objects.get(), conflicts.Status.SEEN, None)
        parse_publication(pub)
        self.assertEqual(MetadataConflict.objects.get().status, conflicts.Status.SEEN)

    def test_open_conflict_disappears_when_the_sources_agree_again(self):
        pub = publication_with_openalex(["Thomas Thuillier"])
        authorships = [
            {"raw_author_name": "Thomas Thuillier", "institutions": []},
            {"raw_author_name": "Julien Angot", "institutions": []},
        ]
        store_record(pub, Source.OPENALEX, {"authorships": authorships})
        parse_publication(pub)
        self.assertFalse(MetadataConflict.objects.exists())

    def test_no_conflict_when_the_authors_match(self):
        publication_with_openalex(["Thuillier, Thomas", "Angot, Julien"])
        self.assertFalse(MetadataConflict.objects.exists())


class ResolveTests(TestCase):
    def conflict(self, kind):
        return MetadataConflict.objects.create(
            kind=kind,
            publication=Publication.objects.create(title="A"),
            field="x",
            source=Source.OPENALEX,
        )

    def test_informative_conflict_can_only_be_seen(self):
        conflict = self.conflict(conflicts.Kind.AUTHORS_MISMATCH)
        with self.assertRaises(ValueError):
            conflicts.resolve(conflict, conflicts.Status.ACCEPTED, None)
        conflicts.resolve(conflict, conflicts.Status.SEEN, None)
        self.assertIsNotNone(conflict.resolved_at)

    def test_other_conflicts_are_kept_or_accepted(self):
        conflict = self.conflict(conflicts.Kind.ORCID)
        with self.assertRaises(ValueError):
            conflicts.resolve(conflict, conflicts.Status.SEEN, None)
        conflicts.resolve(conflict, conflicts.Status.KEPT, None)
        self.assertEqual(conflict.status, conflicts.Status.KEPT)


class ConflictsPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        self.client.force_login(self.user)
        self.pub = publication_with_openalex(["Thomas Thuillier"])
        self.conflict = MetadataConflict.objects.get()

    def test_page_lists_open_conflicts_with_the_seen_button(self):
        response = self.client.get(reverse("conflict_list"))
        self.assertContains(response, "Auteurs différents selon les sources")
        self.assertContains(response, 'value="seen"')
        self.assertNotContains(response, 'value="accepted"')

    def test_decision_is_traced(self):
        url = reverse("conflict_resolve", args=[self.conflict.pk])
        self.assertRedirects(self.client.post(url, {"decision": "seen"}), reverse("conflict_list"))
        self.conflict.refresh_from_db()
        self.assertEqual((self.conflict.status, self.conflict.resolved_by), ("seen", self.user))
        response = self.client.get(reverse("conflict_list"))
        self.assertContains(response, "Aucun conflit à trancher")
        self.assertContains(response, "Décisions récentes")

    def test_impossible_decision_is_refused(self):
        url = reverse("conflict_resolve", args=[self.conflict.pk])
        response = self.client.post(url, {"decision": "accepted"}, follow=True)
        self.assertContains(response, "pas possible")
        self.conflict.refresh_from_db()
        self.assertEqual(self.conflict.status, "open")

    def test_post_only_and_login_required(self):
        url = reverse("conflict_resolve", args=[self.conflict.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("conflict_list")).status_code, 302)
