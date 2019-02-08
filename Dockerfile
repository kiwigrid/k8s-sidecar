FROM        python:3.7-slim
COPY        requirements.txt /app/
RUN         pip install -r /app/requirements.txt
COPY        sidecar/sidecar.py /app/
ENV         PYTHONUNBUFFERED=1
WORKDIR     /app/
CMD         [ "python", "-u", "/app/sidecar.py" ]
