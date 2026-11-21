from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, Publication, UserPublication
from references.services.imports.importer import import_publication
from references.tests.helpers import crossref_record
from references.tests.sources import simulated_sources

SOURCE_DOI = "10.1000/source"
CITED_DOI = "10.1000/cited"


def crossref_json(title, references=()):
    return {"message": {"title": [title], "reference": list(references)}}


CROSSREF = {
    SOURCE_DOI: crossref_json("Source", [{"key": "r1", "DOI": CITED_DOI}, {"key": "r2"}]),
    CITED_DOI: crossref_json("Cited", [{"key": "c1", "DOI": "10.1000/deeper"}]),
}


# Crossref knows CROSSREF, the other sources know nothing.
CROSSREF_SOURCES = simulated_sources(crossref=CROSSREF)


@CROSSREF_SOURCES
class ImportPublicationTests(TestCase):
    def test_creating_a_publication_does_not_call_crossref(self):
        Publication.objects.create(doi=SOURCE_DOI)
        self.assertEqual(CROSSREF_SOURCES.single("crossref"), [])

    def test_metadata_is_fetched_only_once(self):
        pub = Publication.objects.create(doi=SOURCE_DOI)
        self.assertTrue(import_publication(pub))
        self.assertTrue(import_publication(pub))
        self.assertEqual(CROSSREF_SOURCES.single("crossref"), [SOURCE_DOI])
        self.assertEqual(pub.title, "Source")
        self.assertIsNotNone(crossref_record(pub))

    def test_force_fetch_refreshes(self):
        pub = Publication.objects.create(doi=SOURCE_DOI)
        import_publication(pub)
        import_publication(pub, force_fetch=True)
        self.assertEqual(CROSSREF_SOURCES.single("crossref"), [SOURCE_DOI, SOURCE_DOI])

    def test_unknown_doi_returns_false(self):
        pub = Publication.objects.create(doi="10.1000/unknown")
        self.assertFalse(import_publication(pub))
        self.assertIsNone(crossref_record(pub))

    def test_without_references_cited_publications_are_not_created(self):
        pub = Publication.objects.create(doi=SOURCE_DOI)
        import_publication(pub)
        self.assertFalse(CitedReference.objects.exists())
        self.assertEqual(Publication.objects.count(), 1)

    def test_with_references_imports_cited_publications_one_level_deep(self):
        pub = Publication.objects.create(doi=SOURCE_DOI)
        import_publication(pub, with_references=True)

        cited = Publication.objects.get(doi=CITED_DOI)
        self.assertEqual(cited.title, "Cited")
        self.assertEqual(CitedReference.objects.filter(source=pub).count(), 2)
        self.assertFalse(CitedReference.objects.filter(source=cited).exists())
        self.assertFalse(Publication.objects.filter(doi="10.1000/deeper").exists())

    def test_already_fetched_cited_publications_are_not_fetched_again(self):
        Publication.objects.create(doi=CITED_DOI)
        import_publication(Publication.objects.get(doi=CITED_DOI))
        CROSSREF_SOURCES.forget()

        import_publication(Publication.objects.create(doi=SOURCE_DOI), with_references=True)
        self.assertEqual(CROSSREF_SOURCES.single("crossref"), [SOURCE_DOI])
        self.assertEqual(CROSSREF_SOURCES.batches("crossref"), [])

    def test_cited_publications_are_fetched_in_one_batch(self):
        references = [{"key": f"r{i}", "DOI": f"10.1000/many{i}"} for i in range(120)]
        CROSSREF_SOURCES.add(crossref={"10.1000/big": crossref_json("Big", references)})

        import_publication(Publication.objects.create(doi="10.1000/big"), with_references=True)

        self.assertEqual(CROSSREF_SOURCES.single("crossref"), ["10.1000/big"])
        # One batch of 120 DOIs: three requests of at most 50.
        batches = CROSSREF_SOURCES.batches("crossref")
        self.assertEqual([len(batch) for batch in batches], [50, 50, 20])

    def test_doi_unknown_to_crossref_is_not_requested_again_by_imports(self):
        other = crossref_json("Other", [{"key": "o1", "DOI": "10.1000/ghost"}])
        CROSSREF_SOURCES.add(crossref={"10.1000/other": other})
        import_publication(Publication.objects.create(doi="10.1000/other"), with_references=True)
        ghost = Publication.objects.get(doi="10.1000/ghost")
        self.assertIsNotNone(crossref_record(ghost))
        self.assertIsNone(crossref_record(ghost).data)

        CROSSREF_SOURCES.forget()
        import_publication(Publication.objects.get(doi="10.1000/other"), with_references=True)
        self.assertEqual(CROSSREF_SOURCES.batches("crossref"), [])


@CROSSREF_SOURCES
class AddToCorpusViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        self.client.force_login(self.user)

    def test_add_by_doi_imports_publication_and_references(self):
        self.client.post(reverse("corpus_add_by_identifier"), {"identifier": SOURCE_DOI})
        pub = Publication.objects.get(doi=SOURCE_DOI)
        self.assertTrue(UserPublication.objects.filter(user=self.user, publication=pub).exists())
        self.assertTrue(pub.parse_references)
        self.assertEqual(CitedReference.objects.filter(source=pub).count(), 2)

    def test_add_by_doi_of_a_known_cited_publication_imports_its_references(self):
        # The cited publication exists, already fetched, without its references (#9).
        import_publication(Publication.objects.create(doi=SOURCE_DOI), with_references=True)
        cited = Publication.objects.get(doi=CITED_DOI)
        CROSSREF_SOURCES.forget()

        self.client.post(reverse("corpus_add_by_identifier"), {"identifier": CITED_DOI})

        self.assertEqual(CitedReference.objects.filter(source=cited).count(), 1)
        self.assertEqual(CROSSREF_SOURCES.single("crossref"), [])
        self.assertEqual(CROSSREF_SOURCES.batches("crossref"), [["10.1000/deeper"]])

    def test_both_ways_of_adding_share_the_same_logic(self):
        pub = Publication.objects.create(doi=SOURCE_DOI)
        self.client.post(reverse("corpus_add", args=[pub.pk]))
        pub.refresh_from_db()
        self.assertTrue(pub.parse_references)
        self.assertEqual(CitedReference.objects.filter(source=pub).count(), 2)

    def test_message_reports_a_failed_import(self):
        response = self.client.post(
            reverse("corpus_add_by_identifier"), {"identifier": "10.1000/unknown"}, follow=True
        )
        self.assertContains(response, "n&#x27;ont pas pu être récupérées")
