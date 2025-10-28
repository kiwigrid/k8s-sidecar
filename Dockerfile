FROM python:alpine3.22 AS base

FROM base AS builder
WORKDIR /app
RUN python -m venv .venv && .venv/bin/pip install --no-cache-dir -U pip setuptools
COPY        src/ /app/
RUN apk add --no-cache gcc && \
    if [ "$TARGETARCH" = "s390x" ]; then \
        echo "s390x detected, installing pydantic without binary." && \
        PYDANTIC_NO_BINARY=1 .venv/bin/pip install --no-cache-dir -r requirements.txt; \
    else \
        .venv/bin/pip install --no-cache-dir -r requirements.txt; \
    fi && \
    rm requirements.txt && \
	find /app/.venv \( -type d -a -name test -o -name tests \) -o \( -type f -a -name '*.pyc' -o -name '*.pyo' \) -exec rm -rf '{}' \+


FROM base
LABEL org.opencontainers.image.source=https://github.com/kiwigrid/k8s-sidecar
LABEL org.opencontainers.image.description="K8s sidecar image to collect configmaps and secrets as files"
LABEL org.opencontainers.image.licenses=MIT
ENV         PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
# Use the nobody user's numeric UID/GID to satisfy MustRunAsNonRoot PodSecurityPolicies
# https://kubernetes.io/docs/concepts/policy/pod-security-policy/#users-and-groups
USER        65534:65534
CMD         [ "python", "-u", "/app/sidecar.py" ]
