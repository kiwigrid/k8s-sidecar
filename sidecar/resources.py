#!/usr/bin/env python

import base64
import os
import signal
import sys
import traceback
from collections import defaultdict
from multiprocessing import Process
from time import sleep

from kubernetes import client, watch
from kubernetes.client.rest import ApiException
from urllib3.exceptions import MaxRetryError
from urllib3.exceptions import ProtocolError

from helpers import request, write_data_to_file, remove_file, timestamp, unique_filename, CONTENT_TYPE_TEXT, \
    CONTENT_TYPE_BASE64_BINARY, execute

RESOURCE_SECRET = "secret"
RESOURCE_CONFIGMAP = "configmap"

_list_namespace = defaultdict(lambda: {
    RESOURCE_SECRET: "list_namespaced_secret",
    RESOURCE_CONFIGMAP: "list_namespaced_config_map"
}, {'ALL': {
    RESOURCE_SECRET: "list_secret_for_all_namespaces",
    RESOURCE_CONFIGMAP: "list_config_map_for_all_namespaces"
}})


def signal_handler(signum, frame):
    print(f"{timestamp()} Subprocess exiting gracefully")
    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)


def _get_file_data_and_name(full_filename, content, enable_5xx, content_type=CONTENT_TYPE_TEXT):
    if content_type == CONTENT_TYPE_BASE64_BINARY:
        file_data = base64.b64decode(content)
    else:
        file_data = content

    if full_filename.endswith(".url"):
        filename = full_filename[:-4]
        file_data = request(file_data, "GET", enable_5xx).text
    else:
        filename = full_filename

    return filename, file_data


def _get_destination_folder(metadata, default_folder, folder_annotation):
    if metadata.annotations and folder_annotation in metadata.annotations.keys():
        folder_annotation = metadata.annotations[folder_annotation]
        if os.path.isabs(folder_annotation):
            dest_folder = folder_annotation
        else:
            dest_folder = os.path.join(default_folder, folder_annotation)
        print(f"{timestamp()} Found a folder override annotation, "
              f"placing the {metadata.name} in: {dest_folder}")
        return dest_folder
    return default_folder


def list_resources(label, label_value, target_folder, url, method, payload,
                   namespace, folder_annotation, resource, unique_filenames, script, enable_5xx):
    v1 = client.CoreV1Api()
    # Filter resources based on label and value or just label
    label_selector = f"{label}={label_value}" if label_value else label

    additional_args = {
        'label_selector': label_selector
    }
    if namespace != "ALL":
        additional_args['namespace'] = namespace

    ret = getattr(v1, _list_namespace[namespace][resource])(**additional_args)

    files_changed = False

    # For all the found resources
    for item in ret.items:
        metadata = item.metadata

        print(f"{timestamp()} Working on {resource}: {metadata.namespace}/{metadata.name}")

        # Get the destination folder
        dest_folder = _get_destination_folder(metadata, target_folder, folder_annotation)

        if resource == RESOURCE_CONFIGMAP:
            files_changed |= _process_config_map(dest_folder, item, resource, unique_filenames, enable_5xx)
        else:
            files_changed = _process_secret(dest_folder, item, resource, unique_filenames, enable_5xx)

    if script and files_changed:
        execute(script)

    if url and files_changed:
        request(url, method, enable_5xx, payload)


def _process_secret(dest_folder, secret, resource, unique_filenames, enable_5xx, is_removed=False):
    if secret.data is None:
        print(f"{timestamp()} No data field in {resource}")
        return False
    else:
        return _iterate_data(
            secret.data,
            dest_folder,
            secret.metadata,
            resource,
            unique_filenames,
            CONTENT_TYPE_BASE64_BINARY,
            enable_5xx,
            is_removed)


def _process_config_map(dest_folder, config_map, resource, unique_filenames, enable_5xx, is_removed=False):
    files_changed = False
    if config_map.data is None and config_map.binary_data is None:
        print(f"{timestamp()} No data/binaryData field in {resource}")
    if config_map.data is not None:
        files_changed |= _iterate_data(
            config_map.data,
            dest_folder,
            config_map.metadata,
            resource,
            unique_filenames,
            CONTENT_TYPE_TEXT,
            enable_5xx,
            is_removed)
    if config_map.binary_data is not None:
        files_changed |= _iterate_data(
            config_map.binary_data,
            dest_folder,
            config_map.metadata,
            resource,
            unique_filenames,
            CONTENT_TYPE_BASE64_BINARY,
            enable_5xx,
            is_removed)
    return files_changed


def _iterate_data(data, dest_folder, metadata, resource, unique_filenames, content_type, enable_5xx,
                  remove_files=False):
    files_changed = False
    for data_key in data.keys():
        data_content = data[data_key]
        files_changed |= _update_file(
            data_key,
            data_content,
            dest_folder,
            metadata,
            resource,
            unique_filenames,
            content_type,
            enable_5xx,
            remove_files)
    return files_changed


def _update_file(data_key, data_content, dest_folder, metadata, resource,
                 unique_filenames, content_type, enable_5xx, remove=False):
    try:
        filename, file_data = _get_file_data_and_name(data_key,
                                                      data_content,
                                                      enable_5xx,
                                                      content_type)
        if unique_filenames:
            filename = unique_filename(filename=filename,
                                       namespace=metadata.namespace,
                                       resource=resource,
                                       resource_name=metadata.name)
        if not remove:
            return write_data_to_file(dest_folder, filename, file_data, content_type)
        else:
            return remove_file(dest_folder, filename)
    except Exception as e:
        print(f"{timestamp()} Error when updating from ${data_key} into ${dest_folder}: ${e}")
        return False


def _watch_resource_iterator(label, label_value, target_folder, url, method, payload,
                             namespace, folder_annotation, resource, unique_filenames, script, enable_5xx):
    v1 = client.CoreV1Api()
    # Filter resources based on label and value or just label
    label_selector = f"{label}={label_value}" if label_value else label

    additional_args = {
        'label_selector': label_selector
    }
    if namespace != "ALL":
        additional_args['namespace'] = namespace

    stream = watch.Watch().stream(getattr(v1, _list_namespace[namespace][resource]), **additional_args)

    # Process events
    for event in stream:
        item = event["object"]
        metadata = item.metadata
        event_type = event["type"]

        print(f"{timestamp()} Working on {event_type} {resource} {metadata.namespace}/{metadata.name}")

        files_changed = False

        # Get the destination folder
        dest_folder = _get_destination_folder(metadata, target_folder, folder_annotation)

        item_removed = event_type == "DELETED"
        if resource == RESOURCE_CONFIGMAP:
            files_changed |= _process_config_map(dest_folder, item, resource, unique_filenames, enable_5xx,
                                                 item_removed)
        else:
            files_changed |= _process_secret(dest_folder, item, resource, unique_filenames, enable_5xx, item_removed)

        if script and files_changed:
            execute(script)

        if url and files_changed:
            request(url, method, enable_5xx, payload)


def _watch_resource_loop(mode, *args):
    while True:
        try:
            # Always wait to slow down the loop in case of exceptions
            sleep(int(os.getenv("ERROR_THROTTLE_SLEEP", 5)))
            if mode == "SLEEP":
                list_resources(*args)
                sleep(int(os.getenv("SLEEP_TIME", 60)))
            else:
                _watch_resource_iterator(*args)
        except ApiException as e:
            if e.status != 500:
                print(f"{timestamp()} ApiException when calling kubernetes: {e}\n")
            else:
                raise
        except ProtocolError as e:
            print(f"{timestamp()} ProtocolError when calling kubernetes: {e}\n")
        except MaxRetryError as e:
            print(f"{timestamp()} MaxRetryError when calling kubernetes: {e}\n")
        except Exception as e:
            print(f"{timestamp()} Received unknown exception: {e}\n")
            traceback.print_exc()


def watch_for_changes(mode, label, label_value, target_folder, url, method, payload,
                      current_namespace, folder_annotation, resources, unique_filenames, script, enable_5xx):
    processes = _start_watcher_processes(current_namespace, folder_annotation, label,
                                         label_value, method, mode, payload, resources,
                                         target_folder, unique_filenames, script, url, enable_5xx)

    while True:
        died = False
        for proc, ns, resource in processes:
            if not proc.is_alive():
                print(f"{timestamp()} Process for {ns}/{resource} died")
                died = True
        if died:
            print(f"{timestamp()} At least one process died. Stopping and exiting")
            for proc, ns, resource in processes:
                if proc.is_alive():
                    proc.terminate()
            raise Exception("Loop died")

        sleep(5)


def _start_watcher_processes(namespace, folder_annotation, label, label_value, method,
                             mode, payload, resources, target_folder, unique_filenames, script, url, enable_5xx):
    processes = []
    for resource in resources:
        for ns in namespace.split(','):
            proc = Process(target=_watch_resource_loop,
                           args=(mode, label, label_value, target_folder, url, method, payload,
                                 ns, folder_annotation, resource, unique_filenames, script, enable_5xx)
                           )
            proc.daemon = True
            proc.start()
            processes.append((proc, ns, resource))

    return processes
