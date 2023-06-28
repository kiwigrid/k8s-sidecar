#!/usr/bin/env python

import os
import re

from kubernetes import client, config
from kubernetes.client import ApiException
from kubernetes.config.kube_config import KUBE_CONFIG_DEFAULT_LOCATION
from requests.packages.urllib3.util.retry import Retry

from helpers import REQ_RETRY_TOTAL, REQ_RETRY_CONNECT, REQ_RETRY_READ, REQ_RETRY_BACKOFF_FACTOR
from logger import get_logger
from resources import watch_for_changes, prepare_payload

METHOD = "METHOD"
UNIQUE_FILENAMES = "UNIQUE_FILENAMES"
SKIP_TLS_VERIFY = "SKIP_TLS_VERIFY"
# FOLDER = "FOLDER"
# FOLDER_ANNOTATION = "FOLDER_ANNOTATION"
LABEL = "LABEL"
LABEL_VALUE = "LABEL_VALUE"
RESOURCE = "RESOURCE"
# REQ_PAYLOAD = "REQ_PAYLOAD"
# REQ_URL = "REQ_URL"
# REQ_METHOD = "REQ_METHOD"
# SCRIPT = "SCRIPT"
# ENABLE_5XX = "ENABLE_5XX"
# IGNORE_ALREADY_PROCESSED = "IGNORE_ALREADY_PROCESSED"

##############################
# Implementation notes:
# - remove the two old implementations (SLEEP and default watch), also secret support is no longer needed
# - add by default 2 workers: 
#   1. full one-way sync (set all rulegroups and remove all rulegroups not backed by resources)
#   2. watch changed configmaps
# - implement fetching label from namespace (_get_namespace_label)
# - implement one-way sync to catch missed events
# - implement similar for alertmanager (use env to select)
# - possible needs retries / backoff
# - 

# Cortex
FUNCTION = "FUNCTION"  # either rules or alerts
X_SCOPE_ORGID_DEFAULT = "X_SCOPE_ORGID_DEFAULT"
X_SCOPE_ORGID_NAMESPACE_LABEL = "X_SCOPE_ORGID_NAMESPACE_LABEL"  # capsule.clastix.io/tenant

# Cortex ruler
RULES_URL = "RULES_URL"  # /api/v1/rules

# Cortex alertmanager
ALERTS_URL = "ALERTS_URL"  # /api/v1/alerts

# Get logger
logger = get_logger()


def main():
    logger.info("Starting collector")

    # folder_annotation = os.getenv(FOLDER_ANNOTATION)
    # if folder_annotation is None:
    #     logger.warning("No folder annotation was provided, "
    #                    "defaulting to k8s-sidecar-target-directory")
    #     folder_annotation = "k8s-sidecar-target-directory"

    label = os.getenv(LABEL)
    if label is None:
        logger.fatal("Should have added {LABEL} as environment variable! Exit")
        return -1

    label_value = os.getenv(LABEL_VALUE)
    if label_value:
        logger.debug(f"Filter labels with value: {label_value}")

    # target_folder = os.getenv(FOLDER)
    # if target_folder is None:
    #     logger.fatal(f"Should have added {FOLDER} as environment variable! Exit")
    #     return -1

    resources = os.getenv(RESOURCE, "configmap")
    resources = ("secret", "configmap") if resources == "both" else (resources,)
    logger.debug(f"Selected resource type: {resources}")

    # request_method = os.getenv(REQ_METHOD)
    # request_url = os.getenv(REQ_URL)
   
    # request_payload = os.getenv(REQ_PAYLOAD)
    # if request_payload:
    #     request_payload = prepare_payload(os.getenv(REQ_PAYLOAD))
    # script = os.getenv(SCRIPT)

    _initialize_kubeclient_configuration()

    unique_filenames = os.getenv(UNIQUE_FILENAMES)
    if unique_filenames is not None and unique_filenames.lower() == "true":
        logger.info(f"Unique filenames will be enforced.")
        unique_filenames = True
    else:
        logger.info(f"Unique filenames will not be enforced.")
        unique_filenames = False

    # enable_5xx = os.getenv(ENABLE_5XX)
    # if enable_5xx is not None and enable_5xx.lower() == "true":
    #     logger.info(f"5xx response content will be enabled.")
    #     enable_5xx = True
    # else:
    #     logger.info(f"5xx response content will not be enabled.")
    #     enable_5xx = False

    function = os.getenv(FUNCTION, "rules")
    x_scope_orgid_default = os.getenv(X_SCOPE_ORGID_DEFAULT, 'system')
    x_scope_orgid_namespace_label = os.getenv(X_SCOPE_ORGID_NAMESPACE_LABEL, 'system')
    rules_url = os.getenv(RULES_URL, None)
    alerts_url = os.getenv(ALERTS_URL, None)

    # ignore_already_processed = False
    # if os.getenv(IGNORE_ALREADY_PROCESSED) is not None and os.getenv(IGNORE_ALREADY_PROCESSED).lower() == "true":
    #     # Check API version
    #     try:
    #         version = client.VersionApi().get_code()
    #         # Filter version content and retain only numbers
    #         v_major = re.sub(r'\D', '', version.major)
    #         v_minor = re.sub(r'\D', '', version.minor)

    #         if len(v_major) and len(v_minor) and (int(v_major) > 1 or (int(v_major) == 1 and int(v_minor) >= 19)):
    #             logger.info("Ignore already processed resource version will be enabled.")
    #             ignore_already_processed = True
    #         else:
    #             logger.info("Can't enable 'ignore already processed resource version', "
    #                          f"kubernetes api version (%s) is lower than v1.19 or unrecognized format." % version.git_version)

    #     except ApiException as e:
    #         logger.error("Exception when calling VersionApi", exc_info=True)

    # if not ignore_already_processed:
    #     logger.debug("Ignore already processed resource version will not be enabled.")

    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as f:
        namespace = os.getenv("NAMESPACE", f.read())

    # method = os.getenv(METHOD)
    # if method == "LIST":
    #     for res in resources:
    #         for ns in namespace.split(','):
    #             list_resources(label, label_value, target_folder, request_url, request_method, request_payload,
    #                            ns, folder_annotation, res, unique_filenames, script, enable_5xx,
    #                            ignore_already_processed)
    # else:
    watch_for_changes(function, label, label_value, rules_url, alerts_url, x_scope_orgid_default, 
                        x_scope_orgid_namespace_label,
                        namespace, resources)


def _initialize_kubeclient_configuration():
    """
    Updates the default configuration of the kubernetes client. This is
    picked up later on automatically then.
    """

    # this is where kube_config is going to look for a config file
    kube_config = os.path.expanduser(KUBE_CONFIG_DEFAULT_LOCATION)
    if os.path.exists(kube_config):
        logger.info(f"Loading config from '{kube_config}'...")
        config.load_kube_config(kube_config)
    else:
        logger.info("Loading incluster config ...")
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

    logger.info(f"Config for cluster api at '{configuration.host}' loaded...")


if __name__ == "__main__":
    main()
