import os
from datetime import date, timedelta
from pyspark.sql import SparkSession

RAW_PARQUET_PATH = os.getenv("RAW_PARQUET_PATH", "/data/raw/rides")

spark = SparkSession.builder.appName("parquet-compaction").getOrCreate()
yday = date.today() - timedelta(days=1)
indir = f"{RAW_PARQUET_PATH}/date={yday.isoformat()}"
outdir = indir  # overwrite partition

df = spark.read.parquet(indir)
(df.coalesce(2)
   .write.mode("overwrite")
   .parquet(outdir))

spark.stop()
