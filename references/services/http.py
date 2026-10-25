"""
JSON GET requests to external APIs (Crossref, Open Library): shared session,
retries on rate limiting (429), server and network errors, and logging.

A request made while a page loads keeps the user waiting: it is retried once, and
given up when the source asks to wait longer than a few seconds. Management
commands wrap their work in patient_requests() to wait as long as the source asks.
"""

import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import cache

import requests

logger = logging.getLogger(__name__)

PROJECT_URL = "https://github.com/tanguycadoux/research-paper-relationship-graph"
USER_AGENT = "references-manager/0.1"
REQUEST_TIMEOUT = 10
RETRY_STATUSES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class RetryLimits:
    attempts: int
    max_delay: int  # seconds; a longer Retry-After gives up instead of waiting


PAGE_LIMITS = RetryLimits(attempts=2, max_delay=5)
PATIENT_LIMITS = RetryLimits(attempts=3, max_delay=60)
_limits = ContextVar("http_retry_limits", default=PAGE_LIMITS)


@contextmanager
def patient_requests():
    """Let the requests made inside wait as long as the sources ask (commands)."""
    token = _limits.set(PATIENT_LIMITS)
    try:
        yield
    finally:
        _limits.reset(token)


def get_json(url, *, params=None, headers=None, service, subject, contact=""):
    """
    Return the decoded JSON of a GET request, or None if it cannot be retrieved.
    A 404 (unknown resource) or a 403 (access refused) is not retried.
    """
    limits = _limits.get()
    for attempt in range(1, limits.attempts + 1):
        response = _request(url, params, headers, service, subject, contact)
        if response is not None and response.status_code == 200:
            return _parse_json(response, service, subject)
        if not _should_retry(response) or attempt == limits.attempts:
            _log_failure(response, service, subject)
            return None
        delay = _retry_after(response) or 2 ** (attempt - 1)
        if delay > limits.max_delay:
            logger.warning("%s asks to wait %s s for %s: given up", service, delay, subject)
            return None
        time.sleep(delay)
    return None


def user_agent(contact=""):
    if contact:
        return f"{USER_AGENT} ({PROJECT_URL}; mailto:{contact})"
    return f"{USER_AGENT} ({PROJECT_URL})"


@cache
def _get_session():
    return requests.Session()


def _request(url, params, headers, service, subject, contact):
    """Send one request. Return None on network error."""
    logger.info("%s request for %s", service, subject)
    try:
        return _get_session().get(
            url,
            params=params or None,
            headers={"User-Agent": user_agent(contact)} | (headers or {}),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as error:
        logger.warning("%s network error for %s: %s", service, subject, error)
        return None


def _parse_json(response, service, subject):
    try:
        return response.json()
    except ValueError:
        logger.error("%s returned invalid JSON for %s", service, subject)
        return None


def _should_retry(response):
    return response is None or response.status_code in RETRY_STATUSES


def _retry_after(response):
    """Return the Retry-After delay in seconds, or None if absent or not an integer."""
    if response is None:
        return None
    try:
        return int(response.headers.get("Retry-After", ""))
    except ValueError:
        return None


def _log_failure(response, service, subject):
    if response is None:
        logger.error("%s unreachable for %s", service, subject)
    elif response.status_code == 404:
        logger.info("%s is unknown to %s", subject, service)
    elif response.status_code == 403:
        logger.error("%s refused access (403): the client may be blocked", service)
    else:
        logger.error("%s returned %s for %s", service, response.status_code, subject)
