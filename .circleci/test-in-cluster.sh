#!/usr/bin/env bash
#
# install sidecar in kubernetes kind
#

set -o errexit
set -o pipefail
set -o nounset;


CLUSTER_NAME="sidecar-testing"
BIN_DIR="$(mktemp -d)"
KIND="${BIN_DIR}/kind"
CWD="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
KIND_CONFIG="${CWD}/kind-config.yaml"
SIDECAR_MANIFEST="${CWD}/test/sidecar.yaml"

log(){
  echo "[$(date --rfc-3339=seconds -u)] $1"
}

build_dummy_server(){
  docker build -t dummy-server:1.0.0 -f "${CWD}/server/Dockerfile"  .
}

install_kubectl(){
  log 'Installing kubectl...'
  curl -LO https://storage.googleapis.com/kubernetes-release/release/`curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt`/bin/linux/amd64/kubectl
  chmod +x ./kubectl
  sudo mv ./kubectl /usr/local/bin/kubectl
}

install_kind_release() {
  log 'Installing kind...'

  KIND_BINARY_URL="https://github.com/kubernetes-sigs/kind/releases/download/${KIND_VERSION}/kind-linux-amd64"
  wget -O "${KIND}" "${KIND_BINARY_URL}"
  chmod +x "${KIND}"
}

create_kind_cluster() {

    log "Creating cluster with kind config from ${KIND_CONFIG}"

    "${KIND}" create cluster --name "${CLUSTER_NAME}" --loglevel=debug --config "${KIND_CONFIG}" --image "kindest/node:${K8S_VERSION}"

    kubectl cluster-info
    echo

    log 'Waiting for cluster to be ready...'
    until ! grep --quiet 'NotReady' <(kubectl get nodes --no-headers); do
        printf '.'
        sleep 1
    done

    echo '✔︎'
    echo

    kubectl get nodes
    echo

    log 'Cluster ready!'
    echo

    "${KIND}" load docker-image  dummy-server:1.0.0 --name "${CLUSTER_NAME}"
}
wait_for_pod_ready() {
  while [[ $(kubectl get pods $1 -o 'jsonpath={..status.conditions[?(@.type=="Ready")].status}') != "True" ]]; do log "waiting for pod '$1' to become ready..." && sleep 1; done
  log "Pod '$1' ready."
}
install_sidecar(){
  log "Installing sidecar..."
  kubectl apply -f "${SIDECAR_MANIFEST}"
  wait_for_pod_ready "sidecar"
  wait_for_pod_ready "sidecar-5xx"
  wait_for_pod_ready "dummy-server-pod"
}

install_configmap(){
  log "Installing resources..."
  kubectl apply -f "${CWD}"/test/resources.yaml
}

list_pods(){
  log "Retrieving pods..."
  kubectl get pods -oyaml
}


pod_logs(){
  log "Retrieving logs of 'sidecar'..."
  kubectl logs sidecar
  log "Retrieving logs of 'sidecar-5xx'..."
  kubectl logs sidecar-5xx
  log "Retrieving logs of 'dummy-server-pod'..."
  kubectl logs dummy-server-pod
}

verify_resources_read(){
  log "Downloading resource files from sidecar..."
  kubectl cp sidecar:/tmp/hello.world /tmp/hello.world
  kubectl cp sidecar:/tmp/cm-kubelogo.png /tmp/cm-kubelogo.png
  kubectl cp sidecar:/tmp/secret-kubelogo.png /tmp/secret-kubelogo.png
  kubectl cp sidecar:/tmp/script_result /tmp/script_result
  kubectl cp sidecar:/tmp/absolute/absolute.txt /tmp/absolute.txt
  kubectl cp sidecar:/tmp/relative/relative.txt /tmp/relative.txt
  kubectl cp sidecar:/tmp/500.txt /tmp/500.txt || true

  log "Downloading resource files from sidecar-5xx..."
  kubectl cp sidecar-5xx:/tmp-5xx/hello.world /tmp/5xx/hello.world
  kubectl cp sidecar-5xx:/tmp-5xx/cm-kubelogo.png /tmp/5xx/cm-kubelogo.png
  kubectl cp sidecar-5xx:/tmp-5xx/secret-kubelogo.png /tmp/5xx/secret-kubelogo.png
  # script also generates into '/tmp'
  kubectl cp sidecar-5xx:/tmp/script_result /tmp/5xx/script_result
  # absolute path in configmap points to /tmp in 'absolute-configmap'
  kubectl cp sidecar-5xx:/tmp/absolute/absolute.txt /tmp/5xx/absolute.txt
  kubectl cp sidecar-5xx:/tmp-5xx/relative/relative.txt /tmp/5xx/relative.txt
  kubectl cp sidecar-5xx:/tmp-5xx/500.txt /tmp/5xx/500.txt

  log "Verifying file content from sidecar and sidecar-5xx ..."

  # this needs to be the last statement so that it defines the script exit code
  echo -n "Hello World!" | diff - /tmp/hello.world \
    && diff ${CWD}/kubelogo.png /tmp/cm-kubelogo.png \
    && diff ${CWD}/kubelogo.png /tmp/secret-kubelogo.png \
    && echo -n "This absolutely exists" | diff - /tmp/absolute.txt \
    && echo -n "This relatively exists" | diff - /tmp/relative.txt \
    && [ ! -f /tmp/500.txt ] && echo "No 5xx file created" \
    && ls /tmp/script_result \
    && echo -n "Hello World!" | diff - /tmp/5xx/hello.world \
    && diff ${CWD}/kubelogo.png /tmp/5xx/cm-kubelogo.png \
    && diff ${CWD}/kubelogo.png /tmp/5xx/secret-kubelogo.png \
    && echo -n "This absolutely exists" | diff - /tmp/5xx/absolute.txt \
    && echo -n "This relatively exists" | diff - /tmp/5xx/relative.txt \
    && echo -n "500" | diff - /tmp/5xx/500.txt \
    && ls /tmp/5xx/script_result
}

# cleanup on exit (useful for running locally)
cleanup() {
  "${KIND}" delete cluster || true
  rm -rf "${BIN_DIR}"
}
trap cleanup EXIT

main() {
    install_kubectl
    install_kind_release
    build_dummy_server
    create_kind_cluster
    install_sidecar
    install_configmap
    sleep 15
    list_pods
    pod_logs
    verify_resources_read
}
main
