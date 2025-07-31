FROM container-registry.oracle.com/os/oraclelinux:9
COPY rpms /tmp/
RUN dnf install -y /tmp/*.rpm &&\
    dnf clean all &&\
    rm -rf /var/cache/yum/* /tmp/*.rpm &&\
    test -d /LICENSES || ln -s /usr/share/licenses /LICENSES

FROM container-registry.oracle.com/os/oraclelinux:9-slim
COPY --from=0 /usr/share/licenses/k8s-sidecar* /LICENSES
COPY --from=0  /usr/local/share/olcne/k8s-sidecar /usr/src/k8s-sidecar

RUN microdnf install python3-pip &&\
    python3 -m pip install -r /usr/src/k8s-sidecar/src/requirements.txt

ENV         PYTHONUNBUFFERED=1
WORKDIR     /usr/src/k8s-sidecar/src

# Use the nobody user's numeric UID/GID to satisfy MustRunAsNonRoot PodSecurityPolicies
# https://kubernetes.io/docs/concepts/policy/pod-security-policy/#users-and-groups
USER        65534:65534

CMD         [ "python3", "-u", "./sidecar.py" ]
