"""
Publications proposed for a cited reference on its identification page (#160), never
linked without the user. Measured on the base: Crossref finds the works it registers
from the whole text of the reference, DataCite the JACoW proceedings and the arXiv
preprints from the title alone; a JACoW code written in the reference gives its DOI.

The scores of Crossref do not compare from one search to another, so each candidate is
checked here instead: a title close to the cited one, a year that does not contradict
it, and its first author shown as found or not. The answers of the sources are kept on
the reference (one search per reference, until asked again); the publications of the
base are looked up at each display.
"""

import re
from dataclasses import dataclass

from django.db.models import F
from django.utils import timezone

from ..models import Publication
from .crossref_api import search_crossref
from .datacite_api import fetch_datacite_works, search_datacite_title
from .doi import normalize_doi
from .identification import suggested_title, suggested_year
from .jacow import reference_text, without_jacow_code, written_jacow_doi
from .metadata_formats import datacite_message
from .preprints import is_arxiv, title_words
from .search import Normalized, contains, normalize

MAX_CANDIDATES = 5
# Share of the words of the shorter title found in the other one.
TITLE_OVERLAP = 0.8
# Shared words over the words of the longer title: below, the candidate title is more
# than twice as long as the cited one.
MIN_CLOSENESS = 0.5
# Share of the words of a candidate title found in the whole text of the reference,
# when the title of the reference could not be told apart from its authors.
TEXT_OVERLAP = 0.8
# Copies of articles uploaded to ResearchGate, not their publication (#227).
IGNORED_PREFIXES = ("10.13140/",)
# Short words of titles that tell nothing of the work (title_words drops the shorter).
STOP_WORDS = {"the", "and", "for", "with", "from", "into", "via", "its", "are", "how", "what"}
# Under it, two titles are only close: the first author must be found too.
SAME_TITLE = 0.9
YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")
# End of a sentence of a reference, not an initial: « Noah A. Smith. Recurrent… ».
SENTENCE_END = re.compile(r"(?<!\b[A-Z])[.?!]\s+(?=[A-Z0-9“\"])")


@dataclass
class Candidate:
    title: str
    doi: str = ""
    authors: tuple = ()
    year: int | None = None
    venue: str = ""
    kind: str = ""
    publication: Publication | None = None  # already in the base
    closeness: float = 0  # of the titles, see title_closeness
    year_found: bool | None = None  # None: a year is missing on one side
    author_found: bool | None = None

    @property
    def same_title(self):
        return self.closeness >= SAME_TITLE


def candidates_for(ref):
    """
    The candidates of a reference, best first, and whether a source could not answer.
    The sources are asked once; the answer is kept unless a source failed.
    """
    failed = False
    if ref.candidates is None:
        found, failed = search_sources(ref)
        if not failed:
            ref.candidates = found
            ref.candidates_fetched_at = timezone.now()
            ref.save(update_fields=["candidates", "candidates_fetched_at"])
    else:
        found = ref.candidates
    external = [Candidate(**fields) for fields in found]
    return select(ref, local_candidates(ref) + external), failed


def forget_candidates(ref):
    """Search the sources again at the next display."""
    ref.candidates = None
    ref.candidates_fetched_at = None
    ref.save(update_fields=["candidates", "candidates_fetched_at"])


def search_sources(ref):
    """
    The works found by the sources, as Candidate fields (JSON for the cache), JACoW
    code first, then Crossref, then DataCite. failed: a source did not answer.
    """
    found = []
    jacow_doi = written_jacow_doi(reference_text(ref))
    if jacow_doi:
        record = fetch_datacite_works([jacow_doi]).get(jacow_doi)
        found += [datacite_fields(record, kind="Actes JACoW")] if record else []
    crossref = search_crossref(search_text(ref))
    found += [crossref_fields(item) for item in crossref or []]
    title = cited_title(ref)
    datacite = search_datacite_title(title) if title else []
    found += [datacite_fields(record) for record in datacite or []]
    return found, crossref is None or datacite is None


def crossref_fields(item):
    year = (item.get("issued", {}).get("date-parts") or [[None]])[0][0]
    return {
        "doi": normalize_doi(item.get("DOI", "")),
        "title": (item.get("title") or [""])[0],
        "authors": [author.get("family", "") for author in item.get("author", [])[:3]],
        "year": year,
        "venue": (item.get("container-title") or [""])[0],
        "kind": KINDS.get(item.get("type"), ""),
    }


def datacite_fields(record, kind=""):
    message = datacite_message(record)
    attributes = record["data"].get("attributes", {})
    date_parts = message["issued"]["date-parts"][0]
    doi = normalize_doi(attributes.get("doi") or record["data"].get("id", ""))
    if not kind and is_arxiv(doi):
        kind = "Prépublication arXiv"
    elif not kind and doi.startswith("10.18429/jacow-"):
        kind = "Actes JACoW"
    return {
        "doi": doi,
        "title": (message.get("title") or [""])[0],
        "authors": [author["family"] for author in message["author"][:3]],
        "year": date_parts[0] if date_parts else None,
        "venue": (attributes.get("container") or {}).get("title", ""),
        "kind": kind,
    }


KINDS = {
    "journal-article": "Article",
    "proceedings-article": "Actes de conférence",
    "book-chapter": "Chapitre de livre",
    "book": "Livre",
    "monograph": "Livre",
    "edited-book": "Livre",
    "report": "Rapport",
    "posted-content": "Prépublication",
    "dissertation": "Thèse",
}


def search_text(ref):
    return ref.unstructured or ref.structured_description()


def cited_title(ref):
    """
    The title of the cited work: the field of a structured reference, otherwise the
    sentence after the authors in its text (« Authors. Title. In… »).
    """
    title = suggested_title(ref)
    if not title and ref.unstructured:
        sentences = SENTENCE_END.split(ref.unstructured)
        title = sentences[1] if len(sentences) > 1 else ""
    return without_jacow_code(title)


def cited_year(ref):
    year = suggested_year(ref)
    if year:
        return year
    years = YEAR.findall(ref.unstructured)
    return int(years[-1]) if years else None


def local_candidates(ref):
    """Publications of the base whose title holds the two longest words of the cited title."""
    words = sorted(title_words(cited_title(ref)), key=len, reverse=True)[:2]
    if not words:
        return []
    publications = Publication.objects.alias(_title=Normalized(F("title"))).exclude(
        pk=ref.source_id
    )
    for word in words:
        publications = publications.filter(contains("_title", word))
    publications = publications.prefetch_related("authorpublication_set__author")[:20]
    return [local_candidate(pub) for pub in publications]


def local_candidate(pub):
    date = pub.publication_date
    slots = sorted(pub.authorpublication_set.all(), key=lambda slot: slot.order)[:3]
    return Candidate(
        title=pub.title,
        doi=pub.doi,
        authors=tuple(slot.author.last_name for slot in slots),
        year=date.year if date else None,
        publication=pub,
    )


def select(ref, candidates):
    """
    The candidates whose title is close to the cited one and whose year does not
    contradict it, closest first, without duplicates nor the publication already linked.
    """
    text, title, year = search_text(ref), cited_title(ref), cited_year(ref)
    in_base = publications_by_doi(c.doi for c in candidates if c.publication is None)
    selected, seen = [], set()
    for candidate in candidates:
        key = candidate.doi or f"pk:{candidate.publication.pk}"
        if key in seen or candidate.doi.startswith(IGNORED_PREFIXES):
            continue
        seen.add(key)
        candidate.publication = candidate.publication or in_base.get(candidate.doi)
        if candidate.publication is not None and candidate.publication.pk == ref.target_id:
            continue
        check(candidate, text, title, year)
        if is_likely(candidate):
            selected.append(candidate)
    selected.sort(key=lambda candidate: candidate.closeness, reverse=True)
    return selected[:MAX_CANDIDATES]


def is_likely(candidate):
    """A close title, a year that does not contradict it, an author found if needed."""
    if not candidate.closeness or candidate.year_found is False:
        return False
    return candidate.closeness >= SAME_TITLE or candidate.author_found is not False


def publications_by_doi(dois):
    publications = Publication.objects.with_dois({doi for doi in dois if doi})
    by_doi = {}
    for pub in publications:
        by_doi[pub.doi] = pub
        if pub.preprint_doi:
            by_doi[pub.preprint_doi] = pub
    return by_doi


def check(candidate, text, title, year):
    candidate.closeness = title_closeness(candidate.title, text, title)
    if year and candidate.year:
        candidate.year_found = abs(candidate.year - year) <= 1
    if candidate.authors and candidate.authors[0]:
        candidate.author_found = normalize(candidate.authors[0]) in normalize(text)


def title_closeness(candidate_title, text, title):
    """
    How close the candidate title is to the cited one, from 0 (not the same work) to 1.
    Most words of the shorter title are in the other, which is at most twice as long (a
    subtitle added); a longer title is another work that shares its topic. When the
    cited title could not be told apart from the authors, the candidate title must be
    found in the whole text.
    """
    words = significant_words(candidate_title)
    if len(words) < 2:
        return 0
    cited = significant_words(title)
    if len(cited) < 2:
        return 1 if len(words & significant_words(text)) / len(words) >= TEXT_OVERLAP else 0
    shared = len(words & cited)
    if shared / min(len(words), len(cited)) < TITLE_OVERLAP:
        return 0
    closeness = shared / max(len(words), len(cited))
    return closeness if closeness >= MIN_CLOSENESS else 0


def significant_words(text):
    """Words of a title, singular: « Ion Sources » and « Ion Source » are the same."""
    return {
        word[:-1] if len(word) > 3 and word.endswith("s") else word
        for word in title_words(text) - STOP_WORDS
    }
