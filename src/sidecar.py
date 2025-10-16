#!/usr/bin/env python

import os, sys, re

from kubernetes import client
from kubernetes.client import ApiException
from healthz import start_health_server, mark_ready
from logger import get_logger
from resources import list_resources, watch_for_changes, prepare_payload
from client import _initialize_kubeclient_configuration

METHOD                   = "METHOD"
UNIQUE_FILENAMES         = "UNIQUE_FILENAMES"
FOLDER                   = "FOLDER"
FOLDER_ANNOTATION        = "FOLDER_ANNOTATION"
LABEL                    = "LABEL"
LABEL_VALUE              = "LABEL_VALUE"
RESOURCE                 = "RESOURCE"
RESOURCE_NAME            = "RESOURCE_NAME"
REQ_PAYLOAD              = "REQ_PAYLOAD"
REQ_URL                  = "REQ_URL"
REQ_METHOD               = "REQ_METHOD"
REQ_SKIP_INIT            = "REQ_SKIP_INIT"
SCRIPT                   = "SCRIPT"
ENABLE_5XX               = "ENABLE_5XX"
IGNORE_ALREADY_PROCESSED = "IGNORE_ALREADY_PROCESSED"

# Get logger
logger = get_logger()


def exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.error("%s: %s" % (exc_type.__qualname__, exc_value), exc_info=(exc_type, exc_value, exc_traceback))


sys.excepthook = exception_handler


def main():
    logger.info("Starting collector")

    start_health_server()

    folder_annotation = os.getenv(FOLDER_ANNOTATION)
    if folder_annotation is None:
        logger.info("No folder annotation was provided, "
                       "defaulting to k8s-sidecar-target-directory")
        folder_annotation = "k8s-sidecar-target-directory"

    label = os.getenv(LABEL)
    if label is None:
        logger.fatal("Should have added {LABEL} as environment variable! Exit")
        return -1

    label_value = os.getenv(LABEL_VALUE)
    if label_value:
        logger.debug(f"Filter labels with value: {label_value}")

    target_folder = os.getenv(FOLDER)
    if target_folder is None:
        logger.fatal(f"Should have added {FOLDER} as environment variable! Exit")
        return -1

    resources = os.getenv(RESOURCE, "configmap")
    resources = ("secret", "configmap") if resources == "both" else (resources,)
    logger.debug(f"Selected resource type: {resources}")

    resource_name = os.getenv(RESOURCE_NAME, "")
    logger.debug(f"Selected resource name: {resource_name}")

    request_method = os.getenv(REQ_METHOD)
    request_url = os.getenv(REQ_URL)
    request_skip_init = os.getenv(REQ_SKIP_INIT, "false").lower() == "true"

    request_payload = os.getenv(REQ_PAYLOAD)
    if request_payload:
        request_payload = prepare_payload(os.getenv(REQ_PAYLOAD))
    script = os.getenv(SCRIPT)

    _initialize_kubeclient_configuration()

    unique_filenames = os.getenv(UNIQUE_FILENAMES)
    if unique_filenames is not None and unique_filenames.lower() == "true":
        logger.info(f"Unique filenames will be enforced.")
        unique_filenames = True
    else:
        logger.info(f"Unique filenames will not be enforced.")
        unique_filenames = False

    enable_5xx = os.getenv(ENABLE_5XX)
    if enable_5xx is not None and enable_5xx.lower() == "true":
        logger.info(f"5xx response content will be enabled.")
        enable_5xx = True
    else:
        logger.info(f"5xx response content will not be enabled.")
        enable_5xx = False

    ignore_already_processed = False
    if os.getenv(IGNORE_ALREADY_PROCESSED) is not None and os.getenv(IGNORE_ALREADY_PROCESSED).lower() == "true":
        # Check API version
        try:
            version = client.VersionApi().get_code()
            # Filter version content and retain only numbers
            v_major = re.sub(r'\D', '', version.major)
            v_minor = re.sub(r'\D', '', version.minor)

            if len(v_major) and len(v_minor) and (int(v_major) > 1 or (int(v_major) == 1 and int(v_minor) >= 19)):
                logger.info("Ignore already processed resource version will be enabled.")
                ignore_already_processed = True
            else:
                logger.info("Can't enable 'ignore already processed resource version', "
                             f"kubernetes api version (%s) is lower than v1.19 or unrecognized format." % version.git_version)

        except ApiException as e:
            logger.error("Exception when calling VersionApi", exc_info=True)

    if not ignore_already_processed:
        logger.debug("Ignore already processed resource version will not be enabled.")

    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as f:
        namespace = os.getenv("NAMESPACE", f.read())

    method = os.getenv(METHOD)
    if method == "LIST":
        for res in resources:
            for ns in namespace.split(','):
                list_resources(label, label_value, target_folder, request_url, request_method, request_payload,
                               ns, folder_annotation, res, unique_filenames, script, enable_5xx,
                               ignore_already_processed, resource_name)
        mark_ready()
    else:
        # For watch/sleep methods, do an initial list first to ensure files are there at startup
        logger.info("Performing initial list-based sync before starting watch.")
        init_request_url = request_url
        if request_skip_init:
            init_request_url = None
            logger.info("Skipping initial request to external endpoint.")
        for res in resources:
            for ns in namespace.split(','):
                # For this initial list, we can set ignore_already_processed to True
                # so the subsequent watch doesn't re-process immediately if that is enabled.
                list_resources(label, label_value, target_folder, init_request_url, request_method, request_payload,
                               ns, folder_annotation, res, unique_filenames, script, enable_5xx,
                               True, resource_name)

        mark_ready()
        logger.info("Initial sync complete, sidecar is ready.")
        watch_for_changes(method, label, label_value, target_folder, request_url, request_method, request_payload,
                          namespace, folder_annotation, resources, unique_filenames, script, enable_5xx,
                          ignore_already_processed, resource_name)
    mark_ready() # After successful initial LIST sync

if __name__ == "__main__":
    main()
