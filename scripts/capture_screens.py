"""Capture dashboard screenshots with Playwright (system Edge, full control of waits).

Ảnh dùng cho báo cáo được chụp với sidebar thu gọn để phần nội dung chính rộng
hơn và chữ dễ đọc khi in. Ảnh minh hoạ giao diện đầy đủ (có sidebar) vẫn được
giữ riêng qua tham số ``--keep-sidebar``.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8501/"
OUT = Path("output/screenshots")
OUT.mkdir(parents=True, exist_ok=True)

# name, query string, viewport (w, h), wait-for text
SHOTS = [
    ("ui_overview.png", "?tab=overview", (1400, 1010), "Ba điểm chính"),
    ("ui_ingest.png", "?tab=ingest", (1400, 1300), "Nhật ký phiên hiện tại"),
    ("ui_pipeline.png", "?tab=pipeline", (1400, 1200), "Trình duyệt Data Lakehouse"),
    ("ui_hive_q7.png", "?tab=hive&q=7&auto=1", (1400, 1400), "Xuất kết quả CSV"),
    ("ui_hive_q8.png", "?tab=hive&q=8&auto=1", (1400, 1120), "Xuất kết quả CSV"),
    ("ui_architecture.png", "?tab=architecture", (1400, 900), "Kiến trúc & luồng dữ liệu"),
]

HIDE_SIDEBAR = """
section[data-testid="stSidebar"] { display: none !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }
[data-testid="stMain"] { margin-left: 0 !important; width: 100% !important; }
[data-testid="stMainBlockContainer"] {
    padding: 14px 48px 28px !important;
    max-width: 1250px !important;
}
[data-testid="stHeader"] { background: transparent !important; }
"""

args = sys.argv[1:]
keep_sidebar = "--keep-sidebar" in args
only = [a for a in args if not a.startswith("--")] or None

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True,
                                args=["--hide-scrollbars", "--force-device-scale-factor=1"])
    for name, query, (width, height), marker in SHOTS:
        if only and name not in only:
            continue
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
        page.goto(BASE + query, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_selector("text=" + marker, timeout=180000)
        if not keep_sidebar:
            page.add_style_tag(content=HIDE_SIDEBAR)
        page.wait_for_timeout(2500)
        page.screenshot(path=str(OUT / name), full_page=False)
        print("saved", name, (OUT / name).stat().st_size)
        page.close()
    browser.close()
