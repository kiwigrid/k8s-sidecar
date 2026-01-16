
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

All are identical multi-arch images built for `amd64`, `arm64` and `arm/v7`.

## Dropped support for `ppc64le` and `s390x`

With v2.x we have dropped support for the `ppc64le` and `s390x` architectures.
If you still have a need for those architectures please get in touch.
A possible solution would be to setup a dedicated build job using a native runner instead of qemu.

# Features

- Extract files from config maps and secrets
- Filter based on label
- Update/Delete on change of configmap or secret
- Enforce unique filenames
- CI tests for k8s v1.25-v1.33
- Support `binaryData` for both `Secret` and `ConfigMap` kinds
  - Binary data content is base64 decoded before generating the file on disk
  - Values can also be base64 encoded URLs that download binary data e.g. executables
    - The key in the `ConfigMap`/`Secret` must end with "`.url`" ([see](https://github.com/kiwigrid/k8s-sidecar/blob/master/test/resources/resources.yaml#L84))

# Usage

Example for a simple deployment can be found in [`example.yaml`](./examples/example.yaml). Depending on the cluster setup you have to grant yourself admin rights first:

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

## Configuration CLI Flags

| name                  | description                                                                                                                                                      | required | default | type    |
|-----------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------|---------|---------|
| `--req-username-file` | Path to file containing username to use for basic authentication for requests to `REQ_URL` and for `*.url` triggered requests. This overrides the `REQ_USERNAME` | false    | -       | string  |
| `--req-password-file` | Path to file containing password to use for basic authentication for requests to `REQ_URL` and for `*.url` triggered requests. This overrides the `REQ_PASSWORD` | false    | -       | string  |

## Configuration Environment Variables

| name                       | description                                                                                                                                                                                                                                                                                                                         | required | default                                   | type    |
|----------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------|-------------------------------------------|---------|
| `LABEL`                    | Label that should be used for filtering                                                                                                                                                                                                                                                                                             | true     | -                                         | string  |
| `LABEL_VALUE`              | The value for the label you want to filter your resources on. Don't set a value to filter by any value                                                                                                                                                                                                                              | false    | -                                         | string  |
| `FOLDER`                   | Folder where the files should be placed                                                                                                                                                                                                                                                                                             | true     | -                                         | string  |
| `FOLDER_ANNOTATION`        | The annotation the sidecar will look for in configmaps to override the destination folder for files. The annotation _value_ can be either an absolute or a relative path. Relative paths will be relative to `FOLDER`.                                                                                                              | false    | `k8s-sidecar-target-directory`            | string  |
| `NAMESPACE`                | Comma separated list of namespaces. If specified, the sidecar will search for config-maps inside these namespaces. It's also possible to specify `ALL` to search in all namespaces.                                                                                                                                                 | false    | namespace in which the sidecar is running | string  |
| `RESOURCE`                 | Resource type, which is monitored by the sidecar. Options: `configmap`, `secret`, `both`                                                                                                                                                                                                                                            | false    | `configmap`                               | string  |
| `RESOURCE_NAME`            | Comma separated list of resource names, which are monitored by the sidecar. Items can be prefixed by the namespace and the resource type. E.g. `secret/resource-name` or `namespace/secret/resource-name`. Setting this will result `method` set to `WATCH` being treated as `SLEEP`                                             | false    | -                                         | string  |
| `METHOD`                   | If `METHOD` is set to `LIST`, the sidecar will just list config-maps/secrets and exit. With `SLEEP` it will list all config-maps/secrets, then sleep for `SLEEP_TIME` seconds. Anything else will continuously watch for changes (see [Kubernetes Doc](https://kubernetes.io/docs/reference/using-api/api-concepts/#efficient-detection-of-changes)). | false    | -                                         | string  |
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
| `REQ_SKIP_INIT`            | Set to `true` to skip the initial request on startup to `REQ_URL` when using `WATCH` method                                                                                                                                                                                                                                         | false    | `false`                                   | boolean |
| `SCRIPT`                   | Absolute path to a script to execute after a configmap got reloaded. It runs before calls to `REQ_URI`. If the file is not executable it will be passed to `sh`. Otherwise it's executed as is. [Shebangs](https://en.wikipedia.org/wiki/Shebang_(Unix)) known to work are `#!/bin/sh` and `#!/usr/bin/env python`                  | false    | -                                         | string  |
| `ERROR_THROTTLE_SLEEP`     | How many seconds to wait before watching resources again when an error occurs                                                                                                                                                                                                                                                       | false    | `5`                                       | integer |
| `SKIP_TLS_VERIFY`          | Set to `true` to skip tls verification for kube api calls                                                                                                                                                                                                                                                                           | false    | -                                         | boolean |
| `REQ_SKIP_TLS_VERIFY`      | Set to `true` to skip tls verification for all HTTP requests (except the Kube API server, which are controlled by `SKIP_TLS_VERIFY`).                                      | false    | -                                         | boolean |
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
| `LOG_CONFIG`               | Log configuration file path. If not configured, uses the default log config for backward compatibility support. When not configured `LOG_LEVEL, LOG_FORMAT and LOG_TZ` would be used. Refer to [Python logging](https://docs.python.org/3/library/logging.config.html) for log configuration. For sample configuration file  refer to file examples/example_logconfig.yaml | false    | -                                         | string  |
| `HEALTH_PORT`              | The port for the health endpoint (`/healthz`).                                                                                                                                                                                                                                                                                                                             | false    | `8080`                                    | integer |

## Health Endpoint

The sidecar provides a health endpoint at `/healthz` on port `8080` (or as configured by `HEALTH_PORT`) that can be used for Kubernetes readiness and liveness probes. The endpoint is compatible with both IPv4 and IPv6 (dual-stack).

### Readiness Probe

The endpoint will return `HTTP 200 OK` only after the initial synchronization of all configured resources (`ConfigMap`s and/or `Secret`s) is complete. Before that, it will return `HTTP 503 Service Unavailable`. This ensures that the main application container does not start or receive traffic before its configuration is fully available.

Example readinessProbe configuration:

```yaml
readinessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 20
  periodSeconds: 5
```

### Liveness Probe

The endpoint also serves as a liveness probe, checking for two conditions:

1. Kubernetes API Contact: It verifies that the sidecar has had successful contact with the Kubernetes API within the last 60 seconds.
1. Watcher Threads: It ensures that all internal watcher threads (for `ConfigMap`s and `Secret`s) are running correctly.

If any of these checks fail, the endpoint will return `HTTP 503 Service Unavailable`, signaling Kubernetes to restart the container.

Example livenessProbe configuration:

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 35
  periodSeconds: 10
```

## CI & Release workflows

This repository uses three main GitHub Actions workflows:

### 1. Build and Test (`.github/workflows/build_and_test.yaml`)

**Purpose:** End-to-end tests of the sidecar against a local `kind` cluster.

- **Triggers:**
  - `pull_request`
  - `workflow_dispatch`
- **What it does:**
  - Builds a local Docker image of the sidecar (not pushed to any registry).
  - Builds a dummy server image.
  - Loads both images into a `kind` cluster.
  - Runs a comprehensive test suite against multiple Kubernetes versions (matrix).

This workflow does **not** create tags, releases, or push images to registries.

---

### 2. Release (`.github/workflows/release.yaml`)

**Purpose:** Build and publish release images and create GitHub releases.

- **Triggers:**
  - `push` to `master` that touches:
    - `src/**`
    - `Dockerfile`
- **Versioning & tagging:**
  - Uses [`anothrNick/github-tag-action`](https://github.com/anothrNick/github-tag-action).
  - By default, each qualifying push bumps the **patch** version
    (e.g. `2.1.3` → `2.1.4`).
  - The bump behaviour can be overridden via commit message tokens:
    - `#minor` → minor bump
    - `#major` → major bump
    - `#none`  → **no bump**, no build, no release
- **Guard condition:**
  - All steps that build/push images or create a release run only when  
    the tag action reports a real bump (`part != '' && part != 'none'`).
- **What it does when a new tag is created:**
  - Builds multi-arch images for the sidecar.
  - Pushes images to:
    - `docker.io/kiwigrid/k8s-sidecar`
    - `quay.io/kiwigrid/k8s-sidecar`
    - `ghcr.io/kiwigrid/k8s-sidecar`
  - Tags: `<new_tag>` and `latest`.
  - Builds a changelog.
  - Creates a GitHub release for the new tag.

This ensures that:

- Only code changes in `src/**` or `Dockerfile` produce new images.
- Existing tags are not rebuilt and remain **immutable**.
- CI-only or documentation-only changes do not trigger a release.

---

### 3. Release Workflow Tests (`.github/workflows/release_test.yaml`)

**Purpose:** Manually test the release workflow logic (tagging, changelog, image build)
without touching real production tags.

- **Trigger:**
  - `workflow_dispatch` (manual run only).
- **Tagging behaviour:**
  - Uses `github-tag-action` with:
    - `DEFAULT_BUMP: patch`
    - `DRY_RUN: true`
  - This means:
    - A bump is always simulated.
    - No real tags are pushed to the repository.
- **Guard condition:**
  - All release-like steps run only when the tag action reports a real bump
    (`part != '' && part != 'none'`), mirroring the production workflow.
- **What it does:**
  - Builds and pushes test images tagged as `<resolved_tag>-testing` to the registries.
  - Builds a changelog.
  - Creates a **draft** GitHub release with tag name `<resolved_tag>-testing`.

This workflow is intended for maintainers to validate changes to the release
pipeline (tagging, changelog generation, image build) in a safe way while
keeping production tags immutable.
