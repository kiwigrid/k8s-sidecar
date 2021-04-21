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

#if [ -n "${CIRCLE_PULL_REQUEST}" ]; then
  echo -e "\\nTesting in Kubernetes ${K8S_VERSION}\\n"

  log(){
    echo "[$(date --rfc-3339=seconds -u)] $1"
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
  }

  install_sidecar(){
    log "Installing sidecar..."
    kubectl apply -f "${CWD}"/test/sidecar.yaml
  }

  install_configmap(){
    log "Installing resources..."
    kubectl apply -f "${CWD}"/test/resources.yaml
  }

  list_pods(){
    log "Retrieving pods..."
    kubectl get pods -oyaml
  }


  log_sidecar(){
    log "Retrieving sidecar logs..."
    kubectl logs sidecar
  }

  verify_resources_read(){
    log "Downloading resource files from sidecar..."
    kubectl cp sidecar:/tmp/hello.world /tmp/hello.world
    kubectl cp sidecar:/tmp/cm-kubelogo.png /tmp/cm-kubelogo.png
    kubectl cp sidecar:/tmp/secret-kubelogo.png /tmp/secret-kubelogo.png
    kubectl cp sidecar:/tmp/script_result /tmp/script_result
    kubectl cp sidecar:/tmp/absolute/absolute.txt /tmp/absolute.txt
    kubectl cp sidecar:/tmp/relative/relative.txt /tmp/relative.txt
    
    log "Verifying file content..."
    echo -n "Hello World!" | diff - /tmp/hello.world \
      && diff ${CWD}/kubelogo.png /tmp/cm-kubelogo.png \
      && diff ${CWD}/kubelogo.png /tmp/secret-kubelogo.png \
      && echo -n "This absolutely exists" | diff - /tmp/absolute.txt \
      && echo -n "This relatively exists" | diff - /tmp/relative.txt \
      && ls /tmp/script_result
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
      create_kind_cluster
      install_sidecar
      sleep 15
      install_configmap
      sleep 15
      list_pods
      log_sidecar
      verify_resources_read
  }
  main
