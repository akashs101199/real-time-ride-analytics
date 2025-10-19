# Tiny layer on top of the official Spark image to add Prometheus client
FROM apache/spark:3.5.1-python3

USER root
RUN pip install --no-cache-dir prometheus_client
# Switch back to the default spark user
USER spark
