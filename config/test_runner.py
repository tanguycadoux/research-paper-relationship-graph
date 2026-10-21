from unittest.mock import patch

from django.test.runner import DiscoverRunner


class NoNetworkTestRunner(DiscoverRunner):
    """Test runner that makes any network connection fail: external APIs must be mocked."""

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._network_guard = patch(
            "socket.socket.connect",
            side_effect=RuntimeError("Network access is forbidden in tests: mock the API."),
        )
        self._network_guard.start()

    def teardown_test_environment(self, **kwargs):
        self._network_guard.stop()
        super().teardown_test_environment(**kwargs)
