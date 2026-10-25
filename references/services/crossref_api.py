import logging
from functools import cache
from urllib.parse import quote

from django.conf import settings

from . import http
from .doi import normalize_doi

logger = logging.getLogger(__name__)

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
BATCH_SIZE = 50
SEARCH_ROWS = 5
SEARCH_FIELDS = "DOI,title,author,issued,type,container-title"


def fetch_crossref_json(doi):
    """
    Return the Crossref JSON for a DOI, or None if it cannot be retrieved.
    Rate limiting (429), server errors and network errors are retried.
    """
    if not doi:
        return None
    return _get_json("/" + quote(doi, safe="/"), {}, f"DOI {doi}")


def fetch_crossref_works(dois):
    """
    Fetch several DOIs with one list request per batch of BATCH_SIZE.
    Return {doi: json or None}: None when Crossref answered without this DOI.
    DOIs of a batch whose request failed are absent from the result.
    """
    works = {}
    for start in range(0, len(dois), BATCH_SIZE):
        works.update(_fetch_batch(dois[start : start + BATCH_SIZE]))
    return works


def fetch_crossref_by_isbn(isbn):
    """Return the Crossref JSON of the work with this ISBN, or None."""
    data = _get_json("", {"filter": f"isbn:{isbn}", "rows": 1}, f"ISBN {isbn}")
    items = data["message"]["items"] if data else []
    return _as_single_work(items[0]) if items else None


def search_crossref(text):
    """
    The works closest to the text of a cited reference (query.bibliographic), best
    first; None if the request failed. Only the fields shown as candidates are asked.
    """
    params = {"query.bibliographic": text, "rows": SEARCH_ROWS, "select": SEARCH_FIELDS}
    data = _get_json("", params, "bibliographic search")
    return data["message"]["items"] if data else None


def _fetch_batch(dois):
    params = {"filter": ",".join(f"doi:{doi}" for doi in dois), "rows": len(dois)}
    data = _get_json("", params, f"batch of {len(dois)} DOIs")
    if data is None:
        return {}
    found = {normalize_doi(item["DOI"]): item for item in data["message"]["items"]}
    return {doi: _as_single_work(found[doi]) if doi in found else None for doi in dois}


def _as_single_work(item):
    """Wrap a list item like the response of /works/{doi}, the stored format."""
    return {"status": "ok", "message-type": "work", "message": item}


def _get_json(path, params, subject):
    mailto = settings.CROSSREF_MAILTO
    if mailto:
        params = {**params, "mailto": mailto}
    else:
        _warn_missing_mailto()
    return http.get_json(
        CROSSREF_WORKS_URL + path,
        params=params,
        service="Crossref",
        subject=subject,
        contact=mailto,
    )


@cache
def _warn_missing_mailto():
    logger.warning("CROSSREF_MAILTO is not set: requests go to the Crossref public pool.")
