FROM python:3.15.0b2-alpine3.22@sha256:8374b202f092c233441f36b3018fd839c5c42d58b0a8ea479860f9ff2326d8cf AS base
RUN apk add --no-cache \
        libcrypto3=3.5.7-r0 \
        libssl3=3.5.7-r0

FROM base AS builder
# TARGETPLATFORM is automatically set by buildx (e.g., to "linux/arm/v7")
ARG TARGETPLATFORM
WORKDIR /app
RUN python -m venv .venv && .venv/bin/pip install --no-cache-dir pip==26.1.2
COPY        pyproject.toml /app/
COPY        src/ /app/src/
# Install dependencies based on the target platform
RUN case "$TARGETPLATFORM" in \
        "linux/arm/v7"|"linux/ppc64le"|"linux/riscv64") apk add --no-cache gcc musl-dev g++ libffi-dev openssl-dev cargo ;; \
        *) apk add --no-cache gcc musl-dev libffi-dev ;; \
    esac && \
    .venv/bin/pip install --no-cache-dir . && \
    find /app/.venv \( -type d -a -name test -o -name tests \) -o \( -type f -a -name '*.pyc' -o -name '*.pyo' \) -exec rm -rf '{}' \+


FROM base
ARG TARGETPLATFORM
RUN case "$TARGETPLATFORM" in \
        "linux/arm/v7"|"linux/ppc64le"|"linux/riscv64") apk add --no-cache libgcc libstdc++ ;; \
    esac
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
