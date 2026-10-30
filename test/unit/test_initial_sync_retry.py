"""
Unit tests for retrying the initial list-based sync on transient Kubernetes
API errors (#660).

Only the standard library is used, so these run with `python -m unittest
discover -s test/unit` and need no cluster.
"""
import os
import sys
import unittest
from unittest import mock

sys.argv = [sys.argv[0]]  # helpers.py parses sys.argv with argparse at import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from kubernetes.client.rest import ApiException  # noqa: E402
from urllib3.exceptions import MaxRetryError, ProtocolError  # noqa: E402

import resources  # noqa: E402

LIST_ARGS = ("label", None, "/tmp/out", None, "GET", None, "ns", "folder",
             "secret", False, None, False, True, None, False)


class InitialSyncRetryTest(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"INITIAL_SYNC_RETRIES": "3", "ERROR_THROTTLE_SLEEP": "7"})
        patcher.start()
        self.addCleanup(patcher.stop)
        sleep_patcher = mock.patch.object(resources, "sleep")
        self.sleep = sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)

    def _patch_list(self, side_effect):
        patcher = mock.patch.object(resources, "list_resources", side_effect=side_effect)
        list_mock = patcher.start()
        self.addCleanup(patcher.stop)
        return list_mock

    def test_retries_gateway_timeout_until_the_list_succeeds(self):
        list_mock = self._patch_list([ApiException(status=504, reason="Gateway Timeout"),
                                      ApiException(status=503, reason="Service Unavailable"),
                                      True])

        self.assertTrue(resources.list_resources_with_retry(*LIST_ARGS))

        self.assertEqual(3, list_mock.call_count)
        list_mock.assert_called_with(*LIST_ARGS)
        self.sleep.assert_has_calls([mock.call(7), mock.call(7)])

    def test_retries_connection_errors(self):
        list_mock = self._patch_list([ProtocolError("connection reset"),
                                      MaxRetryError(None, "/api/v1/secrets"),
                                      False])

        self.assertFalse(resources.list_resources_with_retry(*LIST_ARGS))
        self.assertEqual(3, list_mock.call_count)

    def test_gives_up_after_the_configured_number_of_retries(self):
        list_mock = self._patch_list(ApiException(status=504, reason="Gateway Timeout"))

        with self.assertRaises(ApiException) as ctx:
            resources.list_resources_with_retry(*LIST_ARGS)

        self.assertEqual(504, ctx.exception.status)
        self.assertEqual(4, list_mock.call_count, "one attempt plus INITIAL_SYNC_RETRIES retries")
        self.assertEqual(3, self.sleep.call_count)

    def test_does_not_retry_permanent_errors(self):
        list_mock = self._patch_list(ApiException(status=403, reason="Forbidden"))

        with self.assertRaises(ApiException):
            resources.list_resources_with_retry(*LIST_ARGS)

        self.assertEqual(1, list_mock.call_count)
        self.sleep.assert_not_called()

    def test_zero_retries_raises_on_the_first_failure(self):
        os.environ["INITIAL_SYNC_RETRIES"] = "0"
        list_mock = self._patch_list(ApiException(status=504, reason="Gateway Timeout"))

        with self.assertRaises(ApiException):
            resources.list_resources_with_retry(*LIST_ARGS)

        self.assertEqual(1, list_mock.call_count)
        self.sleep.assert_not_called()


class SidecarStartupUsesRetryTest(unittest.TestCase):
    """main() must route the initial sync through the retrying wrapper; a bare
    list_resources() call would let a transient 504 end the startup."""

    def test_sidecar_imports_the_retrying_list(self):
        import sidecar
        self.assertIs(resources.list_resources_with_retry, sidecar.list_resources_with_retry)
        self.assertFalse(hasattr(sidecar, "list_resources"))


if __name__ == "__main__":
    unittest.main()
