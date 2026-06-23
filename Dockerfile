FROM python:3.15.0b2-alpine3.22 AS base

FROM base AS builder
# TARGETPLATFORM is automatically set by buildx (e.g., to "linux/arm/v7")
ARG TARGETPLATFORM
WORKDIR /app
RUN python -m venv .venv && .venv/bin/pip install --no-cache-dir -U pip setuptools
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
CMD         [ "python", "-u", "-m", "sidecar" ]
