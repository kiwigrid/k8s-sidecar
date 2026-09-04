import ipaddress
import logging
import logging.config
import os
import socket
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Dict, List, Optional

from logger import get_log_config

# Health state variables
is_ready = False
watcher_processes: List[Thread] = []

# Last successful Kubernetes contact, tracked PER WATCHER THREAD (keyed by
# thread ident). A single shared timestamp is not enough: with RESOURCE=both
# there is one watcher per resource kind, and a healthy one would keep the
# shared timestamp fresh while another sits on a stalled stream (see #621).
watcher_heartbeats: Dict[int, datetime] = {}
_heartbeat_lock = threading.Lock()

# Tolerated delay before declaring not live. Overridden in
# register_watcher_processes() based on how often watchers actually report in;
# the default only applies until watchers are registered.
K8S_CONTACT_THRESHOLD_SECONDS = 60


class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Filter out logs for the /healthz endpoint to reduce noise
        msg = record.getMessage()
        return "/healthz" not in msg


class HealthHandler(BaseHTTPRequestHandler):
    # Keep responses as small/plain as possible
    server_version = "HealthHTTP/1.0"

    def do_GET(self):
        global is_ready, watcher_processes

        if self.path != "/healthz":
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            body = "Not Found"
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return

        now = datetime.now(timezone.utc)

        # Readiness check
        if not is_ready:
            status = 503
            body = "NOT READY"
        # Liveness check (watcher threads still running)
        elif watcher_processes and not all(p.is_alive() for p in watcher_processes):
            status = 503
            body = "NOT LIVE (watcher thread died)"
        # Liveness check (k8s contact, per watcher). This is what catches a
        # watcher that is still alive but stuck in a stream that never returns
        # -- the failure mode of #338/#621, which is_alive() cannot see.
        elif _stale_watchers(now):
            status = 503
            body = "NOT LIVE (K8s contact lost)"
        else:
            status = 200
            body = "OK"

        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    # Avoid noisy default stderr logging; push to logging module instead
    def log_message(self, format: str, *args):
        # Skip logging /healthz entirely, or you can route it through the filter
        if self.path == "/healthz":
            return

        logger = logging.getLogger("health_server.access")
        logger.info(
            "%s - - [%s] " + format,
            self.client_address[0],
            self.log_date_time_string(),
            *args,
            )


# Public helper functions

def mark_ready():
    """
    Mark the sidecar as ready (initial sync done).
    """
    global is_ready
    is_ready = True

def update_k8s_contact():
    """
    Record a successful Kubernetes contact for the CALLING watcher thread.

    Must be called from the watcher thread itself -- the heartbeat is keyed by
    threading.get_ident(). Calling it from the main thread would only refresh
    an entry nothing looks at, which was the original defect (#621): the main
    loop refreshed a single shared timestamp every 5s regardless of whether any
    watcher had reached the API server, so the liveness check could never fail.
    """
    with _heartbeat_lock:
        watcher_heartbeats[threading.get_ident()] = datetime.now(timezone.utc)


def _stale_watchers(now: datetime) -> List[Thread]:
    """
    Return the registered watcher threads whose last Kubernetes contact is older
    than the tolerated threshold. Empty while no watchers are registered (e.g.
    METHOD=LIST), so a one-shot run is never reported as not live.
    """
    threshold = timedelta(seconds=K8S_CONTACT_THRESHOLD_SECONDS)
    with _heartbeat_lock:
        return [
            t for t in watcher_processes
            if (now - watcher_heartbeats.get(t.ident, now)) > threshold
        ]


def register_watcher_processes(processes: List[Thread], heartbeat_interval: Optional[int] = None):
    """
    Register the watcher threads to be monitored for liveness and seed their
    heartbeats, so the clock starts at registration rather than at first report.

    heartbeat_interval is how often a healthy watcher is expected to report in
    (WATCH_SERVER_TIMEOUT when watching, SLEEP_TIME when polling). The threshold
    is derived as twice that, so the check never sits exactly on the reconnect
    boundary and flaps. K8S_CONTACT_THRESHOLD_SECONDS in the environment
    overrides the derived value.
    """
    global watcher_processes, K8S_CONTACT_THRESHOLD_SECONDS
    watcher_processes = processes

    override = os.getenv("K8S_CONTACT_THRESHOLD_SECONDS")
    if override:
        K8S_CONTACT_THRESHOLD_SECONDS = int(override)
    elif heartbeat_interval:
        K8S_CONTACT_THRESHOLD_SECONDS = 2 * int(heartbeat_interval)

    now = datetime.now(timezone.utc)
    with _heartbeat_lock:
        watcher_heartbeats.clear()
        for thread in processes:
            watcher_heartbeats[thread.ident] = now

def _create_health_http_server(health_port: int) -> ThreadingHTTPServer:
    """
    Create the health HTTP server, binding to HEALTH_HOST if set.

    Without HEALTH_HOST, dual-stack IPv6 is attempted first and IPv4 is used
    as a fallback for clusters/pods without IPv6 support (see #531, #605, #606).
    """
    logger = logging.getLogger("health_server")
    health_host = os.getenv("HEALTH_HOST")

    if health_host is not None:
        try:
            family = socket.AF_INET6 if ipaddress.ip_address(health_host).version == 6 else socket.AF_INET
        except ValueError:
            # Not an IP literal (e.g. a hostname); let the OS resolve it as IPv6/dual-stack.
            family = socket.AF_INET6
        ThreadingHTTPServer.address_family = family
        return ThreadingHTTPServer((health_host, health_port), HealthHandler)

    try:
        ThreadingHTTPServer.address_family = socket.AF_INET6
        return ThreadingHTTPServer(("", health_port), HealthHandler)
    except OSError:
        logger.warning("IPv6 not available, falling back to IPv4 for the health server")
        ThreadingHTTPServer.address_family = socket.AF_INET
        return ThreadingHTTPServer(("", health_port), HealthHandler)


def start_health_server():
    """
    Start the lightweight health HTTP server in a background thread.
    """
    def run():
        log_config = get_log_config()

        # Define the filter in the config to be callable
        log_config.setdefault('filters', {})
        log_config['filters']['health_check_filter'] = {
            '()': 'healthz.HealthCheckFilter'
        }

        log_config.setdefault("loggers", {})
        # Loggers for this tiny server. Explicitly use 'console' handler and no propagation.
        # This ensures they use the global logLevel and JSON formatting from logger.py.
        log_config["loggers"].setdefault("health_server.access", {
            "filters": ["health_check_filter"],
        })

        logging.config.dictConfig(log_config)

        health_port = int(os.getenv("HEALTH_PORT", "8080"))
        server = _create_health_http_server(health_port)

        logging.getLogger("health_server").info(
            "Starting health server on port %d", health_port
        )

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()

    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()
