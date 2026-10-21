import logging
import time
from functools import cache
from urllib.parse import quote

import requests
from django.conf import settings

from .doi import normalize_doi

logger = logging.getLogger(__name__)

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
PROJECT_URL = "https://github.com/tanguycadoux/research-paper-relationship-graph"
USER_AGENT = "references-manager/0.1"
REQUEST_TIMEOUT = 10
MAX_ATTEMPTS = 3
MAX_RETRY_DELAY = 60
RETRY_STATUSES = {429, 500, 502, 503, 504}
BATCH_SIZE = 50


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
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = _request(path, params, subject)
        if response is not None and response.status_code == 200:
            return _parse_json(subject, response)
        if not _should_retry(response) or attempt == MAX_ATTEMPTS:
            _log_failure(subject, response)
            return None
        _wait_before_retry(response, attempt)
    return None


def _parse_json(subject, response):
    try:
        return response.json()
    except ValueError:
        logger.error("Crossref returned invalid JSON for %s", subject)
        return None


@cache
def _get_session():
    return requests.Session()


def _request(path, params, subject):
    """
    Send one request to Crossref. Return None on network error.
    """
    mailto = settings.CROSSREF_MAILTO
    if mailto:
        params = {**params, "mailto": mailto}
    else:
        _warn_missing_mailto()
    logger.info("Crossref request for %s", subject)
    try:
        return _get_session().get(
            CROSSREF_WORKS_URL + path,
            params=params or None,
            headers={"User-Agent": _user_agent(mailto)},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as error:
        logger.warning("Crossref network error for %s: %s", subject, error)
        return None


def _user_agent(mailto):
    if mailto:
        return f"{USER_AGENT} ({PROJECT_URL}; mailto:{mailto})"
    return f"{USER_AGENT} ({PROJECT_URL})"


@cache
def _warn_missing_mailto():
    logger.warning("CROSSREF_MAILTO is not set: requests go to the Crossref public pool.")


def _should_retry(response):
    return response is None or response.status_code in RETRY_STATUSES


def _wait_before_retry(response, attempt):
    delay = _retry_after(response) or 2 ** (attempt - 1)
    time.sleep(min(delay, MAX_RETRY_DELAY))


def _retry_after(response):
    """
    Return the Retry-After delay in seconds, or None if absent or not an integer.
    """
    if response is None:
        return None
    try:
        return int(response.headers.get("Retry-After", ""))
    except ValueError:
        return None


def _log_failure(subject, response):
    if response is None:
        logger.error("Crossref unreachable for %s", subject)
    elif response.status_code == 404:
        logger.info("%s is unknown to Crossref", subject)
    elif response.status_code == 403:
        logger.error("Crossref refused access (403): the client may be blocked")
    else:
        logger.error("Crossref returned %s for %s", response.status_code, subject)
