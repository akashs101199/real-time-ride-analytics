from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator

def mk_vol(host, cont, ro=False):
    return {"bind": cont, "mode": "ro" if ro else "rw"}

with DAG(
    dag_id="daily_parquet_compaction",
    schedule="0 3 * * *",  # 3am daily
    start_date=datetime(2025, 1, 1),
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["batch"],
) as dag:

    compact = DockerOperator(
        task_id="compact_yesterday",
        # Use the same official Spark image as the rest of the cluster
        image="apache/spark:3.5.1-python3",
        auto_remove=True,
        command=(
            # Note the updated path for the official image
            "/opt/spark/bin/spark-submit "
            "/opt/spark-apps/batch_compact.py"
        ),
        mounts=[
            mk_vol("${PWD}/services/spark/app", "/opt/spark-apps", ro=True),
            mk_vol("${PWD}/data", "/data", ro=False),
        ],
        docker_url="unix://var/run/docker.sock",
        network_mode="host",
    )