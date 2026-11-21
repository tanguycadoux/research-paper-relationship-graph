import datetime

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.html import strip_tags

from references.models import Author, AuthorPublication, Publication
from references.services.display.citations import (
    ARTICLE,
    BOOK,
    CHAPTER,
    OTHER,
    PREPRINT,
    PROCEEDINGS,
    Work,
    apa,
    citation_work,
    ieee,
    initials,
    publication_citations,
)
from references.tests.helpers import with_crossref

ARTICLE_WORK = Work(
    authors=(("Cadoux", "Tanguy"), ("Simon", "Damien")),
    year=2026,
    title="Transient Analyses",
    kind=ARTICLE,
    venue="IEEE Transactions on Applied Superconductivity",
    short_venue="IEEE Trans. Appl. Supercond.",
    volume="36",
    issue="5",
    pages="1–6",
    doi="10.1109/tasc.2026.1",
)


def names(count):
    return tuple((f"Author{n}", "Ada") for n in range(1, count + 1))


class InitialsTests(SimpleTestCase):
    def test_compound_and_several_given_names(self):
        self.assertEqual(initials("Jean-Pierre Marie"), "J.-P. M.")

    def test_initials_already_written(self):
        self.assertEqual(initials("S.R."), "S. R.")
        self.assertEqual(initials("C. E."), "C. E.")


class ApaTests(SimpleTestCase):
    def test_journal_article(self):
        self.assertEqual(
            apa(ARTICLE_WORK),
            "Cadoux, T., &amp; Simon, D. (2026). Transient Analyses. "
            "<i>IEEE Transactions on Applied Superconductivity</i>, <i>36</i>(5), 1–6. "
            "https://doi.org/10.1109/tasc.2026.1",
        )

    def test_one_author(self):
        work = Work(authors=(("Lovelace", "Ada"),), year=1843, title="Notes")
        self.assertEqual(apa(work), "Lovelace, A. (1843). Notes.")

    def test_three_authors(self):
        work = Work(authors=names(3), year=2020, title="T")
        self.assertTrue(apa(work).startswith("Author1, A., Author2, A., &amp; Author3, A. (2020)."))

    def test_beyond_twenty_authors_the_first_nineteen_then_the_last(self):
        text = apa(Work(authors=names(25), year=2020, title="T"))
        self.assertIn("Author19, A., …, Author25, A. (2020).", text)
        self.assertNotIn("Author20", text)
        self.assertNotIn("&amp;", text)

    def test_without_year(self):
        self.assertIn("(n.d.)", apa(Work(authors=names(1), title="T")))

    def test_without_authors_the_title_comes_first(self):
        self.assertEqual(apa(Work(year=2020, title="Report")), "Report. (2020).")

    def test_no_period_after_a_question_mark(self):
        self.assertIn("Why? (2020)", apa(Work(title="Why?", year=2020)))

    def test_article_number_instead_of_pages(self):
        work = Work(title="T", kind=ARTICLE, venue="J", volume="3", article_number="042")
        self.assertIn("<i>J</i>, <i>3</i>, Article 042.", apa(work))

    def test_arxiv_preprint(self):
        work = Work(
            authors=names(1),
            year=2017,
            title="Attention",
            kind=PREPRINT,
            doi="10.48550/arxiv.1706.03762",
            arxiv="1706.03762",
        )
        self.assertEqual(
            apa(work),
            "Author1, A. (2017). Attention (arXiv:1706.03762). arXiv. "
            "https://doi.org/10.48550/arxiv.1706.03762",
        )

    def test_book_in_italics_with_its_publisher(self):
        work = Work(authors=names(1), year=2016, title="Theory", kind=BOOK, publisher="CUP")
        self.assertEqual(apa(work), "Author1, A. (2016). <i>Theory</i>. CUP.")

    def test_chapter_in_its_book(self):
        work = Work(title="Ch", kind=CHAPTER, venue="Book", pages="1–9", publisher="CUP")
        self.assertIn("Ch. (n.d.). In <i>Book</i> (pp. 1–9). CUP.", apa(work))

    def test_escaped(self):
        work = Work(authors=(("O'Brien & Co", ""),), title="<script>", venue="A & B")
        text = apa(work)
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)
        self.assertIn("<i>A &amp; B</i>.", text)


class IeeeTests(SimpleTestCase):
    def test_journal_article(self):
        self.assertEqual(
            ieee(ARTICLE_WORK),
            "T. Cadoux and D. Simon, “Transient Analyses,” <i>IEEE Trans. Appl. Supercond.</i>, "
            "vol. 36, no. 5, pp. 1–6, 2026, doi: 10.1109/tasc.2026.1.",
        )

    def test_three_to_six_authors(self):
        self.assertTrue(
            ieee(Work(authors=names(3), title="T")).startswith(
                "A. Author1, A. Author2, and A. Author3, “T.”"
            )
        )

    def test_beyond_six_authors_et_al(self):
        self.assertTrue(
            ieee(Work(authors=names(7), title="T")).startswith("A. Author1 <i>et al.</i>")
        )

    def test_without_year_nor_authors(self):
        self.assertEqual(ieee(Work(title="T", kind=OTHER, venue="V")), "“T,” <i>V</i>.")

    def test_proceedings(self):
        work = Work(title="T", kind=PROCEEDINGS, venue="Proc. X", year=2004, pages="86–88")
        self.assertEqual(ieee(work), "“T,” in <i>Proc. X</i>, 2004, pp. 86–88.")

    def test_single_page_and_article_number(self):
        self.assertIn("p. 12", ieee(Work(title="T", kind=ARTICLE, venue="J", pages="12")))
        work = Work(title="T", kind=ARTICLE, venue="J", article_number="042")
        self.assertIn("Art. no. 042", ieee(work))

    def test_arxiv_preprint(self):
        work = Work(authors=names(1), year=2017, title="Attention", kind=PREPRINT, arxiv="1.2")
        self.assertEqual(ieee(work), "A. Author1, “Attention,” arXiv:1.2, 2017.")

    def test_book(self):
        work = Work(authors=names(1), year=2016, title="Theory", kind=BOOK, publisher="CUP")
        self.assertEqual(ieee(work), "A. Author1, <i>Theory</i>. CUP, 2016.")


class CitationWorkTests(TestCase):
    def publication(self, **fields):
        pub = Publication.objects.create(**fields)
        for order, (last, first) in enumerate([("Cadoux", "Tanguy"), ("Simon", "Damien")]):
            author = Author.objects.create(last_name=last, first_name=first)
            AuthorPublication.objects.create(publication=pub, author=author, order=order)
        return pub

    def test_fields_of_the_base_and_venue_of_crossref(self):
        pub = self.publication(
            doi="10.1/a",
            title="Title by hand",
            publication_date=datetime.date(2023, 5, 1),
        )
        with_crossref(
            pub,
            {
                "message": {
                    "type": "journal-article",
                    "title": ["Title of the registry"],
                    "container-title": ["Journal &amp; Co"],
                    "volume": "33",
                    "issue": "5",
                    "page": "1-5",
                    "publisher": "IEEE",
                }
            },
        )
        work = citation_work(pub)
        self.assertEqual(work.authors, (("Cadoux", "Tanguy"), ("Simon", "Damien")))
        self.assertEqual(work.title, "Title by hand")
        self.assertEqual(work.year, 2023)
        self.assertEqual(work.kind, ARTICLE)
        self.assertEqual(work.venue, "Journal & Co")
        self.assertEqual(work.pages, "1–5")

    def test_arxiv_preprint_without_crossref(self):
        work = citation_work(self.publication(doi="10.48550/arXiv.1706.03762", title="T"))
        self.assertEqual(work.kind, PREPRINT)
        self.assertEqual(work.arxiv, "1706.03762")
        self.assertIsNone(work.year)

    def test_publication_entered_by_hand(self):
        citations = publication_citations(Publication.objects.create(title="Notes"))
        self.assertEqual(
            [strip_tags(c.html) for c in citations["styles"]], ["Notes. (n.d.).", "“Notes.”"]
        )
        self.assertTrue(citations["bibtex"].startswith("@misc{notes,"))

    def test_bibtex_entry_of_the_publication_alone(self):
        pub = self.publication(doi="10.1/a", title="T", publication_date=datetime.date(2023, 1, 1))
        bibtex = publication_citations(pub)["bibtex"]
        self.assertIn("@misc{cadoux2023,", bibtex)
        self.assertIn("author = {Cadoux, Tanguy and Simon, Damien}", bibtex)


class CitationPanelTests(TestCase):
    def test_panel_on_the_page_without_any_request(self):
        pub = Publication.objects.create(doi="10.1/a", title="A <b>bold</b> title")
        response = self.client.get(reverse("publication_detail", args=[pub.pk]))
        self.assertContains(response, 'popovertarget="citation-panel"')
        self.assertContains(response, 'id="citation-apa"')
        self.assertContains(response, 'id="citation-ieee"')
        self.assertContains(response, 'id="citation-bibtex"')
        # The entry wraps to the panel instead of being cut on its right (#413).
        self.assertRegex(
            response.content.decode(), r'<pre id="citation-bibtex" class="[^"]*whitespace-pre-wrap'
        )
        self.assertContains(response, "A &lt;b&gt;bold&lt;/b&gt; title")
        # « Copier » waits for the script.
        self.assertContains(response, 'data-copy="citation-apa" hidden')
        self.assertContains(response, "js/copy_citation.js")
