"""
Incoming citations (#163): the works that cite a publication according to OpenAlex,
beyond the base, whose « Cité par » only knows the bibliographies imported. Fetched
on demand from the page of the publication, never at import: an old article may have
thousands of citing works. Only the PER_ORDER most cited and the PER_ORDER most
recent are kept, with the total; a citing work becomes a Publication only when
someone adds it to their corpus.
"""

from django.utils import timezone

from ..models import IncomingCitations, Publication
from .doi import normalize_doi
from .external_records import Source, records_by_source
from .openalex_api import fetch_citing_works, fetch_openalex_work
from .publication_table import corpus_ids
from .titles import clean_title

PER_ORDER = 25
MOST_CITED = "cited_by_count:desc"
MOST_RECENT = "publication_date:desc"
# How the page orders the works kept: ?citants=… (most cited by default).
ORDERS = {
    "citees": ("cited_by", "Les plus citées"),
    "recentes": ("date", "Les plus récentes"),
}


class IncomingCitationsError(Exception):
    """Why the citing works could not be fetched, as said to the user."""


def openalex_id(pub):
    """
    The OpenAlex id of pub ('W2741809807'): from its stored OpenAlex record, else by
    its DOI (a single lookup, free). None if OpenAlex does not know it.
    """
    work = records_by_source(pub).get(Source.OPENALEX)
    if not work and pub.doi:
        work = fetch_openalex_work(pub.doi)
    work_id = (work or {}).get("id") or ""
    return work_id.rsplit("/", 1)[-1] or None


def fetch(pub):
    """
    Fetch and store the works citing pub. Return its IncomingCitations, or raise
    IncomingCitationsError. Two requests at most: the most recent are asked only
    when the most cited are not all of them.
    """
    work_id = openalex_id(pub)
    if work_id is None:
        raise IncomingCitationsError("OpenAlex ne connaît pas cette publication.")
    most_cited = fetch_citing_works(work_id, MOST_CITED, PER_ORDER)
    if most_cited is None:
        raise IncomingCitationsError("OpenAlex n'a pas répondu ; réessayez plus tard.")
    total, works = most_cited
    if total > len(works):
        most_recent = fetch_citing_works(work_id, MOST_RECENT, PER_ORDER)
        if most_recent is None:
            raise IncomingCitationsError("OpenAlex n'a pas répondu ; réessayez plus tard.")
        works += most_recent[1]
    kept = list({summary["openalex"]: summary for summary in map(summarize, works)}.values())
    citations, _ = IncomingCitations.objects.update_or_create(
        publication=pub,
        defaults={"total": total, "works": kept, "fetched_at": timezone.now()},
    )
    return citations


def summarize(work):
    """What the page shows of a citing work, without the rest of the answer."""
    authorships = work.get("authorships") or []
    first = next(
        (slot for slot in authorships if slot.get("author_position") == "first"),
        authorships[0] if authorships else {},
    )
    return {
        "openalex": (work.get("id") or "").rsplit("/", 1)[-1],
        "doi": normalize_doi(work.get("doi") or ""),
        "title": clean_title(work.get("display_name")) or "Sans titre",
        "year": work.get("publication_year"),
        "date": work.get("publication_date") or "",
        "first_author": (first.get("author") or {}).get("display_name") or "",
        "author_count": len(authorships),
        "cited_by": work.get("cited_by_count") or 0,
    }


def citing_works(citations, user, order="citees"):
    """
    The works kept, in the order asked, each with publication (the one of the base
    with its DOI, or None) and in_corpus.
    """
    key = ORDERS.get(order, ORDERS["citees"])[0]
    # Stable sorts: by title among equals.
    works = sorted(citations.works, key=lambda work: work["title"].casefold())
    works.sort(key=lambda work: work[key] or 0, reverse=True)
    dois = [work["doi"] for work in works if work["doi"]]
    known = {}
    for pub in Publication.objects.with_dois(dois):
        known[pub.doi] = known[pub.preprint_doi] = pub
    in_corpus = corpus_ids(user)
    shown = []
    for work in works:
        pub = known.get(work["doi"]) if work["doi"] else None
        shown.append(work | {"publication": pub, "in_corpus": bool(pub) and pub.pk in in_corpus})
    return shown
