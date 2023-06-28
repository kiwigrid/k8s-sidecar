

[![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/kiwigrid/k8s-sidecar?style=flat)](https://github.com/kiwigrid/k8s-sidecar/releases)
[![Release](https://github.com/kiwigrid/k8s-sidecar/actions/workflows/release.yaml/badge.svg)](https://github.com/kiwigrid/k8s-sidecar/actions/workflows/release.yaml)
[![Docker Pulls](https://img.shields.io/docker/pulls/kiwigrid/k8s-sidecar.svg?style=flat)](https://hub.docker.com/r/kiwigrid/k8s-sidecar/)
![Docker Image Size (latest semver)](https://img.shields.io/docker/image-size/kiwigrid/k8s-sidecar)
# What?

This is a docker container intended to run inside a kubernetes cluster to collect config maps with a specified label and store the included files in an local folder. It can also send an HTTP request to a specified URL after a configmap change. The main target is to be run as a sidecar container to supply an application with information from the cluster.

# Why?

This is our simple way to provide files from configmaps or secrets to a service and keep them updated during runtime.

# How?

Run the container created by this repo together with your application in a single pod with a shared volume. Specify which label should be monitored and where the files should be stored.
By adding additional env variables the container can send an HTTP request to specified URL.

# Where?

Images are available at:

- [docker.io/kiwigrid/k8s-sidecar](https://hub.docker.com/r/kiwigrid/k8s-sidecar)
- [quay.io/kiwigrid/k8s-sidecar](https://quay.io/repository/kiwigrid/k8s-sidecar)
- [ghcr.io/kiwigrid/k8s-sidecar](https://github.com/orgs/kiwigrid/packages/container/package/k8s-sidecar)

All are identical multi-arch images built for `amd64`, `arm64`, `arm/v7`, `ppc64le` and `s390x`

# Features

- Extract files from config maps and secrets
- Filter based on label
- Update/Delete on change of configmap or secret
- Enforce unique filenames
- CI tests for k8s v1.21-v1.27
- Support `binaryData` for both `Secret` and `ConfigMap` kinds
  - Binary data content is base64 decoded before generating the file on disk
  - Values can also be base64 encoded URLs that download binary data e.g. executables
    - The key in the `ConfigMap`/`Secret` must end with "`.url`" ([see](https://github.com/kiwigrid/k8s-sidecar/blob/master/test/resources/resources.yaml#L84))

# Build

```shell
docker build --network=host -t cortex-k8s-sidecar:0.1 .
```

# Usage 

Example for a simple deployment can be found in [`example.yaml`](./example.yaml). Depending on the cluster setup you have to grant yourself admin rights first:
```shell
kubectl create clusterrolebinding cluster-admin-binding --clusterrole cluster-admin   --user $(gcloud config get-value account)
```

One can override the default directory that files are copied into using a configmap annotation defined by the environment variable `FOLDER_ANNOTATION` (if not present it will default to `k8s-sidecar-target-directory`). The sidecar will attempt to create directories defined by configmaps if they are not present. Example configmap annotation:
```yaml
metadata:
  annotations:
    k8s-sidecar-target-directory: "/path/to/target/directory"
```

If the filename ends with `.url` suffix, the content will be processed as a URL which the target file contents will be downloaded from.

## Configuration Environment Variables

| name                       | description                                                                                                                                                                                                                                                                                                                         | required | default                                   | type    |
|----------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------|-------------------------------------------|---------|
| `LABEL`                    | Label that should be used for filtering                                                                                                                                                                                                                                                                                             | true     | -                                         | string  |
| `LABEL_VALUE`              | The value for the label you want to filter your resources on. Don't set a value to filter by any value                                                                                                                                                                                                                              | false    | -                                         | string  |
| `FOLDER`                   | Folder where the files should be placed                                                                                                                                                                                                                                                                                             | true     | -                                         | string  |
| `FOLDER_ANNOTATION`        | The annotation the sidecar will look for in configmaps to override the destination folder for files. The annotation _value_ can be either an absolute or a relative path. Relative paths will be relative to `FOLDER`.                                                                                                              | false    | `k8s-sidecar-target-directory`            | string  |
| `NAMESPACE`                | Comma separated list of namespaces. If specified, the sidecar will search for config-maps inside these namespaces. It's also possible to specify `ALL` to search in all namespaces.                                                                                                                                                 | false    | namespace in which the sidecar is running | string  |
| `RESOURCE`                 | Resource type, which is monitored by the sidecar. Options: `configmap`, `secret`, `both`                                                                                                                                                                                                                                            | false    | `configmap`                               | string  |
| `METHOD`                   | If `METHOD` is set to `LIST`, the sidecar will just list config-maps/secrets and exit. With `SLEEP` it will list all config-maps/secrets, then sleep for `SLEEP_TIME` seconds. Anything else will continuously watch for changes (see https://kubernetes.io/docs/reference/using-api/api-concepts/#efficient-detection-of-changes). | false    | -                                         | string  |
| `SLEEP_TIME`               | How many seconds to wait before updating config-maps/secrets when using `SLEEP` method.                                                                                                                                                                                                                                             | false    | `60`                                      | integer |
| `REQ_URL`                  | URL to which send a request after a configmap/secret got reloaded                                                                                                                                                                                                                                                                   | false    | -                                         | URI     |
| `REQ_METHOD`               | Request method `GET` or `POST` for requests tp `REQ_URL`                                                                                                                                                                                                                                                                            | false    | `GET`                                     | string  |
| `REQ_PAYLOAD`              | If you use `REQ_METHOD=POST` you can also provide json payload                                                                                                                                                                                                                                                                      | false    | -                                         | json    |
| `REQ_RETRY_TOTAL`          | Total number of retries to allow for any http request (`*.url` triggered requests, requests to `REQ_URI` and k8s api requests)                                                                                                                                                                                                      | false    | `5`                                       | integer |
| `REQ_RETRY_CONNECT`        | How many connection-related errors to retry on for any http request (`*.url` triggered requests, requests to `REQ_URI` and k8s api requests)                                                                                                                                                                                        | false    | `10`                                      | integer |
| `REQ_RETRY_READ`           | How many times to retry on read errors for any http request (`.url` triggered requests, requests to `REQ_URI` and k8s api requests)                                                                                                                                                                                                 | false    | `5`                                       | integer |
| `REQ_RETRY_BACKOFF_FACTOR` | A backoff factor to apply between attempts after the second try for any http request (`.url` triggered requests, requests to `REQ_URI` and k8s api requests)                                                                                                                                                                        | false    | `1.1`                                     | float   |
| `REQ_TIMEOUT`              | How many seconds to wait for the server to send data before giving up for `.url` triggered requests or requests to `REQ_URI` (does not apply to k8s api requests)                                                                                                                                                                   | false    | `10`                                      | float   |
| `REQ_USERNAME`             | Username to use for basic authentication for requests to `REQ_URL` and for `*.url` triggered requests                                                                                                                                                                                                                               | false    | -                                         | string  |
| `REQ_PASSWORD`             | Password to use for basic authentication for requests to `REQ_URL` and for `*.url` triggered requests                                                                                                                                                                                                                               | false    | -                                         | string  |
| `REQ_BASIC_AUTH_ENCODING`  | Which encoding to use for username and password as [by default it's undefined](https://datatracker.ietf.org/doc/html/rfc7617) (e.g. `utf-8`).                                                                                                                                                                                       | false    | `latin1`                                  | string  |
| `SCRIPT`                   | Absolute path to a script to execute after a configmap got reloaded. It runs before calls to `REQ_URI`. If the file is not executable it will be passed to `sh`. Otherwise it's executed as is. [Shebangs](https://en.wikipedia.org/wiki/Shebang_(Unix)) known to work are `#!/bin/sh` and `#!/usr/bin/env python`                  | false    | -                                         | string  |
| `ERROR_THROTTLE_SLEEP`     | How many seconds to wait before watching resources again when an error occurs                                                                                                                                                                                                                                                       | false    | `5`                                       | integer |
| `SKIP_TLS_VERIFY`          | Set to `true` to skip tls verification for kube api calls                                                                                                                                                                                                                                                                           | false    | -                                         | boolean |
| `REQ_SKIP_TLS_VERIFY`      | Set to `true` to skip tls verification for all HTTP requests (except the Kube API server, which are controlled by `SKIP_TLS_VERIFY`). Note that the latest 'requests' library no longer offer a way to disable this via env vars; however a custom truststore can be set via REQUESTS_CA_BUNDLE.                                    | false    | -                                         | boolean |
| `UNIQUE_FILENAMES`         | Set to true to produce unique filenames where duplicate data keys exist between ConfigMaps and/or Secrets within the same or multiple Namespaces.                                                                                                                                                                                   | false    | `false`                                   | boolean |
| `DEFAULT_FILE_MODE`        | The default file system permission for every file. Use three digits (e.g. '500', '440', ...)                                                                                                                                                                                                                                        | false    | -                                         | string  |
| `KUBECONFIG`               | if this is given and points to a file or `~/.kube/config` is mounted k8s config will be loaded from this file, otherwise "incluster" k8s configuration is tried.                                                                                                                                                                    | false    | -                                         | string  |
| `ENABLE_5XX`               | Set to `true` to enable pulling of 5XX response content from config map. Used in case if the filename ends with `.url` suffix (Please refer to the `*.url` feature here.)                                                                                                                                                           | false    | -                                         | boolean |
| `WATCH_SERVER_TIMEOUT`     | polite request to the server, asking it to cleanly close watch connections after this amount of seconds ([#85](https://github.com/kiwigrid/k8s-sidecar/issues/85))                                                                                                                                                                  | false    | `60`                                      | integer |
| `WATCH_CLIENT_TIMEOUT`     | If you have a network outage dropping all packets with no RST/FIN, this is how many seconds your client waits on watches before realizing & dropping the connection. You can keep this number low. ([#85](https://github.com/kiwigrid/k8s-sidecar/issues/85))                                                                       | false    | `66`                                      | integer |
| `IGNORE_ALREADY_PROCESSED` | Ignore already processed resource version. Avoid numerous checks on same unchanged resource. req kubernetes api >= v1.19                                                                                                                                                                                                            | false    | `false`                                   | boolean |
| `LOG_LEVEL`                | Set the logging level. (DEBUG, INFO, WARN, ERROR, CRITICAL)                                                                                                                                                                                                                                                                         | false    | `INFO`                                    | string  |
| `LOG_FORMAT`               | Set a log format. (JSON or LOGFMT)                                                                                                                                                                                                                                                                                                  | false    | `JSON`                                    | string  |
| `LOG_TZ`                   | Set the log timezone. (LOCAL or UTC)                                                                                                                                                                                                                                                                                                | false    | `LOCAL`                                   | string  |
