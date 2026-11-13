from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.forms import IdentifyReferenceForm
from references.models import Publication, UserPublication
from references.services.corrections.publication_merge import find_merge_target
from references.services.identifiers.arxiv import (
    arxiv_doi,
    bare_arxiv_doi,
    typed_doi,
    written_arxiv_doi,
)
from references.tests.helpers import doi_org_answers, without_doi_org

ATTENTION = "10.48550/arxiv.1706.03762"
OLD_STYLE = "10.48550/arxiv.hep-th/9901001"


class ArxivDoiTests(SimpleTestCase):
    """An arXiv identifier or link typed by a user (#267)."""

    def test_identifier_and_links_give_the_doi(self):
        for text in (
            "1706.03762",
            "1706.03762v5",
            "arXiv:1706.03762",
            "arXiv: 1706.03762v5",
            "https://arxiv.org/abs/1706.03762",
            "https://arxiv.org/abs/1706.03762v5",
            "http://arxiv.org/pdf/1706.03762",
            "https://arxiv.org/pdf/1706.03762v5.pdf",
            "arxiv.org/abs/1706.03762/",
            "  https://www.arxiv.org/abs/1706.03762  ",
        ):
            with self.subTest(text=text):
                self.assertEqual(arxiv_doi(text), ATTENTION)

    def test_old_identifiers(self):
        self.assertEqual(arxiv_doi("hep-th/9901001"), OLD_STYLE)
        self.assertEqual(arxiv_doi("https://arxiv.org/abs/hep-th/9901001v2"), OLD_STYLE)
        self.assertEqual(arxiv_doi("math.AG/0101001"), "10.48550/arxiv.math.ag/0101001")

    def test_other_texts_give_nothing(self):
        for text in (
            "",
            None,
            "10.1038/nature14539",
            "9780262035613",
            "1706.037",
            "see arXiv:1706.03762",
            "https://example.org/abs/1706.03762",
            "https://arxiv.org/list/hep-th/new",
        ):
            with self.subTest(text=text):
                self.assertEqual(arxiv_doi(text), "")

    def test_bare_identifier_only(self):
        self.assertEqual(bare_arxiv_doi("arXiv:1706.03762v5"), ATTENTION)
        self.assertEqual(bare_arxiv_doi("https://arxiv.org/abs/1706.03762"), "")

    def test_typed_doi_takes_a_doi_or_an_arxiv_identifier(self):
        self.assertEqual(typed_doi("https://doi.org/10.1038/NATURE14539"), "10.1038/nature14539")
        self.assertEqual(typed_doi("arXiv:1706.03762"), ATTENTION)
        self.assertEqual(typed_doi(ATTENTION), ATTENTION)
        self.assertEqual(typed_doi("9780262035613"), "")


class WrittenArxivDoiTests(SimpleTestCase):
    """An arXiv identifier written in a reference, for #266."""

    def test_written_forms(self):
        for text in (
            "Szegedy, C. et al. Going deeper. Preprint at http://arxiv.org/abs/1409.4842 (2014).",
            "Going deeper with convolutions. arXiv preprint arXiv:1409.4842, 2014.",
            "Szegedy et al., arXiv:1409.4842v1",
        ):
            with self.subTest(text=text):
                self.assertEqual(written_arxiv_doi(text), "10.48550/arxiv.1409.4842")

    def test_no_identifier(self):
        self.assertEqual(written_arxiv_doi("Szegedy, C. Going deeper (2014)."), "")
        self.assertEqual(written_arxiv_doi(None), "")


@patch(
    "references.services.corpus.entries.import_publication",
    side_effect=lambda pub, **_: pub,
)
class AddByArxivViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        self.client.force_login(self.user)

    def add(self, identifier):
        url = reverse("corpus_add_by_identifier")
        return self.client.post(url, {"identifier": identifier}, follow=True)

    @without_doi_org
    def test_link_adds_the_arxiv_doi(self, _import):
        self.add("https://arxiv.org/abs/1706.03762v5")
        pub = Publication.objects.get(doi=ATTENTION)
        self.assertTrue(UserPublication.objects.filter(user=self.user, publication=pub).exists())

    @without_doi_org
    def test_identifier_of_a_known_publication_adds_it(self, _import):
        known = Publication.objects.create(doi=ATTENTION, title="Attention Is All You Need")
        self.add("arXiv:1706.03762")
        self.assertEqual(Publication.objects.count(), 1)
        self.assertTrue(UserPublication.objects.filter(publication=known).exists())

    def test_identifier_unknown_to_doi_org_is_refused(self, _import):
        with doi_org_answers(False):
            response = self.add("2999.99999")
        self.assertContains(response, "Rien n&#x27;a été ajouté")
        self.assertFalse(Publication.objects.exists())

    def test_invalid_identifier_is_refused(self, _import):
        response = self.add("arXiv:quelque chose")
        self.assertContains(response, "un identifiant ou un lien arXiv")
        self.assertFalse(Publication.objects.exists())


class ArxivElsewhereTests(TestCase):
    def test_identification_form_accepts_an_arxiv_link(self):
        form = IdentifyReferenceForm(
            {"method": "doi", "doi": "https://arxiv.org/pdf/1706.03762v2.pdf"}
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["doi"], ATTENTION)

    def test_identification_form_refuses_other_text(self):
        form = IdentifyReferenceForm({"method": "doi", "doi": "arXiv preprint"})
        self.assertFalse(form.is_valid())
        self.assertIn("doi", form.errors)

    def test_merge_target_by_arxiv_identifier(self):
        target = Publication.objects.create(doi=ATTENTION, title="Attention Is All You Need")
        self.assertEqual(find_merge_target("arXiv:1706.03762v7"), target)

    def test_merge_target_by_arxiv_identifier_of_a_replaced_preprint(self):
        published = Publication.objects.create(
            doi="10.5555/published", preprint_doi=ATTENTION, title="Attention"
        )
        self.assertEqual(find_merge_target("https://arxiv.org/abs/1706.03762"), published)
