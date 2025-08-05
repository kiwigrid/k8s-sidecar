FROM container-registry.oracle.com/os/oraclelinux:9-slim

COPY LICENSE SECURITY.md THIRD_PARTY_LICENSES.txt /usr/share/licenses/

COPY . /usr/src/k8s-sidecar

RUN microdnf install -y python3-pip && \
    microdnf clean all && \
    python3 -m pip install -r /usr/src/k8s-sidecar/src/requirements.txt

ENV         PYTHONUNBUFFERED=1
WORKDIR     /usr/src/k8s-sidecar/src

# Use the nobody user's numeric UID/GID to satisfy MustRunAsNonRoot PodSecurityPolicies
# https://kubernetes.io/docs/concepts/policy/pod-security-policy/#users-and-groups
USER        65534:65534

CMD         [ "python3", "-u", "./sidecar.py" ]
