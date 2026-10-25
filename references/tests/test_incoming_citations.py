from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import IncomingCitations, Publication, UserPublication
from references.services import incoming_citations
from references.services.external_records import Source, store_record
from references.tests.helpers import without_doi_org, without_other_sources


def work(number, year, cited_by, doi="", authors=("Ada Lovelace",)):
    return {
        "id": f"https://openalex.org/W{number}",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "display_name": f"Citant {number}",
        "publication_year": year,
        "publication_date": f"{year}-01-01",
        "cited_by_count": cited_by,
        "authorships": [
            {
                "author_position": "first" if rank == 0 else "middle",
                "author": {"display_name": name},
            }
            for rank, name in enumerate(authors)
        ],
    }


OLD_AND_CITED = work(1, 2001, 50, doi="10.1000/cite", authors=("Ada Lovelace", "Alan Turing"))
RECENT = work(2, 2025, 0)
BOTH = work(3, 2024, 10, doi="10.1000/connu")


def openalex(answers):
    """Mock the list of citing works: {sort: (total, works)}, None for a failure."""
    calls = []

    def fetch(work_id, sort, count):
        calls.append((work_id, sort, count))
        return answers.get(sort)

    return patch("references.services.incoming_citations.fetch_citing_works", new=fetch), calls


class IncomingCitationsTests(TestCase):
    """Works citing a publication according to OpenAlex, on demand (#163)."""

    @classmethod
    def setUpTestData(cls):
        cls.alice = get_user_model().objects.create_user("alice")
        cls.pub = Publication.objects.create(doi="10.1000/cible", title="Cible")
        store_record(cls.pub, Source.OPENALEX, {"id": "https://openalex.org/W99"})
        cls.known = Publication.objects.create(doi="10.1000/connu", title="Connu")

    def setUp(self):
        self.client.force_login(self.alice)

    def fetch(self, answers):
        mock, calls = openalex(answers)
        with mock:
            response = self.client.post(
                reverse("publication_incoming_citations", args=[self.pub.pk])
            )
        return response, calls

    def page(self, **params):
        return self.client.get(reverse("publication_detail", args=[self.pub.pk]), params)

    def test_most_cited_only_when_they_are_all_of_them(self):
        response, calls = self.fetch({incoming_citations.MOST_CITED: (2, [OLD_AND_CITED, RECENT])})
        self.assertRedirects(
            response,
            reverse("publication_detail", args=[self.pub.pk]) + "#incoming-title",
            fetch_redirect_response=False,
        )
        self.assertEqual(calls, [("W99", incoming_citations.MOST_CITED, 25)])
        citations = self.pub.incoming_citations
        self.assertEqual(citations.total, 2)
        self.assertEqual([w["openalex"] for w in citations.works], ["W1", "W2"])

    def test_most_recent_too_beyond_one_page_without_duplicates(self):
        _, calls = self.fetch(
            {
                incoming_citations.MOST_CITED: (300, [OLD_AND_CITED, BOTH]),
                incoming_citations.MOST_RECENT: (300, [RECENT, BOTH]),
            }
        )
        self.assertEqual(len(calls), 2)
        citations = IncomingCitations.objects.get(publication=self.pub)
        self.assertEqual(citations.total, 300)
        self.assertEqual([w["openalex"] for w in citations.works], ["W1", "W3", "W2"])

    def test_summary_keeps_what_the_page_shows(self):
        summary = incoming_citations.summarize(OLD_AND_CITED)
        self.assertEqual(
            summary,
            {
                "openalex": "W1",
                "doi": "10.1000/cite",
                "title": "Citant 1",
                "year": 2001,
                "date": "2001-01-01",
                "first_author": "Ada Lovelace",
                "author_count": 2,
                "cited_by": 50,
            },
        )

    def test_nothing_stored_when_openalex_fails(self):
        response, _ = self.fetch({})
        self.assertFalse(IncomingCitations.objects.exists())
        response = self.client.get(response.url)
        self.assertContains(response, "OpenAlex n&#x27;a pas répondu")

    def test_publication_unknown_to_openalex(self):
        pub = Publication.objects.create(doi="10.1000/inconnu")
        with patch("references.services.incoming_citations.fetch_openalex_work", return_value=None):
            response = self.client.post(
                reverse("publication_incoming_citations", args=[pub.pk]), follow=True
            )
        self.assertContains(response, "OpenAlex ne connaît pas cette publication.")

    def test_work_id_asked_by_doi_without_record(self):
        pub = Publication.objects.create(doi="10.1000/sans-fiche")
        with patch(
            "references.services.incoming_citations.fetch_openalex_work",
            return_value={"id": "https://openalex.org/W7"},
        ) as lookup:
            self.assertEqual(incoming_citations.openalex_id(pub), "W7")
        lookup.assert_called_once_with("10.1000/sans-fiche")

    def test_page_orders_and_links_the_works(self):
        UserPublication.objects.create(user=self.alice, publication=self.known)
        self.fetch(
            {
                incoming_citations.MOST_CITED: (300, [OLD_AND_CITED, BOTH]),
                incoming_citations.MOST_RECENT: (300, [RECENT]),
            }
        )
        response = self.page()
        works = response.context["citing_works"]
        self.assertEqual([w["openalex"] for w in works], ["W1", "W3", "W2"])
        self.assertEqual(works[1]["publication"], self.known)
        self.assertTrue(works[1]["in_corpus"])
        self.assertContains(response, "Seules les 3 plus citées et plus récentes")
        self.assertContains(response, "https://doi.org/10.1000/cite")
        self.assertContains(response, "https://openalex.org/W2")
        recent = self.page(citants="recentes").context["citing_works"]
        self.assertEqual([w["openalex"] for w in recent], ["W2", "W3", "W1"])

    def test_page_before_any_search(self):
        response = self.page()
        self.assertIsNone(response.context["incoming_citations"])
        self.assertContains(response, "Chercher les publications qui la citent")

    def test_no_section_without_doi(self):
        pub = Publication.objects.create(title="Sans DOI")
        response = self.client.get(reverse("publication_detail", args=[pub.pk]))
        self.assertNotContains(response, "Cité dans toute la littérature")

    def test_fetching_needs_a_login(self):
        self.client.logout()
        response, calls = self.fetch({})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(calls, [])

    @without_other_sources
    def test_adding_a_citing_work_comes_back_to_the_page(self):
        url = reverse("publication_detail", args=[self.pub.pk]) + "#incoming-title"
        with patch("references.views.corpus.add_identified", return_value=None):
            response = self.client.post(
                reverse("corpus_add_by_identifier"),
                {"identifier": "10.1000/cite", "status": "to_read", "next": url},
            )
        self.assertRedirects(response, url, fetch_redirect_response=False)
        self.assertTrue(Publication.objects.filter(doi="10.1000/cite").exists())

    @without_doi_org
    def test_corpus_form_still_goes_back_to_the_corpus(self):
        response = self.client.post(reverse("corpus_add_by_identifier"), {"identifier": "x"})
        self.assertRedirects(response, reverse("corpus"))
