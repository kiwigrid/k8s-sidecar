#!/usr/bin/env python

import errno
import hashlib
import os
from datetime import datetime
import subprocess

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

CONTENT_TYPE_TEXT = "ascii"
CONTENT_TYPE_BASE64_BINARY = "binary"


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
                print(f"{timestamp()} Error: insufficient privileges to create {folder}. "
                      f"Skipping {filename}.")
                return

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
            print(f"{timestamp()} Contents of {filename} haven't changed. Not overwriting existing file")
            return False

    if data_type == "binary":
        write_type = "wb"
    else:
        write_type = "w"

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
        os.remove(complete_file)
        return True
    else:
        print(f"{timestamp()} Error: {complete_file} file not found")
        return False


def request(url, method, payload=None):
    retry_total = 5 if os.getenv("REQ_RETRY_TOTAL") is None else int(os.getenv("REQ_RETRY_TOTAL"))
    retry_connect = 5 if os.getenv("REQ_RETRY_CONNECT") is None else int(
        os.getenv("REQ_RETRY_CONNECT"))
    retry_read = 5 if os.getenv("REQ_RETRY_READ") is None else int(os.getenv("REQ_RETRY_READ"))
    retry_backoff_factor = 0.2 if os.getenv("REQ_RETRY_BACKOFF_FACTOR") is None else float(
        os.getenv("REQ_RETRY_BACKOFF_FACTOR"))
    timeout = 10 if os.getenv("REQ_TIMEOUT") is None else float(os.getenv("REQ_TIMEOUT"))

    username = os.getenv("REQ_USERNAME")
    password = os.getenv("REQ_PASSWORD")
    if username and password:
        auth = (username, password)
    else:
        auth = None

    r = requests.Session()
    retries = Retry(total=retry_total,
                    connect=retry_connect,
                    read=retry_read,
                    backoff_factor=retry_backoff_factor,
                    status_forcelist=[500, 502, 503, 504])
    r.mount("http://", HTTPAdapter(max_retries=retries))
    r.mount("https://", HTTPAdapter(max_retries=retries))
    if url is None:
        print(f"{timestamp()} No url provided. Doing nothing.")
        return

    # If method is not provided use GET as default
    if method == "GET" or not method:
        res = r.get("%s" % url, auth=auth, timeout=timeout)
    elif method == "POST":
        res = r.post("%s" % url, auth=auth, json=payload, timeout=timeout)
        print(f"{timestamp()} {method} request sent to {url}. "
              f"Response: {res.status_code} {res.reason} {res.text}")
    else:
        print(f"{timestamp()} Invalid REQ_METHOD: '{method}', please use 'GET' or 'POST'. Doing nothing.")
        return
    return res


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
    try:
        result = subprocess.run(["sh", script_path],
                                capture_output=True,
                                check=True)
        print(f"{timestamp()} Script stdout: {result.stdout}")
        print(f"{timestamp()} Script stderr: {result.stderr}")
        print(f"{timestamp()} Script exit code: {result.returncode}")
    except subprocess.CalledProcessError as e:
        print(f"{timestamp()} Script failed with error: {e}")
