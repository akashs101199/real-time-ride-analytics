import json
import os
import random
import time
from datetime import datetime, timezone, timedelta

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
from prometheus_client import Counter, Gauge, start_http_server

BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "rides")

msgs_sent = Counter("producer_messages_sent", "Messages successfully sent")
errs = Counter("producer_errors", "Produce errors")
rate_gauge = Gauge("producer_target_msgs_per_sec", "Target send rate per second")

cities = ["Austin", "Chicago", "NYC", "SF", "Seattle"]


def make_event():
    now = datetime.now(timezone.utc)
    pickup = now - timedelta(seconds=random.randint(0, 30))
    duration = random.expovariate(1 / 600)  # avg 10 min, long-tail
    dropoff = pickup + timedelta(seconds=duration)
    fare = round(max(3.0, random.gauss(18, 7) + (duration / 300)), 2)
    return {
        "event_time": now.isoformat(),
        "ride_id": random.randint(1_000_000, 9_999_999),
        "driver_id": random.randint(1000, 9999),
        "city": random.choice(cities),
        "pickup_ts": pickup.isoformat(),
        "dropoff_ts": dropoff.isoformat(),
        "fare": float(fare),
        "status": "completed",
    }


def get_producer():
    """Create a Kafka producer with a retry mechanism."""
    retries = 5
    for i in range(retries):
        try:
            print(f"Connecting to Kafka broker at {BROKER} (attempt {i+1}/{retries})...")
            producer = KafkaProducer(
                bootstrap_servers=BROKER,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            print("Successfully connected to Kafka.")
            return producer
        except NoBrokersAvailable:
            print("Kafka broker not available. Retrying in 5 seconds...")
            time.sleep(5)
    raise ConnectionError("Could not connect to Kafka after several retries.")


if __name__ == "__main__":
    start_http_server(8000)
    producer = get_producer()

    target_rate = 200  # msgs/sec (tweak as needed)
    rate_gauge.set(target_rate)
    interval = 0.1
    batch = int(target_rate * interval)

    while True:
        start = time.time()
        for _ in range(batch):
            try:
                producer.send(TOPIC, make_event())
                msgs_sent.inc()
            except Exception:
                errs.inc()
        producer.flush()
        time.sleep(max(0, interval - (time.time() - start)))
