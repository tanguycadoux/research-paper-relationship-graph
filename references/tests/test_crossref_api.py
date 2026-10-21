from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from references.services import crossref_api

LOGGER = "references.services.crossref_api"


def make_response(status_code, payload=None, headers=None):
    response = Mock(status_code=status_code, headers=headers or {})
    response.json.return_value = payload
    return response


@override_settings(CROSSREF_MAILTO="someone@example.org")
@patch("references.services.crossref_api.time.sleep")
@patch("references.services.crossref_api._get_session")
class FetchCrossrefJsonTests(SimpleTestCase):
    def fetch(self, get_session, responses, doi="10.1000/abc"):
        get_session.return_value.get.side_effect = responses
        with self.assertLogs(LOGGER, level="INFO") as logs:
            result = crossref_api.fetch_crossref_json(doi)
        return result, logs

    def test_returns_json_on_success(self, get_session, sleep):
        result, _ = self.fetch(get_session, [make_response(200, {"message": {}})])
        self.assertEqual(result, {"message": {}})
        sleep.assert_not_called()

    def test_sends_mailto_param_and_user_agent(self, get_session, sleep):
        self.fetch(get_session, [make_response(200, {})])
        kwargs = get_session.return_value.get.call_args.kwargs
        self.assertEqual(kwargs["params"], {"mailto": "someone@example.org"})
        self.assertIn("mailto:someone@example.org", kwargs["headers"]["User-Agent"])

    def test_unknown_doi_is_not_retried(self, get_session, sleep):
        result, _ = self.fetch(get_session, [make_response(404)])
        self.assertIsNone(result)
        self.assertEqual(get_session.return_value.get.call_count, 1)

    def test_blocked_client_is_not_retried(self, get_session, sleep):
        result, logs = self.fetch(get_session, [make_response(403)])
        self.assertIsNone(result)
        self.assertEqual(get_session.return_value.get.call_count, 1)
        self.assertIn("403", logs.output[-1])

    def test_rate_limit_waits_retry_after_then_succeeds(self, get_session, sleep):
        responses = [make_response(429, headers={"Retry-After": "3"}), make_response(200, {})]
        result, _ = self.fetch(get_session, responses)
        self.assertEqual(result, {})
        sleep.assert_called_once_with(3)

    def test_server_errors_use_exponential_backoff_then_give_up(self, get_session, sleep):
        result, _ = self.fetch(get_session, [make_response(503)] * 3)
        self.assertIsNone(result)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2])

    def test_network_error_is_retried(self, get_session, sleep):
        responses = [requests.ConnectionError("down"), make_response(200, {})]
        result, _ = self.fetch(get_session, responses)
        self.assertEqual(result, {})

    def test_empty_doi_sends_no_request(self, get_session, sleep):
        self.assertIsNone(crossref_api.fetch_crossref_json(""))
        get_session.return_value.get.assert_not_called()


@override_settings(CROSSREF_MAILTO="")
@patch("references.services.crossref_api._get_session")
class WithoutMailtoTests(SimpleTestCase):
    def test_uses_public_pool_without_mailto(self, get_session):
        get_session.return_value.get.return_value = make_response(200, {})
        with self.assertLogs(LOGGER, level="INFO"):
            crossref_api.fetch_crossref_json("10.1000/abc")
        kwargs = get_session.return_value.get.call_args.kwargs
        self.assertIsNone(kwargs["params"])
        self.assertNotIn("mailto", kwargs["headers"]["User-Agent"])
