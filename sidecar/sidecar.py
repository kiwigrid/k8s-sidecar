#!/usr/bin/env python

import os

from kubernetes import client, config
from kubernetes.config.kube_config import KUBE_CONFIG_DEFAULT_LOCATION

from helpers import timestamp
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

    method = os.getenv(REQ_METHOD)
    url = os.getenv(REQ_URL)
    payload = os.getenv(REQ_PAYLOAD)

    # this is where kube_config is going to look for a config file
    kube_config = os.path.expanduser(KUBE_CONFIG_DEFAULT_LOCATION)
    if os.path.exists(kube_config):
        config.load_kube_config(kube_config)
    else:
        config.load_incluster_config()

    print(f"{timestamp()} Config for cluster api loaded...")
    current_namespace = open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read()

    if os.getenv(SKIP_TLS_VERIFY) == "true":
        configuration = client.Configuration()
        configuration.verify_ssl = False
        configuration.debug = False
        client.Configuration.set_default(configuration)

    unique_filenames = os.getenv(UNIQUE_FILENAMES)
    if unique_filenames is not None and unique_filenames.lower() == "true":
        print(f"{timestamp()} Unique filenames will be enforced.")
        unique_filenames = True
    else:
        print(f"{timestamp()} Unique filenames will not be enforced.")
        unique_filenames = False

    if os.getenv(METHOD) == "LIST":
        for res in resources:
            list_resources(label, label_value, target_folder, url, method, payload,
                           current_namespace, folder_annotation, res, unique_filenames)
    else:
        watch_for_changes(os.getenv(METHOD), label, label_value, target_folder, url, method,
                          payload, current_namespace, folder_annotation, resources, unique_filenames)


if __name__ == "__main__":
    main()
