"""Collect the exact numbers used in the report (run inside dashboard container)."""
import json
import sys

sys.path.insert(0, "/app/src")
from hive_client import query_hive

Q = {
    "yearly": "SELECT year, COUNT(*) AS n FROM arxiv_historical GROUP BY year ORDER BY year",
    "groups": "SELECT main_group, COUNT(*) AS n FROM arxiv_historical GROUP BY main_group ORDER BY n DESC",
    "top_cats": "SELECT primary_category, COUNT(*) AS n FROM arxiv_historical GROUP BY primary_category ORDER BY n DESC LIMIT 12",
    "stream": "SELECT main_group_clean, COUNT(*) AS events, COUNT(DISTINCT id) AS papers FROM arxiv_stream GROUP BY main_group_clean ORDER BY events DESC",
    "stream_total": "SELECT COUNT(*) AS events, COUNT(DISTINCT id) AS papers FROM arxiv_stream",
    "kw2015": "SELECT word, document_count, papers_per_1000 FROM hot_keyword_trends WHERE year = 2015 AND word IN ('transformer','attention','diffusion','quantum','neural','graph') ORDER BY papers_per_1000 DESC",
}
for name, sql in Q.items():
    df = query_hive(sql)
    print("==", name)
    print(df.to_string(index=False))
