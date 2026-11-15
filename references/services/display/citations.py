"""
The citation of a publication, formatted here from what the base holds (#286): APA
(7th edition) and IEEE, and its BibTeX entry, the one of the corpus export.

doi.org would format them too (content negotiation, `Accept: text/x-bibliography;
style=apa`), but at one request per style and per publication, for DOIs only, and
from the record of the registry: the title or the authors corrected by hand would be
lost. Here, no request, and the same data as the rest of the page.

The styles are written in English, as the articles they cite (« n.d. », « et al. »,
« pp. »). The HTML is escaped, with the venue or the book title in italics.
"""

import re
from dataclasses import dataclass

from django.utils.html import escape
from django.utils.safestring import mark_safe

from ...models import Publication
from ..corpus.corpus_transfer import bibtex_entry, ordered_authors
from ..imports.preprints import arxiv_id, is_arxiv
from ..sources.external_records import Source, records_by_source
from .publication_details import clean_text

ARTICLE = "article"
PROCEEDINGS = "proceedings"
CHAPTER = "chapter"
BOOK = "book"
PREPRINT = "preprint"
OTHER = "other"
KINDS = {
    "journal-article": ARTICLE,
    "proceedings-article": PROCEEDINGS,
    "book-chapter": CHAPTER,
    "book-part": CHAPTER,
    "book-section": CHAPTER,
    "book": BOOK,
    "monograph": BOOK,
    "edited-book": BOOK,
    "reference-book": BOOK,
    "posted-content": PREPRINT,
}
NAME_PARTS = re.compile(r"[\s.]+")
# APA lists up to 20 authors, then the first 19, an ellipsis and the last one.
APA_MAX_AUTHORS = 20
# IEEE names up to 6 authors, then the first one and « et al. ».
IEEE_MAX_AUTHORS = 6


@dataclass(frozen=True)
class Work:
    """What a citation says of a publication: names are (family, given)."""

    authors: tuple = ()
    year: int | None = None
    title: str = ""
    kind: str = OTHER
    venue: str = ""
    short_venue: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    article_number: str = ""
    publisher: str = ""
    doi: str = ""
    arxiv: str = ""


@dataclass(frozen=True)
class Citation:
    style: str
    slug: str
    html: str


def publication_citations(pub):
    """{"styles": [Citation…], "bibtex": "@article{…}"} for the citation panel."""
    pub = Publication.objects.with_author_slots().get(pk=pub.pk)
    work = citation_work(pub)
    return {
        "styles": [
            Citation("APA", "apa", mark_safe(apa(work))),
            Citation("IEEE", "ieee", mark_safe(ieee(work))),
        ],
        "bibtex": bibtex_entry(pub, set()),
    }


def citation_work(pub):
    """The Work of pub: its own fields, and the venue of its Crossref record."""
    message = (records_by_source(pub).get(Source.CROSSREF) or {}).get("message") or {}
    page = message.get("page", "")
    return Work(
        authors=tuple((author.last_name, author.first_name) for author in ordered_authors(pub)),
        year=pub.publication_date.year if pub.publication_date else None,
        title=pub.readable_title or pub.title,
        kind=PREPRINT if is_arxiv(pub.doi) else KINDS.get(message.get("type"), OTHER),
        venue=first_text(message.get("container-title")),
        short_venue=first_text(message.get("short-container-title")),
        volume=message.get("volume", ""),
        issue=message.get("issue", ""),
        pages=page.replace("-", "–"),
        article_number="" if page else message.get("article-number", ""),
        publisher=message.get("publisher", ""),
        doi=pub.doi,
        arxiv=arxiv_id(pub.doi) if is_arxiv(pub.doi) else "",
    )


def first_text(values):
    return clean_text(next(iter(values or []), ""))


def italic(text):
    return f"<i>{escape(text)}</i>" if text else ""


def italic_sentence(text):
    """« <i>Title</i>. »: the period after the italics, unless the title ends one."""
    return italic(text) + ("" if with_period(text) == text else ".")


def initials(given):
    """« Jean-Pierre Marie » -> « J.-P. M. », « S.R. » -> « S. R. »."""
    return " ".join(
        "-".join(f"{part[0]}." for part in word.split("-") if part)
        for word in NAME_PARTS.split(given)
        if word
    )


def with_period(text):
    """A sentence ends once: no period after « ? », « ! » or « . »."""
    return text if not text or text[-1] in ".?!" else f"{text}."


# APA


def apa(work):
    authors = apa_authors(work.authors)
    year = f"({work.year})." if work.year else "(n.d.)."
    title = APA_TITLES.get(work.kind, apa_title)(work)
    # Without authors, the title takes their place, before the year.
    head = [authors, year, title] if authors else [title, year]
    tail = [APA_SOURCES.get(work.kind, apa_other_source)(work), apa_doi(work)]
    return " ".join(part for part in [*head, *tail] if part)


def apa_name(family, given):
    return escape(f"{family}, {initials(given)}" if given else family)


def apa_authors(authors):
    """« Dupont, J., Martin, A., &amp; Durand, P. »; beyond 20, « … » before the last one."""
    names = [apa_name(*author) for author in authors]
    if len(names) > APA_MAX_AUTHORS:
        return with_period(", ".join([*names[: APA_MAX_AUTHORS - 1], "…", names[-1]]))
    if len(names) > 1:
        return with_period(", ".join(names[:-1]) + f", &amp; {names[-1]}")
    return with_period("".join(names))


def apa_title(work):
    return escape(with_period(work.title))


def apa_book_title(work):
    return italic_sentence(work.title)


def apa_preprint_title(work):
    if work.arxiv:
        return escape(f"{work.title} (arXiv:{work.arxiv}).")
    return apa_title(work)


def apa_article_source(work):
    """« Journal, 12(3), 45–67. »: the journal and the volume in italics."""
    if not work.venue:
        return ""
    parts = [italic(work.venue)]
    if work.volume:
        issue = f"({escape(work.issue)})" if work.issue else ""
        parts.append(italic(work.volume) + issue)
    if work.pages or work.article_number:
        parts.append(escape(work.pages or f"Article {work.article_number}"))
    return ", ".join(parts) + "."


def apa_in_source(work):
    """« In Proceedings (pp. 45–67). Publisher. »"""
    pages = f" (pp. {escape(work.pages)})" if work.pages else ""
    container = f"In {italic(work.venue)}{pages}." if work.venue else ""
    return " ".join(part for part in [container, apa_publisher(work)] if part)


def apa_publisher(work):
    return escape(with_period(work.publisher))


def apa_preprint_source(work):
    return "arXiv." if work.arxiv else apa_publisher(work)


def apa_other_source(work):
    return italic_sentence(work.venue) if work.venue else apa_publisher(work)


def apa_doi(work):
    return escape(f"https://doi.org/{work.doi}") if work.doi else ""


APA_TITLES = {BOOK: apa_book_title, PREPRINT: apa_preprint_title}
APA_SOURCES = {
    ARTICLE: apa_article_source,
    PROCEEDINGS: apa_in_source,
    CHAPTER: apa_in_source,
    BOOK: apa_publisher,
    PREPRINT: apa_preprint_source,
}


# IEEE


def ieee(work):
    """« A. Author, “Title,” Journal, vol. 1, …, 2020, doi: … »: one sentence."""
    authors = ieee_authors(work.authors)
    details = [*IEEE_DETAILS.get(work.kind, ieee_other_details)(work), ieee_doi(work)]
    details = ", ".join(detail for detail in details if detail)
    if work.kind == BOOK:
        body = italic_sentence(work.title) + (f" {details}." if details else "")
    else:
        # The comma, or the period, inside the quotation marks.
        title = escape(work.title)
        body = f"“{title},” {details}." if details else f"“{with_period(title)}”"
    return f"{authors}, {body}" if authors else body


def ieee_name(family, given):
    return escape(f"{initials(given)} {family}" if given else family)


def ieee_authors(authors):
    names = [ieee_name(*author) for author in authors]
    if len(names) > IEEE_MAX_AUTHORS:
        return f"{names[0]} <i>et al.</i>"
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def ieee_pages(work):
    if work.article_number:
        return f"Art. no. {escape(work.article_number)}"
    if not work.pages:
        return ""
    return escape(f"pp. {work.pages}" if "–" in work.pages else f"p. {work.pages}")


def ieee_year(work):
    return str(work.year) if work.year else ""


def ieee_article_details(work):
    return [
        italic(work.short_venue or work.venue),
        escape(f"vol. {work.volume}") if work.volume else "",
        escape(f"no. {work.issue}") if work.issue else "",
        ieee_pages(work),
        ieee_year(work),
    ]


def ieee_proceedings_details(work):
    venue = f"in {italic(work.venue)}" if work.venue else ""
    return [venue, ieee_year(work), ieee_pages(work)]


def ieee_chapter_details(work):
    venue = f"in {italic(work.venue)}" if work.venue else ""
    return [venue, escape(work.publisher), ieee_year(work), ieee_pages(work)]


def ieee_book_details(work):
    return [escape(work.publisher), ieee_year(work)]


def ieee_preprint_details(work):
    source = escape(f"arXiv:{work.arxiv}") if work.arxiv else escape(work.publisher)
    return [source, ieee_year(work)]


def ieee_other_details(work):
    return [italic(work.venue) or escape(work.publisher), ieee_year(work)]


def ieee_doi(work):
    return escape(f"doi: {work.doi}") if work.doi else ""


IEEE_DETAILS = {
    ARTICLE: ieee_article_details,
    PROCEEDINGS: ieee_proceedings_details,
    CHAPTER: ieee_chapter_details,
    BOOK: ieee_book_details,
    PREPRINT: ieee_preprint_details,
}
