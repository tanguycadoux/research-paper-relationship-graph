"""
Client of the OpenAlex API, a complement to Crossref and DataCite: institutions
with ROR identifiers, ORCIDs missing from Crossref, author identifiers.

Terms (checked on 2026-10-21): free, no key. A single work is free and unlimited;
a filtered list request uses a small part of a daily budget (about 1,000 batches
a day without key).
"""

import re

from django.conf import settings

from ..identifiers.doi import normalize_doi
from . import http

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
OPENALEX_INSTITUTIONS_URL = "https://api.openalex.org/institutions"
BATCH_SIZE = 50
DOI_URL = re.compile(r"^https?://(?:dx\.)?doi\.org/", re.IGNORECASE)


def fetch_openalex_work(doi):
    """Return the OpenAlex work of a DOI, or None. Single lookups are free."""
    if not doi:
        return None
    return _get_json(f"{OPENALEX_WORKS_URL}/doi:{doi}", {}, f"DOI {doi}")


def fetch_openalex_works(dois):
    """
    Fetch several DOIs with one request per batch of BATCH_SIZE.
    Return {doi: json or None}: None when OpenAlex answered without this DOI.
    DOIs of a batch whose request failed are absent from the result.
    """
    return http.in_batches(dois, BATCH_SIZE, _fetch_batch)


def _fetch_batch(dois):
    params = {"filter": "doi:" + "|".join(dois), "per-page": len(dois)}
    data = _get_json(OPENALEX_WORKS_URL, params, f"batch of {len(dois)} DOIs")
    if data is None:
        return {}
    found = {doi: work for work in data.get("results", []) for doi in work_dois(work)}
    return {doi: found.get(doi) for doi in dois}


def work_dois(work):
    """
    Every DOI of an OpenAlex work, main one first. A work groups the versions of an
    article: the work of an arXiv preprint may be known by its journal DOI (#227).
    """
    urls = [work.get("doi")] + [
        location.get("landing_page_url") for location in work.get("locations") or []
    ]
    dois = [normalize_doi(url) for url in urls if url and DOI_URL.match(url)]
    return list(dict.fromkeys(doi for doi in dois if doi))


# What the list of citing works shows: the authorships are needed for the first author.
CITING_FIELDS = "id,doi,display_name,publication_year,publication_date,authorships,cited_by_count"


def fetch_citing_works(work_id, sort, count):
    """
    The first count works citing an OpenAlex work ('W2741809807'), in the order of
    sort ('cited_by_count:desc'). Return (total, works), or None if the request
    failed. A filtered list: it uses the daily budget (#163).
    """
    params = {
        "filter": f"cites:{work_id}",
        "sort": sort,
        "per-page": count,
        "select": CITING_FIELDS,
    }
    data = _get_json(OPENALEX_WORKS_URL, params, f"works citing {work_id}")
    if data is None:
        return None
    return (data.get("meta") or {}).get("count", 0), data.get("results") or []


def short_id(url):
    """'https://openalex.org/I4210141222' -> 'I4210141222' (a ROR link too); "" for None."""
    return (url or "").rsplit("/", 1)[-1]


def contact_params():
    mailto = settings.CROSSREF_MAILTO
    return {"mailto": mailto} if mailto else {}


def _get_json(url, params, subject):
    """One OpenAlex request, with the contact address when there is one."""
    return http.get_json(
        url,
        params=params | contact_params(),
        service="OpenAlex",
        subject=subject,
        contact=settings.CROSSREF_MAILTO,
    )


def fetch_openalex_institutions(ids):
    """
    Return {OpenAlex id: institution} for institution ids ('I2738703131'), one
    request per batch of BATCH_SIZE. Used for the ancestors of an institution.
    """
    return http.in_batches(ids, BATCH_SIZE, _institutions_batch)


def _institutions_batch(ids):
    params = {"filter": "openalex:" + "|".join(ids), "per-page": len(ids)}
    data = _get_json(OPENALEX_INSTITUTIONS_URL, params, f"batch of {len(ids)} institutions")
    return {
        short_id(institution["id"]): institution for institution in (data or {}).get("results", [])
    }
