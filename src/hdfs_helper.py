"""
================================================================================
HDFS HELPER UTILITIES
Giao tiếp với Hadoop HDFS qua WebHDFS REST API hoặc PySpark / Docker CLI
================================================================================
"""

import os
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import List, Dict, Any, Optional

HDFS_HTTP_HOST = os.getenv("HDFS_HTTP_HOST", "namenode" if os.path.exists("/home/jovyan") or os.path.exists("/app") else "localhost")
HDFS_HTTP_PORT = int(os.getenv("HDFS_HTTP_PORT", "9870"))
HDFS_RPC_URL = os.getenv("HDFS_NAMENODE", "hdfs://namenode:9000")


def get_webhdfs_base_url() -> str:
    """Trả về WebHDFS URL dựa trên môi trường container hay máy chủ."""
    host = HDFS_HTTP_HOST
    return f"http://{host}:{HDFS_HTTP_PORT}/webhdfs/v1"


def check_hdfs_status() -> Dict[str, Any]:
    """Kiểm tra NameNode có đang hoạt động hay không."""
    base_url = get_webhdfs_base_url()
    url = f"{base_url}/?op=LISTSTATUS"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BigDataHelper"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "status": "ONLINE",
                "message": "HDFS NameNode is healthy and responding",
                "details": data.get("FileStatuses", {}).get("FileStatus", []),
            }
    except Exception as e:
        return {
            "status": "OFFLINE_OR_INITIALIZING",
            "message": str(e),
            "details": [],
        }


def list_hdfs_dir(path: str = "/data") -> List[Dict[str, Any]]:
    """Liệt kê danh sách thư mục và file trong HDFS."""
    base_url = get_webhdfs_base_url()
    clean_path = urllib.parse.quote(path.lstrip("/"), safe="/")
    url = f"{base_url}/{clean_path}?op=LISTSTATUS"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BigDataHelper"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("FileStatuses", {}).get("FileStatus", [])
    except Exception as e:
        print(f"⚠️ Không thể đọc danh sách HDFS tại {path}: {e}")
        return []


def create_hdfs_dir(path: str = "/data") -> bool:
    """Tạo thư mục trên HDFS qua WebHDFS PUT."""
    base_url = get_webhdfs_base_url()
    clean_path = urllib.parse.quote(path.lstrip("/"), safe="/")
    url = f"{base_url}/{clean_path}?op=MKDIRS&permission=777"
    try:
        req = urllib.request.Request(url, method="PUT")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status in (200, 201) and json.loads(resp.read().decode("utf-8")).get("boolean") is True
    except Exception as e:
        print(f"⚠️ Lỗi tạo thư mục HDFS {path}: {e}")
        return False


if __name__ == "__main__":
    print("🔍 Kiểm tra trạng thái HDFS...")
    res = check_hdfs_status()
    print("Status:", res["status"])
    print("Message:", res["message"])

