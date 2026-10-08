"""
Regression tests for charset detection in the shipped interpreter.

`requests` falls back to `charset_normalizer` when a response has neither a
`text/*` content type nor a charset. The compiled `charset_normalizer`
extension crashed with a segmentation fault on the Python 3.15 beta base image
(#633), which killed the sidecar on `.url` downloads (resources.py) and when
logging webhook responses (helpers.py).

Each check runs in a subprocess, so a crash fails the test with a clear
message instead of killing the test runner. CI also runs this file inside the
built image, which is where an ABI mismatch would show up.
"""
import subprocess
import sys
import textwrap
import unittest

LATIN1_BODY = "Grüße aus Köln, Straße".encode("latin-1")


def _run(code):
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)],
                          capture_output=True, text=True, timeout=120)


class CharsetDetectionTest(unittest.TestCase):

    def assertRunsCleanly(self, result):
        self.assertEqual(
            result.returncode, 0,
            f"subprocess exited with {result.returncode} "
            f"(negative = killed by signal, -11 = SIGSEGV)\nstderr:\n{result.stderr}")

    def test_charset_normalizer_detects_non_utf8_input(self):
        result = _run(f"""
            import charset_normalizer
            best = charset_normalizer.from_bytes({LATIN1_BODY!r}).best()
            assert best is not None, "no encoding detected"
            print(best.encoding)
        """)
        self.assertRunsCleanly(result)

    def test_requests_decodes_body_without_charset(self):
        for content_type in ("application/octet-stream", None):
            with self.subTest(content_type=content_type):
                result = _run(f"""
                    import requests
                    r = requests.models.Response()
                    r.status_code = 200
                    r._content = {LATIN1_BODY!r}
                    if {content_type!r} is not None:
                        r.headers["Content-Type"] = {content_type!r}
                    r.encoding = requests.utils.get_encoding_from_headers(r.headers)
                    assert r.encoding is None, r.encoding  # forces charset detection
                    assert "Gr" in r.text
                """)
                self.assertRunsCleanly(result)


if __name__ == "__main__":
    unittest.main()
