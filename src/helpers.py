#!/usr/bin/env python

import errno
import hashlib
import os
import stat
import subprocess
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
from requests.packages.urllib3.util.retry import Retry
from types import SimpleNamespace

from logger import get_logger
import argparse

parser = argparse.ArgumentParser(description="CLI flags for kiwigrid sidecar")
parser.add_argument("--req-username-file", type=str, metavar=argparse.REMAINDER, help="path to file containing basic-auth username for REQ. This takes precedence over the environment variable REQ_USERNAME")
parser.add_argument("--req-password-file", type=str, metavar=argparse.REMAINDER, help="path to file containing basic-auth password for REQ. This takes precedence over the environment variable REQ_PASSWORD")
args = parser.parse_args()

CONTENT_TYPE_TEXT          = "ascii"
CONTENT_TYPE_BASE64_BINARY = "binary"

REQ_RETRY_TOTAL          = 5 if os.getenv("REQ_RETRY_TOTAL") is None else int(os.getenv("REQ_RETRY_TOTAL"))
REQ_RETRY_CONNECT        = 10 if os.getenv("REQ_RETRY_CONNECT") is None else int(os.getenv("REQ_RETRY_CONNECT"))
REQ_RETRY_READ           = 5 if os.getenv("REQ_RETRY_READ") is None else int(os.getenv("REQ_RETRY_READ"))
REQ_RETRY_BACKOFF_FACTOR = 1.1 if os.getenv("REQ_RETRY_BACKOFF_FACTOR") is None else float(
    os.getenv("REQ_RETRY_BACKOFF_FACTOR"))
REQ_TIMEOUT              = 10 if os.getenv("REQ_TIMEOUT") is None else float(os.getenv("REQ_TIMEOUT"))

# Allows to suppress TLS verification for all HTTPs requests (except to the API server, which are controller by SKIP_TLS_VERIFY)
# This is particularly useful when the connection to the main container happens as "localhost"
# and most likely the TLS cert offered by that will have an external URL in it.
# Note that the latest 'requests' library no longer offer a way to disable this via
# env vars; however a custom truststore can be set via REQUESTS_CA_BUNDLE
REQ_TLS_VERIFY = False if os.getenv("REQ_SKIP_TLS_VERIFY") == "true" else None

# Tune default timeouts as outlined in
# https://github.com/kubernetes-client/python/issues/1148#issuecomment-626184613
# https://github.com/kubernetes-client/python/blob/master/examples/watch/timeout-settings.md
# I picked 60 and 66 due to https://github.com/nolar/kopf/issues/847#issuecomment-971651446

# 60 is a polite request to the server, asking it to cleanly close the connection after that.
# If you have a network outage, this does nothing.
# You can set this number much higher, maybe to 3600 seconds (1h).
WATCH_SERVER_TIMEOUT = os.environ.get("WATCH_SERVER_TIMEOUT", 60)

# 66 is a client-side timeout, configuring your local socket.
# If you have a network outage dropping all packets with no RST/FIN,
# this is how long your client waits before realizing & dropping the connection.
# You can keep this number low, maybe 60 seconds.
WATCH_CLIENT_TIMEOUT = os.environ.get("WATCH_CLIENT_TIMEOUT", 66)

# Get logger
logger = get_logger()


def write_data_to_file(folder, filename, data, data_type=CONTENT_TYPE_TEXT):
    """
    Write text to a file. If the parent folder doesn't exist, create it. If there are insufficient
    permissions to create the directory, log an error and return.
    """
    if not os.path.exists(folder):
        try:
            os.makedirs(folder)
        except OSError as e:
            if e.errno not in (errno.EACCES, errno.EEXIST):
                raise
            if e.errno == errno.EACCES:
                logger.error(f"Error: insufficient privileges to create {folder}. "
                             f"Skipping {filename}.")
                return False

    absolute_path = os.path.join(folder, filename)
    if os.path.exists(absolute_path):
        # Compare file contents with new ones so we don't update the file if nothing changed
        if data_type == "binary":
            sha256_hash_new = hashlib.sha256(data)
        else:
            sha256_hash_new = hashlib.sha256(data.encode('utf-8'))

        with open(absolute_path, 'rb') as f:
            sha256_hash_cur = hashlib.sha256()
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash_cur.update(byte_block)

        if sha256_hash_new.hexdigest() == sha256_hash_cur.hexdigest():
            logger.debug(f"Contents of {filename} haven't changed. Not overwriting existing file")
            return False

    if data_type == "binary":
        write_type = "wb"
    else:
        write_type = "w"

    logger.info(f"Writing {absolute_path} ({data_type})")
    with open(absolute_path, write_type) as f:
        f.write(data)
        f.close()
    if os.getenv('DEFAULT_FILE_MODE'):
        mode = int(os.getenv('DEFAULT_FILE_MODE'), base=8)
        os.chmod(absolute_path, mode)
    return True


def remove_file(folder, filename):
    complete_file = os.path.join(folder, filename)
    if os.path.isfile(complete_file):
        logger.info(f"Removing {complete_file}")
        os.remove(complete_file)
        return True
    else:
        logger.error(f"Unable to remove {complete_file}, file not found")
        return False


def read_file_content(file_path):
    try:
        with open(file_path, 'r') as file:
            return file.read().strip()
    except FileNotFoundError:
        logger.warning(f"File not found at: {file_path}")
    except PermissionError:
        logger.error(f"No read permission for file: {file_path}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    return None


def fetch_basic_auth_credentials():
    username = os.getenv("REQ_USERNAME")
    password = os.getenv("REQ_PASSWORD")
    # CLI flags take precedence over environment variables
    req_username_file = args.req_username_file or os.getenv("REQ_USERNAME_FILE")
    req_password_file = args.req_password_file or os.getenv("REQ_PASSWORD_FILE")
    if req_username_file:
        username_from_file = read_file_content(req_username_file)
        if username_from_file is not None:
            username = username_from_file
    if req_password_file:
        password_from_file = read_file_content(req_password_file)
        if password_from_file is not None:
            password = password_from_file
    return username, password


def _basic_auth_encoding():
    return os.getenv("REQ_BASIC_AUTH_ENCODING") or "latin1"


def _http_basic_auth(username, password):
    if not username or not password:
        return None
    encoding = _basic_auth_encoding()
    return HTTPBasicAuth(username.encode(encoding), password.encode(encoding))


def _fetch_url_basic_auth_credentials():
    username = os.getenv("URL_USERNAME")
    password = os.getenv("URL_PASSWORD")
    # File paths override the environment variables when the file is readable.
    # A missing file leaves the env value in place (read_file_content returns None).
    username_file = os.getenv("URL_USERNAME_FILE")
    password_file = os.getenv("URL_PASSWORD_FILE")
    if username_file:
        username_from_file = read_file_content(username_file)
        if username_from_file is not None:
            username = username_from_file
    if password_file:
        password_from_file = read_file_content(password_file)
        if password_from_file is not None:
            password = password_from_file
    return username, password


def _use_req_basic_auth_for_file_urls():
    flag = os.getenv("URL_USE_REQ_BASIC_AUTH")
    if flag is None:
        return True
    return flag.lower() != "false"


def _strip_url_userinfo(url):
    """Drop userinfo from a URL, keeping bracketed IPv6 hosts intact.

    urlsplit().username and .password are already percent-decoded. A username
    with an empty password is still explicit auth and must not fall through.
    """
    parts = urlsplit(url)
    if parts.username is None:
        return url, None, None
    host = parts.netloc.rsplit("@", 1)[-1]
    cleaned = urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
    return cleaned, parts.username, parts.password


def _file_url_basic_auth(url):
    """Select basic auth for a *.url download and return the URL without userinfo.

    Order: userinfo embedded in the URL, then URL_USERNAME/URL_PASSWORD (both
    required), then the REQ pair unless URL_USE_REQ_BASIC_AUTH is false.
    """
    url, username, password = _strip_url_userinfo(url)
    if username is not None:
        encoding = _basic_auth_encoding()
        if password is None:
            password = ""
        return url, HTTPBasicAuth(username.encode(encoding), password.encode(encoding))

    username, password = _fetch_url_basic_auth_credentials()
    auth = _http_basic_auth(username, password)
    if auth is not None:
        return url, auth
    if _use_req_basic_auth_for_file_urls():
        username, password = fetch_basic_auth_credentials()
        return url, _http_basic_auth(username, password)
    return url, None


def request(url, method, enable_5xx=False, payload=None, *, file_url=False):
    enforce_status_codes = list() if enable_5xx else [500, 502, 503, 504]
    if file_url and url:
        url, auth = _file_url_basic_auth(url)
    else:
        username, password = fetch_basic_auth_credentials()
        auth = _http_basic_auth(username, password)

    r = requests.Session()

    retries = Retry(total=REQ_RETRY_TOTAL,
                    connect=REQ_RETRY_CONNECT,
                    read=REQ_RETRY_READ,
                    backoff_factor=REQ_RETRY_BACKOFF_FACTOR,
                    allowed_methods=["GET", "POST"],
                    status_forcelist=enforce_status_codes)
    r.mount("http://", HTTPAdapter(max_retries=retries))
    r.mount("https://", HTTPAdapter(max_retries=retries))
    if url is None:
        logger.warning(f"No url provided. Doing nothing.")
        return

    try:
        # If method is not provided use GET as default
        if method == "GET" or not method:
            res = r.get("%s" % url, auth=auth, timeout=REQ_TIMEOUT, verify=REQ_TLS_VERIFY)  # lgtm[python/request-without-cert-validation]
            logger.info(f"Request sent to {url}. Response: {res.status_code} {res.reason} {res.text}")
        elif method == "POST":
            res = r.post("%s" % url, auth=auth, json=payload, timeout=REQ_TIMEOUT, verify=REQ_TLS_VERIFY)  # lgtm[python/request-without-cert-validation]
            logger.info(f"{payload} sent to {url}. Response: {res.status_code} {res.reason} {res.text}")
        else:
            logger.warning(f"Invalid REQ_METHOD: '{method}', please use 'GET' or 'POST'. Doing nothing.")
            return
        return res
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error for URL {url}: {e}")
    except requests.exceptions.SSLError as e:
        logger.error(f"SSL certificate verification failed for URL {url}: {e}")   
    except requests.exceptions.RetryError as e:
        logger.error(f"Max retries exceeded for URL {url}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during request to {url}: {e}")
    # Return a dummy-object with empty attributes to avoid AttributeError if no response is returned (e.g. MaxRetryError)
    logger.debug(f"Returning dummy response for URL {url}")
    return SimpleNamespace(text="", content=b"")

def timestamp():
    """Get a timestamp of the current time for logging."""
    return datetime.now().strftime("[%Y-%m-%d %X]")


def unique_filename(filename, namespace, resource, resource_name):
    """Return a unique filename derived from the arguments provided, e.g.
    "namespace_{namespace}.{configmap|secret}_{resource_name}.{filename}".

    This is used where duplicate data keys may exist between ConfigMaps
    and/or Secrets within the same or multiple Namespaces.

    Keyword arguments:
    filename -- the filename derived from a data key present in a ConfigMap or Secret.
    namespace -- the Namespace from which data is sourced.
    resource -- the resource type, e.g. "configmap" or "secret".
    resource_name -- the name of the "configmap" or "secret" resource instance.
    """
    return "namespace_" + namespace + "." + resource + "_" + resource_name + "." + filename


def execute(script_path):
    logger.info(f"Executing script from {script_path}")
    try:
        if os.access(script_path, os.X_OK):
            result = subprocess.run([script_path],
                                    capture_output=True,
                                    check=True)
        else:
            result = subprocess.run(["sh", script_path],
                                    capture_output=True,
                                    check=True)
        logger.debug(f"Script stdout: {result.stdout}")
        logger.debug(f"Script stderr: {result.stderr}")
        logger.debug(f"Script exit code: {result.returncode}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Script failed with error: {e}")
