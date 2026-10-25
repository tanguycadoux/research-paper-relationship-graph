from unittest.mock import patch

from django.conf import settings
from django.test.runner import DiscoverRunner


class NoNetworkTestRunner(DiscoverRunner):
    """
    Test runner that makes any network connection fail: external APIs must be mocked.
    The development cache of the responses is off, so that no test reads it.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        settings.HTTP_CACHE_PATH = None
        self._network_guard = patch(
            "socket.socket.connect",
            side_effect=RuntimeError("Network access is forbidden in tests: mock the API."),
        )
        self._network_guard.start()

    def teardown_test_environment(self, **kwargs):
        self._network_guard.stop()
        super().teardown_test_environment(**kwargs)
