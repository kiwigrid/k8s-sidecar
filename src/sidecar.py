#!/usr/bin/env python

import os

from kubernetes import client, config
from kubernetes.config.kube_config import KUBE_CONFIG_DEFAULT_LOCATION
from requests.packages.urllib3.util.retry import Retry

from helpers import timestamp, REQ_RETRY_TOTAL, REQ_RETRY_CONNECT, REQ_RETRY_READ, REQ_RETRY_BACKOFF_FACTOR
from resources import list_resources, watch_for_changes

METHOD = "METHOD"
UNIQUE_FILENAMES = "UNIQUE_FILENAMES"
SKIP_TLS_VERIFY = "SKIP_TLS_VERIFY"
FOLDER = "FOLDER"
FOLDER_ANNOTATION = "FOLDER_ANNOTATION"
LABEL = "LABEL"
LABEL_VALUE = "LABEL_VALUE"
RESOURCE = "RESOURCE"
REQ_PAYLOAD = "REQ_PAYLOAD"
REQ_URL = "REQ_URL"
REQ_METHOD = "REQ_METHOD"
SCRIPT = "SCRIPT"
ENABLE_5XX = "ENABLE_5XX"
IGNORE_ALREADY_PROCESSED = "IGNORE_ALREADY_PROCESSED"


def main():
    print(f"{timestamp()} Starting collector")

    folder_annotation = os.getenv(FOLDER_ANNOTATION)
    if folder_annotation is None:
        print(f"{timestamp()} No folder annotation was provided, "
              "defaulting to k8s-sidecar-target-directory")
        folder_annotation = "k8s-sidecar-target-directory"

    label = os.getenv(LABEL)
    if label is None:
        print(f"{timestamp()} Should have added {LABEL} as environment variable! Exit")
        return -1

    label_value = os.getenv(LABEL_VALUE)
    if label_value:
        print(f"{timestamp()} Filter labels with value: {label_value}")

    target_folder = os.getenv(FOLDER)
    if target_folder is None:
        print(f"{timestamp()} Should have added {FOLDER} as environment variable! Exit")
        return -1

    resources = os.getenv(RESOURCE, "configmap")
    resources = ("secret", "configmap") if resources == "both" else (resources,)
    print(f"{timestamp()} Selected resource type: {resources}")

    request_method = os.getenv(REQ_METHOD)
    request_url = os.getenv(REQ_URL)
    request_payload = os.getenv(REQ_PAYLOAD)
    script = os.getenv(SCRIPT)

    _initialize_kubeclient_configuration()

    unique_filenames = os.getenv(UNIQUE_FILENAMES)
    if unique_filenames is not None and unique_filenames.lower() == "true":
        print(f"{timestamp()} Unique filenames will be enforced.")
        unique_filenames = True
    else:
        print(f"{timestamp()} Unique filenames will not be enforced.")
        unique_filenames = False

    enable_5xx = os.getenv(ENABLE_5XX)
    if enable_5xx is not None and enable_5xx.lower() == "true":
        print(f"{timestamp()} 5xx response content will be enabled.")
        enable_5xx = True
    else:
        print(f"{timestamp()} 5xx response content will not be enabled.")
        enable_5xx = False

    ignore_already_processed = os.getenv(IGNORE_ALREADY_PROCESSED)
    if ignore_already_processed is not None and ignore_already_processed.lower() == "true":
        # Check API version
        version = client.VersionApi().get_code()
        if int(version.major) > 1 or (int(version.major) == 1 and int(version.minor) >= 19):
            print(f"{timestamp()} ignore already processed resource will be enabled.")
            ignore_already_processed = True
        else:
            print(
                f"{timestamp()} Can't enable 'ignore already processed resource' option, kubernetes api version is "
                f"lower than v1.19.")
            ignore_already_processed = False
    else:
        print(f"{timestamp()} ignore already processed resource will not be enabled.")
        ignore_already_processed = False

    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as f:
        namespace = os.getenv("NAMESPACE", f.read())

    method = os.getenv(METHOD)
    if method == "LIST":
        for res in resources:
            for ns in namespace.split(','):
                list_resources(label, label_value, target_folder, request_url, request_method, request_payload,
                               ns, folder_annotation, res, unique_filenames, script, enable_5xx)
    else:
        watch_for_changes(method, label, label_value, target_folder, request_url, request_method, request_payload,
                          namespace, folder_annotation, resources, unique_filenames, script, enable_5xx,
                          ignore_already_processed)


def _initialize_kubeclient_configuration():
    """
    Updates the default configuration of the kubernetes client. This is
    picked up later on automatically then.
    """

    # this is where kube_config is going to look for a config file
    kube_config = os.path.expanduser(KUBE_CONFIG_DEFAULT_LOCATION)
    if os.path.exists(kube_config):
        print(f"{timestamp()} Loading config from '{kube_config}'...")
        config.load_kube_config(kube_config)
    else:
        print(f"{timestamp()} Loading incluster config ...")
        config.load_incluster_config()

    if os.getenv(SKIP_TLS_VERIFY) == "true":
        configuration = client.Configuration.get_default_copy()
        configuration.verify_ssl = False
        configuration.debug = False
        client.Configuration.set_default(configuration)

    # push urllib3 retries to k8s client config
    configuration = client.Configuration.get_default_copy()
    configuration.retries = Retry(total=REQ_RETRY_TOTAL,
                                  connect=REQ_RETRY_CONNECT,
                                  read=REQ_RETRY_READ,
                                  backoff_factor=REQ_RETRY_BACKOFF_FACTOR)
    client.Configuration.set_default(configuration)

    print(f"{timestamp()} Config for cluster api at '{configuration.host}' loaded...")


if __name__ == "__main__":
    main()
