"""
The journal of the requests to the external APIs (#395): one JSON line per request in
settings.API_LOG_PATH (logs/api.log by default), to see afterwards what the application
asked, for which page, request of the queue or command, and how long it took
("event": "api"); and one line per request of the queue the worker did ("event": "file"):
its wait, its duration, the API requests it made, its outcome. The summary:
python manage.py api_log.
"""

import json
import logging
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

from django.utils import timezone

logger = logging.getLogger("references.api")
# Where the requests come from: set by the middleware (pages) and the worker (queue).
_context = ContextVar("api_log_context", default=None)
# The API requests made inside an api_context, counted for the line of a queue request.
_counter = ContextVar("api_log_counter", default=None)
# Parameters never written: a contact address.
HIDDEN_PARAMS = {"mailto", "email"}


@dataclass
class Counter:
    api_requests: int = 0


@contextmanager
def api_context(via, label, **details):
    """
    The requests made inside come from via (page, file, commande), label says what.
    Yield a Counter of the API requests made inside.
    """
    counter = Counter()
    tokens = _context.set({"via": via, "label": label, **details}), _counter.set(counter)
    try:
        yield counter
    finally:
        _context.reset(tokens[0])
        _counter.reset(tokens[1])


def current_context():
    """The context set around the request, else the command that runs, if any."""
    context = _context.get()
    if context is not None:
        return context
    if len(sys.argv) > 1 and Path(sys.argv[0]).name == "manage.py":
        return {"via": "commande", "label": sys.argv[1]}
    return {"via": "autre", "label": Path(sys.argv[0]).name}


def record(service, subject, url, params, response=None, *, ms, attempt, stream, error=""):
    """One request: its answer (None on network error), its duration in milliseconds."""
    counter = _counter.get()
    if counter is not None:
        counter.api_requests += 1
    if not logger.isEnabledFor(logging.INFO):
        return
    entry = {
        "event": "api",
        "at": timezone.now().isoformat(timespec="milliseconds"),
        "service": service,
        "subject": str(subject),
        "url": url,
        "params": {k: v for k, v in (params or {}).items() if k not in HIDDEN_PARAMS},
        "status": response.status_code if response is not None else None,
        "ms": round(ms),
        "cache": getattr(response, "from_cache", False) is True,
        "bytes": size(response, stream),
        "attempt": attempt,
        "error": error,
        **current_context(),
    }
    logger.info(json.dumps(entry, ensure_ascii=False, default=str))


def record_request(request, *, ms, api_requests, references=None, batch=None):
    """
    One request of the queue, once done (#378): its wait in the queue, its duration, the
    API requests it made, the references of its publication, its outcome. Done in a batch
    of imports (#381), the duration and the API requests are those of the whole batch.
    """
    if not logger.isEnabledFor(logging.INFO):
        return
    started = request.started_at
    waited = (started - request.requested_at).total_seconds() * 1000 if started else None
    entry = {
        "event": "file",
        "at": timezone.now().isoformat(timespec="milliseconds"),
        "action": request.action,
        "identifier": request.identifier,
        "request": request.pk,
        "status": request.status,
        "wait_ms": round(waited) if waited is not None else None,
        "ms": round(ms),
        "api_requests": api_requests,
        "references": references,
        "batch": batch,
        "error": request.error,
    }
    logger.info(json.dumps(entry, ensure_ascii=False, default=str))


def size(response, stream):
    """The size of the answer, without reading a streamed one (its declared length)."""
    if response is None:
        return None
    if not stream:
        return len(response.content)
    length = response.headers.get("Content-Length", "")
    return int(length) if length.isdigit() else None


class ApiLogHandler(RotatingFileHandler):
    """A rotating file whose folder is created when the first line is written."""

    def __init__(self, filename, **kwargs):
        super().__init__(filename, delay=True, **kwargs)

    def _open(self):
        Path(self.baseFilename).parent.mkdir(parents=True, exist_ok=True)
        return super()._open()
