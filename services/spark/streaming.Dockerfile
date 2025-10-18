# Tiny layer on top of Bitnami Spark, just to add Python for PySpark
FROM bitnami/spark:3.5.1

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip \
 && pip3 install --no-cache-dir prometheus_client \
 && rm -rf /var/lib/apt/lists/*
# convenience symlink (some tools call "python")
RUN ln -s /usr/bin/python3 /usr/bin/python || true
USER 1001
