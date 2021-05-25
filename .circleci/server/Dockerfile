FROM python:3.7

RUN pip install fastapi uvicorn

EXPOSE 80

ARG SERVER_FILE="./.circleci/server/server.py"

COPY $SERVER_FILE /server.py

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "80"]
