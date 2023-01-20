FROM python:3.9-alpine
RUN pip install fastapi uvicorn
EXPOSE 80
COPY server.py /server.py
COPY static /static/
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "80"]
