from kubernetes import client, config, watch
import base64
import os
import sys
import requests
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter


def writeTextToFile(folder, filename, data):
    with open(folder +"/"+ filename, 'w') as f:
        f.write(data)
        f.close()


def request(url, method, payload = None):
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
    return res

def removeFile(folder, filename):
    completeFile = folder +"/"+filename
    if os.path.isfile(completeFile):
        os.remove(completeFile)
    else:
        print("Error: %s file not found" % completeFile)


def listConfigmaps(label, targetFolder, url, method, payload, current):
    v1 = client.CoreV1Api()
    namespace = os.getenv("NAMESPACE")
    if namespace is None:
        ret = v1.list_namespaced_config_map(namespace=current)
    elif namespace == "ALL":
        ret = v1.list_config_map_for_all_namespaces()
    else:
        ret = v1.list_namespaced_config_map(namespace=namespace)
    for cm in ret.items:
        metadata = cm.metadata
        if metadata.labels is None:
            continue
        print(f'Working on configmap {metadata.namespace}/{metadata.name}')
        if label in cm.metadata.labels.keys():
            print("Configmap with label found")
            dataMap=cm.data
            if dataMap is None:
                print("Configmap does not have data.")
                continue
            if label in cm.metadata.labels.keys():
                for filename in dataMap.keys():
                    fileData = dataMap[filename]
                    if filename.endswith(".url"):
                        filename = filename[:-4]
                        fileData = request(fileData, "GET").text
                    writeTextToFile(targetFolder, filename, fileData)
                    if url is not None:
                        request(url, method, payload)

def getAnnotation(obj, annotation):
    if not hasattr(obj, 'metadata'):
        return None
    if not hasattr(obj.metadata, 'annotations'):
        return None
    return obj.metadata.annotations.get(annotation)


def watchForChanges(label, targetFolder, url, method, payload, current):
    v1 = client.CoreV1Api()
    w = watch.Watch()
    stream = None
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
            dataMap=event['object'].data
            if dataMap is None:
                print("Configmap does not have data.")
                continue
            eventType = event['type']
            contentBase64Encoded = getAnnotation(event['object'], 'k8s-sidecar.kiwigrid/base64-data')
            for filename in dataMap.keys():
                print("File in configmap %s %s" % (filename, eventType))
                if (eventType == "ADDED") or (eventType == "MODIFIED"):
                    fileData = dataMap[filename]
                    if contentBase64Encoded:
                        fileData = base64.b64decode(fileData).decode()
                    if filename.endswith(".url"):
                        filename = filename[:-4]
                        fileData = request(fileData, "GET").text
                    writeTextToFile(targetFolder, filename, fileData)
                    if url is not None:
                        request(url, method, payload)
                else:
                    if filename.endswith(".url"):
                        filename = filename[:-4]
                    removeFile(targetFolder, filename)
                    if url is not None:
                        request(url, method, payload)


def main():
    print("Starting config map collector")
    label = os.getenv('LABEL')
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
    namespace = open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read()

    if os.getenv('SKIP_TLS_VERIFY') == 'true':
        configuration = client.Configuration()
        configuration.verify_ssl=False
        configuration.debug = False
        client.Configuration.set_default(configuration)

    k8s_method = os.getenv("METHOD")    
    if k8s_method == "LIST":
        listConfigmaps(label, targetFolder, url, method, payload, namespace)
    else:
        watchForChanges(label, targetFolder, url, method, payload, namespace)


if __name__ == '__main__':
    main()
