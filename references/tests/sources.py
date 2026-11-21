"""
Simulated external sources, at the HTTP level (#299).

A test says which answers exist; the clients (crossref_api, openalex_api…) and the
shared HTTP code run as in production, only the transport is replaced: a requests
adapter mounted on the session of references.services.sources.http answers according
to the URL and the parameters, from what the test gave.

    @simulated_sources(crossref={DOI: crossref_json("Title")})
    def test_import(self): ...

    with simulated_sources(openalex=[fixture("openalex_work.json")]) as sources:
        ...
        self.assertEqual(sources.batches("openalex"), [[DOI_A, DOI_B]])

While it is active, every source is simulated and knows only what it was given:
an unknown DOI is a 404, a batch answers without it, a search finds nothing. A
source given in `unreachable` answers 503 to every request (retried without
waiting). doi.org registers the DOIs the simulated Crossref and DataCite know, and
does not answer for the others (accepted, as when doi.org is unreachable), unless
`doi_org` says otherwise. A request that no route simulates (another host, another
path or parameter) fails the test: « requête non simulée : GET https://… ».
"""

import io
import json
import logging
import re
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from functools import wraps
from inspect import iscoroutinefunction
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

import requests
from requests.adapters import BaseAdapter

from references.services.identifiers.doi import normalize_doi
from references.services.sources import http
from references.services.sources.openalex_api import work_dois

FIXTURES = Path(__file__).parent / "fixtures"
SERVICES = ("crossref", "datacite", "openalex", "doi.org", "orcid", "arxiv", "openlibrary")
HOSTS = {
    "api.crossref.org": "crossref",
    "api.datacite.org": "datacite",
    "api.openalex.org": "openalex",
    "doi.org": "doi.org",
    "pub.orcid.org": "orcid",
    "arxiv.org": "arxiv",
    "export.arxiv.org": "arxiv",
    "openlibrary.org": "openlibrary",
}


def fixture(name):
    """The decoded JSON of references/tests/fixtures/<name>."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# The answers a test gives, restored when the simulation ends (add()).
ANSWERS = (
    "crossref",
    "datacite",
    "openalex",
    "crossref_searches",
    "datacite_searches",
    "openalex_citing",
    "institutions",
    "orcid_records",
    "orcid_names",
    "eprints",
    "openlibrary",
)


_active = []


def active_sources():
    """The simulation in progress (to add answers from a decorated test), or None."""
    return _active[0] if _active else None


class UnsimulatedRequest(AssertionError):
    """A request that no route of the simulated sources answers."""


@dataclass
class Request:
    """A request received by the simulated sources."""

    service: str
    url: str
    path: str
    params: dict
    kind: str = ""  # "work", "batch", "isbn", "search", "citing", "institutions"…
    keys: list = field(default_factory=list)  # DOIs, ORCIDs, ids asked


@dataclass
class Answer:
    status: int
    body: bytes = b""
    headers: dict = field(default_factory=dict)


def _json(data, status=200):
    return Answer(status, json.dumps(data).encode(), {"Content-Type": "application/json"})


NOT_FOUND = Answer(404, b'{"status": "error", "message": "Resource not found."}')


class simulated_sources:  # noqa: N801 (used like patch)
    """
    Simulate every external source, with these answers. Used as a decorator (of a
    test method or of a TestCase class, like patch) or as a context manager.

    crossref, datacite, openalex: the works, as {doi: answer} or a list of answers
        (the DOI read in the answer). A Crossref or DataCite answer is the response of
        a single DOI ({"message": …} / {"data": …}); an OpenAlex answer is a work,
        found by each DOI of its locations (work_dois).
    crossref_searches, datacite_searches: {text: [items]} for query.bibliographic
        and the DataCite title search (the words of the title).
    openalex_citing: {work id: [works]} for the works citing an OpenAlex work, or
        {work id: (total, [works])} when OpenAlex counts more; sorted as asked.
    institutions: the OpenAlex institutions, a list.
    orcid_records: {orcid: record}; orcid_names: {orcid: expanded-search entry}.
    eprints: {arXiv id: bytes}; openlibrary: {isbn: search document}.
    doi_org: True or False for every DOI, or {doi: True / False}.
    unreachable: services answering 503 ("crossref", "openalex", "doi.org"…).
    """

    def __init__(
        self,
        *,
        crossref=None,
        datacite=None,
        openalex=None,
        crossref_searches=None,
        datacite_searches=None,
        openalex_citing=None,
        institutions=(),
        orcid_records=None,
        orcid_names=None,
        eprints=None,
        openlibrary=None,
        doi_org=None,
        unreachable=(),
    ):
        unknown = set(unreachable) - set(SERVICES)
        if unknown:
            raise ValueError(f"Sources inconnues : {', '.join(sorted(unknown))}")
        self.crossref = _keyed(crossref, _crossref_doi)
        self.datacite = _keyed(datacite, lambda answer: answer["data"]["id"])
        self.openalex = {}
        for work in _answers(openalex):
            for doi in work_dois(work):
                self.openalex.setdefault(doi, work)
        self.crossref_searches = dict(crossref_searches or {})
        self.datacite_searches = dict(datacite_searches or {})
        self.openalex_citing = dict(openalex_citing or {})
        self.institutions = {item["id"].rsplit("/", 1)[-1]: item for item in institutions}
        self.orcid_records = dict(orcid_records or {})
        self.orcid_names = dict(orcid_names or {})
        self.eprints = dict(eprints or {})
        self.openlibrary = dict(openlibrary or {})
        self.doi_org = doi_org
        self.unreachable = set(unreachable)
        self.requests = []
        self.unsimulated = []
        self._stack = None

    # Use as a context manager or a decorator.

    def __enter__(self):
        if _active:
            raise RuntimeError(
                "Sources déjà simulées : ajoutez des réponses avec add() plutôt qu'une "
                "seconde simulation."
            )
        self.requests = []
        self.unsimulated = []
        saved = {name: dict(getattr(self, name)) for name in ANSWERS}
        saved |= {"doi_org": self.doi_org, "unreachable": set(self.unreachable)}
        session = requests.Session()
        adapter = _Adapter(self)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        self._stack = ExitStack()
        self._stack.callback(lambda: self.__dict__.update(saved))
        _active.append(self)
        self._stack.callback(_active.remove, self)
        self._stack.enter_context(patch.object(http, "_get_session", lambda: session))
        # Retries do not wait; the module keeps its own clock.
        no_wait = SimpleNamespace(monotonic=time.monotonic, sleep=lambda seconds: None)
        self._stack.enter_context(patch.object(http, "time", no_wait))
        # The lines of the clients stay off the console; assertLogs still sees them.
        for handler in logging.getLogger("references").handlers:
            handler.addFilter(_quiet_clients)
            self._stack.callback(handler.removeFilter, _quiet_clients)
        return self

    def __exit__(self, *exc_info):
        self._stack.close()
        if self.unsimulated and exc_info[0] is None:
            raise UnsimulatedRequest(_unsimulated_message(self.unsimulated[0]))
        return False

    def __call__(self, target):
        if isinstance(target, type):
            for name in dir(target):
                if name.startswith("test") and callable(getattr(target, name)):
                    setattr(target, name, self(getattr(target, name)))
            return target
        if iscoroutinefunction(target):
            raise TypeError("simulated_sources ne décore pas une coroutine")

        @wraps(target)
        def wrapper(*args, **kwargs):
            with self:
                return target(*args, **kwargs)

        return wrapper

    def add(self, **answers):
        """
        Add answers while the simulation is active (same arguments as the
        constructor); they are forgotten when it ends.
        """
        other = simulated_sources(**answers)
        for name in ANSWERS:
            getattr(self, name).update(getattr(other, name))
        if other.doi_org is not None:
            self.doi_org = other.doi_org
        self.unreachable |= other.unreachable

    # What the tests check.

    def forget(self):
        """Forget the requests received so far (like reset_mock)."""
        self.requests.clear()

    def to(self, service):
        """The requests received by a service, in order."""
        return [request for request in self.requests if request.service == service]

    def single(self, service):
        """The DOIs (or ORCIDs) asked one at a time, in order."""
        return [request.keys[0] for request in self.to(service) if request.kind == "work"]

    def batches(self, service, kind="batch"):
        """
        The DOIs (or ORCIDs) of each grouped request, in order; kind="institutions"
        for the ids of the OpenAlex institutions.
        """
        return [request.keys for request in self.to(service) if request.kind == kind]

    def searches(self, service):
        """The texts searched in a service (Crossref, DataCite), in order."""
        return [request.keys[0] for request in self.to(service) if request.kind == "search"]

    def asked(self, service):
        """Every DOI (or key) asked to a service, alone or in a batch, in order."""
        return [key for request in self.to(service) for key in request.keys]

    # Routes.

    def answer(self, request):
        parts = urlsplit(request.url)
        service = HOSTS.get(parts.hostname)
        params = {key: values[-1] for key, values in parse_qs(parts.query).items()}
        path = unquote(parts.path)
        received = Request(service, request.url, path, params)
        if service is None or request.method != "GET":
            return self._unsimulated(request)
        route = getattr(self, "_" + service.replace(".", "_"))
        answer = route(received)
        if answer is None:
            return self._unsimulated(request)
        self.requests.append(received)
        if service in self.unreachable:
            return Answer(503, b"Service Unavailable")
        return answer

    def _unsimulated(self, request):
        self.unsimulated.append(request)
        raise UnsimulatedRequest(_unsimulated_message(request))

    def _crossref(self, request):
        params = request.params
        if request.path.startswith("/works/"):
            doi = normalize_doi(request.path.removeprefix("/works/"))
            request.kind, request.keys = "work", [doi]
            answer = self.crossref.get(doi)
            return NOT_FOUND if answer is None else _json(answer)
        if request.path != "/works":
            return None
        if params.get("filter", "").startswith("doi:"):
            dois = [normalize_doi(item.removeprefix("doi:")) for item in _split(params["filter"])]
            request.kind, request.keys = "batch", dois
            items = [self.crossref[doi]["message"] for doi in dois if doi in self.crossref]
            return _json(_crossref_list(items))
        if params.get("filter", "").startswith("isbn:"):
            isbn = params["filter"].removeprefix("isbn:")
            request.kind, request.keys = "isbn", [isbn]
            items = [
                answer["message"]
                for answer in self.crossref.values()
                if isbn in {_isbn(value) for value in answer["message"].get("ISBN", [])}
            ]
            return _json(_crossref_list(items[: int(params.get("rows", 20))]))
        if "query.bibliographic" in params:
            text = params["query.bibliographic"]
            request.kind, request.keys = "search", [text]
            items = self.crossref_searches.get(text, [])
            return _json(_crossref_list(items[: int(params.get("rows", 20))]))
        return None

    def _datacite(self, request):
        params = request.params
        if request.path.startswith("/dois/"):
            doi = normalize_doi(request.path.removeprefix("/dois/"))
            request.kind, request.keys = "work", [doi]
            answer = self.datacite.get(doi)
            return NOT_FOUND if answer is None else _json(answer)
        if request.path != "/dois":
            return None
        if "ids" in params:
            dois = [normalize_doi(doi) for doi in _split(params["ids"])]
            request.kind, request.keys = "batch", dois
            items = [self.datacite[doi]["data"] for doi in dois if doi in self.datacite]
            return _json({"data": items, "meta": {"total": len(items)}})
        match = re.fullmatch(r'titles\.title:"(.*)"', params.get("query", ""))
        if match:
            request.kind, request.keys = "search", [match.group(1)]
            items = [answer["data"] for answer in self.datacite_searches.get(match.group(1), [])]
            return _json({"data": items[: int(params.get("page[size]", 25))]})
        return None

    def _openalex(self, request):
        params = request.params
        if request.path.startswith("/works/doi:"):
            doi = normalize_doi(request.path.removeprefix("/works/doi:"))
            request.kind, request.keys = "work", [doi]
            work = self.openalex.get(doi)
            return NOT_FOUND if work is None else _json(work)
        filter_ = params.get("filter", "")
        if request.path == "/works" and filter_.startswith("doi:"):
            dois = [normalize_doi(doi) for doi in filter_.removeprefix("doi:").split("|")]
            request.kind, request.keys = "batch", dois
            works = list(
                {id(work): work for doi in dois if (work := self.openalex.get(doi))}.values()
            )
            return _json({"meta": {"count": len(works)}, "results": works})
        if request.path == "/works" and filter_.startswith("cites:"):
            work_id = filter_.removeprefix("cites:")
            request.kind, request.keys = "citing", [work_id]
            citing = self.openalex_citing.get(work_id, [])
            total, works = citing if isinstance(citing, tuple) else (len(citing), citing)
            if "sort" in params:
                key, _, order = params["sort"].partition(":")
                works = sorted(works, key=lambda work: work.get(key) or 0, reverse=order == "desc")
            count = int(params.get("per-page", 25))
            return _json({"meta": {"count": total}, "results": works[:count]})
        if request.path == "/institutions" and filter_.startswith("openalex:"):
            ids = filter_.removeprefix("openalex:").split("|")
            request.kind, request.keys = "institutions", ids
            found = [self.institutions[i] for i in ids if i in self.institutions]
            return _json({"meta": {"count": len(found)}, "results": found})
        return None

    def _doi_org(self, request):
        if not request.path.startswith("/ra/"):
            return None
        dois = [normalize_doi(doi) for doi in request.path.removeprefix("/ra/").split(",")]
        request.kind, request.keys = "batch", dois
        answers = []
        for doi in dois:
            written, registered = self._registered(doi)
            if registered is True:
                agency = "DataCite" if doi in self.datacite else "Crossref"
                answers.append({"DOI": written, "RA": agency})
            elif registered is False:
                answers.append({"DOI": written, "status": "DOI does not exist"})
        return _json(answers)

    def _registered(self, doi):
        """(the DOI as doi.org writes it, True / False / None)."""
        if isinstance(self.doi_org, dict):
            for written, registered in self.doi_org.items():
                if normalize_doi(written) == doi:
                    return written, registered
        if isinstance(self.doi_org, bool):
            return doi, self.doi_org
        return doi, (True if doi in self.crossref or doi in self.datacite else None)

    def _orcid(self, request):
        match = re.fullmatch(r"/v3\.0/([0-9X-]+)/record", request.path)
        if match:
            request.kind, request.keys = "work", [match.group(1)]
            record = self.orcid_records.get(match.group(1))
            return NOT_FOUND if record is None else _json(record)
        match = re.fullmatch(r"orcid:\((.*)\)", request.params.get("q", ""))
        if request.path == "/v3.0/expanded-search/" and match:
            orcids = match.group(1).split(" OR ")
            request.kind, request.keys = "batch", orcids
            entries = [self.orcid_names[orcid] for orcid in orcids if orcid in self.orcid_names]
            return _json({"expanded-result": entries or None, "num-found": len(entries)})
        return None

    def _arxiv(self, request):
        if not request.path.startswith("/e-print/"):
            return None
        arxiv_id = request.path.removeprefix("/e-print/")
        request.kind, request.keys = "work", [arxiv_id]
        content = self.eprints.get(arxiv_id)
        return NOT_FOUND if content is None else Answer(200, content)

    def _openlibrary(self, request):
        if request.path != "/search.json" or "isbn" not in request.params:
            return None
        isbn = request.params["isbn"]
        request.kind, request.keys = "isbn", [isbn]
        doc = self.openlibrary.get(isbn)
        docs = [doc] if doc else []
        return _json({"numFound": len(docs), "start": 0, "docs": docs})


class _Adapter(BaseAdapter):
    def __init__(self, sources):
        super().__init__()
        self.sources = sources

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        answer = self.sources.answer(request)
        response = requests.Response()
        response.status_code = answer.status
        response.headers.update(answer.headers)
        response.raw = io.BytesIO(answer.body)
        response.encoding = "utf-8"
        response.url = request.url
        response.request = request
        response.reason = {200: "OK", 404: "Not Found", 503: "Service Unavailable"}.get(
            answer.status, ""
        )
        return response

    def close(self):
        pass


def _quiet_clients(record):
    return not record.name.startswith("references.services.sources")


def _unsimulated_message(request):
    return (
        f"requête non simulée : {request.method} {request.url} (voir references/tests/sources.py)"
    )


def _answers(answers):
    if answers is None:
        return []
    return list(answers.values()) if isinstance(answers, dict) else list(answers)


def _keyed(answers, doi_of):
    """{normalized doi: answer}, from {doi: answer} or a list of answers."""
    if answers is None:
        return {}
    if isinstance(answers, dict):
        return {normalize_doi(doi): _with_doi(answer, doi) for doi, answer in answers.items()}
    return {normalize_doi(doi_of(answer)): answer for answer in answers}


def _with_doi(answer, doi):
    """
    An answer written without its DOI gets it, as the source gives it: "DOI" in a
    Crossref message, "id" in a DataCite record.
    """
    message = answer.get("message")
    if isinstance(message, dict) and "DOI" not in message:
        return {**answer, "message": {"DOI": doi, **message}}
    data = answer.get("data")
    if isinstance(data, dict) and "id" not in data:
        return {**answer, "data": {"id": doi, **data}}
    return answer


def _crossref_doi(answer):
    return answer["message"]["DOI"]


def _crossref_list(items):
    return {
        "status": "ok",
        "message-type": "work-list",
        "message": {"total-results": len(items), "items": items},
    }


def _split(value):
    return [item for item in value.split(",") if item]


def _isbn(value):
    return re.sub(r"[^0-9X]", "", value.upper())
