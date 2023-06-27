FROM python:3.11.3-alpine3.16 as base

FROM base as builder
WORKDIR /app
RUN python -m venv .venv && .venv/bin/pip install --no-cache-dir -U pip setuptools
COPY        src/requirements.txt /app/requirements.txt
RUN apk add --no-cache gcc && \
	.venv/bin/pip install --no-cache-dir -r requirements.txt && \
    rm requirements.txt && \
	find /app/.venv \( -type d -a -name test -o -name tests \) -o \( -type f -a -name '*.pyc' -o -name '*.pyo' \) -exec rm -rf '{}' \+
COPY        src/ /app/


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
