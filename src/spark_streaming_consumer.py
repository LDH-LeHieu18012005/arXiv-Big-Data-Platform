"""Append Kafka events with durable checkpoints. Replay IDs remain separate events.

Use COUNT(DISTINCT id) to count papers.

Design notes
------------
* Invalid events never kill the stream. Each micro-batch is split: valid rows go to
  the partitioned Parquet sink, rejected rows go to ``/data/arxiv_stream_rejects_v2``
  with a ``reject_reason`` column. A poison message therefore cannot make the
  consumer crash-loop on the same checkpointed batch.
* The write path is implemented with ``foreachBatch`` only because a single streaming
  query cannot fan out to two sinks. Offsets are still committed by the streaming
  checkpoint after both writes finish.
"""
import argparse
import os
from data_contract import add_submission_year, add_categories, add_tokens
from project_config import HDFS_ROOT, OUTPUT_DIR
from spark_common import create_spark_session

REQUIRED_FIELDS = ("id", "title", "abstract", "categories")


def _reject_reason():
    """Null for a valid event, otherwise a short machine-readable reason."""
    from pyspark.sql import functions as F
    missing = F.lit(False)
    for key in REQUIRED_FIELDS:
        missing = missing | F.col(key).isNull() | (F.length(F.trim(key)) == 0)
    bad_year = F.col("year").isNull() | (
        F.col("supplied_year").isNotNull() & (F.col("supplied_year") != F.col("year"))
    )
    return (F.when(missing, F.lit("missing_required_field"))
             .when(bad_year, F.lit("invalid_year")))


def _write_batch(batch_df, batch_id, output_path, reject_path):
    """Split one micro-batch into the main lakehouse sink and the quarantine sink."""
    from pyspark.sql import functions as F
    batch_df = batch_df.persist()
    try:
        valid = batch_df.filter(F.col("_reject_reason").isNull()).drop("_reject_reason", "supplied_year")
        rejects = (batch_df.filter(F.col("_reject_reason").isNotNull())
                   .withColumnRenamed("_reject_reason", "reject_reason"))
        if not valid.isEmpty():
            valid.write.mode("append").partitionBy("main_group_clean").parquet(output_path)
        if not rejects.isEmpty():
            rejects.write.mode("append").parquet(reject_path)
    finally:
        batch_df.unpersist()


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
    clean = add_tokens(add_categories(add_submission_year(parsed)))
    # Tag instead of raising: one bad event must not stop ingestion forever.
    clean = clean.withColumn("_reject_reason", _reject_reason())
    clean = clean.drop("submission_year", "update_year", "category_list", "id_year", "year_source")
    clean = clean.withColumn("processed_time", F.current_timestamp()).withColumn("main_group_clean", F.col("main_group"))
    out_path = output_path or f"{HDFS_ROOT}/data/arxiv_stream_v2"
    reject_path = f"{HDFS_ROOT}/data/arxiv_stream_rejects_v2"
    return (clean.writeStream
            .foreachBatch(lambda batch_df, batch_id: _write_batch(batch_df, batch_id, out_path, reject_path))
            .option("checkpointLocation", checkpoint_dir or f"{HDFS_ROOT}/checkpoint/arxiv_stream_v2")
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
