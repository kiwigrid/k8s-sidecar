#!/usr/bin/env bash

set -x

CONTAINER_CLI="${CONTAINER_CLI:-podman}"

name="k8s-sidecar"
version="v1.30.7"
registry="container-registry.oracle.com/olcne"
docker_tag=${registry}/${name}:v${version}

"${CONTAINER_CLI}" build --pull \
    --build-arg https_proxy=${https_proxy} \
    --volume /etc/yum.repos.d:/etc/yum.repos.d \
    --tag ${docker_tag} -f ./olm/builds/Dockerfile .
