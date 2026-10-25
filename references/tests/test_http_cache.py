import importlib.util
import tempfile
from io import StringIO
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

import requests
from django.core.management import call_command
from django.test import TestCase, override_settings

from references.services import http

# A development dependency: the CI tests run without it, like production.
HAS_REQUESTS_CACHE = importlib.util.find_spec("requests_cache") is not None


class HttpCacheTests(TestCase):
    """The development cache of the responses (settings.HTTP_CACHE_PATH)."""

    def setUp(self):
        http._get_session.cache_clear()
        self.addCleanup(http._get_session.cache_clear)
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "http_cache.sqlite"

    def session(self, path):
        with override_settings(HTTP_CACHE_PATH=path):
            session = http._get_session()
        self.addCleanup(session.close)
        return session

    def test_cache_is_off_in_tests(self):
        self.assertIs(type(http._get_session()), requests.Session)

    def test_no_cache_without_path(self):
        self.assertIs(type(self.session(None)), requests.Session)
        self.assertFalse(http.clear_cache())

    def test_plain_session_without_requests_cache(self):
        with patch.dict("sys.modules", {"requests_cache": None}):
            self.assertIs(type(self.session(self.path)), requests.Session)

    @skipUnless(HAS_REQUESTS_CACHE, "requests-cache is not installed")
    def test_cached_session_with_path(self):
        session = self.session(self.path)
        self.assertEqual(session.settings.allowable_codes, (200,))
        self.assertTrue(http.clear_cache())

    @skipUnless(HAS_REQUESTS_CACHE, "requests-cache is not installed")
    @override_settings(DEBUG=True)
    def test_reset_data_clears_it_on_demand(self):
        self.session(self.path)
        out = StringIO()
        call_command("reset_data", "--no-input", "--clear-http-cache", stdout=out)
        self.assertIn("Cache des sources vidé.", out.getvalue())
