"""« Récupérer les bibliographies » up to level 2 or 3 (#431), through the queue."""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from references.models import (
    BibliographyRequest,
    CitedReference,
    FetchRequest,
    Publication,
    UserPublication,
)
from references.services.corpus import tags
from references.services.imports import bibliography_levels, bibliography_requests, fetch_queue
from references.services.imports.bibliography_requests import Scope, Start
from references.services.imports.importer import import_publication
from references.tests.sources import simulated_sources
from references.tests.test_importer import crossref_json

Status = BibliographyRequest.Status
FetchStatus = FetchRequest.Status

# A cites B and C; B cites D and E, C cites E; D cites F; E and F cite nothing.
A, B, C, D, E, F = (f"10.1000/{name}" for name in "abcdef")
CITES = {A: [B, C], B: [D, E], C: [E], D: [F], E: [], F: []}
CROSSREF = {
    doi: crossref_json(doi[-1].upper(), [{"key": f"k{i}", "DOI": c} for i, c in enumerate(cited)])
    for doi, cited in CITES.items()
}
SOURCES = simulated_sources(crossref=CROSSREF)


def run_worker():
    call_command("fetch_worker", "--once", stdout=StringIO())


def imported_a():
    """A with its bibliography, before the test: B and C are known, with their own."""
    with simulated_sources(crossref=CROSSREF):
        return import_publication(Publication.objects.create(doi=A), with_references=True)


def dois(pks):
    return sorted(Publication.objects.filter(pk__in=pks).values_list("doi", flat=True))


@SOURCES
class BibliographyRequestTests(TestCase):
    """The levels, the queue, the cap, « Arrêter »."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        # A is in the corpus with its bibliography: level 1 is in the base.
        self.a = imported_a()
        self.entry = UserPublication.objects.create(user=self.user, publication=self.a)

    def ask(self, depth, start=None):
        return bibliography_requests.ask(
            self.user, start or Start(Scope.PUBLICATION, publication=self.a), depth
        )

    def test_the_estimate_of_each_level(self):
        estimate = bibliography_levels.estimate([self.a.pk])
        levels = [
            (lv.publications, lv.publications_exact, lv.imports, lv.exact) for lv in estimate.levels
        ]
        # Level 1: B and C, the references of A, whose bibliography is in the base.
        # Level 2: about 2 × 2, once the bibliographies of B and C are fetched.
        # Level 3: about 4 × 2, from the 4 bibliographies of level 2.
        self.assertEqual(levels, [(2, True, 0, True), (4, False, 2, True), (8, False, 4, False)])
        self.assertEqual(estimate.average, 2)
        self.assertEqual(
            [(c["depth"], c["imports"], c["exact"]) for c in estimate.choices],
            [(2, 2, True), (3, 6, False)],
        )
        self.assertEqual(estimate.choice(2)["minutes"], 1)
        self.assertEqual(SOURCES.asked("crossref"), [])

    def test_level_2_goes_through_the_queue_in_one_batch(self):
        request = self.ask(2)
        self.assertEqual((request.level, request.status), (2, Status.RUNNING))
        fetches = FetchRequest.objects.all()
        self.assertEqual(sorted(f.identifier for f in fetches), [B, C])
        # Nobody asked for them: they pass after the requests of the pages.
        self.assertFalse(fetches.filter(requesters__isnull=False).exists())
        run_worker()
        request.refresh_from_db()
        self.assertEqual(request.status, Status.DONE)
        # B and C were known with their references: only their cited D and E are asked,
        # in one batch.
        self.assertEqual(SOURCES.single("crossref"), [])
        self.assertEqual([sorted(batch) for batch in SOURCES.batches("crossref")], [[D, E]])
        self.assertTrue(CitedReference.objects.filter(source__doi=B, target__doi=D).exists())
        self.assertEqual(bibliography_requests.imported_count(request), 2)
        # Nothing is added to the corpus.
        self.assertEqual(UserPublication.objects.count(), 1)

    def test_level_3_forms_after_level_2(self):
        request = self.ask(3)
        run_worker()
        request.refresh_from_db()
        self.assertEqual((request.level, request.status), (3, Status.DONE))
        level_3 = request.items.filter(level=3).values_list("publication", flat=True)
        self.assertEqual(dois(level_3), [D, E])
        self.assertTrue(Publication.objects.filter(doi=F).exists())
        self.assertTrue(CitedReference.objects.filter(source__doi=D, target__doi=F).exists())

    def test_what_is_in_the_base_costs_nothing(self):
        self.ask(2)
        run_worker()
        SOURCES.forget()
        count = FetchRequest.objects.count()
        again = self.ask(2)
        self.assertEqual(again.status, Status.DONE)
        self.assertEqual(FetchRequest.objects.count(), count)
        run_worker()
        self.assertEqual(SOURCES.batches("crossref"), [])
        self.assertEqual(SOURCES.single("crossref"), [])

    @override_settings(BIBLIOGRAPHY_REQUEST_LIMIT=1)
    def test_the_cap_stops_the_request(self):
        request = self.ask(3)
        self.assertTrue(request.capped)
        self.assertEqual(FetchRequest.objects.count(), 1)
        run_worker()
        request.refresh_from_db()
        self.assertEqual((request.level, request.status), (2, Status.DONE))
        self.assertEqual(
            bibliography_requests.progress_text(request),
            "Plafond de 1 publication atteint au niveau 2 : 1 publication récupérée.",
        )

    def test_one_request_per_start_raised_to_a_deeper_level(self):
        first = self.ask(2)
        second = self.ask(3)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(BibliographyRequest.objects.get().depth, 3)
        self.assertEqual(FetchRequest.objects.count(), 2)

    def test_stop_cancels_the_imports_nobody_else_waits_for(self):
        request = self.ask(2)
        asked = fetch_queue.enqueue(Publication.objects.get(doi=B), self.user, with_references=True)
        self.assertTrue(bibliography_requests.stop(request, self.user))
        self.assertEqual(request.status, Status.STOPPED)
        cancelled = FetchRequest.objects.get(identifier=C)
        self.assertEqual(cancelled.status, FetchStatus.FAILED)
        self.assertIn("Annulée", cancelled.error)
        asked.refresh_from_db()
        self.assertEqual(asked.status, FetchStatus.PENDING)
        self.assertFalse(bibliography_requests.stop(request, self.user))
        run_worker()
        request.refresh_from_db()
        self.assertEqual(request.status, Status.STOPPED)

    def test_a_level_is_formed_once(self):
        request = self.ask(3)
        stale = BibliographyRequest.objects.get(pk=request.pk)
        stale.level = 1
        self.assertFalse(bibliography_requests.next_level(stale))
        self.assertEqual(request.items.filter(level=2).count(), 2)

    def test_from_the_corpus_and_a_tag(self):
        tags.tag_entry(self.entry, "Projet")
        for start in (Start(Scope.CORPUS), Start(Scope.TAG, tag="Projet")):
            self.assertEqual(start.publication_pks(self.user), [self.a.pk])
        request = self.ask(2, Start(Scope.TAG, tag="Projet"))
        self.assertEqual(request.start, "tag:Projet")
        self.assertEqual(FetchRequest.objects.count(), 2)
        corpus = self.ask(2, Start(Scope.CORPUS))
        self.assertNotEqual(corpus.pk, request.pk)
        # The imports of B and C are shared by both requests.
        self.assertEqual(FetchRequest.objects.count(), 2)

    def test_the_requests_of_the_pages_pass_first(self):
        self.ask(2)
        added = Publication.objects.create(doi="10.1000/added")
        asked = fetch_queue.enqueue(added, self.user, with_references=False)
        self.assertEqual(fetch_queue.claim_next(), asked)

    def test_the_toast_says_the_level_then_the_end_once(self):
        request = self.ask(2)
        toast = bibliography_requests.combined_toast(self.user, None)
        self.assertEqual(toast["text"], "Niveau 2 : 0 publication récupérée sur 2.")
        self.assertTrue(toast["active"] and toast["bibliographies"])
        run_worker()
        toast = bibliography_requests.combined_toast(self.user, None)
        done = "Bibliographies récupérées jusqu'au niveau 2 : 2 publications récupérées."
        self.assertEqual(toast["text"], done)
        self.assertFalse(toast["active"])
        self.assertIsNone(bibliography_requests.combined_toast(self.user, None))
        request.refresh_from_db()
        self.assertTrue(request.notified)


@SOURCES
class BibliographyPagesTests(TestCase):
    """The action, the page of confirmation, « Arrêter », the toast."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        self.a = imported_a()
        entry = UserPublication.objects.create(user=self.user, publication=self.a)
        tags.tag_entry(entry, "Projet A")
        self.client.force_login(self.user)
        self.url = reverse("bibliography_request")

    def test_the_action_on_the_three_starts(self):
        page = self.client.get(reverse("publication_detail", args=[self.a.pk]))
        self.assertContains(page, f"{self.url}?publication={self.a.pk}")
        self.assertContains(self.client.get(reverse("corpus")), f'href="{self.url}"')
        page = self.client.get(reverse("corpus"), {"tag": "Projet A"})
        self.assertContains(page, f"{self.url}?tag=Projet%20A")

    def test_the_page_of_confirmation(self):
        page = self.client.get(self.url, {"publication": self.a.pk})
        self.assertContains(page, "Récupérer les bibliographies")
        self.assertContains(page, "2 publications à récupérer")
        self.assertContains(page, 'value="3"')
        self.assertContains(page, "Le worker de la file ne tourne pas")
        self.assertFalse(BibliographyRequest.objects.exists())

    def test_the_page_of_a_tag(self):
        page = self.client.get(self.url, {"tag": "Projet A"})
        self.assertContains(page, "le tag « Projet A »")
        self.assertContains(page, 'name="tag" value="Projet A"')

    @override_settings(BIBLIOGRAPHY_REQUEST_LIMIT=3)
    def test_the_page_says_the_cap(self):
        page = self.client.get(self.url)
        self.assertContains(page, "plafond de 3 publications")

    def test_ask_then_stop(self):
        response = self.client.post(self.url, {"tag": "Projet A", "depth": "3"})
        self.assertRedirects(response, f"{self.url}?tag=Projet+A")
        request = BibliographyRequest.objects.get()
        self.assertEqual((request.scope, request.depth), (Scope.TAG, 3))
        page = self.client.get(response.url)
        self.assertContains(page, "Demande en cours")
        self.assertContains(page, "Niveau 2 : 0 publication récupérée sur 2.")
        listing = self.client.get(reverse("bibliography_request_list"))
        self.assertContains(listing, "Arrêter")
        stop = reverse("bibliography_request_stop", args=[request.pk])
        response = self.client.post(stop, {"next": "https://example.org/"})
        self.assertRedirects(response, reverse("bibliography_request_list"))
        request.refresh_from_db()
        self.assertEqual(request.status, Status.STOPPED)

    def test_a_wrong_depth_is_refused(self):
        response = self.client.post(self.url, {"depth": "4"}, follow=True)
        self.assertContains(response, "Choisissez le niveau 2 ou le niveau 3.")
        self.assertFalse(BibliographyRequest.objects.exists())

    def test_the_request_of_another_user_cannot_be_stopped(self):
        other = get_user_model().objects.create_user("bob")
        request = bibliography_requests.ask(other, Start(Scope.CORPUS), 2)
        response = self.client.post(reverse("bibliography_request_stop", args=[request.pk]))
        self.assertEqual(response.status_code, 404)

    def test_the_toast_follows_the_request(self):
        self.client.post(self.url, {"publication": self.a.pk, "depth": "2"})
        page = self.client.get(reverse("corpus"))
        self.assertContains(page, "Niveau 2 : 0 publication récupérée sur 2.")
        self.assertContains(page, reverse("bibliography_request_list"))
        state = self.client.get(reverse("fetch_progress")).json()
        self.assertEqual(state["text"], "Niveau 2 : 0 publication récupérée sur 2.")
        self.assertTrue(state["active"])
