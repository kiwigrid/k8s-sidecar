import logging
import logging.config
import os
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from multiprocessing import Process
from typing import List

from logger import get_log_config

# Health state variables
is_ready = False
last_k8s_contact = datetime.now(timezone.utc)
watcher_processes: List[Process] = []

# Settings
K8S_CONTACT_THRESHOLD_SECONDS = 60  # tolerated delay before declaring not live


class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Filter out logs for the /healthz endpoint to reduce noise
        msg = record.getMessage()
        return "/healthz" not in msg


class HealthHandler(BaseHTTPRequestHandler):
    # Keep responses as small/plain as possible
    server_version = "HealthHTTP/1.0"

    def do_GET(self):
        global is_ready, last_k8s_contact, watcher_processes

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
        # Liveness check (k8s contact)
        elif (now - last_k8s_contact) > timedelta(
                seconds=K8S_CONTACT_THRESHOLD_SECONDS
        ):
            status = 503
            body = "NOT LIVE (K8s contact lost)"
        # Liveness check (watcher processes)
        elif watcher_processes and not all(p.is_alive() for p in watcher_processes):
            status = 503
            body = "NOT LIVE (watcher thread died)"
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
    Update the timestamp of the last successful Kubernetes contact.
    """
    global last_k8s_contact
    last_k8s_contact = datetime.now(timezone.utc)

def register_watcher_processes(processes: List[Process]):
    """
    Register the list of watcher threads to be monitored for liveness.
    """
    global watcher_processes
    watcher_processes = processes

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
        # Access logger for this tiny server
        log_config["loggers"].setdefault("health_server.access", {
            "level": log_level,
            "propagate": True,
            "filters": ["health_check_filter"],
        })

        logging.config.dictConfig(log_config)

        health_port = int(os.getenv("HEALTH_PORT", "8080"))
        server = ThreadingHTTPServer(("0.0.0.0", health_port), HealthHandler)

        logging.getLogger("health_server").info(
            "Starting health server on 0.0.0.0:%d", health_port
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
