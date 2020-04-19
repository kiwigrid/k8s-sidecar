#!/usr/bin/env python

import os
import errno
import base64

import requests
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from datetime import datetime


def writeTextToFile(folder, filename, data):
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

    absolutepath = os.path.join(folder, filename)
    with open(absolutepath, 'w') as f:
        f.write(data)
        f.close()
    if os.getenv('DEFAULT_FILE_MODE'):
        mode = int(os.getenv('DEFAULT_FILE_MODE'), base=8)
        os.chmod(absolutepath, mode)


def removeFile(folder, filename):
    completeFile = os.path.join(folder, filename)
    if os.path.isfile(completeFile):
        os.remove(completeFile)
    else:
        print(f"{timestamp()} Error: {completeFile} file not found")


def request(url, method, payload=None):
    retryTotal = 5 if os.getenv("REQ_RETRY_TOTAL") is None else int(os.getenv("REQ_RETRY_TOTAL"))
    retryConnect = 5 if os.getenv("REQ_RETRY_CONNECT") is None else int(
        os.getenv("REQ_RETRY_CONNECT"))
    retryRead = 5 if os.getenv("REQ_RETRY_READ") is None else int(os.getenv("REQ_RETRY_READ"))
    retryBackoffFactor = 0.2 if os.getenv("REQ_RETRY_BACKOFF_FACTOR") is None else float(
        os.getenv("REQ_RETRY_BACKOFF_FACTOR"))
    timeout = 10 if os.getenv("REQ_TIMEOUT") is None else float(os.getenv("REQ_TIMEOUT"))

    r = requests.Session()
    retries = Retry(total=retryTotal,
                    connect=retryConnect,
                    read=retryRead,
                    backoff_factor=retryBackoffFactor,
                    status_forcelist=[500, 502, 503, 504])
    r.mount("http://", HTTPAdapter(max_retries=retries))
    r.mount("https://", HTTPAdapter(max_retries=retries))
    if url is None:
        print(f"{timestamp()} No url provided. Doing nothing.")
        return

    headers = {
    }

    userName = os.getenv("REQ_AUTH_USERNAME")
    password = os.getenv("REQ_AUTH_PASSWORD")
    if userName is not None and password is not None:
        credentials = (userName + ':' + password).encode('utf-8')
        base64_encoded_credentials = base64.b64encode(credentials).decode('utf-8')        
        headers['Authorization'] = 'Basic ' + base64_encoded_credentials

    # If method is not provided use GET as default
    if method == "GET" or not method:
        res = r.get("%s" % url, timeout=timeout)
    elif method == "POST":
        res = r.post("%s" % url, json=payload, timeout=timeout, headers=headers)
        print(f"{timestamp()} {method} request sent to {url}. "
              f"Response: {res.status_code} {res.reason}")
    return res


def timestamp():
    """Get a timestamp of the current time for logging."""
    return datetime.now().strftime("[%Y-%m-%d %X]")
