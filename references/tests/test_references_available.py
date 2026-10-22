from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, Publication, UserPublication
from references.services.publication_table import for_publication_table, references_available
from references.tests.helpers import with_crossref, without_other_sources
from references.tests.test_importer import CROSSREF, SOURCE_DOI, with_mocked_crossref


def crossref_with_bibliography(count):
    references = [{"key": f"r{i}", "unstructured": f"Ref {i}"} for i in range(count)]
    return {"message": {"title": ["T"], "reference-count": count, "reference": references}}


class ReferencesAvailableTests(TestCase):
    """Bibliographies stored but not imported stand out (#126)."""

    @classmethod
    def setUpTestData(cls):
        cls.outside = with_crossref(
            Publication.objects.create(doi="10.1000/out", title="Hors corpus"),
            crossref_with_bibliography(13),
        )
        cls.single = with_crossref(
            Publication.objects.create(doi="10.1000/one", title="Une seule"),
            crossref_with_bibliography(1),
        )
        cls.imported = with_crossref(
            Publication.objects.create(doi="10.1000/in", title="Importée"),
            crossref_with_bibliography(2),
        )
        CitedReference.objects.create(source=cls.imported, position=0, unstructured="?")
        CitedReference.objects.create(source=cls.imported, target=cls.single, position=1)
        cls.manual = Publication.objects.create(title="Saisie à la main")

    def test_annotation_alongside_references_to_identify(self):
        rows = {
            pub.title: (pub.references_imported, pub.references_available, pub.to_identify)
            for pub in for_publication_table(Publication.objects.all())
        }
        self.assertEqual(
            rows,
            {
                "Hors corpus": (0, 13, 0),
                "Une seule": (0, 1, 0),
                "Importée": (2, 2, 1),
                "Saisie à la main": (0, 0, 0),
            },
        )

    def test_count_on_the_detail_page_reads_the_stored_answer(self):
        self.assertEqual(references_available(self.outside), 13)
        self.assertEqual(references_available(self.manual), 0)

    def test_badges_in_the_publication_list(self):
        response = self.client.get(reverse("publication_list"))
        self.assertContains(response, "13 références non importées")
        self.assertContains(response, "1 référence non importée")
        self.assertNotContains(response, "2 références non importées")

    def test_text_and_button_on_the_detail_page(self):
        url = reverse("publication_detail", args=[self.outside.pk])
        import_url = reverse("publication_import_references", args=[self.outside.pk])
        response = self.client.get(url)
        self.assertContains(response, "Les sources listent 13 références")
        self.assertNotContains(response, import_url)
        self.client.force_login(get_user_model().objects.create_user("alice"))
        self.assertContains(self.client.get(url), import_url)
        imported_page = self.client.get(reverse("publication_detail", args=[self.imported.pk]))
        self.assertNotContains(imported_page, "Importer ses références")


@without_other_sources
@with_mocked_crossref
class ImportReferencesViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        self.pub = with_crossref(Publication.objects.create(doi=SOURCE_DOI), CROSSREF[SOURCE_DOI])
        self.url = reverse("publication_import_references", args=[self.pub.pk])

    def test_imports_without_adding_to_the_corpus(self, fetch, fetch_works):
        self.client.force_login(self.user)
        response = self.client.post(self.url, follow=True)
        self.assertRedirects(response, reverse("publication_detail", args=[self.pub.pk]))
        self.assertEqual(CitedReference.objects.filter(source=self.pub).count(), 2)
        self.assertFalse(UserPublication.objects.exists())
        self.assertContains(response, "2 référence(s) importée(s)")
        fetch.assert_not_called()  # the publication's own answer is already stored

    def test_post_only_and_login_required(self, fetch, fetch_works):
        self.assertRedirects(
            self.client.post(self.url),
            f"{reverse('login')}?next={self.url}",
            fetch_redirect_response=False,
        )
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertFalse(CitedReference.objects.exists())
