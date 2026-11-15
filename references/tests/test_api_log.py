import json
import logging
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, TestCase

from references.middleware import ApiLogContextMiddleware
from references.models import CitedReference, FetchRequest, Publication
from references.services.imports import fetch_actions, fetch_queue
from references.services.sources import api_log, http
from references.services.sources import api_log_summary as summary

LOGGER = logging.getLogger("references.api")


def response(status=200, content=b'{"ok": true}', cached=False):
    answer = requests.Response()
    answer.status_code = status
    answer._content = content
    answer.from_cache = cached
    return answer


class JournalTests(SimpleTestCase):
    """One JSON line per request to an external API (#395)."""

    def lines(self, call):
        with patch.object(LOGGER, "disabled", False), self.assertLogs(LOGGER, "INFO") as logs:
            call()
        return [json.loads(record.getMessage()) for record in logs.records]

    def get(self, answer):
        session = MagicMock()
        session.get.side_effect = answer if isinstance(answer, Exception) else None
        session.get.return_value = answer
        with patch.object(http, "_get_session", return_value=session):
            return http.get_json(
                "https://api.crossref.org/works/10.1000/a",
                params={"rows": 2, "mailto": "contact@example.org"},
                service="Crossref",
                subject="10.1000/a",
            )

    def test_a_request(self):
        (line,) = self.lines(lambda: self.get(response()))
        self.assertEqual(line["event"], "api")
        self.assertEqual(line["service"], "Crossref")
        self.assertEqual(line["subject"], "10.1000/a")
        self.assertEqual(line["url"], "https://api.crossref.org/works/10.1000/a")
        self.assertEqual(line["params"], {"rows": 2})  # never the contact address
        self.assertEqual((line["status"], line["cache"], line["bytes"]), (200, False, 12))
        self.assertEqual((line["attempt"], line["error"]), (1, ""))
        self.assertIsInstance(line["ms"], int)
        # Without a page or a request of the queue around: the command that runs.
        self.assertEqual(line["via"], "commande")

    def test_an_unknown_subject_and_the_cache(self):
        (line,) = self.lines(lambda: self.get(response(404, b"")))
        self.assertEqual(line["status"], 404)
        (line,) = self.lines(lambda: self.get(response(cached=True)))
        self.assertTrue(line["cache"])

    def test_a_network_error_and_its_retry(self):
        with patch.object(http.time, "sleep"):
            lines = self.lines(lambda: self.get(requests.ConnectionError("refusée")))
        self.assertEqual([line["attempt"] for line in lines], [1, 2])
        self.assertEqual((lines[0]["status"], lines[0]["error"]), (None, "refusée"))

    def test_the_context_around(self):
        def call():
            with api_log.api_context("page", "GET /publications/3/", user=7):
                self.get(response())

        (line,) = self.lines(call)
        self.assertEqual(
            (line["via"], line["label"], line["user"]), ("page", "GET /publications/3/", 7)
        )

    def test_nothing_is_written_by_the_tests(self):
        with self.assertNoLogs(LOGGER, "INFO"):
            self.get(response())


class ContextTests(TestCase):
    def test_a_page_names_its_path_and_user(self):
        user = get_user_model().objects.create_user("alice")
        request = RequestFactory().post("/publications/3/refresh/")
        request.user = user
        middleware = ApiLogContextMiddleware(lambda request: api_log.current_context())
        self.assertEqual(
            middleware(request),
            {"via": "page", "label": "POST /publications/3/refresh/", "user": user.pk},
        )

    def test_a_request_of_the_queue(self):
        pub = Publication.objects.create(doi="10.1000/a")
        request = fetch_queue.enqueue(pub, None, with_references=False)
        seen = {}

        def run(fetch):
            seen.update(api_log.current_context())
            return pub

        with patch.object(fetch_actions, "run", side_effect=run):
            fetch_queue.process(request)
        self.assertEqual(seen, {"via": "file", "label": "import 10.1000/a", "request": request.pk})
        self.assertEqual(FetchRequest.objects.get().status, FetchRequest.Status.DONE)


class QueueRequestLineTests(TestCase):
    """One line per request of the queue the worker did (#395)."""

    def setUp(self):
        self.pub = Publication.objects.create(doi="10.1000/a")
        for position in range(3):
            CitedReference.objects.create(source=self.pub, position=position)

    def process(self, run):
        request = fetch_queue.enqueue(self.pub, None, with_references=True)
        claimed = fetch_queue.claim_next()
        with (
            patch.object(fetch_actions, "run", side_effect=run),
            patch.object(LOGGER, "disabled", False),
            self.assertLogs(LOGGER, "INFO") as logs,
        ):
            fetch_queue.process(claimed)
        lines = [json.loads(record.getMessage()) for record in logs.records]
        return request, lines

    def api_request(self):
        api_log.record("Crossref", "x", "https://x", {}, response(), ms=5, attempt=1, stream=False)

    def test_a_request_done(self):
        def run(fetch):
            self.api_request()
            self.api_request()
            return self.pub

        request, lines = self.process(run)
        self.assertEqual([line["event"] for line in lines], ["api", "api", "file"])
        line = lines[-1]
        self.assertEqual(
            (line["action"], line["identifier"], line["request"]),
            ("import_with_references", "10.1000/a", request.pk),
        )
        self.assertEqual((line["status"], line["error"]), ("done", ""))
        self.assertEqual((line["api_requests"], line["references"]), (2, 3))
        self.assertIsInstance(line["wait_ms"], int)
        self.assertIsInstance(line["ms"], int)

    def test_a_request_failed(self):
        def run(fetch):
            raise fetch_actions.FetchFailed("DOI inconnu.")

        _request, (line,) = self.process(run)
        self.assertEqual((line["status"], line["error"]), ("failed", "DOI inconnu."))
        self.assertEqual((line["api_requests"], line["references"]), (0, None))


class HandlerTests(SimpleTestCase):
    def test_the_folder_is_created_with_the_first_line(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "logs" / "api.log"
            handler = api_log.ApiLogHandler(str(path), maxBytes=1000, backupCount=1)
            self.assertFalse(path.parent.exists())
            handler.emit(logging.makeLogRecord({"msg": "{}"}))
            handler.close()
            self.assertEqual(path.read_text(), "{}\n")


def line(at, service="Crossref", status=200, ms=100, cache=False, via="page", label="GET /"):
    return json.dumps(
        {
            "at": at,
            "service": service,
            "subject": "10.1000/a",
            "status": status,
            "ms": ms,
            "cache": cache,
            "via": via,
            "label": label,
        }
    )


class SummaryTests(SimpleTestCase):
    """python manage.py api_log (#395)."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "api.log"
        Path(f"{self.path}.1").write_text(
            line("2026-11-15T10:00:00+00:00", ms=400, via="file", label="import 10.1000/a") + "\n"
        )
        self.path.write_text(
            "\n".join(
                [
                    line("2026-11-15T11:00:00+00:00", label="POST /publications/12/refresh/"),
                    line("2026-11-15T11:00:01+00:00", status=404, ms=50),
                    line("2026-11-15T11:00:02+00:00", service="OpenAlex", cache=True),
                    line("2026-11-15T11:00:03+00:00", service="ORCID", status=None, ms=10_000),
                    json.dumps(
                        {
                            "event": "file",
                            "at": "2026-11-15T11:00:04+00:00",
                            "action": "import_with_references",
                            "status": "done",
                            "wait_ms": 170,
                            "ms": 1300,
                            "api_requests": 3,
                        }
                    ),
                    "pas du JSON",
                ]
            )
        )

    def found(self, since=None):
        return summary.entries(summary.journal_files(self.path), since)

    def test_the_rotated_files_are_read_first(self):
        found = self.found()
        self.assertEqual(len(found), 6)
        self.assertEqual(found[0]["via"], "file")

    def test_by_source(self):
        crossref = summary.summarize(self.found())["by_service"]["Crossref"]
        self.assertEqual((crossref.requests, crossref.unknown, crossref.errors), (3, 1, 0))
        self.assertEqual(crossref.median(), 100)
        openalex = summary.summarize(self.found())["by_service"]["OpenAlex"]
        self.assertEqual((openalex.cached, openalex.sent), (1, 0))
        orcid = summary.summarize(self.found())["by_service"]["ORCID"]
        self.assertEqual((orcid.errors, orcid.seconds()), (1, 10.0))

    def test_the_requests_of_the_queue(self):
        queue = summary.summarize(self.found())["by_action"]["import_with_references"]
        self.assertEqual((queue.requests, queue.failed), (1, 0))
        self.assertEqual((queue.median_wait(), queue.median(), queue.per_request()), (170, 1300, 3))
        # Not counted as a request to an API.
        self.assertNotIn(None, summary.summarize(self.found())["by_service"])

    def test_by_origin_without_numbers(self):
        origins = summary.summarize(self.found())["by_origin"]
        self.assertIn("page POST /publications/<n>/refresh/", origins)
        self.assertIn("file import", origins)

    def test_the_command(self):
        out = StringIO()
        call_command("api_log", file=str(self.path), stdout=out)
        text = out.getvalue()
        self.assertIn("5 requêtes du 2026-11-15 10:00 au 2026-11-15 11:00", text)
        self.assertIn("dont 1 servie par le cache ; 1 demande de la file traitée.", text)
        self.assertIn("Demandes de la file", text)
        self.assertIn("Par source", text)
        self.assertIn("page POST /publications/<n>/refresh/", text)
        self.assertIn("Les plus lentes", text)

    def test_an_empty_journal(self):
        out = StringIO()
        call_command("api_log", file=str(self.path.parent / "absent.log"), stdout=out)
        self.assertIn("Aucune requête dans le journal.", out.getvalue())
