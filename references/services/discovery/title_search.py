"""
Find a publication from its title (#309), to add it without knowing its DOI: the
candidates of the identification of a reference (#160) for a text typed by the user, a
title and, if known, its first author and year. The base first, so that a known
publication is not created again; then Crossref (the whole text) and DataCite (the
title). Each candidate is checked here, as for a reference: the scores of Crossref do
not compare.

One request per source when the form is sent, never while typing; the answers are kept
a few minutes, so that coming back to the results after an addition asks nothing.
"""

import hashlib
import json
from dataclasses import dataclass

from django.core.cache import cache

from ..corrections.candidates import (
    Candidate,
    crossref_fields,
    datacite_fields,
    publications_titled,
    select_likely,
    significant_words,
)
from ..sources.crossref_api import search_crossref
from ..sources.datacite_api import search_datacite_title

CACHE_SECONDS = 10 * 60
# More than for a reference: a fragment of a title is less precise than a whole one, and
# the right work came 6th or later for one fragment of 8 measured. Still one request.
CROSSREF_ROWS = 10
MAX_CANDIDATES = 8
# Fewer significant words would match too many works.
MIN_WORDS = 2


@dataclass(frozen=True)
class TitleQuery:
    title: str
    author: str = ""
    year: int | None = None

    @property
    def text(self):
        """What Crossref is given (query.bibliographic): author, title, year."""
        return " ".join(part for part in (self.author, self.title, str(self.year or "")) if part)

    def cache_key(self):
        fields = json.dumps([self.title.casefold(), self.author.casefold(), self.year])
        return "title-search:" + hashlib.sha256(fields.encode()).hexdigest()


def is_searchable(title):
    return len(significant_words(title)) >= MIN_WORDS


def search(query):
    """The likely candidates, best first, and whether a source could not answer."""
    found, failed = sources_answers(query)
    candidates = publications_titled(query.title) + [Candidate(**fields) for fields in found]
    likely = select_likely(
        candidates,
        query.text,
        query.title,
        query.year,
        author_text=query.author,
        fragment=True,
        limit=MAX_CANDIDATES,
    )
    return likely, failed


def sources_answers(query):
    """The works found by the sources, as Candidate fields; kept unless a source failed."""
    found = cache.get(query.cache_key())
    if found is not None:
        return found, False
    crossref = search_crossref(query.text, rows=CROSSREF_ROWS)
    datacite = search_datacite_title(query.title)
    found = [crossref_fields(item) for item in crossref or []]
    found += [datacite_fields(record) for record in datacite or []]
    failed = crossref is None or datacite is None
    if not failed:
        cache.set(query.cache_key(), found, CACHE_SECONDS)
    return found, failed
