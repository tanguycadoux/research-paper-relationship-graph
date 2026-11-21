from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import Publication
from references.services.display.open_access import licence_of, link_label, open_access_link
from references.services.sources.external_records import Source, store_record


def openalex_work(**location):
    """A stored OpenAlex answer whose best open access location is location."""
    return {"best_oa_location": {"is_oa": True, **location} if location else None}


class LinkLabelTests(SimpleTestCase):
    def test_versions(self):
        self.assertEqual(
            link_label("publishedVersion"), "Lire l'article (accès libre, version publiée)"
        )
        self.assertEqual(
            link_label("acceptedVersion"), "Lire l'article (accès libre, version acceptée)"
        )
        self.assertEqual(
            link_label("submittedVersion"), "Lire l'article (accès libre, version soumise)"
        )

    def test_unknown_version(self):
        self.assertEqual(link_label(None), "Lire l'article (accès libre)")


class LicenceTests(SimpleTestCase):
    """#442: the licence of the open access version, short and in plain words."""

    def test_creative_commons(self):
        self.assertEqual(
            licence_of("cc-by-nc-nd"),
            {
                "label": "CC BY-NC-ND",
                "url": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
            },
        )
        self.assertEqual(licence_of("CC-BY")["label"], "CC BY")

    def test_other_licences(self):
        self.assertEqual(
            licence_of("publisher-specific-oa"), {"label": "licence de l'éditeur", "url": None}
        )
        self.assertEqual(licence_of("other-oa")["label"], "autre licence libre")
        self.assertEqual(
            licence_of("cc0")["url"], "https://creativecommons.org/publicdomain/zero/1.0/"
        )

    def test_unknown_or_missing(self):
        for code in (None, "", "implied-oa", "cc-by-xyz"):
            with self.subTest(code=code):
                self.assertIsNone(licence_of(code))


class OpenAccessLinkTests(TestCase):
    """#284: from the stored OpenAlex answer, without any request."""

    def setUp(self):
        self.pub = Publication.objects.create(title="A", doi="10.1/a")

    def test_pdf_first(self):
        store_record(
            self.pub,
            Source.OPENALEX,
            openalex_work(
                pdf_url="https://repo.org/a.pdf",
                landing_page_url="https://repo.org/a",
                version="acceptedVersion",
            ),
        )
        self.assertEqual(
            open_access_link(self.pub),
            {
                "url": "https://repo.org/a.pdf",
                "label": "Lire l'article (accès libre, version acceptée)",
                "licence": None,
            },
        )

    def test_landing_page_without_pdf(self):
        store_record(
            self.pub,
            Source.OPENALEX,
            openalex_work(landing_page_url="https://journal.org/a", version="publishedVersion"),
        )
        self.assertEqual(open_access_link(self.pub)["url"], "https://journal.org/a")

    def test_licence_of_the_openalex_version(self):
        store_record(
            self.pub,
            Source.OPENALEX,
            openalex_work(pdf_url="https://repo.org/a.pdf", license="cc-by"),
        )
        self.assertEqual(open_access_link(self.pub)["licence"]["label"], "CC BY")

    def test_closed_article(self):
        store_record(self.pub, Source.OPENALEX, openalex_work())
        self.assertIsNone(open_access_link(self.pub))

    def test_not_open_location(self):
        location = openalex_work(landing_page_url="https://journal.org/a")
        location["best_oa_location"]["is_oa"] = False
        store_record(self.pub, Source.OPENALEX, location)
        self.assertIsNone(open_access_link(self.pub))

    def test_unknown_to_openalex(self):
        store_record(self.pub, Source.OPENALEX, None)
        self.assertIsNone(open_access_link(self.pub))
        self.assertIsNone(open_access_link(Publication.objects.create(title="B")))

    def test_arxiv_preprint_always_has_its_pdf(self):
        pub = Publication.objects.create(title="B", doi="10.48550/arXiv.1706.03762")
        self.assertEqual(
            open_access_link(pub),
            {
                "url": "https://arxiv.org/pdf/1706.03762",
                "label": "Lire l'article (accès libre, version soumise)",
                "licence": None,
            },
        )

    def test_published_version_of_an_arxiv_preprint(self):
        self.pub.preprint_doi = "10.48550/arXiv.1706.03762"
        self.pub.save()
        self.assertEqual(open_access_link(self.pub)["url"], "https://arxiv.org/pdf/1706.03762")
        store_record(
            self.pub,
            Source.OPENALEX,
            openalex_work(pdf_url="https://journal.org/a.pdf", version="publishedVersion"),
        )
        self.assertEqual(open_access_link(self.pub)["url"], "https://journal.org/a.pdf")


class DetailPageTests(TestCase):
    def test_link_on_the_detail_page(self):
        pub = Publication.objects.create(title="A", doi="10.1/a")
        store_record(
            pub,
            Source.OPENALEX,
            openalex_work(pdf_url="https://repo.org/a.pdf", version="publishedVersion"),
        )
        response = self.client.get(reverse("publication_detail", args=[pub.pk]))
        self.assertContains(response, 'href="https://repo.org/a.pdf" target="_blank"')
        self.assertContains(response, "Lire l&#x27;article (accès libre, version publiée)")

    def test_licence_on_the_detail_page(self):
        pub = Publication.objects.create(title="A", doi="10.1/a")
        store_record(
            pub,
            Source.OPENALEX,
            openalex_work(pdf_url="https://repo.org/a.pdf", license="cc-by-nd"),
        )
        response = self.client.get(reverse("publication_detail", args=[pub.pk]))
        self.assertContains(
            response, 'href="https://creativecommons.org/licenses/by-nd/4.0/" target="_blank"'
        )
        self.assertContains(response, "CC BY-ND")

    def test_licence_without_text(self):
        pub = Publication.objects.create(title="A", doi="10.1/a")
        store_record(
            pub,
            Source.OPENALEX,
            openalex_work(pdf_url="https://repo.org/a.pdf", license="publisher-specific-oa"),
        )
        response = self.client.get(reverse("publication_detail", args=[pub.pk]))
        self.assertContains(response, "licence de l&#x27;éditeur")

    def test_nothing_when_closed(self):
        pub = Publication.objects.create(title="A", doi="10.1/a")
        response = self.client.get(reverse("publication_detail", args=[pub.pk]))
        self.assertNotContains(response, "Lire l")
