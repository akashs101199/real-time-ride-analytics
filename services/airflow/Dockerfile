FROM apache/airflow:2.9.2-python3.11

ARG AIRFLOW_VERSION=2.9.2
ARG PYTHON_VERSION=3.11

ENV AIRFLOW_HOME=/opt/airflow
ENV VENV_PATH=/opt/airflow/venv
ENV CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

USER airflow

RUN python -m venv "${VENV_PATH}" \
 && "${VENV_PATH}/bin/pip" install --upgrade pip setuptools wheel \
 && "${VENV_PATH}/bin/pip" install --no-cache-dir \
      --constraint "${CONSTRAINT_URL}" \
      apache-airflow-providers-docker \
      psycopg2-binary

ENV PATH="${VENV_PATH}/bin:${PATH}"
