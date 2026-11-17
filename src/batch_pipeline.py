"""Reproducible batch ETL and analytics. All outputs use schema version 2."""
import json
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from project_config import DATA_DIR, RESULTS_DIR, SCHEMA_VERSION, HDFS_ROOT
from data_contract import add_submission_year, add_categories, add_tokens

HOT_KEYWORDS = ["transformer", "attention", "bert", "gpt", "diffusion", "reinforcement",
                "federated", "quantum", "generative", "adversarial", "multimodal",
                "contrastive", "self-supervised", "neural", "deep", "graph"]

# K-Means is trained and evaluated on deterministic samples so the run fits on a laptop.
MAX_MODEL_TRAIN_DOCUMENTS = 200_000
MAX_MODEL_TEST_DOCUMENTS = 50_000


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temp.replace(path)


def invalidate_results():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "manifest.json").unlink(missing_ok=True)


def preprocess(spark):
    from pyspark.sql import functions as F
    invalidate_results()
    (DATA_DIR / "clean_manifest.json").unlink(missing_ok=True)
    started = time.perf_counter()
    raw = spark.read.parquet(str(DATA_DIR / "arxiv_data.parquet"))
    raw_count = raw.count()
    required = ["id", "title", "abstract", "categories"]
    missing = set(required) - set(raw.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    df = add_submission_year(raw)
    valid = F.col("year").between(1991, datetime.now(timezone.utc).year)
    for col in required:
        valid = valid & F.col(col).isNotNull() & (F.length(F.trim(col)) > 0)
    df = df.filter(valid).cache()
    valid_count = df.count()
    # Conflicting duplicate IDs are rejected. Arbitrary dropDuplicates would select an unknown version.
    conflicts = df.groupBy("id").count().filter("count > 1").count()
    if conflicts:
        df.unpersist()
        raise ValueError(f"Found {conflicts} duplicate IDs; resolve source versions before ETL")
    clean = add_tokens(add_categories(df))
    if "authors" not in clean.columns:
        clean = clean.withColumn("authors", F.lit(None).cast("string"))
    if "authors_parsed" not in clean.columns:
        clean = clean.withColumn("authors_parsed", F.lit(None).cast("array<array<string>>"))
    clean = (clean.withColumn("title_length", F.length("title"))
             .withColumn("abstract_length", F.length("abstract"))
             .withColumn("token_count", F.size("abstract_tokens"))
             .withColumn("decade", F.concat((F.floor(F.col("year") / 10) * 10).cast("int"), F.lit("s"))))
    columns = ["id", "title", "abstract", "authors", "authors_parsed", "categories",
               "year", "submission_year", "update_year", "id_year", "submitted_at", "year_source", "decade", "category_list",
               "primary_category", "main_group", "title_length", "abstract_length",
               "clean_abstract", "abstract_tokens", "token_count"]
    clean.select(columns).write.mode("overwrite").parquet(str(DATA_DIR / "arxiv_clean.parquet"))
    df.unpersist()
    verified = spark.read.parquet(str(DATA_DIR / "arxiv_clean.parquet"))
    stats = verified.agg(F.count("*").alias("rows"), F.min("year").alias("min_year"), F.max("year").alias("max_year")).first().asDict()
    stats["v1_id_year_differences"] = verified.filter("year != id_year").count()
    if not stats["rows"] or stats["rows"] != valid_count:
        raise ValueError("Empty dataset or row-count mismatch after Parquet write")
    metadata = dict(schema_version=SCHEMA_VERSION, clean_run_id=str(uuid.uuid4()), raw_rows=raw_count,
                    rejected_rows=raw_count-valid_count, seconds=time.perf_counter()-started,
                    year_definition="first_arxiv_submission", **stats)
    source_manifest = DATA_DIR / "source_manifest.json"
    metadata["source"] = json.loads(source_manifest.read_text(encoding="utf-8")) if source_manifest.exists() else {"revision": "unknown_existing_local_files", "scope": "downloaded_shards_only"}
    save_json(DATA_DIR / "clean_manifest.json", metadata)
    return metadata


def with_growth(frame, keys, value_col):
    """All inputs must contain every calendar year, including zero counts."""
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window
    window = Window.partitionBy(*keys).orderBy("year") if keys else Window.orderBy("year")
    return (frame.withColumn("previous_count", F.lag(value_col).over(window))
            .withColumn("yoy_growth_rate", F.when(F.col("previous_count") > 0,
                        (F.col(value_col) / F.col("previous_count") - 1) * 100)))


def analyze(spark, clusters=10, train_clusters=True):
    from pyspark.sql import functions as F
    from pyspark.ml.feature import CountVectorizer, IDF, Normalizer
    from pyspark.ml.clustering import KMeans
    clean_meta = json.loads((DATA_DIR / "clean_manifest.json").read_text(encoding="utf-8"))
    if clean_meta.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Run preprocessing with current schema first")
    invalidate_results()
    save_json(RESULTS_DIR / "clusters.json", [])
    (RESULTS_DIR / "topics.json").unlink(missing_ok=True)
    shutil.rmtree(RESULTS_DIR / "lda_model", ignore_errors=True)
    started = time.perf_counter()
    df = spark.read.parquet(str(DATA_DIR / "arxiv_clean.parquet")).cache()
    count = df.count()
    if count != clean_meta["rows"]:
        raise ValueError("Clean data no longer matches its manifest")
    lo, hi = clean_meta["min_year"], clean_meta["max_year"]
    years = spark.range(lo, hi+1).select(F.col("id").cast("int").alias("year"))
    yearly = with_growth(years.join(df.groupBy("year").count(), "year", "left").fillna(0, ["count"]), [], "count")
    groups = df.select("main_group").distinct()
    field = (years.crossJoin(groups).join(df.groupBy("year", "main_group").count(), ["year", "main_group"], "left")
             .fillna(0, ["count"]).join(yearly.select("year", F.col("count").alias("year_total")), "year")
             .withColumn("percentage_share", F.when(F.col("year_total") > 0, F.col("count") / F.col("year_total") * 100)))
    field = with_growth(field, ["main_group"], "count")
    category = df.groupBy("year", "primary_category").count()
    from pyspark.sql.window import Window
    category = category.withColumn("rank", F.row_number().over(Window.partitionBy("year").orderBy(F.desc("count"), "primary_category")))
    words = df.select("id", "year", "main_group", F.explode("abstract_tokens").alias("word"))
    # countDistinct keeps one hash set per (year, word) group and blows up on long abstracts.
    # Deduplicating the token rows first gives the same document_count with a plain shuffle.
    frequencies = words.groupBy("year", "word").count().withColumnRenamed("count", "frequency")
    document_counts = (words.select("year", "word", "id").distinct().groupBy("year", "word").count()
                       .withColumnRenamed("count", "document_count"))
    word_counts = frequencies.join(document_counts, ["year", "word"], "inner")
    keyword_grid = years.crossJoin(spark.range(1).select(F.explode(F.array(*[F.lit(w) for w in HOT_KEYWORDS])).alias("word")))
    keywords = (keyword_grid.join(word_counts, ["year", "word"], "left").fillna(0, ["frequency", "document_count"])
                .join(yearly.select("year", F.col("count").alias("year_total")), "year")
                .withColumn("papers_per_1000", F.when(F.col("year_total") > 0, F.col("document_count") * 1000 / F.col("year_total"))))
    group_words = words.groupBy("main_group", "word").count()
    group_window = Window.partitionBy("main_group").orderBy(F.desc("count"), "word")
    group_terms = group_words.withColumn("rank", F.row_number().over(group_window)).filter("rank <= 50")
    field_metrics = (df.groupBy("main_group").agg(
        F.count("*").alias("papers"),
        F.avg(F.size("authors_parsed")).alias("avg_authors"),
        F.avg("abstract_length").alias("avg_abstract_length"),
        F.avg("token_count").alias("avg_token_count"),
        F.avg("title_length").alias("avg_title_length"),
        F.countDistinct("primary_category").alias("distinct_categories")))
    outputs = {"yearly_growth": yearly, "field_trends": field, "top_categories_yearly": category,
               "hot_keyword_trends": keywords, "field_metrics": field_metrics,
               "group_terms": group_terms,
               "top_terms": words.groupBy("word").count().orderBy(F.desc("count"), "word").limit(200)}
    # Parsed name components are arrays, never pass an array to trim().
    authors = df.select("id", "year", F.explode("authors_parsed").alias("parts"))
    authors = authors.withColumn("author", F.trim(F.concat_ws(" ", F.element_at("parts", 2), F.element_at("parts", 1))))
    authors = authors.filter(F.length("author") > 0).select("id", "year", "author").distinct()
    outputs["top_authors"] = authors.groupBy("author").count().orderBy(F.desc("count"), "author").limit(20)
    outputs["author_trends"] = (df.filter(F.size("authors_parsed") > 0).groupBy("year")
                                .agg(F.avg(F.size("authors_parsed")).alias("avg_authors"), F.count("*").alias("papers_with_parsed_authors")))
    timings = {}
    try:
        for name, frame in outputs.items():
            begin = time.perf_counter()
            frame.coalesce(1).write.mode("overwrite").parquet(str(RESULTS_DIR / f"{name}.parquet"))
            timings[name] = time.perf_counter()-begin
        model_metrics = {"status": "not_requested"}
        if train_clusters:
            begin = time.perf_counter()
            corpus = df.filter(F.size("abstract_tokens") > 0).select("id", "abstract_tokens")
            # Deterministic split by ID, vocabulary fitted only on training records.
            train = corpus.filter(F.pmod(F.xxhash64("id"), F.lit(5)) != 0)
            test = corpus.filter(F.pmod(F.xxhash64("id"), F.lit(5)) == 0)
            train_available, test_available = train.count(), test.count()
            if train_available < 2 or test_available < 1:
                model_metrics = {"status": "insufficient_documents"}
            else:
                # Train on a deterministic sample so the run fits on a laptop. sample() keeps the
                # original partitions; limit() would collapse the job to a single task.
                train_fraction = min(1.0, MAX_MODEL_TRAIN_DOCUMENTS / train_available)
                train_sample = train.sample(False, train_fraction, seed=42)
                vocab = CountVectorizer(inputCol="abstract_tokens", outputCol="features",
                                        vocabSize=10000, minDF=1.0).fit(train_sample)
                train_counts = vocab.transform(train_sample).cache()
                # TF-IDF gives rare, discriminative terms more weight than common words, which is
                # the standard input for K-Means on text.
                idf = IDF(inputCol="features", outputCol="tfidf_features").fit(train_counts)
                normalizer = Normalizer(inputCol="tfidf_features", outputCol="norm_features")
                train_vectors = normalizer.transform(idf.transform(train_counts)).cache()
                train_documents = train_vectors.count()
                vocab.write().overwrite().save(str(RESULTS_DIR / "vocabulary_model"))
                idf.write().overwrite().save(str(RESULTS_DIR / "idf_model"))
                normalizer.write().overwrite().save(str(RESULTS_DIR / "normalizer_model"))
                kmeans = KMeans(k=clusters, maxIter=20, seed=42, featuresCol="norm_features",
                                predictionCol="cluster").fit(train_vectors)
                kmeans.write().overwrite().save(str(RESULTS_DIR / "kmeans_model"))
                vocabulary = vocab.vocabulary
                cluster_terms = []
                for index, center in enumerate(kmeans.clusterCenters()):
                    values = center.toArray() if hasattr(center, "toArray") else list(center)
                    order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)[:10]
                    order = [i for i in order if values[i] > 0]
                    total = float(sum(values[i] for i in order)) or 1.0
                    cluster_terms.append({"cluster": index, "terms": [vocabulary[i] for i in order],
                                          "weights": [float(values[i] / total) for i in order]})
                # Cluster share is measured on a deterministic sample, never hard-coded.
                share_fraction = min(1.0, 5000 / max(train_documents, 1))
                sample = train_vectors.sample(False, share_fraction, seed=42).limit(5000)
                predicted = kmeans.transform(sample)
                counts = {row["cluster"]: row["count"] for row in predicted.groupBy("cluster").count().collect()}
                sampled = sum(counts.values()) or 1
                for item in cluster_terms:
                    item["share"] = counts.get(item["cluster"], 0) / sampled
                save_json(RESULTS_DIR / "clusters.json", cluster_terms)
                test_fraction = min(1.0, MAX_MODEL_TEST_DOCUMENTS / test_available)
                test_sample = test.sample(False, test_fraction, seed=42)
                # A test abstract whose tokens are all outside the vocabulary becomes a zero
                # vector; K-Means still assigns it to its nearest centroid, so no Python UDF
                # (and no dense 10k-float conversion) is needed here.
                test_vectors = normalizer.transform(idf.transform(vocab.transform(test_sample))).cache()
                test_count = test_vectors.count()
                model_metrics = {"status": "trained", "model_type": "kmeans", "features": "tfidf",
                                 "k": clusters, "vocabulary_size": len(vocabulary),
                                 "train_documents": train_documents, "train_available": train_available,
                                 "test_documents": test_count, "test_available": test_available,
                                 "train_wsse": float(kmeans.summary.trainingCost),
                                 "train_mean_sq_distance": float(kmeans.summary.trainingCost) / max(train_documents, 1),
                                 "seconds": time.perf_counter()-begin}
                train_counts.unpersist()
                train_vectors.unpersist()
                test_vectors.unpersist()
        manifest = dict(schema_version=SCHEMA_VERSION, clean_run_id=clean_meta["clean_run_id"],
                        generated_at=datetime.now(timezone.utc).isoformat(), rows=count, min_year=lo, max_year=hi,
                        groups=groups.count(), spark_version=spark.version, spark_master=spark.sparkContext.master,
                        scope="downloaded_shards_only_not_a_representative_sample", year_definition="first_arxiv_submission",
                        timings_seconds=timings, preprocessing_seconds=clean_meta["seconds"], model=model_metrics,
                        source=clean_meta.get("source"), total_analysis_seconds=time.perf_counter()-started)
        save_json(RESULTS_DIR / "manifest.json", manifest)
        return manifest
    finally:
        df.unpersist()


def sync_hdfs(spark):
    """Rewrite curated columns with exactly the Hive external-table schema."""
    from pyspark.sql import functions as F
    manifest = json.loads((DATA_DIR / "clean_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Run preprocessing first")
    from project_config import read_manifest
    read_manifest()
    df = spark.read.parquet(str(DATA_DIR / "arxiv_clean.parquet"))
    cols = ["id", "title", "abstract", "authors", "categories", "year", "submission_year", "update_year",
            "primary_category", "main_group", "abstract_tokens"]
    if df.count() != manifest["rows"]:
        raise ValueError("Clean data changed since preprocessing")
    target = f"{HDFS_ROOT}/data/arxiv_clean_v2"
    # Physical partitioning makes the Hive partition-pruning claim verifiable.
    df.select(cols).write.mode("overwrite").partitionBy("year").parquet(target)
    if spark.read.parquet(target).count() != manifest["rows"]:
        raise ValueError("HDFS row count does not match local clean data")
    spark.read.parquet(str(RESULTS_DIR / "hot_keyword_trends.parquet")).write.mode("overwrite").parquet(f"{HDFS_ROOT}/data/hot_keyword_trends_v2")
    return target


if __name__ == "__main__":
    import argparse
    from spark_common import create_spark_session
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["preprocess", "analyze", "sync-hdfs", "all"])
    parser.add_argument("--skip-clusters", action="store_true")
    args = parser.parse_args()
    spark = create_spark_session("ArXivBatch")
    try:
        if args.stage in ("preprocess", "all"):
            print(preprocess(spark))
        if args.stage in ("analyze", "all"):
            print(analyze(spark, train_clusters=not args.skip_clusters))
        if args.stage in ("sync-hdfs", "all"):
            print(sync_hdfs(spark))
    finally:
        spark.stop()
