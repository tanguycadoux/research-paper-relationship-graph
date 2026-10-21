"""
Client of the DataCite REST API: DOIs registered with DataCite (conference
proceedings such as JACoW, Zenodo deposits, datasets…), unknown to Crossref.
"""

from urllib.parse import quote

from . import http
from .doi import normalize_doi

DATACITE_DOIS_URL = "https://api.datacite.org/dois"
BATCH_SIZE = 50


def fetch_datacite_json(doi):
    """Return the DataCite JSON for a DOI, or None if it cannot be retrieved."""
    if not doi:
        return None
    return http.get_json(
        f"{DATACITE_DOIS_URL}/{quote(doi, safe='/')}", service="DataCite", subject=f"DOI {doi}"
    )


def fetch_datacite_works(dois):
    """
    Fetch several DOIs with one request per batch of BATCH_SIZE.
    Return {doi: json or None}: None when DataCite answered without this DOI.
    DOIs of a batch whose request failed are absent from the result.
    """
    works = {}
    for start in range(0, len(dois), BATCH_SIZE):
        works.update(_fetch_batch(dois[start : start + BATCH_SIZE]))
    return works


def _fetch_batch(dois):
    data = http.get_json(
        DATACITE_DOIS_URL,
        params={"ids": ",".join(dois), "page[size]": len(dois)},
        service="DataCite",
        subject=f"batch of {len(dois)} DOIs",
    )
    if data is None:
        return {}
    found = {normalize_doi(item["id"]): {"data": item} for item in data.get("data", [])}
    return {doi: found.get(doi) for doi in dois}
