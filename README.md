# Real-Time Data Pipeline (Beginner Friendly)

This starter lets you run a real-time pipeline on your computer using Docker.

**What it does**
- Makes pretend "rideshare" events (like taxi rides).
- Sends them into Kafka (a message queue).
- Spark reads them, cleans them, and makes minute-by-minute stats.
- Stats go into Postgres (a database) and also Parquet files.
- Streamlit shows pretty charts.
- Prometheus + Promtail send metrics/logs to Grafana Cloud (optional).
- Airflow runs a small nightly job to tidy files.

## One-time setup
1) Install Docker Desktop and Git.
2) Copy `.env.example` to `.env` and fill in:
   - `SLACK_WEBHOOK_URL` (optional)
   - Grafana Cloud `PROM_*` and `LOKI_*` (optional)
3) In a terminal, run:
   ```bash
   docker compose up -d --build
   ```

## Open these in your browser
- Spark UI: http://localhost:8080
- Streamlit: http://localhost:8501
- Airflow: http://localhost:8088
- Prometheus (local check): http://localhost:9090

## Stop everything
```bash
docker compose down -v
```
# real-time-ride-analytics
