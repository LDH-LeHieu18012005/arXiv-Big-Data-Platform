"""Shared paths and output contract; independent of the current directory."""
import json
import os
from pathlib import Path

BASE_DIR = Path(os.getenv("ARXIV_BASE_DIR", Path(__file__).resolve().parents[1]))
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
RESULTS_DIR = OUTPUT_DIR / "analysis_results"
SCHEMA_VERSION = 2
HDFS_ROOT = os.getenv("HDFS_NAMENODE", "hdfs://namenode:9000")


def read_manifest():
    path = RESULTS_DIR / "manifest.json"
    if not path.exists():
        raise RuntimeError("Kết quả cũ/chưa được xác minh. Hãy chạy lại notebook 02 và 03.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("Schema kết quả không tương thích; cần chạy lại pipeline batch.")
    clean_path = DATA_DIR / "clean_manifest.json"
    if not clean_path.exists() or json.loads(clean_path.read_text(encoding="utf-8")).get("clean_run_id") != value.get("clean_run_id"):
        raise RuntimeError("Dữ liệu sạch đã thay đổi; hãy chạy lại bước phân tích.")
    return value
