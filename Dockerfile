FROM       python:3.7-slim-stretch
WORKDIR    /app
RUN        pip install kubernetes==8.0.1
COPY       sidecar/sidecar.py .
ENV        PYTHONUNBUFFERED=1
CMD [ "python", "-u", "/app/sidecar.py" ]
