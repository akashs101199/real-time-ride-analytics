# services/spark/app/streaming_job.py
import os
from pyspark.sql import SparkSession, functions as F, types as T

APP_NAME = "rides-streaming"

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "rides")

RAW_PARQUET_PATH = os.getenv("RAW_PARQUET_PATH", "/data/raw/rides")
CHECKPOINT_RAW = os.getenv("CHECKPOINT_RAW", "/data/checkpoints/raw")
CHECKPOINT_AGG = os.getenv("CHECKPOINT_AGG", "/data/checkpoints/agg")

POSTGRES_URL = os.getenv("POSTGRES_URL", "jdbc:postgresql://postgres:5432/rtp")
POSTGRES_USER = os.getenv("POSTGRES_USER", "rtp")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "rtp_password")
POSTGRES_TABLE = "public.rides_minute_metrics"

WINDOW = os.getenv("WINDOW", "1 minute")
WATERMARK = os.getenv("WATERMARK", "30 seconds")

# Choose how to write aggregates:
#  - "update_append" (default): keep every update (versioned history)
#  - "complete_overwrite": one row per window/city; table is fully refreshed each batch
AGG_WRITE_STRATEGY = os.getenv("AGG_WRITE_STRATEGY", "update_append").lower()


def build_spark() -> SparkSession:
    spark = (
        SparkSession.builder.appName(APP_NAME)
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", os.getenv("SPARK_SHUFFLE_PARTITIONS", "4"))
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("INFO")
    return spark


def log_boot():
    print("[boot] starting rides-streaming")
    print(f"[boot] kafka={KAFKA_BROKER} topic={KAFKA_TOPIC} startingOffsets=earliest failOnDataLoss=false")
    print(f"[boot] raw_path={RAW_PARQUET_PATH} ckpt_raw={CHECKPOINT_RAW} ckpt_agg={CHECKPOINT_AGG}")
    print(f"[boot] window={WINDOW} watermark={WATERMARK}")
    print(f"[boot] agg_write_strategy={AGG_WRITE_STRATEGY}")


def schema_for_events() -> T.StructType:
    return T.StructType(
        [
            T.StructField("event_time", T.StringType(), True),
            T.StructField("ride_id", T.LongType(), True),
            T.StructField("driver_id", T.LongType(), True),
            T.StructField("city", T.StringType(), True),
            T.StructField("pickup_ts", T.StringType(), True),
            T.StructField("dropoff_ts", T.StringType(), True),
            T.StructField("fare", T.DoubleType(), True),
            T.StructField("status", T.StringType(), True),
        ]
    )


def read_kafka_stream(spark: SparkSession, schema: T.StructType):
    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BROKER)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", "false")
        .load()
    )

    parsed = (
        raw.select(F.col("value").cast("string").alias("json_str"))
        .select(F.from_json("json_str", schema).alias("data"))
        .select("data.*")
    )

    for c in ["event_time", "pickup_ts", "dropoff_ts"]:
        parsed = parsed.withColumn(c, F.to_timestamp(F.col(c)))

    parsed = parsed.filter(
        F.col("event_time").isNotNull() & F.col("city").isNotNull() & F.col("fare").isNotNull()
    )

    parsed = parsed.withColumn(
        "duration_sec",
        F.when(
            F.col("pickup_ts").isNotNull() & F.col("dropoff_ts").isNotNull(),
            F.col("dropoff_ts").cast("long") - F.col("pickup_ts").cast("long"),
        ).cast("double"),
    )

    return parsed


def write_raw_sink(df):
    return (
        df.writeStream.format("parquet")
        .option("path", RAW_PARQUET_PATH)
        .option("checkpointLocation", CHECKPOINT_RAW)
        .queryName("rides-raw")
        .outputMode("append")
        .start()
    )


def make_aggregates(df):
    agg = (
        df.withWatermark("event_time", WATERMARK)
        .groupBy(F.window("event_time", WINDOW), F.col("city"))
        .agg(
            F.count(F.lit(1)).alias("events"),
            F.avg("fare").alias("avg_fare"),
            F.expr("percentile_approx(fare, 0.95)").alias("p95_fare"),
            F.avg("duration_sec").alias("avg_duration_sec"),
        )
        .select(
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            F.col("city"),
            F.col("events").cast("bigint"),
            F.round(F.col("avg_fare"), 2).alias("avg_fare"),
            F.round(F.col("p95_fare"), 2).alias("p95_fare"),
            F.round(F.col("avg_duration_sec"), 2).alias("avg_duration_sec"),
        )
    )
    return agg


def foreach_batch_append(batch_df, batch_id: int):
    count = batch_df.count()
    print(f"[foreachBatch] (append/update) batch {batch_id}: writing {count} rows to {POSTGRES_TABLE}")
    if count == 0:
        return
    (
        batch_df.write.format("jdbc")
        .option("url", POSTGRES_URL)
        .option("dbtable", POSTGRES_TABLE)
        .option("user", POSTGRES_USER)
        .option("password", POSTGRES_PASSWORD)
        .option("driver", "org.postgresql.Driver")
        .mode("append")
        .save()
    )


def foreach_batch_overwrite(batch_df, batch_id: int):
    count = batch_df.count()
    print(f"[foreachBatch] (complete/overwrite) batch {batch_id}: writing {count} rows to {POSTGRES_TABLE}")
    # overwrite + truncate keeps exactly one row per (window, city)
    (
        batch_df.write.format("jdbc")
        .option("url", POSTGRES_URL)
        .option("dbtable", POSTGRES_TABLE)
        .option("user", POSTGRES_USER)
        .option("password", POSTGRES_PASSWORD)
        .option("driver", "org.postgresql.Driver")
        .option("truncate", "true")
        .mode("overwrite")
        .save()
    )


def write_agg_sink(agg_df):
    if AGG_WRITE_STRATEGY == "complete_overwrite":
        return (
            agg_df.writeStream
            .outputMode("complete")
            .foreachBatch(foreach_batch_overwrite)
            .option("checkpointLocation", CHECKPOINT_AGG)
            .queryName("rides-streaming")
            .trigger(processingTime="5 seconds")
            .start()
        )
    else:
        # default: keep the history of updates
        return (
            agg_df.writeStream
            .outputMode("update")
            .foreachBatch(foreach_batch_append)
            .option("checkpointLocation", CHECKPOINT_AGG)
            .queryName("rides-streaming")
            .trigger(processingTime="5 seconds")
            .start()
        )


def main():
    spark = build_spark()
    log_boot()
    schema = schema_for_events()
    print("[boot] parsed events schema:")
    for f in schema:
        print(f"  - {f.name}: {f.dataType.simpleString()}")

    events = read_kafka_stream(spark, schema)
    q_raw = write_raw_sink(events)
    print("[boot] started raw sink -> parquet")

    agg = make_aggregates(events)
    q_agg = write_agg_sink(agg)
    print("[boot] started aggregation sink -> Postgres")

    q_agg.awaitTermination()
    q_raw.awaitTermination()


if __name__ == "__main__":
    main()
