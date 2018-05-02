from kubernetes import client, config, watch
import os
import sys


def writeTextToFile(folder, filename, data):
    with open(folder +"/"+ filename, 'w') as f:
        f.write(data)
        f.close()


def removeFile(folder, filename):
    completeFile = folder +"/"+filename
    if os.path.isfile(completeFile):
        os.remove(completeFile)
    else:
        print("Error: %s file not found" % completeFile)


def watchForChanges(label, targetFolder):
    v1 = client.CoreV1Api()
    w = watch.Watch()
    for event in w.stream(v1.list_config_map_for_all_namespaces):
        if event['object'].metadata.labels is None:
            continue
        print("Working on configmap %s" % event['object'].metadata.name)
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
                else:
                    removeFile(targetFolder, filename)


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
    config.load_incluster_config()
    print("Config for cluster api loaded...")
    watchForChanges(label, targetFolder)


if __name__ == '__main__':
    main()
