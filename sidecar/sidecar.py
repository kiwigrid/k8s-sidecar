from kubernetes import client, config, watch
import os
import sys
import requests
from kubernetes.client.rest import ApiException
from urllib3.exceptions import ProtocolError
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter


def writeTextToFile(folder, filename, data):
    if not os.path.exists(folder):
        try:
            os.makedirs(folder)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise


    with open(folder +"/"+ filename, 'w') as f:
        f.write(data)
        f.close()


def request(url, method, payload):
    r = requests.Session()
    retries = Retry(total = 5,
            connect = 5,
            backoff_factor = 0.2,
            status_forcelist = [ 500, 502, 503, 504 ])
    r.mount('http://', HTTPAdapter(max_retries=retries))
    r.mount('https://', HTTPAdapter(max_retries=retries))
    if url is None:
        print("No url provided. Doing nothing.")
        # If method is not provided use GET as default
    elif method == "GET" or method is None:
        res = r.get("%s" % url, timeout=10)
        print ("%s request sent to %s. Response: %d %s" % (method, url, res.status_code, res.reason))
    elif method == "POST":
        res = r.post("%s" % url, json=payload, timeout=10)
        print ("%s request sent to %s. Response: %d %s" % (method, url, res.status_code, res.reason))


def removeFile(folder, filename):
    completeFile = folder +"/"+filename
    if os.path.isfile(completeFile):
        os.remove(completeFile)
    else:
        print("Error: %s file not found" % completeFile)


def watchForChanges(label, targetFolder, url, method, payload, current, folderAnnotation):
    v1 = client.CoreV1Api()
    w = watch.Watch()
    stream = None
    destFolder = targetFolder
    namespace = os.getenv("NAMESPACE")
    if namespace is None:
        stream = w.stream(v1.list_namespaced_config_map, namespace=current)
    elif namespace == "ALL":
        stream = w.stream(v1.list_config_map_for_all_namespaces)
    else:
        stream = w.stream(v1.list_namespaced_config_map, namespace=namespace)
    for event in stream:
        metadata = event['object'].metadata
        if metadata.labels is None:
            continue
        print(f'Working on configmap {metadata.namespace}/{metadata.name}')
        if label in event['object'].metadata.labels.keys():
            print("Configmap with label found")

            if folderAnnotation is not None:
                if event['object'].metadata.annotations is not None:
                    if folderAnnotation in event['object'].metadata.annotations.keys():
                        destFolder = event['object'].metadata.annotations[folderAnnotation]
                        print(f'Found a folder override annotation, placing the configmap in: {destFolder}')

            dataMap=event['object'].data
            if dataMap is None:
                print("Configmap does not have data.")
                continue
            eventType = event['type']
            for filename in dataMap.keys():
                print("File in configmap %s %s" % (filename, eventType))
                if (eventType == "ADDED") or (eventType == "MODIFIED"):
                    writeTextToFile(destFolder, filename, dataMap[filename])
                    if url is not None:
                        request(url, method, payload)
                else:
                    removeFile(destFolder, filename)
                    if url is not None:
                        request(url, method, payload)


def main():
    print("Starting config map collector")
    label = os.getenv('LABEL')
    folderAnnotation = os.getenv('FOLDER_ANNOTATIONS')
    if folderAnnotation is None:
        print("No folder annotation was provided, defaulting to k8s-sidecar-target-directory")
        folderAnnotation = "k8s-sidecar-target-directory"
    if label is None:
        print("Should have added LABEL as environment variable! Exit")
        return -1
    targetFolder = os.getenv('FOLDER')
    if targetFolder is None:
        print("Should have added FOLDER as environment variable! Exit")
        return -1

    method = os.getenv('REQ_METHOD')
    url = os.getenv('REQ_URL')
    payload = os.getenv('REQ_PAYLOAD')

    config.load_incluster_config()
    print("Config for cluster api loaded...")
    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as f:
        namespace = f.read()

    
    while True:
        try:
            watchForChanges(label, targetFolder, url, method, payload, namespace, folderAnnotation)
        except ApiException as e:
            if "500" not in e:
              print("ApiException when calling kubernetes: %s\n" % e)
            else:
              raise
        except ProtocolError as e:
            print("ProtocolError when calling kubernetes: %s\n" % e)
        except:
            raise


if __name__ == '__main__':
    main()
