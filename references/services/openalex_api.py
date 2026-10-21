"""
Client of the OpenAlex API, a complement to Crossref and DataCite: institutions
with ROR identifiers, ORCIDs missing from Crossref, author identifiers.

Terms (checked on 2026-10-21): free, no key. A single work is free and unlimited;
a filtered list request uses a small part of a daily budget (about 1,000 batches
a day without key).
"""

from django.conf import settings

from . import http
from .doi import normalize_doi

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
BATCH_SIZE = 50


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
    found = {normalize_doi(work.get("doi") or ""): work for work in data.get("results", [])}
    return {doi: found.get(doi) for doi in dois}


def contact_params():
    mailto = settings.CROSSREF_MAILTO
    return {"mailto": mailto} if mailto else {}
