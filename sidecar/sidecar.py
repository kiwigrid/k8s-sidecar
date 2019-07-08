import os

from kubernetes import client, config

from resources import listResources, watchForChanges


def main():
    print("Starting collector")

    folderAnnotation = os.getenv('FOLDER_ANNOTATIONS')
    if folderAnnotation is None:
        print("No folder annotation was provided, defaulting to k8s-sidecar-target-directory")
        folderAnnotation = "k8s-sidecar-target-directory"

    label = os.getenv('LABEL')
    if label is None:
        print("Should have added LABEL as environment variable! Exit")
        return -1

    targetFolder = os.getenv('FOLDER')
    if targetFolder is None:
        print("Should have added FOLDER as environment variable! Exit")
        return -1

    resources = os.getenv('RESOURCE', 'configmap')
    resources = ("secret", "configmap") if resources == "both" else (resources, )
    print(f"Selected resource type: {resources}")

    method = os.getenv('REQ_METHOD')
    url = os.getenv('REQ_URL')
    payload = os.getenv('REQ_PAYLOAD')

    config.load_incluster_config()
    print("Config for cluster api loaded...")
    namespace = open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read()

    if os.getenv('SKIP_TLS_VERIFY') == 'true':
        configuration = client.Configuration()
        configuration.verify_ssl = False
        configuration.debug = False
        client.Configuration.set_default(configuration)

    if os.getenv("METHOD") == "LIST":
        for res in resources:
            listResources(label, targetFolder, url, method, payload,
                          namespace, folderAnnotation, res)
    else:
        watchForChanges(label, targetFolder, url, method,
                        payload, namespace, folderAnnotation, resources)


if __name__ == '__main__':
    main()
