"""Verify the streaming path end to end (run inside the dashboard container)."""
import sys

sys.path.insert(0, "/app/src")
from hive_client import query_hive, refresh_all_partitions
from hdfs_helper import list_hdfs_dir
from kafka_producer import get_kafka_producer
import time

print("counts:", refresh_all_partitions())
print(query_hive("SELECT id, main_group_clean, year, LENGTH(abstract) AS raw_chars, SIZE(abstract_tokens) AS tokens FROM arxiv_stream WHERE id = '2401.96928'").to_string(index=False))
print("rejects dir:", [(e.get("pathSuffix"), e.get("length")) for e in list_hdfs_dir("/data/arxiv_stream_rejects_v2")])
