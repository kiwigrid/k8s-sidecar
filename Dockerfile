FROM        python:3.8-alpine
ENV         PYTHONUNBUFFERED=1
WORKDIR     /app

COPY        requirements.txt .
RUN         apk add --no-cache gcc && \
	        pip install -r requirements.txt && \
	        apk del -r gcc && \
            rm -rf /var/cache/apk/* requirements.txt

COPY        sidecar/* ./

# Use the nobody user's numeric UID/GID to satisfy MustRunAsNonRoot PodSecurityPolicies
# https://kubernetes.io/docs/concepts/policy/pod-security-policy/#users-and-groups
USER        65534:65534

CMD         [ "python", "-u", "/app/sidecar.py" ]
