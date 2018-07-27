from kubernetes import client, config, watch
import os
import sys
import requests


def writeTextToFile(folder, filename, data):
    with open(folder +"/"+ filename, 'w') as f:
        f.write(data)
        f.close()


def request(url, method, payload):
    if url is None:
        print("No url provided. Doing nothing.")
        # If method is not provided use GET as default
    elif method == "GET" or method is None:
        r = requests.get("%s" % url)
        print ("%s request sent to %s. Response: %d %s" % (method, url, r.status_code, r.reason))
    elif method == "POST":
        r = requests.post("%s" % url, json=payload)
        print ("%s request sent to %s. Response: %d %s" % (method, url, r.status_code, r.reason))


def removeFile(folder, filename):
    completeFile = folder +"/"+filename
    if os.path.isfile(completeFile):
        os.remove(completeFile)
    else:
        print("Error: %s file not found" % completeFile)


def watchForChanges(label, targetFolder, url, method, payload):
    v1 = client.CoreV1Api()
    w = watch.Watch()
    for event in w.stream(v1.list_config_map_for_all_namespaces):
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
            for filename in dataMap.keys():
                print("File in configmap %s %s" % (filename, eventType))
                if (eventType == "ADDED") or (eventType == "MODIFIED"):
                    writeTextToFile(targetFolder, filename, dataMap[filename])
                    if url is not None:
                        request(url, method, payload)
                else:
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
    watchForChanges(label, targetFolder, url, method, payload)


if __name__ == '__main__':
    main()
