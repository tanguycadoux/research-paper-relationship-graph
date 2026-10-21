import logging
import time
from functools import cache
from urllib.parse import quote

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

CROSSREF_WORKS_URL = "https://api.crossref.org/works/"
PROJECT_URL = "https://github.com/tanguycadoux/research-paper-relationship-graph"
USER_AGENT = "references-manager/0.1"
REQUEST_TIMEOUT = 10
MAX_ATTEMPTS = 3
MAX_RETRY_DELAY = 60
RETRY_STATUSES = {429, 500, 502, 503, 504}


def fetch_crossref_json(doi):
    """
    Return the Crossref JSON for a DOI, or None if it cannot be retrieved.
    Rate limiting (429), server errors and network errors are retried.
    """
    if not doi:
        return None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = _request_work(doi)
        if response is not None and response.status_code == 200:
            return _parse_json(doi, response)
        if not _should_retry(response) or attempt == MAX_ATTEMPTS:
            _log_failure(doi, response)
            return None
        _wait_before_retry(response, attempt)
    return None


def _parse_json(doi, response):
    try:
        return response.json()
    except ValueError:
        logger.error("Crossref returned invalid JSON for DOI %s", doi)
        return None


@cache
def _get_session():
    return requests.Session()


def _request_work(doi):
    """
    Send one request to Crossref. Return None on network error.
    """
    mailto = settings.CROSSREF_MAILTO
    if not mailto:
        _warn_missing_mailto()
    logger.info("Crossref request for DOI %s", doi)
    try:
        return _get_session().get(
            CROSSREF_WORKS_URL + quote(doi, safe="/"),
            params={"mailto": mailto} if mailto else None,
            headers={"User-Agent": _user_agent(mailto)},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as error:
        logger.warning("Crossref network error for DOI %s: %s", doi, error)
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


def _log_failure(doi, response):
    if response is None:
        logger.error("Crossref unreachable for DOI %s", doi)
    elif response.status_code == 404:
        logger.info("DOI %s is unknown to Crossref", doi)
    elif response.status_code == 403:
        logger.error("Crossref refused access (403): the client may be blocked")
    else:
        logger.error("Crossref returned %s for DOI %s", response.status_code, doi)
