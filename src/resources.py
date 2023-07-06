#!/usr/bin/env python

import base64
import copy
import os
import signal
import sys
import traceback
import json
import yaml
import pprint
from collections import defaultdict
from multiprocessing import Process
from time import sleep
from kubernetes import client, watch
from kubernetes.client.rest import ApiException
from urllib3.exceptions import MaxRetryError, ProtocolError

from helpers import (CONTENT_TYPE_BASE64_BINARY, CONTENT_TYPE_TEXT,
                     WATCH_CLIENT_TIMEOUT, WATCH_SERVER_TIMEOUT, execute,
                     remove_file, request, unique_filename, write_data_to_file)
from helpers import request_get, request_delete, request_post
from logger import get_logger

RESOURCE_SECRET = "secret"
RESOURCE_CONFIGMAP = "configmap"

_list_namespace = defaultdict(
    lambda: {
        RESOURCE_SECRET: "list_namespaced_secret",
        RESOURCE_CONFIGMAP: "list_namespaced_config_map"
    },
    {
        'ALL': {
            RESOURCE_SECRET: "list_secret_for_all_namespaces",
            RESOURCE_CONFIGMAP: "list_config_map_for_all_namespaces"
        }
    }
)

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

def _del_rulegroup(namespace, orgid, rules_url, rulegroup_name):
    headers = {'X-Scope-OrgID': orgid}

    url = f'{rules_url}/{namespace}/{rulegroup_name}'
    logger.info(f"RULER DEL - namespace: {namespace}, group: {rulegroup_name}, url: {url}")
    request_delete(url, headers)


def _set_rulegroup(namespace, orgid, rules_url, rulegroup_name, rulegroup_content):
    headers = {
        'Content-Type': 'application/yaml',
        'X-Scope-OrgID': orgid,
    }

    payload = {
        'name': rulegroup_name,
        'rules': rulegroup_content,
    }

    url = f'{rules_url}/{namespace}'
    logger.info(f"RULER SET - namespace: {namespace}, group: {rulegroup_name}, url: {url}")
    request_post(url, headers, yaml.dump(payload))


def _del_alertmanager_config(orgid, alerts_url):
    headers = {'X-Scope-OrgID': orgid}
    logger.info(f"ALERTMANAGER DEL - url: {alerts_url}")
    request_delete(alerts_url, headers)


def _set_alertmanager_config(orgid, alerts_url, alertmanager_config):
    headers = {'X-Scope-OrgID': orgid}
    payload = yaml.dump(alertmanager_config).replace("\n", "\n  ")
    payload = f"alertmanager_config: |\n  {payload}"
    logger.info(f"ALERTMANAGER SET - url: {alerts_url} headers: {headers}, payload: {payload}")
    request_post(alerts_url, headers, payload)


def _get_cortex_alertmanager_list(alerts_url, orgid):
    headers = {'X-Scope-OrgID': orgid}

    logger.info(f"ALERTMANAGER SYNC - CORTEX list: url: {alerts_url}, headers: {headers}")
    response = request_get(alerts_url, headers=headers)
    logger.info(f"ALERTMANAGER SYNC - CORTEX list: response: {response}")

    if "alertmanager storage object not found" in response.text:
        return {}
    else:
        content = response.content.decode("utf-8")
        content = yaml.safe_load(content)
        logger.info(f"ALERTMANAGER SYNC - CORTEX list content: {content}")

        return {orgid: content}


def _get_cortex_rulegroups_list(namespace_label, rules_url):
    headers = {'X-Scope-OrgID': namespace_label}

    logger.info(f"RULER SYNC - CORTEX list rules: url: {rules_url}, headers: {headers}")
    response = request_get(rules_url, headers=headers)
    logger.info(f"RULER SYNC - CORTEX list rules response: {response}")

    if "no rule groups found" in response.text:
        return {}
    else:
        content = response.content.decode("utf-8")
        content = yaml.safe_load(content)
        logger.info(f"RULER SYNC - CORTEX list rules content: {content}")

        return content


def _watch_configmap_resources(v1, label, label_value, namespace, resource):
    # Filter resources based on label and value or just label
    label_selector = f"{label}={label_value}" if label_value else label

    additional_args = {
        'label_selector': label_selector,
        'timeout_seconds': WATCH_SERVER_TIMEOUT,
        '_request_timeout': WATCH_CLIENT_TIMEOUT,
    }

    if namespace != "ALL":
        additional_args['namespace'] = namespace

    value = watch.Watch().stream(getattr(v1, _list_namespace[namespace][resource]), **additional_args)

    logger.info(f"Configmap loaded from {resource} resources: {additional_args}")
    return value


def _get_namespace_label(v1, namespace, label, default):
    # prevent fetching all namespaces; so a filter on name is required
    ns = v1.list_namespace(field_selector=f'metadata.name={namespace}').items[0]
    value = ns.metadata.labels.get(label, default)
    logger.info(f'get label {label} for namespace {namespace}: {value}')
    return value


def _watch_resource_iterator(function, label, label_value, rules_url, alerts_url, x_scope_orgid_default,
                        x_scope_orgid_namespace_label, namespace, resource):
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


def _get_namespace_labels(v1, x_scope_orgid_namespace_label):
    logger.info(f"SYNC - label_selector: {x_scope_orgid_namespace_label}")
    namespaces = v1.list_namespace(label_selector=x_scope_orgid_namespace_label)

    namespace_labels = []
    for namespace in namespaces.items:
        logger.info(f"SYNC - NAMESPACE NAME: {namespace.metadata.name}")
        logger.info(f"SYNC - NAMESPACE LABEL: {namespace.metadata.labels[x_scope_orgid_namespace_label]}")
        namespace_labels.append({namespace.metadata.name: namespace.metadata.labels[x_scope_orgid_namespace_label]})

    logger.info(f"SYNC - NAMESPACE LABELS: {namespace_labels}")

    return namespace_labels


def _get_alertmanager_from_configmaps(v1, namespace_label, orgid):
    alertmanager_dict_configmap = {}
    alertmanager_dict_configmap[orgid] = {}
    configmap = v1.list_namespaced_config_map(namespace_label, label_selector='cortex/alertmanager-config').items

    if configmap and configmap is not None:
        for configmap_item in configmap:
            if configmap_item.data.keys():
                for file in configmap_item.data.keys():
                    alertmanager_dict_configmap[orgid][file] = {}
                    configmap_document = yaml.load(configmap_item.data[file], Loader=yaml.Loader)
                    if configmap_document:
                        alertmanager_dict_configmap[orgid][file]["alertmanager_config"] = configmap_document
                    else:
                        alertmanager_dict_configmap[orgid][file]["alertmanager_config"] = {}
            else:
                alertmanager_dict_configmap[orgid] = {}

    logger.info(f"ALERTMANAGER SYNC - CONFIGMAP content: {pprint.pformat(alertmanager_dict_configmap)}")

    return alertmanager_dict_configmap


def _get_rulegroups_from_configmaps(v1, namespace_label):
    rulegroup_dict_configmap = {}
    configmap = v1.list_namespaced_config_map(namespace_label, label_selector='cortex/rules').items
    if configmap and configmap is not None:
        for configmap_item in configmap:
            logger.info(f"RULER SYNC - CONFIGMAP ITEM DATA: {configmap_item.data}")
            logger.info(f"RULER SYNC - CONFIGMAP ITEM METADATA: {configmap_item.metadata}")
            rulegroup_dict_configmap[namespace_label] = {}
            if configmap_item.data.keys():
                for key in configmap_item.data.keys():
                    rulegroup_dict_configmap[namespace_label][key] = {}
                    configmap_document = yaml.load(configmap_item.data[key], Loader=yaml.Loader)
                    logger.info(f"RULER SYNC - CONFIGMAP DOC: {configmap_document}")
                    logger.info(f"RULER SYNC - CONFIGMAP DOC KEYS: {configmap_document.keys()}")
                    if 'groups' in configmap_document.keys() and configmap_document['groups'] is not None:
                        rulegroup_dict_configmap[namespace_label] = {}
                        for configmap_group in configmap_document['groups']:
                            logger.info(f"RULER SYNC - CONFIGMAP namespace_label: {namespace_label}")
                            logger.info(f"RULER SYNC - CONFIGMAP rulegroup name: {configmap_group['name']}")
                            logger.info(f"RULER SYNC - CONFIGMAP rulegroup content: {pprint.pformat(configmap_group['rules'])}")
                            rulegroup_dict_configmap[namespace_label][configmap_group['name']] = configmap_group['rules']

    logger.info(f"RULER SYNC - CONFIGMAP rulegroup dict: {pprint.pformat(rulegroup_dict_configmap)}")

    return rulegroup_dict_configmap


def _get_rulegroups_from_cortex(rules_url, namespace_label, x_scope_orgid_default, namespace):
    rulegroup_dict_cortex = {}
    logger.info(f"RULER SYNC - CORTEX {namespace_label} {x_scope_orgid_default} {namespace}")

    cortex_rulegroups = _get_cortex_rulegroups_list(namespace_label, rules_url)
    logger.info(f"RULER SYNC - CORTEX rulegroup list: {cortex_rulegroups}")
    for cortex_namespace in cortex_rulegroups:
        logger.info(f"RULER SYNC - CORTEX namespace: {cortex_namespace}")
        rulegroup_dict_cortex[cortex_namespace] = {}
        for cortex_rulegroup in cortex_rulegroups[cortex_namespace]:
            logger.info(f"RULER SYNC - CORTEX rulegroup: {cortex_rulegroup['name']}")
            logger.info(f"RULER SYNC - CORTEX rulegroup: {pprint.pformat(cortex_rulegroup['rules'])}")
            rulegroup_dict_cortex[cortex_namespace][cortex_rulegroup['name']] = cortex_rulegroup['rules']

    logger.info(f"RULER SYNC - CORTEX rulegroup dict: {pprint.pformat(rulegroup_dict_cortex)}")

    return rulegroup_dict_cortex


def _watch_resource_loop(*args):
    while True:
        try:
            # Always wait to slow down the loop in case of exceptions
            sleep(int(os.getenv("ERROR_THROTTLE_SLEEP", 5)))
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


def rulegroup_equalize(namespace, orgid, rulegroup_dict_configmap, rulegroup_dict_cortex, rules_url):
    if namespace in rulegroup_dict_configmap:
        for rulegroup_configmap in rulegroup_dict_configmap[namespace]:
            if not namespace in rulegroup_dict_cortex or \
                    not rulegroup_configmap in rulegroup_dict_cortex[namespace] or \
                    not rulegroup_dict_configmap[namespace][rulegroup_configmap] == rulegroup_dict_cortex[namespace][rulegroup_configmap]:
                _set_rulegroup(namespace, orgid, rules_url, rulegroup_configmap, rulegroup_dict_configmap[namespace][rulegroup_configmap])

    if namespace in rulegroup_dict_cortex:
        for rulegroup_cortex in rulegroup_dict_cortex[namespace]:
            if namespace not in rulegroup_dict_configmap or not rulegroup_cortex in rulegroup_dict_configmap[namespace]:
                _del_rulegroup(namespace, orgid, rules_url, rulegroup_cortex)


def alertmanager_equalize(orgid, alertmanager_dict_configmap, alertmanager_dict_cortex, alerts_url):

    if str(orgid) in alertmanager_dict_configmap:

        for file in alertmanager_dict_configmap[orgid]:
            if str(orgid) in alertmanager_dict_cortex:
                if not alertmanager_dict_configmap[orgid][file]['alertmanager_config'] \
                        and alertmanager_dict_cortex[orgid]['alertmanager_config']:
                    _del_alertmanager_config(orgid, alerts_url)
                elif alertmanager_dict_cortex[orgid]['alertmanager_config'] \
                        and not alertmanager_dict_cortex[orgid]['alertmanager_config']:
                    _set_alertmanager_config(orgid, alerts_url, alertmanager_dict_configmap[orgid][file]['alertmanager_config'])
                elif alertmanager_dict_configmap[orgid][file]['alertmanager_config'] \
                        != yaml.load(alertmanager_dict_cortex[orgid]['alertmanager_config'], Loader=yaml.Loader):
                    _set_alertmanager_config(orgid, alerts_url, alertmanager_dict_configmap[orgid][file]['alertmanager_config'])
            else:
                if alertmanager_dict_configmap[orgid][file]['alertmanager_config']:
                    _set_alertmanager_config(orgid, alerts_url, alertmanager_dict_configmap[orgid][file]['alertmanager_config'])
            #TODO if not alertmanager_dict_configmap[orgid][file] == yaml.load(alertmanager_dict_cortex[orgid]['template_files'], Loader=yaml.Loader):


    if str(orgid) in alertmanager_dict_cortex:
        if orgid not in alertmanager_dict_configmap:
            _del_alertmanager_config(orgid, alerts_url)


def _sync_alertmanager(v1, function, label, label_value, rules_url, alerts_url, x_scope_orgid_default,
                        x_scope_orgid_namespace_label, namespace, resource):
    namespace_labels = _get_namespace_labels(v1, x_scope_orgid_namespace_label)

    for namespace_label in namespace_labels:
        namespace_name = list(namespace_label.keys())[0]
        orgid = list(namespace_label.values())[0]

        alertmanager_dict_configmap = _get_alertmanager_from_configmaps(v1, namespace_name, orgid)
        alertmanager_dict_cortex = _get_cortex_alertmanager_list(alerts_url, orgid)

        alertmanager_equalize(orgid, alertmanager_dict_configmap, alertmanager_dict_cortex, alerts_url)


def _sync_ruler(v1, function, label, label_value, rules_url, alerts_url, x_scope_orgid_default,
                        x_scope_orgid_namespace_label, namespace, resource):
    namespace_labels = _get_namespace_labels(v1, x_scope_orgid_namespace_label)

    for namespace_label in namespace_labels:
        namespace_name = list(namespace_label.keys())[0]
        orgid = list(namespace_label.values())[0]

        rulegroup_dict_configmap = _get_rulegroups_from_configmaps(v1, namespace_name)
        rulegroup_dict_cortex = _get_rulegroups_from_cortex(rules_url, orgid, x_scope_orgid_default, namespace)

        rulegroup_equalize(namespace_name, orgid, rulegroup_dict_configmap, rulegroup_dict_cortex, rules_url)


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
            v1 = client.CoreV1Api()
            #_sync_ruler(v1, *args)
            _sync_alertmanager(v1, *args)
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
            #proc = Process(target=_watch_resource_loop,
            #               args=(function, label, label_value, rules_url, alerts_url, x_scope_orgid_default,
            #            x_scope_orgid_namespace_label,
            #                     ns, resource)
            #               )
            #proc.daemon = True
            #proc.start()
            #processes.append((proc, ns, resource))
            proc_sync = Process(target=_sync,
                           args=(function, label, label_value, rules_url, alerts_url, x_scope_orgid_default,
                        x_scope_orgid_namespace_label,
                                 ns, resource)
                           )
            proc_sync.daemon = True
            proc_sync.start()
            processes.append((proc_sync, ns, resource))

    return processes
