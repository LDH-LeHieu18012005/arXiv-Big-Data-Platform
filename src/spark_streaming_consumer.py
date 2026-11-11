"""Append Kafka events with durable checkpoints. Replay IDs remain separate events.

Use COUNT(DISTINCT id) to count papers. Invalid events fail their microbatch instead
of silently disappearing. The error must be corrected before resuming ingestion.
"""
import argparse
import os
from data_contract import add_submission_year, add_categories, add_tokens
from project_config import HDFS_ROOT, OUTPUT_DIR
from spark_common import create_spark_session


def start_stream(spark, kafka_servers=None, topic=None, output_path=None, checkpoint_dir=None):
    from pyspark.sql import functions as F
    from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType
    schema = StructType([StructField(name, StringType()) for name in ("id", "title", "authors", "categories", "abstract", "submitted_at")]
                        + [StructField("year", IntegerType()), StructField("timestamp", DoubleType())])
    raw = (spark.readStream.format("kafka")
           .option("kafka.bootstrap.servers", kafka_servers or os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092"))
           .option("subscribe", topic or os.getenv("KAFKA_TOPIC", "arxiv-papers-v2"))
           .option("startingOffsets", "earliest").option("failOnDataLoss", "true").load())
    parsed = raw.select(F.from_json(F.col("value").cast("string"), schema, {"mode": "FAILFAST"}).alias("paper")).select("paper.*")
    parsed = parsed.withColumnRenamed("year", "supplied_year")
    # Check basic required fields before the NLP transformers encounter nulls.
    valid = F.lit(True)
    for key in ("id", "title", "abstract", "categories"):
        valid = valid & F.col(key).isNotNull() & (F.length(F.trim(key)) > 0)
    parsed = parsed.withColumn("_valid", F.when(valid, F.lit(True)).otherwise(F.raise_error("Invalid required fields"))).filter("_valid = true").drop("_valid")
    clean = add_tokens(add_categories(add_submission_year(parsed)))
    valid_year = F.col("year").isNotNull() & (F.col("supplied_year").isNull() | (F.col("supplied_year") == F.col("year")))
    clean = clean.withColumn("_valid", F.when(valid_year, F.lit(True)).otherwise(F.raise_error("Invalid arXiv year")))
    clean = clean.filter("_valid = true").drop("_valid", "supplied_year", "submission_year", "update_year", "category_list", "id_year", "year_source")
    clean = clean.withColumn("processed_time", F.current_timestamp()).withColumn("main_group_clean", F.col("main_group"))
    return (clean.writeStream.format("parquet").outputMode("append")
            .option("path", output_path or f"{HDFS_ROOT}/data/arxiv_stream_v2")
            .option("checkpointLocation", checkpoint_dir or f"{HDFS_ROOT}/checkpoint/arxiv_stream_v2")
            .option("compression", "snappy").partitionBy("main_group_clean")
            .trigger(processingTime="5 seconds").start())


def run_streaming_pipeline(**kwargs):
    spark = create_spark_session("ArXivStreaming", kafka=True)
    try:
        start_stream(spark, **kwargs).awaitTermination()
    finally:
        spark.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    options = dict(output_path=str(OUTPUT_DIR / "stream_parquet_v2"), checkpoint_dir=str(OUTPUT_DIR / "checkpoint_v2")) if args.local else {}
    run_streaming_pipeline(**options)
