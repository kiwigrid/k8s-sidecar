#!/usr/bin/env python

import base64
import copy
import os
import signal
import sys
import traceback
import json
import yaml
import requests
from collections import defaultdict
from multiprocessing import Process
from time import sleep

from kubernetes import client, watch
from kubernetes.client.rest import ApiException
from urllib3.exceptions import MaxRetryError, ProtocolError

from helpers import (CONTENT_TYPE_BASE64_BINARY, CONTENT_TYPE_TEXT,
                     WATCH_CLIENT_TIMEOUT, WATCH_SERVER_TIMEOUT, execute,
                     remove_file, request, unique_filename, write_data_to_file)
from helpers import request_delete, request_post
from logger import get_logger

RESOURCE_SECRET = "secret"
RESOURCE_CONFIGMAP = "configmap"

_list_namespace = defaultdict(lambda: {
    RESOURCE_SECRET: "list_namespaced_secret",
    RESOURCE_CONFIGMAP: "list_namespaced_config_map"
}, {'ALL': {
    RESOURCE_SECRET: "list_secret_for_all_namespaces",
    RESOURCE_CONFIGMAP: "list_config_map_for_all_namespaces"
}})

_resources_version_map = {
    RESOURCE_SECRET: {},
    RESOURCE_CONFIGMAP: {},
}
_resources_object_map = {
    RESOURCE_SECRET: {},
    RESOURCE_CONFIGMAP: {},
}
_resources_dest_folder_map = {
    RESOURCE_SECRET: {},
    RESOURCE_CONFIGMAP: {},
}

# Get logger
logger = get_logger()


def signal_handler(signum, frame):
    logger.info("Subprocess exiting gracefully")
    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)

def prepare_payload(payload):
    """Prepare payload as dict for request."""
    try:
       payload_dict = json.loads(payload)
       return payload_dict
    except ValueError as err:
        logger.warning(f"Payload will be posted as quoted json")
        return payload

# def _get_file_data_and_name(full_filename, content, enable_5xx, content_type=CONTENT_TYPE_TEXT):
#     if content_type == CONTENT_TYPE_BASE64_BINARY:
#         file_data = base64.b64decode(content)
#     else:
#         file_data = content

#     if full_filename.endswith(".url"):
#         filename = full_filename[:-4]
#         if content_type == CONTENT_TYPE_BASE64_BINARY:
#             file_url = file_data.decode('utf8')
#             file_data = request(file_url, "GET", enable_5xx).content
#         else:
#             file_data = request(file_data, "GET", enable_5xx).text
#     else:
#         filename = full_filename

#     return filename, file_data


# def _get_destination_folder(metadata, default_folder, folder_annotation):
#     if metadata.annotations and folder_annotation in metadata.annotations.keys():
#         folder_annotation = metadata.annotations[folder_annotation]
#         if os.path.isabs(folder_annotation):
#             dest_folder = folder_annotation
#         else:
#             dest_folder = os.path.join(default_folder, folder_annotation)
#         logger.info(f"Found a folder override annotation, "
#                     f"placing the {metadata.name} in: {dest_folder}")
#         return dest_folder
#     return default_folder


# def list_resources(label, label_value, target_folder, rest_endpoint_conf, request_url, request_method, request_payload,
#                    namespace, folder_annotation, resource, unique_filenames, script, enable_5xx,
#                    ignore_already_processed):
#     v1 = client.CoreV1Api()
#     # Filter resources based on label and value or just label
#     label_selector = f"{label}={label_value}" if label_value else label

#     additional_args = {
#         'label_selector': label_selector
#     }
#     if namespace != "ALL":
#         additional_args['namespace'] = namespace

#     logger.info(f"Performing list-based sync on {resource} resources: {additional_args}")

#     ret = getattr(v1, _list_namespace[namespace][resource])(**additional_args)

#     files_changed = False
#     exist_keys = set()

#     # For all the found resources
#     for item in ret.items:
#         metadata = item.metadata
#         exist_keys.add(metadata.namespace + metadata.name)

#         # Ignore already processed resource
#         # Avoid numerous logs about useless resource processing each time the LIST loop reconnects
#         if ignore_already_processed:
#             if _resources_version_map[resource].get(metadata.namespace + metadata.name) == metadata.resource_version:
#                 logger.debug(f"Ignoring {resource} {metadata.namespace}/{metadata.name}")
#                 continue

#             _resources_version_map[resource][metadata.namespace + metadata.name] = metadata.resource_version

#         logger.debug(f"Working on {resource}: {metadata.namespace}/{metadata.name}")

#         # Get the destination folder
#         dest_folder = _get_destination_folder(metadata, target_folder, folder_annotation)

#         if resource == RESOURCE_CONFIGMAP:
#             files_changed |= _process_config_map(dest_folder, item, resource, unique_filenames, enable_5xx)
#         else:
#             files_changed = _process_secret(dest_folder, item, resource, unique_filenames, enable_5xx)

#     # Clear the cache that is not listed.
#     for key in set(_resources_object_map[resource].keys()) - exist_keys:
#         item = _resources_object_map[resource].get(key)
#         metadata = item.metadata

#         logger.debug(f"Removing {resource}: {metadata.namespace}/{metadata.name}")

#         if resource == RESOURCE_CONFIGMAP:
#             files_changed |= _process_config_map(None, item, resource, unique_filenames, enable_5xx, True)
#         else:
#             files_changed = _process_secret(None, item, resource, unique_filenames, enable_5xx, True)

#     if script and files_changed:
#         execute(script)

#     if request_url and files_changed:
#         request(request_url, request_method, enable_5xx, request_payload)


# def _process_secret(dest_folder, secret, resource, unique_filenames, enable_5xx, is_removed=False):
#     files_changed = False

#     old_secret = _resources_object_map[resource].get(secret.metadata.namespace + secret.metadata.name) or copy.deepcopy(secret)
#     old_dest_folder = _resources_dest_folder_map[resource].get(secret.metadata.namespace + secret.metadata.name) or dest_folder
#     if is_removed:
#         _resources_object_map[resource].pop(secret.metadata.namespace + secret.metadata.name, None)
#     else:
#         _resources_object_map[resource][secret.metadata.namespace + secret.metadata.name] = copy.deepcopy(secret)
#         _resources_dest_folder_map[resource][secret.metadata.namespace + secret.metadata.name] = dest_folder

#     if secret.data is None:
#         logger.warning(f"No data field in {resource}")

#     if secret.data is not None:
#         files_changed |= _iterate_data(
#             secret.data,
#             dest_folder,
#             secret.metadata,
#             resource,
#             unique_filenames,
#             CONTENT_TYPE_BASE64_BINARY,
#             enable_5xx,
#             is_removed)
#     if old_secret.data is not None and not is_removed:
#         if old_dest_folder == dest_folder:
#             for key in set(old_secret.data.keys()) & set(secret.data or {}):
#                 old_secret.data.pop(key)
#         files_changed |= _iterate_data(
#             old_secret.data,
#             old_dest_folder,
#             old_secret.metadata,
#             resource,
#             unique_filenames,
#             CONTENT_TYPE_BASE64_BINARY,
#             enable_5xx,
#             True)
#     return files_changed


# def _process_config_map(dest_folder, config_map, resource, unique_filenames, enable_5xx, is_removed=False):
#     files_changed = False

#     old_config_map = _resources_object_map[resource].get(config_map.metadata.namespace + config_map.metadata.name) or copy.deepcopy(config_map)
#     old_dest_folder = _resources_dest_folder_map[resource].get(config_map.metadata.namespace + config_map.metadata.name) or dest_folder
#     if is_removed:
#         _resources_object_map[resource].pop(config_map.metadata.namespace + config_map.metadata.name, None)
#     else:
#         _resources_object_map[resource][config_map.metadata.namespace + config_map.metadata.name] = copy.deepcopy(config_map)
#         _resources_dest_folder_map[resource][config_map.metadata.namespace + config_map.metadata.name] = dest_folder

#     if config_map.data is None and config_map.binary_data is None:
#         logger.warning(f"No data/binaryData field in {resource}")

#     if config_map.data is not None:
#         logger.debug(f"Found 'data' on {resource}")
#         files_changed |= _iterate_data(
#             config_map.data,
#             dest_folder,
#             config_map.metadata,
#             resource,
#             unique_filenames,
#             CONTENT_TYPE_TEXT,
#             enable_5xx,
#             is_removed)
#     if old_config_map.data is not None and not is_removed:
#         if old_dest_folder == dest_folder:
#             for key in set(old_config_map.data.keys()) & set(config_map.data or {}):
#                 old_config_map.data.pop(key)
#         files_changed |= _iterate_data(
#             old_config_map.data,
#             old_dest_folder,
#             old_config_map.metadata,
#             resource,
#             unique_filenames,
#             CONTENT_TYPE_TEXT,
#             enable_5xx,
#             True)
#     if config_map.binary_data is not None:
#         logger.debug(f"Found 'binary_data' on {resource}")
#         files_changed |= _iterate_data(
#             config_map.binary_data,
#             dest_folder,
#             config_map.metadata,
#             resource,
#             unique_filenames,
#             CONTENT_TYPE_BASE64_BINARY,
#             enable_5xx,
#             is_removed)
#     if old_config_map.binary_data is not None and not is_removed:
#         if old_dest_folder == dest_folder:
#             for key in set(old_config_map.binary_data.keys()) & set(config_map.binary_data or {}):
#                 old_config_map.binary_data.pop(key)
#         files_changed |= _iterate_data(
#             old_config_map.binary_data,
#             old_dest_folder,
#             old_config_map.metadata,
#             resource,
#             unique_filenames,
#             CONTENT_TYPE_BASE64_BINARY,
#             enable_5xx,
#             True)
#     return files_changed


# def _iterate_data(data, dest_folder, metadata, resource, unique_filenames, content_type, enable_5xx,
#                   remove_files=False):
#     files_changed = False
#     for data_key in data.keys():
#         data_content = data[data_key]
#         files_changed |= _update_file(
#             data_key,
#             data_content,
#             dest_folder,
#             metadata,
#             resource,
#             unique_filenames,
#             content_type,
#             enable_5xx,
#             remove_files)
#     return files_changed


# def _update_file(data_key, data_content, dest_folder, metadata, resource,
#                  unique_filenames, content_type, enable_5xx, remove=False):
#     try:
#         filename, file_data = _get_file_data_and_name(data_key,
#                                                       data_content,
#                                                       enable_5xx,
#                                                       content_type)
#         if unique_filenames:
#             filename = unique_filename(filename=filename,
#                                        namespace=metadata.namespace,
#                                        resource=resource,
#                                        resource_name=metadata.name)
#         if not remove:
#             return write_data_to_file(dest_folder, filename, file_data, content_type)
#         else:
#             return remove_file(dest_folder, filename)
#     except Exception:
#         logger.exception(f"Error when updating from '%s' into '%s'", data_key, dest_folder)
#         return False

def _get_namespace_label(v1, namespace, label, default):
    # prevent fetching all namespaces; so a filter on name is required
    ns = v1.list_namespace(field_selector=f'metadata.name={namespace}').items[0]
    value = ns.metadata.labels.get(label, default)
    logger.info(f'get label {label} for namespace {namespace}: {value}')
    return value


def _watch_resource_iterator(function, label, label_value, rules_url, alerts_url, x_scope_orgid_default, 
                        x_scope_orgid_namespace_label, 
                             namespace, resource):
    v1 = client.CoreV1Api()
    # Filter resources based on label and value or just label
    label_selector = f"{label}={label_value}" if label_value else label

    additional_args = {
        'label_selector': label_selector,
        'timeout_seconds': WATCH_SERVER_TIMEOUT,
        '_request_timeout': WATCH_CLIENT_TIMEOUT,
    }
    if namespace != "ALL":
        additional_args['namespace'] = namespace

    logger.info(f"Performing watch-based sync on {resource} resources: {additional_args}")
    # logger.info(f"Watch {_list_namespace[namespace][resource]}")

    stream = watch.Watch().stream(getattr(v1, _list_namespace[namespace][resource]), **additional_args)

    # Process events
    for event in stream:
        item = event['object']
        metadata = item.metadata
        event_type = event['type']

        # rules
        if function == "rules":
            for key in item.data.keys():
                document = yaml.load(item.data[key], Loader=yaml.Loader)
                for group in document['groups']:
                    if event_type == "DELETED":
                        headers = {
                            'X-Scope-OrgID': _get_namespace_label(v1, metadata.namespace, x_scope_orgid_namespace_label, x_scope_orgid_default),
                        }
                        url = f'{rules_url}/{metadata.namespace}/{group["name"]}'
                        response = request_delete(url, headers)

                    else:  # ADDED / MODIFIED
                        headers = {
                            'Content-Type': 'application/yaml',
                            'X-Scope-OrgID': _get_namespace_label(v1, metadata.namespace, x_scope_orgid_namespace_label, x_scope_orgid_default),
                        }
                        payload = {
                            'name': group["name"],
                            'rules': group["rules"],
                        }
                        url = f'{rules_url}/{metadata.namespace}'
                        response = request_post(url, headers, yaml.dump(payload))
        else:  # alerts
            for key in item.data.keys():
                if event_type == "DELETED":
                    headers = {
                        'X-Scope-OrgID': _get_namespace_label(v1, metadata.namespace, x_scope_orgid_namespace_label, x_scope_orgid_default),
                    }
                    url = f'{alerts_url}'
                    response = request_delete(url, headers)

                else:  # ADDED / MODIFIED
                    headers = {
                        'Content-Type': 'application/yaml',
                        'X-Scope-OrgID': _get_namespace_label(v1, metadata.namespace, x_scope_orgid_namespace_label, x_scope_orgid_default),
                    }
                    payload = {
                        'alertmanager_config': item.data[key]
                    }
                    url = f'{alerts_url}'
                    response = request_post(url, headers, yaml.dump(payload))

        # # Ignore already processed resource
        # # Avoid numerous logs about useless resource processing each time the WATCH loop reconnects
        # if ignore_already_processed:
        #     if _resources_version_map[resource].get(metadata.namespace + metadata.name) == metadata.resource_version:
        #         if event_type == "ADDED" or event_type == "MODIFIED":
        #             logger.debug(f"Ignoring {event_type} {resource} {metadata.namespace}/{metadata.name}")
        #             continue
        #         elif event_type == "DELETED":
        #             _resources_version_map[resource].pop(metadata.namespace + metadata.name)

        #     if event_type == "ADDED" or event_type == "MODIFIED":
        #         _resources_version_map[resource][metadata.namespace + metadata.name] = metadata.resource_version

        # logger.debug(f"Working on {event_type} {resource} {metadata.namespace}/{metadata.name}")

        # files_changed = False

        # # Get the destination folder
        # dest_folder = _get_destination_folder(metadata, target_folder, folder_annotation)

        # item_removed = event_type == "DELETED"
        # if resource == RESOURCE_CONFIGMAP:
        #     files_changed |= _process_config_map(dest_folder, item, resource, unique_filenames, enable_5xx,
        #                                          item_removed)
        # else:
        #     files_changed |= _process_secret(dest_folder, item, resource, unique_filenames, enable_5xx, item_removed)

        # if script and files_changed:
        #     execute(script)

        # if request_url and files_changed:
        #     request(request_url, request_method, enable_5xx, request_payload)


def _watch_resource_loop(*args):
    while True:
        try:
            # Always wait to slow down the loop in case of exceptions
            sleep(int(os.getenv("ERROR_THROTTLE_SLEEP", 5)))
            # if mode == "SLEEP":
            #     list_resources(*args)
            #     sleep(int(os.getenv("SLEEP_TIME", 60)))
            # else:
            _watch_resource_iterator(*args)
        except ApiException as e:
            if e.status != 500:
                logger.error(f"ApiException when calling kubernetes: {e}\n")
            else:
                raise
        except ProtocolError as e:
            logger.error(f"ProtocolError when calling kubernetes: {e}\n")
        except MaxRetryError as e:
            logger.error(f"MaxRetryError when calling kubernetes: {e}\n")
        except Exception as e:
            logger.error(f"Received unknown exception: {e}\n")
            traceback.print_exc()

def _sync(*args):
    while True:
        try:
            logger.info(f"Sync back rest api state")
            # __sync__(*args)
            # Cleanup content at the REST endpoint when resources no longer exist
            # 1. Fetch all rules/alerts definitions from the LHS (ConfigMaps) (upstream)
            # 2. process all of them (iterate + post the content to the rest endpoint)
            # 3. List all rules/alerts from the RHS (rest endpoint)
            # 4. Remove all rules (groups) or alerts that no longer are present on the LHS (Configmaps / local administration)
            sleep(int(os.getenv("SYNC_SLEEP", 60)))
        except Exception as e:
            logger.exception(f"Exception caught: {e}\n")
            traceback.print_exc()


def watch_for_changes(function, label, label_value, rules_url, alerts_url, x_scope_orgid_default, 
                      x_scope_orgid_namespace_label, 
                      current_namespace, resources):
    processes = _start_watcher_processes(function, current_namespace, label,
                                         label_value, resources,
                                         rules_url, alerts_url, x_scope_orgid_default, 
                        x_scope_orgid_namespace_label)

    while True:
        died = False
        for proc, ns, resource in processes:
            if not proc.is_alive():
                logger.fatal(f"Process for {ns}/{resource} died")
                died = True
        if died:
            logger.fatal("At least one process died. Stopping and exiting")
            for proc, ns, resource in processes:
                if proc.is_alive():
                    proc.terminate()
            raise Exception("Loop died")

        sleep(5)


def _start_watcher_processes(function, namespace, label, label_value, resources, 
            rules_url, alerts_url, x_scope_orgid_default, 
            x_scope_orgid_namespace_label):
    """
    Watch configmap resources for changes and update accordingly
    -and-
    Run a full one-way sync every n seconds (to catch missed events for instance after upgrading)
    """
    processes = []
    for resource in resources:
        for ns in namespace.split(','):
            proc = Process(target=_watch_resource_loop,
                           args=(function, label, label_value, rules_url, alerts_url, x_scope_orgid_default, 
                        x_scope_orgid_namespace_label, 
                                 ns, resource)
                           )
            proc.daemon = True
            proc.start()
            processes.append((proc, ns, resource))
            proc_sync = Process(target=_sync,
                           args=(function, label, label_value, rules_url, alerts_url, x_scope_orgid_default, 
                        x_scope_orgid_namespace_label, 
                                 ns, resource)
                           )
            proc_sync.daemon = True
            proc_sync.start()
            processes.append((proc_sync, ns, resource))

    return processes
