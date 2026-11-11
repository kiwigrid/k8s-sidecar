"""
Unit tests for the watch timeouts WATCH_SERVER_TIMEOUT / WATCH_CLIENT_TIMEOUT
(#85, #150).

The kubernetes client only turns `_request_timeout` into a socket timeout when
it is a number or a (connect, read) tuple; any other value is silently ignored
and the watch socket gets no timeout at all. Values read from the environment
are strings, so setting WATCH_CLIENT_TIMEOUT used to disable the protection
against dead connections that it exists for: a watch on a connection that goes
silent (packets dropped, no RST/FIN) then blocks forever (#338).

Only the standard library is used, so these run with `python -m unittest
discover -s test/unit` and need no cluster and no extra test dependency. A
silent connection is modelled by a local server that answers the watch request
with response headers and then stops sending without closing the socket. To
the client this is indistinguishable from a network that drops all packets.
"""
import importlib
import os
import socket
import sys
import threading
import unittest
from unittest import mock

sys.argv = [sys.argv[0]]  # helpers.py parses sys.argv with argparse at import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from kubernetes import client  # noqa: E402
from urllib3.exceptions import ReadTimeoutError  # noqa: E402

import helpers      # noqa: E402
import resources    # noqa: E402

# Short enough to keep the suite fast, long enough to be safely above the time
# a local connection needs to be established.
CLIENT_TIMEOUT = 1
# How long to wait for the watch to give up before declaring it stuck.
WATCHDOG = CLIENT_TIMEOUT + 5


def _helpers_reloaded_with(env):
    """Re-import helpers with `env` set and return the reloaded module.

    helpers reads the timeouts once, at import time. The caller must reload it
    again afterwards (see _restore_helpers) so other tests see the defaults.
    """
    with mock.patch.dict(os.environ, env):
        return importlib.reload(helpers)


def _restore_helpers():
    for var in ("WATCH_SERVER_TIMEOUT", "WATCH_CLIENT_TIMEOUT"):
        os.environ.pop(var, None)
    importlib.reload(helpers)


class SilentServer:
    """Accepts one HTTP request, sends the headers of a chunked response, then
    goes silent while keeping the connection open, like a dead network path."""

    def __init__(self):
        self._listener = socket.create_server(("127.0.0.1", 0))
        self.port = self._listener.getsockname()[1]
        self._conns = []
        self.request_line = None
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        try:
            conn, _ = self._listener.accept()
        except OSError:
            return  # listener closed before a client connected
        self._conns.append(conn)
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(4096)
            if not chunk:
                return
            data += chunk
        self.request_line = data.split(b"\r\n", 1)[0].decode()
        conn.sendall(b"HTTP/1.1 200 OK\r\n"
                     b"Content-Type: application/json\r\n"
                     b"Transfer-Encoding: chunked\r\n"
                     b"\r\n")
        # ...and nothing more. The connection stays open until close().

    def close(self):
        # Closing the connection also releases a client that would otherwise
        # stay blocked on it forever.
        for conn in self._conns:
            conn.close()
        self._listener.close()


class WatchClientTimeoutTest(unittest.TestCase):

    def setUp(self):
        self.server = SilentServer()
        self.addCleanup(self.server.close)

    def _run_watch(self, server_timeout, client_timeout):
        """Run the sidecar's watch against the silent server.

        Returns (finished, exception): whether the watch returned or raised
        within WATCHDOG seconds, and what it raised.
        """
        configuration = client.Configuration()
        configuration.host = f"http://127.0.0.1:{self.server.port}"
        result = {}

        def watch():
            try:
                resources._watch_resource_iterator(
                    label="grafana_dashboard", label_value=None, target_folder="/nonexistent",
                    request_url=None, request_method="GET", request_payload=None,
                    namespace="default", folder_annotation="k8s-sidecar-target-directory",
                    resource="configmap", unique_filenames=False, script=None, enable_5xx=False,
                    ignore_already_processed=False, folder_per_namespace=False)
            except BaseException as e:  # noqa: B902 - report whatever ends the watch
                result["exception"] = e

        with mock.patch.object(resources, "_initialize_kubeclient_configuration"), \
                mock.patch.object(resources, "get_api_client",
                                  lambda: client.ApiClient(configuration=configuration)), \
                mock.patch.object(resources, "WATCH_SERVER_TIMEOUT", server_timeout), \
                mock.patch.object(resources, "WATCH_CLIENT_TIMEOUT", client_timeout):
            worker = threading.Thread(target=watch, daemon=True)
            worker.start()
            worker.join(WATCHDOG)
            finished = not worker.is_alive()

        # Make sure the server really saw a watch request; otherwise a passing
        # test could just mean the request never got that far.
        self.assertIsNotNone(self.server.request_line, "the watch request never reached the server")
        self.assertIn("watch=True", self.server.request_line)
        return finished, result.get("exception")

    def _assert_watch_timed_out(self, finished, exception):
        self.assertTrue(
            finished,
            f"watch still blocked on a silent connection after {WATCHDOG}s; "
            f"WATCH_CLIENT_TIMEOUT={CLIENT_TIMEOUT} was not applied to the socket")
        self.assertIsInstance(exception, ReadTimeoutError,
                              f"watch ended, but not with a read timeout: {exception!r}")

    def test_default_timeouts_apply_to_watch_socket(self):
        # Control case: an int, as helpers yields when the variables are unset.
        # Shows the harness detects a timeout when the value does get applied.
        finished, exception = self._run_watch(server_timeout=60, client_timeout=CLIENT_TIMEOUT)
        self._assert_watch_timed_out(finished, exception)

    def test_timeouts_from_environment_apply_to_watch_socket(self):
        reloaded = _helpers_reloaded_with({"WATCH_SERVER_TIMEOUT": "60",
                                           "WATCH_CLIENT_TIMEOUT": str(CLIENT_TIMEOUT)})
        self.addCleanup(_restore_helpers)
        finished, exception = self._run_watch(server_timeout=reloaded.WATCH_SERVER_TIMEOUT,
                                              client_timeout=reloaded.WATCH_CLIENT_TIMEOUT)
        self._assert_watch_timed_out(finished, exception)


class WatchTimeoutConfigTest(unittest.TestCase):

    def tearDown(self):
        _restore_helpers()

    def test_defaults_are_integers(self):
        _restore_helpers()  # reloads helpers with both variables unset
        reloaded = helpers
        self.assertEqual(reloaded.WATCH_SERVER_TIMEOUT, 60)
        self.assertEqual(reloaded.WATCH_CLIENT_TIMEOUT, 66)

    def test_values_from_environment_are_integers(self):
        reloaded = _helpers_reloaded_with({"WATCH_SERVER_TIMEOUT": "3600",
                                           "WATCH_CLIENT_TIMEOUT": "3660"})
        self.assertIs(type(reloaded.WATCH_SERVER_TIMEOUT), int)
        self.assertIs(type(reloaded.WATCH_CLIENT_TIMEOUT), int)
        self.assertEqual(reloaded.WATCH_SERVER_TIMEOUT, 3600)
        self.assertEqual(reloaded.WATCH_CLIENT_TIMEOUT, 3660)


if __name__ == "__main__":
    unittest.main()
