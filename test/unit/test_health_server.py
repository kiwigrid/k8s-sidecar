"""
Unit tests for binding the health server (HEALTH_PORT).

Only the standard library is used, like test_liveness.py.
"""
import errno
import logging
import os
import socket
import sys
import unittest

sys.argv = [sys.argv[0]]
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import healthz  # noqa: E402


def _ipv6_available():
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
            s.bind(("::", 0))
        return True
    except OSError:
        return False


class HealthServerBindTest(unittest.TestCase):

    def setUp(self):
        os.environ.pop("HEALTH_HOST", None)

    def test_free_port_starts_the_server(self):
        server = healthz._create_health_http_server(0)
        self.addCleanup(server.server_close)
        self.assertNotEqual(0, server.server_address[1])

    def test_port_in_use_is_reported_as_such(self):
        """Two sidecars in one pod with the same HEALTH_PORT: the second one
        must fail with EADDRINUSE, not report that IPv6 is unavailable."""
        busy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(busy.close)
        busy.bind(("", 0))
        busy.listen()
        port = busy.getsockname()[1]

        with self.assertLogs("health_server", level="DEBUG") as logs:
            logging.getLogger("health_server").debug("start")
            with self.assertRaises(OSError) as ctx:
                healthz._create_health_http_server(port)

        self.assertEqual(errno.EADDRINUSE, ctx.exception.errno)
        if _ipv6_available():
            self.assertFalse(
                any("IPv6 not available" in line for line in logs.output),
                logs.output,
            )


if __name__ == "__main__":
    unittest.main()
