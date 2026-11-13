"""Chạy thử toàn bộ mẫu truy vấn trong dashboard_app.py trên Hive thật.

Chạy trong container dashboard:
    docker exec -e PYTHONIOENCODING=utf-8 dashboard python /app/verify_hive_templates.py
"""
import ast
import sys
import time
from pathlib import Path

sys.path.insert(0, "/app/src")
from hive_client import query_hive  # noqa: E402

source = Path("/app/src/dashboard_app.py").read_text(encoding="utf-8")
tree = ast.parse(source)

templates = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "templates" and isinstance(node.value, ast.Dict):
                templates = ast.literal_eval(node.value)
if not templates:
    raise SystemExit("Không tìm thấy dict templates trong dashboard_app.py")

print(f"{len(templates)} mẫu truy vấn")
failures = 0
for name, sql in templates.items():
    started = time.perf_counter()
    try:
        df = query_hive(sql)
        elapsed = time.perf_counter() - started
        preview = df.head(3).to_string(index=False).replace("\n", " | ")
        print(f"OK  {name}: {len(df)} dòng, {elapsed:.2f}s :: {preview[:160]}")
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print(f"FAIL {name}: {exc.__class__.__name__}: {str(exc)[:300]}")

print("failures", failures)
