#!/usr/bin/env python

import base64
import os
import signal
import sys
from multiprocessing import Process
from time import sleep

from kubernetes import client, watch
from kubernetes.client.rest import ApiException
from urllib3.exceptions import MaxRetryError
from urllib3.exceptions import ProtocolError

from helpers import request, write_text_to_file, remove_file, timestamp, unique_filename

_list_namespaced = {
    "secret": "list_namespaced_secret",
    "configmap": "list_namespaced_config_map"
}


def signal_handler(signum, frame):
    print(f"{timestamp()} Subprocess exiting gracefully")
    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)

_list_for_all_namespaces = {
    "secret": "list_secret_for_all_namespaces",
    "configmap": "list_config_map_for_all_namespaces"
}


def _get_file_data_and_name(full_filename, content, resource, content_type="ascii"):
    if resource == "secret":
        file_data = base64.b64decode(content).decode()
    elif content_type == "binary":
        file_data = base64.decodebytes(content.encode('ascii'))
    else:
        file_data = content

    if full_filename.endswith(".url"):
        filename = full_filename[:-4]
        file_data = request(file_data, "GET").text
    else:
        filename = full_filename

    return filename, file_data


def _get_destination_folder(metadata, default_folder, folder_annotation):
    if metadata.annotations and folder_annotation in metadata.annotations.keys():
        dest_folder = metadata.annotations[folder_annotation]
        print(f"{timestamp()} Found a folder override annotation, "
              f"placing the {metadata.name} in: {dest_folder}")
        return dest_folder
    return default_folder


def list_resources(label, label_value, target_folder, url, method, payload,
                   current_namespace, folder_annotation, resource, unique_filenames):
    v1 = client.CoreV1Api()
    namespace = os.getenv("NAMESPACE", current_namespace)
    # Filter resources based on label and value or just label
    label_selector = f"{label}={label_value}" if label_value else label

    if namespace == "ALL":
        ret = getattr(v1, _list_for_all_namespaces[resource])(label_selector=label_selector)
    else:
        ret = getattr(v1, _list_namespaced[resource])(namespace=namespace, label_selector=label_selector)

    files_changed = False

    # For all the found resources
    for sec in ret.items:
        metadata = sec.metadata

        print(f"{timestamp()} Working on {resource}: {metadata.namespace}/{metadata.name}")

        # Get the destination folder
        dest_folder = _get_destination_folder(metadata, target_folder, folder_annotation)

        # Check if it's an empty ConfigMap or Secret
        if resource == "configmap":
            if sec.data is None and sec.binary_data is None:
                print(f"{timestamp()} No data/binaryData field in {resource}")
                continue
        else:
            if sec.data is None:
                print(f"{timestamp()} No data field in {resource}")
                continue

        # Each key on the data is a file
        if sec.data is not None:
            for data_key in sec.data.keys():
                filename, file_data = _get_file_data_and_name(data_key,
                                                              sec.data[data_key],
                                                              resource)
                if unique_filenames:
                    filename = unique_filename(filename=filename,
                                               namespace=metadata.namespace,
                                               resource=resource,
                                               resource_name=metadata.name)

                files_changed |= write_text_to_file(dest_folder, filename, file_data)

        # Each key on the binaryData is a file
        if resource == "configmap" and sec.binary_data is not None:
            for data_key in sec.binary_data.keys():
                filename, file_data = _get_file_data_and_name(data_key,
                                                              sec.binary_data[data_key],
                                                              resource,
                                                              content_type="binary")
                if unique_filenames:
                    filename = unique_filename(filename=filename,
                                               namespace=metadata.namespace,
                                               resource=resource,
                                               resource_name=metadata.name)

                files_changed |= write_text_to_file(dest_folder, filename, file_data, data_type="binary")

    if url and files_changed:
        request(url, method, payload)


def _watch_resource_iterator(label, label_value, target_folder, url, method, payload,
                             current_namespace, folder_annotation, resource, unique_filenames):
    v1 = client.CoreV1Api()
    namespace = os.getenv("NAMESPACE", current_namespace)
    # Filter resources based on label and value or just label
    label_selector = f"{label}={label_value}" if label_value else label

    if namespace == "ALL":
        stream = watch.Watch().stream(getattr(v1, _list_for_all_namespaces[resource]), label_selector=label_selector)
    else:
        stream = watch.Watch().stream(getattr(v1, _list_namespaced[resource]), namespace=namespace,
                                      label_selector=label_selector)

    # Process events
    for event in stream:
        metadata = event["object"].metadata

        print(f"{timestamp()} Working on {resource} {metadata.namespace}/{metadata.name}")

        files_changed = False

        # Get the destination folder
        dest_folder = _get_destination_folder(metadata, target_folder, folder_annotation)

        # Check if it's an empty ConfigMap or Secret

        if event["object"].data is None and event["object"].binary_data is None:
            print(f"{timestamp()} {resource} does not have data/binaryData.")
            continue

        data_map = {}
        if event["object"].data is not None:
            data_map.update(event["object"].data)

        if event["object"].binary_data is not None:
            data_map.update(event["object"].binary_data)

        event_type = event["type"]
        # Each key on the data is a file
        for data_key in data_map.keys():
            print(f"{timestamp()} File in {resource} {data_key} {event_type}")

            if (event_type == "ADDED") or (event_type == "MODIFIED"):
                filename, filedata = _get_file_data_and_name(data_key, data_map[data_key],
                                                             resource)
                if unique_filenames:
                    filename = unique_filename(filename=filename,
                                               namespace=metadata.namespace,
                                               resource=resource,
                                               resource_name=metadata.name)

                files_changed |= write_text_to_file(dest_folder, filename, filedata)
            else:
                # Get filename from event
                filename = data_key[:-4] if data_key.endswith(".url") else data_key

                if unique_filenames:
                    filename = unique_filename(filename=filename,
                                               namespace=metadata.namespace,
                                               resource=resource,
                                               resource_name=metadata.name)

                files_changed |= remove_file(dest_folder, filename)
        if url and files_changed:
            request(url, method, payload)


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


def watch_for_changes(mode, label, label_value, target_folder, url, method, payload,
                      current_namespace, folder_annotation, resources, unique_filenames):
    first_proc, sec_proc = _start_watcher_processes(current_namespace, folder_annotation, label, label_value, method,
                                                    mode, payload, resources, target_folder, unique_filenames, url)

    while True:
        if not first_proc.is_alive():
            print(f"{timestamp()} Process for {resources[0]} died. Stopping and exiting")
            if len(resources) == 2 and sec_proc.is_alive():
                sec_proc.terminate()
            elif len(resources) == 2:
                print(f"{timestamp()} Process for {resources[1]}  also died...")
            raise Exception("Loop died")

        if len(resources) == 2 and not sec_proc.is_alive():
            print(f"{timestamp()} Process for {resources[1]} died. Stopping and exiting")
            if first_proc.is_alive():
                first_proc.terminate()
            else:
                print(f"{timestamp()} Process for {resources[0]}  also died...")
            raise Exception("Loop died")

        sleep(5)


def _start_watcher_processes(current_namespace, folder_annotation, label, label_value, method, mode, payload, resources,
                             target_folder, unique_filenames, url):
    first_proc = Process(target=_watch_resource_loop,
                         args=(mode, label, label_value, target_folder, url, method, payload,
                               current_namespace, folder_annotation, resources[0], unique_filenames)
                         )
    first_proc.daemon = True
    first_proc.start()
    sec_proc = None
    if len(resources) == 2:
        sec_proc = Process(target=_watch_resource_loop,
                           args=(mode, label, label_value, target_folder, url, method, payload,
                                 current_namespace, folder_annotation, resources[1], unique_filenames)
                           )
        sec_proc.daemon = True
        sec_proc.start()
    return first_proc, sec_proc
