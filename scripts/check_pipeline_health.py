"""Read-only health report for the running demo stack (run inside the dashboard container)."""
import json
import os
import sys

sys.path.insert(0, "/app/src")
from hive_client import query_hive
from hdfs_helper import list_hdfs_dir
from project_config import RESULTS_DIR, DATA_DIR

print("== manifest ==")
manifest = json.loads((RESULTS_DIR / "manifest.json").read_text(encoding="utf-8"))
for key in ("rows", "min_year", "max_year", "groups", "schema_version", "scope", "year_definition",
            "preprocessing_seconds", "total_analysis_seconds", "spark_version"):
    print(" ", key, "=", manifest.get(key))
print("  model =", {k: manifest.get("model", {}).get(k) for k in ("status", "model_type", "k", "train_documents", "test_documents", "train_mean_sq_distance")})

print("\n== local data ==")
for name in ("arxiv_data.parquet", "arxiv_clean.parquet"):
    p = DATA_DIR / name
    print(" ", name, "exists" if p.exists() else "MISSING")
print("  clean_manifest:", json.loads((DATA_DIR / "clean_manifest.json").read_text(encoding="utf-8")) if (DATA_DIR / "clean_manifest.json").exists() else "MISSING")

print("\n== HDFS ==")
for path in ("/data", "/data/arxiv_clean_v2", "/data/arxiv_stream_v2", "/data/hot_keyword_trends_v2"):
    try:
        entries = list_hdfs_dir(path)
        print(f"  {path}: {len(entries)} entries", [e.get('pathSuffix') for e in entries][:6])
    except Exception as exc:
        print(" ", path, "ERR", exc)

print("\n== Hive ==")
checks = {
    "databases": "SHOW DATABASES",
    "tables": "SHOW TABLES IN arxiv_db",
    "historical_partitions": "SHOW PARTITIONS arxiv_historical",
    "stream_partitions": "SHOW PARTITIONS arxiv_stream",
    "historical_rows": "SELECT COUNT(*) AS n FROM arxiv_historical",
    "stream_rows": "SELECT COUNT(*) AS n FROM arxiv_stream",
    "stream_distinct": "SELECT COUNT(DISTINCT id) AS n FROM arxiv_stream",
    "groups": "SELECT main_group, COUNT(*) AS n FROM arxiv_historical GROUP BY main_group ORDER BY n DESC",
}
for name, sql in checks.items():
    try:
        df = query_hive(sql)
        print(f"  {name}:")
        print(df.to_string(max_rows=20, index=False))
    except Exception as exc:
        print(f"  {name}: ERROR {exc}")
