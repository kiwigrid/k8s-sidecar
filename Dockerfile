# Stage 1 - Install build dependencies
FROM python:3.8-alpine AS builder

WORKDIR /app

RUN python -m venv .venv && .venv/bin/pip install --no-cache-dir -U pip setuptools

COPY requirements.txt .

RUN apk add --no-cache gcc && \
	.venv/bin/pip install --no-cache-dir -r requirements.txt && \
	find /app/.venv \( -type d -a -name test -o -name tests \) -o \( -type f -a -name '*.pyc' -o -name '*.pyo' \) -exec rm -rf '{}' \+

# Stage 2 - Copy only necessary files to the runner stage
FROM python:3.8-alpine

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /app /app

COPY sidecar/* ./

ENV PATH="/app/.venv/bin:$PATH"

# Use the nobody user's numeric UID/GID to satisfy MustRunAsNonRoot PodSecurityPolicies
# https://kubernetes.io/docs/concepts/policy/pod-security-policy/#users-and-groups
USER        65534:65534

CMD         [ "python", "-u", "/app/sidecar.py" ]
