"""
Client of the OpenAlex API, a complement to Crossref and DataCite: institutions
with ROR identifiers, ORCIDs missing from Crossref, author identifiers.

Terms (checked on 2026-10-21): free, no key. A single work is free and unlimited;
a filtered list request uses a small part of a daily budget (about 1,000 batches
a day without key).
"""

import re

from django.conf import settings

from . import http
from .doi import normalize_doi

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
OPENALEX_INSTITUTIONS_URL = "https://api.openalex.org/institutions"
BATCH_SIZE = 50
DOI_URL = re.compile(r"^https?://(?:dx\.)?doi\.org/", re.IGNORECASE)


def fetch_openalex_work(doi):
    """Return the OpenAlex work of a DOI, or None. Single lookups are free."""
    if not doi:
        return None
    return http.get_json(
        f"{OPENALEX_WORKS_URL}/doi:{doi}",
        params=contact_params(),
        service="OpenAlex",
        subject=f"DOI {doi}",
        contact=settings.CROSSREF_MAILTO,
    )


def fetch_openalex_works(dois):
    """
    Fetch several DOIs with one request per batch of BATCH_SIZE.
    Return {doi: json or None}: None when OpenAlex answered without this DOI.
    DOIs of a batch whose request failed are absent from the result.
    """
    works = {}
    for start in range(0, len(dois), BATCH_SIZE):
        works.update(_fetch_batch(dois[start : start + BATCH_SIZE]))
    return works


def _fetch_batch(dois):
    params = {"filter": "doi:" + "|".join(dois), "per-page": len(dois)} | contact_params()
    data = http.get_json(
        OPENALEX_WORKS_URL,
        params=params,
        service="OpenAlex",
        subject=f"batch of {len(dois)} DOIs",
        contact=settings.CROSSREF_MAILTO,
    )
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
    } | contact_params()
    data = http.get_json(
        OPENALEX_WORKS_URL,
        params=params,
        service="OpenAlex",
        subject=f"works citing {work_id}",
        contact=settings.CROSSREF_MAILTO,
    )
    if data is None:
        return None
    return (data.get("meta") or {}).get("count", 0), data.get("results") or []


def contact_params():
    mailto = settings.CROSSREF_MAILTO
    return {"mailto": mailto} if mailto else {}


def fetch_openalex_institutions(ids):
    """
    Return {OpenAlex id: institution} for institution ids ('I2738703131'), one
    request per batch of BATCH_SIZE. Used for the ancestors of an institution.
    """
    institutions = {}
    for start in range(0, len(ids), BATCH_SIZE):
        batch = ids[start : start + BATCH_SIZE]
        data = http.get_json(
            OPENALEX_INSTITUTIONS_URL,
            params={"filter": "openalex:" + "|".join(batch), "per-page": len(batch)}
            | contact_params(),
            service="OpenAlex",
            subject=f"batch of {len(batch)} institutions",
            contact=settings.CROSSREF_MAILTO,
        )
        for institution in (data or {}).get("results", []):
            institutions[institution["id"].rsplit("/", 1)[-1]] = institution
    return institutions
