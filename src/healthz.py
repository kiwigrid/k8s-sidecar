from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from datetime import datetime, timedelta, timezone
import threading
import uvicorn

# Create FastAPI app
app = FastAPI()

# Health state variables
is_ready = False
last_k8s_contact = datetime.now(timezone.utc)

# Settings
K8S_CONTACT_THRESHOLD_SECONDS = 60  # tolerated delay before declaring not live

@app.get("/healthz")
def healthz():
    """
    Health endpoint for readiness and liveness probes.
    """
    now = datetime.now(timezone.utc)

    # Check readiness
    if not is_ready:
        return PlainTextResponse("NOT READY", status_code=503)

    # Check liveness
    if (now - last_k8s_contact) > timedelta(seconds=K8S_CONTACT_THRESHOLD_SECONDS):
        return PlainTextResponse("NOT LIVE", status_code=503)

    return PlainTextResponse("OK", status_code=200)

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

def start_health_server():
    """
    Start the FastAPI health server in a background thread.
    """
    def run():
        uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")

    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()
