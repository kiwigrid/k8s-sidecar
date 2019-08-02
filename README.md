

[![CircleCI](https://img.shields.io/circleci/project/github/kiwigrid/k8s-sidecar/master.svg?style=plastic)](https://circleci.com/gh/kiwigrid/k8s-sidecar)
[![Docker Pulls](https://img.shields.io/docker/pulls/kiwigrid/k8s-sidecar.svg?style=plastic)](https://hub.docker.com/r/kiwigrid/k8s-sidecar/)

# What?

This is a docker container intended to run inside a kubernetes cluster to collect config maps with a specified label and store the included files in an local folder. It can also send a html request to a specified URL after a configmap change. The main target is to be run as a sidecar container to supply an application with information from the cluster. The contained python script is working with the Kubernetes API 1.10

# Why?

Currently (April 2018) there is no simple way to hand files in configmaps to a service and keep them updated during runtime.

# How?

Run the container created by this repo together you application in an single pod with a shared volume. Specify which label should be monitored and where the files should be stored.
By adding additional env variables the container can send a html request to specified URL.

# Features

- Extract files from config maps
- Filter based on label
- Update/Delete on change of configmap

# Usage

Example for a simple deployment can be found in `example.yaml`. Depending on the cluster setup you have to grant yourself admin rights first: `kubectl create clusterrolebinding cluster-admin-binding   --clusterrole cluster-admin   --user $(gcloud config get-value account)`

One can override the default directory that files are copied into using a configmap annotation defined by the environment variable "FOLDER_ANNOTATION" (if not present it will default to "k8s-sidecar-target-directory"). The sidecar will attempt to create directories defined by configmaps if they are not present. Example configmap annotation:
  k8s-sidecar-target-directory: "/path/to/target/directory"

If the filename ends with `.url` suffix, the content will be processed as an URL the target file will be downloaded and used as the content file.

## Configuration Environment Variables

- `LABEL`
  - description: Label that should be used for filtering
  - required: true
  - type: string

- `FOLDER`
  - description: Folder where the files should be placed
  - required: true
  - type: string

- `FOLDER_ANNOTATION`
  - description: The annotation the sidecar will look for in configmaps to override the destination folder for files, defaults to "k8s-sidecar-target-directory"
  - required: false
  - type: string

- `NAMESPACE`
  - description: If specified, the sidecar will search for config-maps inside this namespace. Otherwise the namespace in which the sidecar is running will be used. It's also possible to specify `ALL` to search in all namespaces.
  - required: false
  - type: string

- `RESOURCE`
  - description: Resouce type, which is monitored by the sidecar. Options: configmap (default), secret, both
  - required: false
  - default: configmap
  - type: string

- `METHOD`
  - description: If `METHOD` is set with `LIST`, the sidecar will just list config-maps and exit. Default is watch.
  - required: false
  - type: string

- `REQ_URL`
  - description: URL to which send a request after a configmap got reloaded
  - required: false
  - type: URI

- `REQ_METHOD`
  - description: Request method GET(default) or POST
  - required: false
  - type: string

- `REQ_PAYLOAD`
  - description: If you use POST you can also provide json payload
  - required: false
  - type: json

- `REQ_RETRY_TOTAL`
  - description: Total number of retries to allow
  - required: false
  - default: 5
  - type: integer

- `REQ_RETRY_CONNECT`
  - description: How many connection-related errors to retry on
  - required: false
  - default: 5
  - type: integer

- `REQ_RETRY_READ`
  - description: How many times to retry on read errors
  - required: false
  - default: 5
  - type: integer

- `REQ_RETRY_BACKOFF_FACTOR`
  - description: A backoff factor to apply between attempts after the second try
  - required: false
  - default: 0.2
  - type: float

- `REQ_TIMEOUT`
  - description: many seconds to wait for the server to send data before giving up
  - required: false
  - default: 10
  - type: float

- `SKIP_TLS_VERIFY`
  - description: Set to true to skip tls verification for kube api calls
  - required: false
  - type: boolean
