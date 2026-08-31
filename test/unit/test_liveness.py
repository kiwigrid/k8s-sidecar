"""
Unit tests for the watcher liveness signal (#621, #626).

Only the standard library is used, so these run with `python -m unittest
discover -s test/unit` and need no cluster and no extra test dependency.

Note on mocking: the stand-ins for `list_resources` and
`_watch_resource_iterator` are built with `create_autospec`, so calling them
with the wrong number of arguments raises TypeError just like the real
function would. A permissive `lambda *a, **k` would swallow that and hide
exactly the class of bug that #628 fixes.
"""
import os
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import create_autospec

sys.argv = [sys.argv[0]]  # helpers.py parses sys.argv with argparse at import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import healthz      # noqa: E402
import resources    # noqa: E402


def _live_thread(stop):
    t = threading.Thread(target=stop.wait, daemon=True)
    t.start()
    return t


class PerWatcherHeartbeatTest(unittest.TestCase):
    """The liveness signal must be per watcher, not one shared timestamp."""

    def setUp(self):
        self.stop = threading.Event()
        self.addCleanup(self.stop.set)
        healthz.watcher_heartbeats.clear()
        healthz.watcher_processes = []
        healthz.K8S_CONTACT_THRESHOLD_SECONDS = 60

    def test_healthy_watcher_does_not_mask_a_stalled_sibling(self):
        """With RESOURCE=both there is one watcher per resource kind. A single
        shared timestamp would let the healthy one keep the check green."""
        a, b = _live_thread(self.stop), _live_thread(self.stop)
        healthz.register_watcher_processes([a, b], heartbeat_interval=30)

        # Only watcher A reports in; B is alive but stuck in a stalled stream.
        healthz.watcher_heartbeats[a.ident] = datetime.now(timezone.utc)
        healthz.watcher_heartbeats[b.ident] = datetime.now(timezone.utc) - timedelta(seconds=300)

        stale = healthz._stale_watchers(datetime.now(timezone.utc))
        self.assertEqual([b], stale)
        self.assertTrue(b.is_alive(), "is_alive() stays True, which is why it cannot catch this")

    def test_no_watchers_registered_is_never_stale(self):
        """METHOD=LIST registers no watchers; a one-shot run must not report
        itself as not live."""
        self.assertEqual([], healthz._stale_watchers(datetime.now(timezone.utc)))

    def test_threshold_is_derived_from_the_reporting_interval(self):
        healthz.register_watcher_processes([_live_thread(self.stop)], heartbeat_interval=30)
        self.assertEqual(60, healthz.K8S_CONTACT_THRESHOLD_SECONDS)

    def test_environment_overrides_the_derived_threshold(self):
        os.environ["K8S_CONTACT_THRESHOLD_SECONDS"] = "123"
        self.addCleanup(os.environ.pop, "K8S_CONTACT_THRESHOLD_SECONDS", None)
        healthz.register_watcher_processes([_live_thread(self.stop)], heartbeat_interval=30)
        self.assertEqual(123, healthz.K8S_CONTACT_THRESHOLD_SECONDS)

    def test_registration_seeds_heartbeats(self):
        """The clock has to start at registration, otherwise a watcher that has
        not reported yet looks stale on the very first probe."""
        t = _live_thread(self.stop)
        healthz.register_watcher_processes([t], heartbeat_interval=30)
        self.assertIn(t.ident, healthz.watcher_heartbeats)
        self.assertEqual([], healthz._stale_watchers(datetime.now(timezone.utc)))


class WatchLoopHeartbeatTest(unittest.TestCase):
    """Both branches of _watch_resource_loop() must record a heartbeat."""

    LOOP_ARGS = dict(
        label="l", label_value=None, target_folder="/tmp/does-not-matter",
        request_url=None, request_method=None, request_payload=None,
        folder_annotation=None, resource="configmap", unique_filenames=False,
        script=None, enable_5xx=False, ignore_already_processed=False,
    )

    def _run_one_iteration(self, mode, namespace="ALL", resource_name=None):
        stamped = []
        shutdown = threading.Event()

        # autospec: wrong argument counts raise, they do not get swallowed.
        fake_list = create_autospec(resources.list_resources, side_effect=lambda *a, **k: shutdown.set())
        fake_watch = create_autospec(resources._watch_resource_iterator, side_effect=lambda *a, **k: shutdown.set())

        patches = {
            "update_k8s_contact": lambda: stamped.append(True),
            "_initialize_kubeclient_configuration": lambda: None,
            "sleep": lambda _s: shutdown.set(),
            "list_resources": fake_list,
            "_watch_resource_iterator": fake_watch,
        }
        originals = {name: getattr(resources, name) for name in patches}
        for name, value in patches.items():
            setattr(resources, name, value)
        self.addCleanup(lambda: [setattr(resources, n, v) for n, v in originals.items()])

        a = self.LOOP_ARGS
        resources._watch_resource_loop(
            shutdown, mode, a["label"], a["label_value"], a["target_folder"],
            a["request_url"], a["request_method"], a["request_payload"],
            namespace, a["folder_annotation"], a["resource"], a["unique_filenames"],
            a["script"], a["enable_5xx"], a["ignore_already_processed"],
            resource_name, False,
        )
        return stamped

    def test_sleep_branch_records_a_heartbeat(self):
        self.assertTrue(self._run_one_iteration("SLEEP"))

    def test_watch_branch_records_a_heartbeat(self):
        """An idle cluster produces no events, so the per-event stamp never
        fires. Without the stamp after a completed reconnect, a healthy sidecar
        would age out and be restarted."""
        self.assertTrue(self._run_one_iteration("WATCH"))

    def test_watch_with_resource_name_takes_the_list_path_and_still_stamps(self):
        self.assertTrue(self._run_one_iteration("WATCH", namespace="default", resource_name="cm-a"))


class HeartbeatIntervalTest(unittest.TestCase):
    """The interval must match the branch a watcher actually takes."""

    def setUp(self):
        os.environ["SLEEP_TIME"] = "90"
        self.addCleanup(os.environ.pop, "SLEEP_TIME", None)

    def test_sleep_mode_uses_sleep_time(self):
        self.assertEqual(90, resources.heartbeat_interval("SLEEP", "ALL", None))

    def test_plain_watch_uses_the_server_timeout(self):
        self.assertEqual(int(resources.WATCH_SERVER_TIMEOUT),
                         resources.heartbeat_interval("WATCH", "ALL", None))

    def test_watch_with_resource_name_on_one_namespace_uses_sleep_time(self):
        """This is the case the derivation used to get wrong: WATCH plus
        RESOURCE_NAME on a single namespace runs the list-and-sleep path, so it
        reports in at SLEEP_TIME. Sizing it against WATCH_SERVER_TIMEOUT flaps
        once SLEEP_TIME exceeds twice that value."""
        self.assertEqual(90, resources.heartbeat_interval("WATCH", "default", "cm-a"))

    def test_watch_with_resource_name_on_all_namespaces_still_watches(self):
        """RESOURCE_NAME only diverts to the list path when the namespace is
        not ALL, so this one must stay on the watch interval."""
        self.assertEqual(int(resources.WATCH_SERVER_TIMEOUT),
                         resources.heartbeat_interval("WATCH", "ALL", "cm-a"))


if __name__ == "__main__":
    unittest.main()
