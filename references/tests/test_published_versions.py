import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import Author, AuthorPublication, MetadataConflict, Publication
from references.services.external_records import Source, store_record
from references.services.openalex_api import fetch_openalex_works, work_dois
from references.services.published_versions import suggest_published_versions
from references.tests.helpers import without_other_sources

ARXIV = "10.48550/arxiv.2403.03225"
JOURNAL = "10.1038/s41598-025-95297-z"
COPY = "10.65215/2q58a426"  # a third party's copy, posted-content (#227)
TITLE = "Leveraging prior mean models for faster Bayesian optimization"
Kind = MetadataConflict.Kind


def openalex_work(*dois):
    """An OpenAlex work grouping a journal version and the arXiv preprint."""
    return {
        "doi": f"https://doi.org/{dois[0]}",
        "locations": [{"landing_page_url": f"https://doi.org/{doi}"} for doi in dois]
        + [{"landing_page_url": "http://arxiv.org/abs/2403.03225"}],
    }


def crossref(doi=JOURNAL, kind="journal-article", title=TITLE, family="Boltz", year=2025):
    return {
        "message": {
            "DOI": doi,
            "type": kind,
            "title": [title],
            "author": [{"given": "Tobias", "family": family}],
            "container-title": ["Scientific Reports"],
            "issued": {"date-parts": [[year, 4, 10]]},
        }
    }


class WorkDoisTests(SimpleTestCase):
    def test_every_doi_of_the_work_main_one_first(self):
        self.assertEqual(work_dois(openalex_work(JOURNAL, ARXIV)), [JOURNAL, ARXIV])

    @patch("references.services.openalex_api.http.get_json")
    def test_batch_finds_a_preprint_known_by_its_journal_doi(self, get_json):
        work = openalex_work(JOURNAL, ARXIV)
        get_json.return_value = {"results": [work]}
        self.assertEqual(fetch_openalex_works([ARXIV]), {ARXIV: work})


class PreprintTestCase(TestCase):
    def setUp(self):
        self.preprint = Publication.objects.create(
            doi=ARXIV, title=TITLE, publication_date=datetime.date(2024, 1, 1)
        )
        author = Author.objects.create(first_name="T.", last_name="Boltz")
        AuthorPublication.objects.create(publication=self.preprint, author=author, order=0)

    def with_openalex(self, *dois):
        store_record(self.preprint, Source.OPENALEX, openalex_work(*dois))

    def suggest(self, works):
        with patch(
            "references.services.published_versions.fetch_crossref_works", return_value=works
        ) as fetch:
            reported = suggest_published_versions([self.preprint])
        return reported, fetch

    def proposal(self):
        return MetadataConflict.objects.filter(kind=Kind.PUBLISHED_VERSION).first()


class SuggestTests(PreprintTestCase):
    def test_verified_version_is_proposed_not_applied(self):
        self.with_openalex(JOURNAL, ARXIV)
        reported, fetch = self.suggest({JOURNAL: crossref()})
        self.assertEqual(reported, 1)
        fetch.assert_called_once_with([JOURNAL])
        proposal = self.proposal()
        self.assertEqual((proposal.current_value, proposal.proposed_value), (ARXIV, JOURNAL))
        self.assertEqual(proposal.details["venue"], "Scientific Reports")
        self.assertTrue(proposal.details["same_title"])
        self.preprint.refresh_from_db()
        self.assertEqual(self.preprint.doi, ARXIV)

    def test_checks_of_the_version(self):
        for name, data in (
            ("copy of a third party", crossref(kind="posted-content")),
            ("another first author", crossref(family="Vaswani")),
            ("published before the preprint", crossref(year=2023)),
            ("another title", crossref(title="Superconducting magnets for ion sources")),
        ):
            with self.subTest(name):
                self.with_openalex(JOURNAL, ARXIV)
                self.assertEqual(self.suggest({JOURNAL: data})[0], 0)
                self.assertIsNone(self.proposal())

    def test_first_verified_candidate_wins(self):
        self.with_openalex(COPY, JOURNAL, ARXIV)
        self.suggest({COPY: crossref(doi=COPY, kind="posted-content"), JOURNAL: crossref()})
        self.assertEqual(self.proposal().proposed_value, JOURNAL)

    def test_asked_once(self):
        self.with_openalex(JOURNAL, ARXIV)
        self.suggest({JOURNAL: crossref()})
        MetadataConflict.objects.update(status=MetadataConflict.Status.KEPT)
        reported, fetch = self.suggest({JOURNAL: crossref()})
        self.assertEqual(reported, 0)
        fetch.assert_not_called()

    def test_nothing_to_check_without_openalex_work_or_other_doi(self):
        _, fetch = self.suggest({})
        fetch.assert_not_called()
        self.with_openalex(ARXIV)
        _, fetch = self.suggest({})
        fetch.assert_not_called()


@without_other_sources
@patch("references.views.conflicts.import_publication", side_effect=lambda pub, **kw: pub)
class DecisionTests(PreprintTestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user("alice")
        self.client.force_login(self.user)
        self.with_openalex(JOURNAL, ARXIV)
        self.suggest({JOURNAL: crossref()})

    def decide(self, decision, answer=None):
        with patch(
            "references.services.published_versions.fetch_crossref_json",
            return_value=crossref() if answer is None else answer,
        ):
            return self.client.post(
                reverse("conflict_resolve", args=[self.proposal().pk]),
                {"decision": decision},
                follow=True,
            )

    def test_conflicts_page_and_publication_page_show_the_proposal(self, _import):
        self.assertContains(self.client.get(reverse("conflict_list")), "Scientific Reports")
        response = self.client.get(reverse("publication_detail", args=[self.preprint.pk]))
        self.assertContains(response, "OpenAlex propose une version publiée")

    def test_accepted_version_replaces_the_preprint(self, imported):
        response = self.decide("accepted")
        self.assertContains(response, "est remplacée par sa version publiée")
        self.preprint.refresh_from_db()
        self.assertEqual((self.preprint.doi, self.preprint.preprint_doi), (JOURNAL, ARXIV))
        self.assertEqual(self.proposal().status, MetadataConflict.Status.ACCEPTED)
        imported.assert_called_once()

    def test_accepted_version_already_in_the_base(self, _import):
        published = Publication.objects.create(doi=JOURNAL, title=TITLE)
        self.decide("accepted")
        self.assertFalse(Publication.objects.filter(pk=self.preprint.pk).exists())
        proposal = self.proposal()
        self.assertEqual((proposal.publication, proposal.status), (published, "accepted"))

    def test_nothing_changes_when_crossref_does_not_answer(self, _import):
        response = self.decide("accepted", answer=False)
        self.assertContains(response, "Crossref n&#x27;a pas répondu")
        self.preprint.refresh_from_db()
        self.assertEqual(self.preprint.doi, ARXIV)
        self.assertEqual(self.proposal().status, MetadataConflict.Status.OPEN)

    def test_kept_preprint(self, _import):
        self.decide("kept")
        self.preprint.refresh_from_db()
        self.assertEqual(self.preprint.doi, ARXIV)
        self.assertEqual(self.proposal().status, MetadataConflict.Status.KEPT)
