FROM        python:3.7-alpine AS builder
ENV         PYTHONUNBUFFERED=1
WORKDIR     /app

COPY        requirements.txt .
RUN         apk add --no-cache gcc && \
	    pip install -r requirements.txt && \
	    apk del gcc

COPY sidecar/* ./

#run as non-privileged user 
USER nobody
CMD         [ "python", "-u", "/app/sidecar.py" ]
