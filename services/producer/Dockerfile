FROM python:3.11-slim
WORKDIR /app
COPY producer.py /app/
RUN pip install --no-cache-dir kafka-python prometheus_client
CMD ["python", "producer.py"]
