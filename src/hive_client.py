"""Hive queries return actual Hive results or raise an error."""
import os
import re
from contextlib import closing
from pathlib import Path
import pandas as pd


def get_hive_connection(database=None):
    from pyhive import hive
    default_host = "hive-server" if Path("/app").exists() or Path("/home/jovyan").exists() else "localhost"
    return hive.Connection(host=os.getenv("HIVE_HOST", default_host),
                           port=int(os.getenv("HIVE_PORT", "10000")),
                           username=os.getenv("HIVE_USER", "jovyan"),
                           database=database or os.getenv("HIVE_DATABASE", "arxiv_db"), auth="NOSASL")


def test_hive_connection():
    try:
        with closing(get_hive_connection("default")) as conn, closing(conn.cursor()) as cursor:
            cursor.execute("SHOW DATABASES")
            return True, "Online. Databases: " + ", ".join(row[0] for row in cursor.fetchall())
    except Exception as exc:
        return False, str(exc)


def query_hive(sql):
    with closing(get_hive_connection()) as conn, closing(conn.cursor()) as cursor:
        cursor.execute(sql)
        if cursor.description is None:
            return pd.DataFrame()
        return pd.DataFrame.from_records(cursor.fetchall(), columns=[c[0].split(".")[-1] for c in cursor.description])


def initialize_hive():
    script = Path(__file__).with_name("hive_init.sql").read_text(encoding="utf-8")
    script = re.sub(r"--[^\n]*", "", script)
    with closing(get_hive_connection("default")) as conn, closing(conn.cursor()) as cursor:
        for statement in script.split(";"):
            if statement.strip():
                cursor.execute(statement.strip())


def refresh_stream_partitions():
    with closing(get_hive_connection()) as conn, closing(conn.cursor()) as cursor:
        cursor.execute("MSCK REPAIR TABLE arxiv_stream")


def refresh_historical_partitions():
    """Discover the year partitions written by the batch HDFS sync."""
    with closing(get_hive_connection()) as conn, closing(conn.cursor()) as cursor:
        cursor.execute("MSCK REPAIR TABLE arxiv_historical")


def refresh_all_partitions():
    """Return the row counts that are visible after a full partition refresh."""
    refresh_historical_partitions()
    refresh_stream_partitions()
    return {
        "historical": int(query_hive("SELECT COUNT(*) AS row_count FROM arxiv_historical").iloc[0, 0]),
        "stream": int(query_hive("SELECT COUNT(*) AS row_count FROM arxiv_stream").iloc[0, 0]),
    }


if __name__ == "__main__":
    initialize_hive()
    print("Hive DDL executed successfully")
