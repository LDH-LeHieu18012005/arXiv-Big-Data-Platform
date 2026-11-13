"""Rasterize the CogAI Lab logo SVG to a transparent PNG for the slides."""
import base64
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
svg = (ROOT / "src" / "assets" / "cogailab_logo.svg").read_text(encoding="utf-8")
out = ROOT / "output" / "screenshots" / "cogailab_logo.png"
out.parent.mkdir(parents=True, exist_ok=True)

html = (
    "<html><body style='margin:0;background:transparent'>"
    f"<div id='logo' style='width:560px;height:160px'>{svg}</div>"
    "</body></html>"
)

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 560, "height": 160}, device_scale_factor=2)
    page.set_content(html)
    page.locator("#logo svg").screenshot(path=str(out), omit_background=True)
    browser.close()
print("saved", out, out.stat().st_size)
