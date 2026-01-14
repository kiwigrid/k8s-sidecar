FROM python:3.9-alpine
RUN pip install fastapi uvicorn
EXPOSE 80
COPY server.py /server.py
COPY static /static/
CMD ["uvicorn", "server:app", "--host", "", "--port", "80"]
