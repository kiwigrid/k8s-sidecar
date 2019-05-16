import base64
import os
from threading import Thread

from kubernetes import client, watch
from kubernetes.client.rest import ApiException
from urllib3.exceptions import ProtocolError

from helpers import request, writeTextToFile, removeFile

_list_namespaced = {
    "secret": "list_namespaced_secret",
    "configmap": "list_namespaced_config_map"
}

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


def listResources(label, targetFolder, url, method, payload, current, folderAnnotation, resource):
    v1 = client.CoreV1Api()
    namespace = os.getenv("NAMESPACE", current)
    if namespace == "ALL":
        ret = getattr(v1, _list_for_all_namespaces[resource])()
    else:
        ret = getattr(v1, _list_namespaced[resource])(namespace=namespace)

    for sec in ret.items:
        destFolder = targetFolder
        metadata = sec.metadata
        if metadata.labels is None:
            continue
        print(f'Working on {resource}: {metadata.namespace}/{metadata.name}')
        if label in sec.metadata.labels.keys():
            print(f"Found {resource} with label")
            if sec.metadata.annotations is not None:
                if folderAnnotation in sec.metadata.annotations.keys():
                    destFolder = sec.metadata.annotations[folderAnnotation]

            dataMap = sec.data
            if dataMap is None:
                print(f"No data field in {resource}")
                continue

            if label in sec.metadata.labels.keys():
                for data_key in dataMap.keys():
                    filename, filedata = _get_file_data_and_name(data_key, dataMap[data_key],
                                                                 resource)
                    writeTextToFile(destFolder, filename, filedata)

                    if url is not None:
                        request(url, method, payload)


def _watch_resource_iterator(label, targetFolder, url, method, payload,
                             current, folderAnnotation, resource, thread):
    print_prefix = "Thread: " if thread else ""
    v1 = client.CoreV1Api()
    namespace = os.getenv("NAMESPACE", current)
    if namespace == "ALL":
        stream = watch.Watch().stream(getattr(v1, _list_for_all_namespaces[resource]))
    else:
        stream = watch.Watch().stream(getattr(v1, _list_namespaced[resource]), namespace=namespace)

    for event in stream:
        destFolder = targetFolder
        metadata = event['object'].metadata
        if metadata.labels is None:
            continue
        print(f'{print_prefix}Working on {resource} {metadata.namespace}/{metadata.name}')
        if label in event['object'].metadata.labels.keys():
            print(f"{print_prefix}{resource} with label found")
            if event['object'].metadata.annotations is not None:
                if folderAnnotation in event['object'].metadata.annotations.keys():
                    destFolder = event['object'].metadata.annotations[folderAnnotation]
                    print(f'{print_prefix}ound a folder override annotation, '
                          'placing the {resource} in: {destFolder}')
            dataMap = event['object'].data
            if dataMap is None:
                print(f"{print_prefix}{resource} does not have data.")
                continue
            eventType = event['type']
            for data_key in dataMap.keys():
                print(f"{print_prefix}File in {resource} {data_key} {eventType}")

                if (eventType == "ADDED") or (eventType == "MODIFIED"):
                    filename, filedata = _get_file_data_and_name(data_key, dataMap[data_key],
                                                                 resource)
                    writeTextToFile(destFolder, filename, filedata)

                    if url is not None:
                        request(url, method, payload)
                else:
                    filename = data_key[:-4] if data_key.endswith(".url") else data_key
                    removeFile(destFolder, filename)
                    if url is not None:
                        request(url, method, payload)


def _watch_resource_loop(*args):
    try:
        _watch_resource_iterator(*args)
    except ApiException as e:
        if e.status != 500:
            print(f"ApiException when calling kubernetes: {e}\n")
        else:
            raise
    except ProtocolError as e:
        print(f"ProtocolError when calling kubernetes: {e}\n")
    except Exception as e:
        print(f"Received unknown exception: {e}\n")


def watchForChanges(label, targetFolder, url, method, payload,
                    current, folderAnnotation, resources):

    if len(resources) == 2:
        Thread(target=_watch_resource_loop,
               args=(label, targetFolder, url, method, payload,
                     current, folderAnnotation, resources[1], True)
               ).start()

    _watch_resource_loop(label, targetFolder, url, method, payload,
                         current, folderAnnotation, resources[0], False)
