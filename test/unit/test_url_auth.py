"""
Unit tests for separate basic auth on *.url downloads (#290).

REQ_USERNAME/REQ_PASSWORD stay on reload requests. *.url downloads prefer
userinfo in the URL, then URL_USERNAME/URL_PASSWORD, then the REQ pair unless
URL_USE_REQ_BASIC_AUTH is false.

Only the standard library is used, so these run with `python -m unittest
discover -s test/unit` and need no cluster and no extra test dependency.
"""
import base64
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock

import requests
from requests.auth import HTTPBasicAuth

sys.argv = [sys.argv[0]]  # helpers.py parses sys.argv with argparse at import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import helpers   # noqa: E402
import resources  # noqa: E402

_AUTH_ENV = (
    "REQ_USERNAME",
    "REQ_PASSWORD",
    "URL_USERNAME",
    "URL_PASSWORD",
    "URL_USERNAME_FILE",
    "URL_PASSWORD_FILE",
    "URL_USE_REQ_BASIC_AUTH",
)

_PLAIN_URL = "https://grafana.com/api/dashboards/7645/revisions/latest/download"
_USERINFO_URL = (
    "https://dash-user:dash-pass@grafana.com/api/dashboards/13329/revisions/latest/download"
)
_STRIPPED_USERINFO_URL = (
    "https://grafana.com/api/dashboards/13329/revisions/latest/download"
)


@contextmanager
def _patched_get(side_effect=None, text="ok", content=b"ok"):
    session = mock.Mock()
    if side_effect is not None:
        session.get.side_effect = side_effect
    else:
        session.get.return_value = SimpleNamespace(
            status_code=200, reason="OK", text=text, content=content)
    with mock.patch("helpers.requests.Session", return_value=session):
        yield session


class UrlDownloadAuthTest(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in _AUTH_ENV}
        for key in _AUTH_ENV:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _assert_basic_auth(self, auth, username, password):
        self.assertIsInstance(auth, HTTPBasicAuth)
        self.assertEqual(username.encode("latin1"), auth.username)
        self.assertEqual(password.encode("latin1"), auth.password)

    def test_default_url_download_uses_req_credentials(self):
        """url-configmap-basic-auth downloads secured.txt.url with the REQ pair."""
        os.environ["REQ_USERNAME"] = "req-user"
        os.environ["REQ_PASSWORD"] = "req-pass"
        url = "http://dummy-server/secured"
        with _patched_get() as session:
            filename, data = resources._get_file_data_and_name(
                "secured.txt.url", url, False)
        self.assertEqual("secured.txt", filename)
        self.assertEqual("ok", data)
        self.assertEqual(url, session.get.call_args.args[0])
        self._assert_basic_auth(session.get.call_args.kwargs["auth"], "req-user", "req-pass")

    def test_embedded_userinfo_overrides_req_and_is_stripped_from_the_log(self):
        os.environ["REQ_USERNAME"] = "req-user"
        os.environ["REQ_PASSWORD"] = "req-pass"
        with self.assertLogs("k8s-sidecar", level="INFO") as logs:
            with _patched_get() as session:
                resources._get_file_data_and_name("dash.json.url", _USERINFO_URL, False)
        self.assertEqual(_STRIPPED_USERINFO_URL, session.get.call_args.args[0])
        self._assert_basic_auth(
            session.get.call_args.kwargs["auth"], "dash-user", "dash-pass")
        logged = "\n".join(logs.output)
        self.assertNotIn("dash-pass", logged)
        self.assertNotIn("dash-user:dash-pass@", logged)

    def test_url_use_req_basic_auth_false_skips_file_urls_only(self):
        os.environ["REQ_USERNAME"] = "req-user"
        os.environ["REQ_PASSWORD"] = "req-pass"
        os.environ["URL_USE_REQ_BASIC_AUTH"] = "False"
        reload_url = "http://grafana.monitoring.svc/api/admin/provisioning/dashboards/reload"
        with _patched_get() as session:
            resources._get_file_data_and_name("dash.json.url", _PLAIN_URL, False)
            helpers.request(reload_url, "GET")
        file_call, reload_call = session.get.call_args_list
        self.assertEqual(_PLAIN_URL, file_call.args[0])
        self.assertIsNone(file_call.kwargs["auth"])
        self.assertEqual(reload_url, reload_call.args[0])
        self._assert_basic_auth(reload_call.kwargs["auth"], "req-user", "req-pass")

    def test_url_pair_overrides_req_and_a_partial_pair_falls_through(self):
        os.environ["REQ_USERNAME"] = "req-user"
        os.environ["REQ_PASSWORD"] = "req-pass"
        os.environ["URL_USERNAME"] = "url-user"
        os.environ["URL_PASSWORD"] = "url-pass"
        with _patched_get() as session:
            resources._get_file_data_and_name("a.url", _PLAIN_URL, False)
        self._assert_basic_auth(session.get.call_args.kwargs["auth"], "url-user", "url-pass")

        del os.environ["URL_PASSWORD"]
        with _patched_get() as session:
            resources._get_file_data_and_name("a.url", _PLAIN_URL, False)
        self._assert_basic_auth(session.get.call_args.kwargs["auth"], "req-user", "req-pass")

        os.environ["URL_PASSWORD"] = "url-pass"
        del os.environ["URL_USERNAME"]
        os.environ["URL_USE_REQ_BASIC_AUTH"] = "false"
        with _patched_get() as session:
            resources._get_file_data_and_name("a.url", _PLAIN_URL, False)
        self.assertIsNone(session.get.call_args.kwargs["auth"])

    def test_url_credential_files_override_readable_values_only(self):
        os.environ["URL_USERNAME"] = "env-user"
        os.environ["URL_PASSWORD"] = "env-pass"
        with tempfile.TemporaryDirectory() as tmp:
            username_path = os.path.join(tmp, "username")
            password_path = os.path.join(tmp, "password")
            with open(username_path, "w", encoding="utf-8") as handle:
                handle.write("file-user\n")
            with open(password_path, "w", encoding="utf-8") as handle:
                handle.write("file-pass\n")
            os.environ["URL_USERNAME_FILE"] = username_path
            os.environ["URL_PASSWORD_FILE"] = password_path
            with _patched_get() as session:
                resources._get_file_data_and_name("a.url", _PLAIN_URL, False)
            self._assert_basic_auth(
                session.get.call_args.kwargs["auth"], "file-user", "file-pass")

            os.environ["URL_PASSWORD_FILE"] = os.path.join(tmp, "missing-password")
            with _patched_get() as session:
                resources._get_file_data_and_name("a.url", _PLAIN_URL, False)
            self._assert_basic_auth(
                session.get.call_args.kwargs["auth"], "file-user", "env-pass")

    def test_base64_url_uses_the_same_userinfo_selection(self):
        os.environ["REQ_USERNAME"] = "req-user"
        os.environ["REQ_PASSWORD"] = "req-pass"
        encoded = base64.b64encode(_USERINFO_URL.encode("utf8")).decode("ascii")
        with _patched_get(content=b"binary-body") as session:
            filename, data = resources._get_file_data_and_name(
                "tool.url", encoded, False,
                content_type=helpers.CONTENT_TYPE_BASE64_BINARY)
        self.assertEqual("tool", filename)
        self.assertEqual(b"binary-body", data)
        self.assertEqual(_STRIPPED_USERINFO_URL, session.get.call_args.args[0])
        self._assert_basic_auth(
            session.get.call_args.kwargs["auth"], "dash-user", "dash-pass")

    def test_disabling_req_fallback_keeps_retry_timeout_and_failure_result(self):
        os.environ["REQ_USERNAME"] = "req-user"
        os.environ["REQ_PASSWORD"] = "req-pass"
        os.environ["URL_USE_REQ_BASIC_AUTH"] = "false"
        with _patched_get(side_effect=requests.exceptions.ConnectionError("down")) as session:
            result = helpers.request(_PLAIN_URL, "GET", file_url=True)
        self.assertIsNone(session.get.call_args.kwargs["auth"])
        self.assertEqual(helpers.REQ_TIMEOUT, session.get.call_args.kwargs["timeout"])
        adapter = session.mount.call_args_list[0].args[1]
        self.assertEqual([500, 502, 503, 504], list(adapter.max_retries.status_forcelist))
        self.assertEqual("", result.text)
        self.assertEqual(b"", result.content)

        with _patched_get(side_effect=requests.exceptions.RetryError("retries")) as session:
            result = helpers.request(_PLAIN_URL, "GET", True, file_url=True)
        adapter = session.mount.call_args_list[0].args[1]
        self.assertEqual([], list(adapter.max_retries.status_forcelist))
        self.assertEqual("", result.text)
        self.assertEqual(b"", result.content)


if __name__ == "__main__":
    unittest.main()
