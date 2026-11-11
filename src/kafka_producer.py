"""Replay actual papers; count only messages acknowledged by Kafka."""
import argparse
import json
import os
import time
from pathlib import Path
from data_contract import validate_paper, year_from_arxiv_id, year_from_created
from project_config import DATA_DIR

DEFAULT_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
DEFAULT_TOPIC = os.getenv("KAFKA_TOPIC", "arxiv-papers-v2")


def get_kafka_producer(bootstrap_servers=DEFAULT_BOOTSTRAP_SERVERS):
    from kafka import KafkaProducer
    return KafkaProducer(bootstrap_servers=bootstrap_servers.split(","),
                         value_serializer=lambda v: json.dumps(v, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                         key_serializer=lambda k: k.encode("utf-8"),
                         acks="all", retries=3, max_block_ms=10000, request_timeout_ms=10000)


def sample_papers_from_local(parquet_path=None, limit=1000):
    import pyarrow.parquet as pq
    path = Path(parquet_path) if parquet_path else DATA_DIR / "arxiv_clean.parquet"
    files = sorted(path.glob("*.parquet")) if path.is_dir() else [path] if path.is_file() else []
    if not files:
        raise FileNotFoundError(f"Không có Parquet: {path}. Chạy notebook 00 và 02 trước.")
    if limit <= 0:
        return
    count = 0
    for file in files:
        for batch in pq.ParquetFile(file).iter_batches(batch_size=100):
            for row in batch.to_pylist():
                record = {key: row.get(key) for key in ("id", "title", "abstract", "categories", "authors")}
                record["authors"] = record["authors"] or ""
                record["submitted_at"] = row.get("submitted_at")
                if not record["submitted_at"] and row.get("versions"):
                    record["submitted_at"] = next((v.get("created") for v in row["versions"] if v.get("version") == "v1"), None)
                record["year"] = year_from_created(record["submitted_at"]) or year_from_arxiv_id(record["id"])
                record["timestamp"] = time.time()
                yield validate_paper(record)
                count += 1
                if count >= limit:
                    return


def send_single_paper(paper_dict, topic=DEFAULT_TOPIC, bootstrap_servers=DEFAULT_BOOTSTRAP_SERVERS):
    record = validate_paper(paper_dict)
    producer = get_kafka_producer(bootstrap_servers)
    try:
        return producer.send(topic, key=record["id"], value=record).get(timeout=15)
    finally:
        producer.close(timeout=5)


def stream_papers_simulation(num_records=50, delay_sec=0.5, topic=DEFAULT_TOPIC,
                             bootstrap_servers=DEFAULT_BOOTSTRAP_SERVERS, parquet_path=None):
    producer = get_kafka_producer(bootstrap_servers)
    sent = 0
    try:
        for record in sample_papers_from_local(parquet_path, num_records):
            producer.send(topic, key=record["id"], value=record).get(timeout=15)
            sent += 1
            print(f"Kafka acknowledged {sent}: {record['id']}")
            time.sleep(delay_sec)
        return sent
    finally:
        producer.close(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--servers", default=DEFAULT_BOOTSTRAP_SERVERS)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--num", type=int, default=20)
    parser.add_argument("--delay", type=float, default=0.2)
    args = parser.parse_args()
    print(stream_papers_simulation(args.num, args.delay, args.topic, args.servers))
