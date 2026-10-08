FROM python:3.14.8-alpine3.24@sha256:f6a589d43c42b9e7f7dc67a12d37132491f362859a5d750607710cc56da3bc72 AS base
RUN apk add --no-cache \
        libcrypto3=3.5.9-r0 \
        libssl3=3.5.9-r0

FROM base AS builder
WORKDIR /app
RUN python -m venv .venv && .venv/bin/pip install --no-cache-dir pip==26.1.2
COPY        pyproject.toml /app/
COPY        src/ /app/src/
# A C toolchain is enough for dependencies without a wheel for the target
# platform (e.g. PyYAML); no Rust/C++ dependency is left since kubernetes 35.
RUN apk add --no-cache \
        gcc=15.2.0-r5 \
        musl-dev=1.2.6-r2 && \
    .venv/bin/pip install --no-cache-dir . && \
    find /app/.venv \( -type d -a -name test -o -name tests \) -o \( -type f -a -name '*.pyc' -o -name '*.pyo' \) -exec rm -rf '{}' \+


FROM base
LABEL org.opencontainers.image.source=https://github.com/kiwigrid/k8s-sidecar
LABEL org.opencontainers.image.description="K8s sidecar image to collect configmaps and secrets as files"
LABEL org.opencontainers.image.licenses=MIT
ENV         PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /app/.venv ./.venv
ENV PATH="/app/.venv/bin:$PATH"
# Use the nobody user's numeric UID/GID to satisfy MustRunAsNonRoot PodSecurityPolicies
# https://kubernetes.io/docs/concepts/policy/pod-security-policy/#users-and-groups
USER        65534:65534
ENTRYPOINT  [ "python", "-u", "-m", "sidecar" ]
