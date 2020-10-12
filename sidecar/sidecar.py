#!/usr/bin/env python

import os

from kubernetes import client, config

from resources import listResources, watchForChanges

from helpers import timestamp

def main():
    print(f"{timestamp()} Starting collector")

    folderAnnotation = os.getenv("FOLDER_ANNOTATION")
    if folderAnnotation is None:
        print(f"{timestamp()} No folder annotation was provided, "
              "defaulting to k8s-sidecar-target-directory")
        folderAnnotation = "k8s-sidecar-target-directory"

    label = os.getenv("LABEL")
    if label is None:
        print(f"{timestamp()} Should have added LABEL as environment variable! Exit")
        return -1

    labelValue = os.getenv("LABEL_VALUE")
    if labelValue:
        print(f"{timestamp()} Filter labels with value: {labelValue}")

    targetFolder = os.getenv("FOLDER")
    if targetFolder is None:
        print(f"{timestamp()} Should have added FOLDER as environment variable! Exit")
        return -1

    resources = os.getenv("RESOURCE", "configmap")
    resources = ("secret", "configmap") if resources == "both" else (resources, )
    print(f"{timestamp()} Selected resource type: {resources}")

    method = os.getenv("REQ_METHOD")
    url = os.getenv("REQ_URL")
    payload = os.getenv("REQ_PAYLOAD")

    try:
      config.load_kube_config()
    except:
      config.load_incluster_config()
    print(f"{timestamp()} Config for cluster api loaded...")
    currentNamespace = open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read()

    if os.getenv("SKIP_TLS_VERIFY") == "true":
        configuration = client.Configuration()
        configuration.verify_ssl = False
        configuration.debug = False
        client.Configuration.set_default(configuration)

    uniqueFilenames = os.getenv("UNIQUE_FILENAMES") 
    if uniqueFilenames is not None and uniqueFilenames.lower() == "true":
        print(f"{timestamp()} Unique filenames will be enforced.")
        uniqueFilenames = True
    else:
        print(f"{timestamp()} Unique filenames will not be enforced.")
        uniqueFilenames = False

    if os.getenv("METHOD") == "LIST":
        for res in resources:
            listResources(label, labelValue, targetFolder, url, method, payload,
                          currentNamespace, folderAnnotation, res, uniqueFilenames)
    else:
        watchForChanges(os.getenv("METHOD"), label, labelValue, targetFolder, url, method,
                        payload, currentNamespace, folderAnnotation, resources, uniqueFilenames)


if __name__ == "__main__":
    main()
