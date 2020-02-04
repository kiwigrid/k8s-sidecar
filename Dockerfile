FROM        python:3.7-slim
#create app directory
WORKDIR     /app
COPY        requirements.txt .
RUN         pip install -r requirements.txt
COPY        sidecar/* ./
ENV         PYTHONUNBUFFERED=1

#run as non-privileged user 
USER nobody
CMD         [ "python", "-u", "/app/sidecar.py" ]
