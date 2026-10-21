from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, Publication, UserPublication
from references.services.importer import import_publication

SOURCE_DOI = "10.1000/source"
CITED_DOI = "10.1000/cited"


def crossref_json(title, references=()):
    return {"message": {"title": [title], "reference": list(references)}}


CROSSREF = {
    SOURCE_DOI: crossref_json("Source", [{"key": "r1", "DOI": CITED_DOI}, {"key": "r2"}]),
    CITED_DOI: crossref_json("Cited", [{"key": "c1", "DOI": "10.1000/deeper"}]),
}


def fake_fetch(doi):
    return CROSSREF.get(doi)


def fake_fetch_works(dois):
    return {doi: CROSSREF.get(doi) for doi in dois}


def with_mocked_crossref(cls):
    """Mock both Crossref calls; test methods receive (fetch, fetch_works)."""
    cls = patch("references.services.importer.fetch_crossref_json", side_effect=fake_fetch)(cls)
    return patch("references.services.importer.fetch_crossref_works", side_effect=fake_fetch_works)(
        cls
    )


@with_mocked_crossref
class ImportPublicationTests(TestCase):
    def test_creating_a_publication_does_not_call_crossref(self, fetch, fetch_works):
        Publication.objects.create(doi=SOURCE_DOI)
        fetch.assert_not_called()

    def test_metadata_is_fetched_only_once(self, fetch, fetch_works):
        pub = Publication.objects.create(doi=SOURCE_DOI)
        self.assertTrue(import_publication(pub))
        self.assertTrue(import_publication(pub))
        fetch.assert_called_once_with(SOURCE_DOI)
        self.assertEqual(pub.title, "Source")
        self.assertIsNotNone(pub.crossref_fetched_at)

    def test_force_fetch_refreshes(self, fetch, fetch_works):
        pub = Publication.objects.create(doi=SOURCE_DOI)
        import_publication(pub)
        import_publication(pub, force_fetch=True)
        self.assertEqual(fetch.call_count, 2)

    def test_unknown_doi_returns_false(self, fetch, fetch_works):
        pub = Publication.objects.create(doi="10.1000/unknown")
        self.assertFalse(import_publication(pub))
        self.assertIsNone(pub.crossref_fetched_at)

    def test_without_references_cited_publications_are_not_created(self, fetch, fetch_works):
        pub = Publication.objects.create(doi=SOURCE_DOI)
        import_publication(pub)
        self.assertFalse(CitedReference.objects.exists())
        self.assertEqual(Publication.objects.count(), 1)

    def test_with_references_imports_cited_publications_one_level_deep(self, fetch, fetch_works):
        pub = Publication.objects.create(doi=SOURCE_DOI)
        import_publication(pub, with_references=True)

        cited = Publication.objects.get(doi=CITED_DOI)
        self.assertEqual(cited.title, "Cited")
        self.assertEqual(CitedReference.objects.filter(source=pub).count(), 2)
        self.assertFalse(CitedReference.objects.filter(source=cited).exists())
        self.assertFalse(Publication.objects.filter(doi="10.1000/deeper").exists())

    def test_already_fetched_cited_publications_are_not_fetched_again(self, fetch, fetch_works):
        Publication.objects.create(doi=CITED_DOI)
        import_publication(Publication.objects.get(doi=CITED_DOI))
        fetch.reset_mock()

        import_publication(Publication.objects.create(doi=SOURCE_DOI), with_references=True)
        fetch.assert_called_once_with(SOURCE_DOI)
        fetch_works.assert_not_called()

    def test_cited_publications_are_fetched_in_one_batch(self, fetch, fetch_works):
        references = [{"key": f"r{i}", "DOI": f"10.1000/many{i}"} for i in range(120)]
        CROSSREF["10.1000/big"] = crossref_json("Big", references)
        self.addCleanup(CROSSREF.pop, "10.1000/big")

        import_publication(Publication.objects.create(doi="10.1000/big"), with_references=True)

        fetch.assert_called_once_with("10.1000/big")
        fetch_works.assert_called_once()
        self.assertEqual(len(fetch_works.call_args.args[0]), 120)

    def test_doi_unknown_to_crossref_is_not_requested_again_by_imports(self, fetch, fetch_works):
        CROSSREF["10.1000/other"] = crossref_json("Other", [{"key": "o1", "DOI": "10.1000/ghost"}])
        self.addCleanup(CROSSREF.pop, "10.1000/other")
        import_publication(Publication.objects.create(doi="10.1000/other"), with_references=True)
        ghost = Publication.objects.get(doi="10.1000/ghost")
        self.assertIsNotNone(ghost.crossref_fetched_at)
        self.assertIsNone(ghost.crossref_json)

        fetch_works.reset_mock()
        import_publication(Publication.objects.get(doi="10.1000/other"), with_references=True)
        fetch_works.assert_not_called()


@with_mocked_crossref
class AddToCorpusViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        self.client.force_login(self.user)

    def test_add_by_doi_imports_publication_and_references(self, fetch, fetch_works):
        self.client.post(reverse("add_publication_to_user_refs_by_doi"), {"doi": SOURCE_DOI})
        pub = Publication.objects.get(doi=SOURCE_DOI)
        self.assertTrue(UserPublication.objects.filter(user=self.user, publication=pub).exists())
        self.assertTrue(pub.parse_references)
        self.assertEqual(CitedReference.objects.filter(source=pub).count(), 2)

    def test_add_by_doi_of_a_known_cited_publication_imports_its_references(
        self, fetch, fetch_works
    ):
        # The cited publication exists, already fetched, without its references (#9).
        import_publication(Publication.objects.create(doi=SOURCE_DOI), with_references=True)
        cited = Publication.objects.get(doi=CITED_DOI)
        fetch.reset_mock()

        fetch_works.reset_mock()
        self.client.post(reverse("add_publication_to_user_refs_by_doi"), {"doi": CITED_DOI})

        self.assertEqual(CitedReference.objects.filter(source=cited).count(), 1)
        fetch.assert_not_called()
        fetch_works.assert_called_once_with(["10.1000/deeper"])

    def test_both_ways_of_adding_share_the_same_logic(self, fetch, fetch_works):
        pub = Publication.objects.create(doi=SOURCE_DOI)
        self.client.get(reverse("add_publication_to_my_refs", args=[pub.pk]))
        pub.refresh_from_db()
        self.assertTrue(pub.parse_references)
        self.assertEqual(CitedReference.objects.filter(source=pub).count(), 2)

    def test_message_reports_a_failed_import(self, fetch, fetch_works):
        response = self.client.post(
            reverse("add_publication_to_user_refs_by_doi"), {"doi": "10.1000/unknown"}, follow=True
        )
        self.assertContains(response, "n&#x27;ont pas pu être récupérées")
