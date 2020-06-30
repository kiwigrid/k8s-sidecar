#!/usr/bin/env python

import base64
import os
import sys
import signal

from multiprocessing import Process
from time import sleep

from kubernetes import client, watch
from kubernetes.client.rest import ApiException
from urllib3.exceptions import ProtocolError
from urllib3.exceptions import MaxRetryError

from helpers import request, writeTextToFile, removeFile, timestamp, uniqueFilename

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


def _get_file_data_and_name(full_filename, content, resource):
    if resource == "secret":
        file_data = base64.b64decode(content).decode()
    else:
        file_data = content

    if full_filename.endswith(".url"):
        filename = full_filename[:-4]
        file_data = request(file_data, "GET").text
    else:
        filename = full_filename

    return filename, file_data


def _get_destination_folder(metadata, defaultFolder, folderAnnotation):
    if metadata.annotations:
        if folderAnnotation in metadata.annotations.keys():
            destFolder = metadata.annotations[folderAnnotation]
            print(f"{timestamp()} Found a folder override annotation, "
                  f"placing the {metadata.name} in: {destFolder}")
            return destFolder
    return defaultFolder


def listResources(label, labelValue, targetFolder, url, method, payload,
                  currentNamespace, folderAnnotation, resource, uniqueFilenames):
    v1 = client.CoreV1Api()
    namespace = os.getenv("NAMESPACE", currentNamespace)
    # Filter resources based on label and value or just label
    labelSelector=f"{label}={labelValue}" if labelValue else label

    if namespace == "ALL":
        ret = getattr(v1, _list_for_all_namespaces[resource])(label_selector=labelSelector)
    else:
        ret = getattr(v1, _list_namespaced[resource])(namespace=namespace, label_selector=labelSelector)

    # For all the found resources
    for sec in ret.items:
        metadata = sec.metadata

        print(f"{timestamp()} Working on {resource}: {metadata.namespace}/{metadata.name}")

        # Get the destination folder
        destFolder = _get_destination_folder(metadata, targetFolder, folderAnnotation)

        # Check if it's an empty ConfigMap or Secret
        dataMap = sec.data
        if dataMap is None:
            print(f"{timestamp()} No data field in {resource}")
            continue

        # Each key on the data is a file
        for data_key in dataMap.keys():
            filename, filedata = _get_file_data_and_name(data_key, dataMap[data_key],
                                                            resource)
            if uniqueFilenames:
                filename = uniqueFilename(filename      = filename,
                                          namespace     = metadata.namespace,
                                          resource      = resource,
                                          resource_name = metadata.name)

            writeTextToFile(destFolder, filename, filedata)

    if url:
        request(url, method, payload)


def _watch_resource_iterator(label, labelValue, targetFolder, url, method, payload,
                             currentNamespace, folderAnnotation, resource, uniqueFilenames):
    v1 = client.CoreV1Api()
    namespace = os.getenv("NAMESPACE", currentNamespace)
    # Filter resources based on label and value or just label
    labelSelector=f"{label}={labelValue}" if labelValue else label

    if namespace == "ALL":
        stream = watch.Watch().stream(getattr(v1, _list_for_all_namespaces[resource]), label_selector=labelSelector)
    else:
        stream = watch.Watch().stream(getattr(v1, _list_namespaced[resource]), namespace=namespace, label_selector=labelSelector)

    # Process events
    for event in stream:
        metadata = event["object"].metadata

        print(f"{timestamp()} Working on {resource} {metadata.namespace}/{metadata.name}")

        # Get the destination folder
        destFolder = _get_destination_folder(metadata, targetFolder, folderAnnotation)

        # Check if it's an empty ConfigMap or Secret
        dataMap = event["object"].data
        if dataMap is None:
            print(f"{timestamp()} {resource} does not have data.")
            continue

        eventType = event["type"]
        # Each key on the data is a file
        for data_key in dataMap.keys():
            print(f"{timestamp()} File in {resource} {data_key} {eventType}")

            if (eventType == "ADDED") or (eventType == "MODIFIED"):
                filename, filedata = _get_file_data_and_name(data_key, dataMap[data_key],
                                                                resource)
                if uniqueFilenames:
                    filename = uniqueFilename(filename      = filename,
                                              namespace     = metadata.namespace,
                                              resource      = resource,
                                              resource_name = metadata.name)

                writeTextToFile(destFolder, filename, filedata)
            else:
                # Get filename from event
                filename = data_key[:-4] if data_key.endswith(".url") else data_key

                if uniqueFilenames:
                    filename = uniqueFilename(filename      = filename,
                                              namespace     = metadata.namespace,
                                              resource      = resource,
                                              resource_name = metadata.name)

                removeFile(destFolder, filename)
        if url:
            request(url, method, payload)


def _watch_resource_loop(mode, *args):
    while True:
        try:
            # Always wait to slow down the loop in case of exceptions
            sleep(os.getenv("ERROR_THROTTLE_SLEEP", 5))
            if mode == "SLEEP":
                listResources(*args)
                sleep(os.getenv("SLEEP_TIME", 60))
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


def watchForChanges(mode, label, labelValue, targetFolder, url, method, payload,
                    currentNamespace, folderAnnotation, resources, uniqueFilenames):

    firstProc = Process(target=_watch_resource_loop,
                        args=(mode, label, labelValue, targetFolder, url, method, payload,
                              currentNamespace, folderAnnotation, resources[0], uniqueFilenames)
                        )
    firstProc.daemon=True
    firstProc.start()

    if len(resources) == 2:
        secProc = Process(target=_watch_resource_loop,
                          args=(mode, label, labelValue, targetFolder, url, method, payload,
                                currentNamespace, folderAnnotation, resources[1], uniqueFilenames)
                          )
        secProc.daemon=True
        secProc.start()

    while True:
        if not firstProc.is_alive():
            print(f"{timestamp()} Process for {resources[0]} died. Stopping and exiting")
            if len(resources) == 2 and secProc.is_alive():
                secProc.terminate()
            elif len(resources) == 2:
                print(f"{timestamp()} Process for {resources[1]}  also died...")
            raise Exception("Loop died")

        if len(resources) == 2 and not secProc.is_alive():
            print(f"{timestamp()} Process for {resources[1]} died. Stopping and exiting")
            if firstProc.is_alive():
                firstProc.terminate()
            else:
                print(f"{timestamp()} Process for {resources[0]}  also died...")
            raise Exception("Loop died")

        sleep(5)
