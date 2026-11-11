"""One explicit Spark runtime for notebooks and services."""
import os


def create_spark_session(name="ArXiv", kafka=False):
    from pyspark.sql import SparkSession
    builder = (SparkSession.builder.appName(name)
               .master(os.getenv("SPARK_MASTER", "local[*]"))
               .config("spark.sql.shuffle.partitions", os.getenv("SPARK_SHUFFLE_PARTITIONS", "8"))
               .config("spark.sql.session.timeZone", "UTC")
               .config("spark.sql.ansi.enabled", "false")
               .config("spark.sql.parquet.outputTimestampType", "INT96")
               .config("spark.driver.memory", os.getenv("SPARK_DRIVER_MEMORY", "4g"))
               .config("spark.executor.memory", os.getenv("SPARK_EXECUTOR_MEMORY", "1500m")))
    if os.getenv("SPARK_DRIVER_HOST"):
        builder = builder.config("spark.driver.host", os.environ["SPARK_DRIVER_HOST"]).config("spark.driver.bindAddress", "0.0.0.0")
    if kafka:
        builder = builder.config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3")
    spark = builder.getOrCreate()
    if spark.version != "3.5.3":
        raise RuntimeError(f"Expected Spark 3.5.3, found {spark.version}. Rebuild Docker images.")
    spark.sparkContext.setLogLevel("WARN")
    return spark
