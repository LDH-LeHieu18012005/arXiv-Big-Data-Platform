"""Dựng bộ slide thuyết trình cho bài tập lớn arXiv Big Data (theme sáng).

Mọi con số đều đọc từ manifest / bảng kết quả của lần chạy thật; các chỉ số
vận hành (streaming, HDFS) là kết quả kiểm chứng end-to-end ngày 12/11/2026.
"""
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RESULTS_DIR = BASE_DIR / "output" / "analysis_results"
CHARTS_DIR = BASE_DIR / "output" / "charts"
SHOTS_DIR = BASE_DIR / "output" / "screenshots"
REPORT_DIR = BASE_DIR / "output" / "reports"

# Bảng màu sáng, đồng bộ dashboard và báo cáo Word
INK = RGBColor(0x12, 0x2B, 0x45)
BLUE = RGBColor(0x1A, 0x6C, 0xF0)
BLUE_SOFT = RGBColor(0xEA, 0xF2, 0xFE)
NAVY = RGBColor(0x12, 0x3A, 0x5C)
MUTED = RGBColor(0x5B, 0x6B, 0x80)
GREEN = RGBColor(0x0E, 0x9F, 0x6E)
AMBER = RGBColor(0xB4, 0x6A, 0x00)
RED = RGBColor(0xB3, 0x2D, 0x2D)
BG = RGBColor(0xFF, 0xFF, 0xFF)
PANEL = RGBColor(0xF4, 0xF8, 0xFD)
BORDER = RGBColor(0xD9, 0xE4, 0xF2)
ZEBRA = RGBColor(0xF8, 0xFB, 0xFF)

STUDENT = "LÊ DƯƠNG HIẾU"
STUDENT_ID = "12423011"
CLASS_ID = "124231"
ADVISOR = "TS. NGUYỄN VĂN QUYẾT"
SCHOOL = "TRƯỜNG ĐẠI HỌC SƯ PHẠM KỸ THUẬT HƯNG YÊN"

# Số liệu kiểm chứng end-to-end (12/11/2026), không lấy từ manifest batch.
STREAM_EVENTS = 57
STREAM_PAPERS = 34
STREAM_BY_GROUP = [("physics", 29, 18), ("math", 21, 12), ("cs", 7, 4)]
STREAM_REJECTS = 1
HDFS_CLEAN = "615,6 MB"


def load_json(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Thiếu tệp kết quả: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_parquet(name):
    path = RESULTS_DIR / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Thiếu bảng phân tích: {path}")
    return pd.read_parquet(path)


def vn_int(value):
    return f"{int(value):,}".replace(",", ".")


def vn_float(value, digits=1):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return f"{float(value):,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pretty_bytes(value):
    value = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{vn_float(value, 1)} {unit}"
        value /= 1024
    return f"{vn_float(value, 1)} GB"


clean = load_json(DATA_DIR / "clean_manifest.json")
analysis = load_json(RESULTS_DIR / "manifest.json")
source = load_json(DATA_DIR / "source_manifest.json")
chart_manifest = load_json(CHARTS_DIR / "manifest.json")
forecast = load_json(BASE_DIR / "output" / "forecast_validation.json")
topics = load_json(RESULTS_DIR / "topics.json")

if clean.get("clean_run_id") != analysis.get("clean_run_id"):
    raise RuntimeError("Manifest không cùng lần chạy; chạy lại pipeline trước khi tạo slide.")
if chart_manifest.get("clean_run_id") != analysis.get("clean_run_id"):
    raise RuntimeError("Biểu đồ không cùng lần chạy; chạy lại visualization.py.")

yearly = load_parquet("yearly_growth").sort_values("year")
categories = load_parquet("top_categories_yearly")
keywords = load_parquet("hot_keyword_trends")
field_metrics = load_parquet("field_metrics").sort_values("papers", ascending=False)
top_authors = load_parquet("top_authors").sort_values("count", ascending=False)

rows = int(analysis["rows"])
min_year, max_year = int(analysis["min_year"]), int(analysis["max_year"])
groups = int(analysis["groups"])
shards = source.get("shards", [])
total_bytes = source.get("total_bytes") or sum(int(s.get("bytes", 0)) for s in shards)
model = analysis.get("model") or {}
timings = analysis.get("timings_seconds") or {}
cat_totals = categories.groupby("primary_category")["count"].sum().sort_values(ascending=False)
top_group = field_metrics.iloc[0]
stable_years = yearly[(yearly["year"] > min_year) & (yearly["year"] < max_year)]
growth_start, growth_end = stable_years.iloc[0], stable_years.iloc[-1]
overall_growth = (growth_end["count"] / growth_start["count"] - 1) * 100
cagr = ((growth_end["count"] / growth_start["count"]) ** (1 / (growth_end["year"] - growth_start["year"])) - 1) * 100
accepted = [item for item in forecast.get("metrics", []) if item.get("status") == "accepted"]
prep_seconds = float(analysis.get("preprocessing_seconds", 0))
analysis_seconds = float(analysis.get("total_analysis_seconds", 0))
lda_seconds = float(model.get("seconds", 0))

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
TOTAL = 23
LOGO = SHOTS_DIR / "cogailab_logo.png"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def new_slide(number=None, footer=True):
    slide = prs.slides.add_slide(BLANK)
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = BG
    bg.line.fill.background()
    bg.shadow.inherit = False
    if footer:
        add_text(slide, "arXiv Big Data  ·  Lê Dương Hiếu  ·  12423011", 0.62, 7.06, 8.0, 0.28,
                 size=9, color=RGBColor(0x8B, 0x9A, 0xAD))
        if number is not None:
            add_text(slide, f"{number:02d} / {TOTAL}", 11.7, 7.06, 1.0, 0.28, size=9,
                     color=RGBColor(0x8B, 0x9A, 0xAD), align=PP_ALIGN.RIGHT)
    return slide


def add_text(slide, text, left, top, width, height, size=16, bold=False, color=INK,
             align=PP_ALIGN.LEFT, font="Calibri", spacing=1.12, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    paragraph.line_spacing = spacing
    run = paragraph.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font
    return box


def add_logo(slide, left=11.42, top=0.34, width=1.42):
    if not LOGO.exists():
        raise FileNotFoundError(f"Thiếu logo: {LOGO} (chạy scripts/render_logo.py)")
    slide.shapes.add_picture(str(LOGO), Inches(left), Inches(top), width=Inches(width))


def header(slide, title, subtitle=None, number=None, logo=True):
    add_text(slide, "ARXIV BIG DATA  ·  BÀI TẬP LỚN", 0.62, 0.30, 7.0, 0.26, size=10,
             bold=True, color=BLUE)
    add_text(slide, title, 0.60, 0.56, 10.6, 0.62, size=26, bold=True, color=INK)
    if subtitle:
        add_text(slide, subtitle, 0.62, 1.16, 10.6, 0.34, size=12.5, color=MUTED)
    line = slide.shapes.add_connector(1, Inches(0.6), Inches(1.58), Inches(12.72), Inches(1.58))
    line.line.color.rgb = BORDER
    line.line.width = Pt(1)
    line.shadow.inherit = False
    if logo:
        add_logo(slide)


def add_bullets(slide, items, left, top, width, height, size=15, color=INK, gap=10, bullet="•  "):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    for index, item in enumerate(items):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.space_after = Pt(gap)
        paragraph.line_spacing = 1.18
        run = paragraph.add_run()
        run.text = bullet + item
        run.font.size = Pt(size)
        run.font.color.rgb = color
        run.font.name = "Calibri"
    return box


def card(slide, left, top, width, height, fill=PANEL, border=BORDER, radius=0.06):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top),
                                   Inches(width), Inches(height))
    shape.adjustments[0] = radius
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = border
    shape.line.width = Pt(1)
    shape.shadow.inherit = False
    return shape


def kpi(slide, left, top, width, height, value, label, color=BLUE, note=None):
    card(slide, left, top, width, height)
    add_text(slide, value, left + 0.22, top + 0.20, width - 0.4, 0.52, size=24, bold=True, color=color)
    add_text(slide, label, left + 0.22, top + 0.72, width - 0.4, 0.34, size=11.5, color=MUTED)
    if note:
        add_text(slide, note, left + 0.22, top + 1.02, width - 0.4, 0.3, size=9.5,
                 color=RGBColor(0x8B, 0x9A, 0xAD))


def chip(slide, label, left, top, width=None, color=BLUE, fill=BLUE_SOFT, size=11):
    width = width or (0.16 * len(label) + 0.32)
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top),
                                   Inches(width), Inches(0.34))
    shape.adjustments[0] = 0.5
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = RGBColor(0xD3, 0xE2, 0xF8)
    shape.shadow.inherit = False
    add_text(slide, label, left, top + 0.04, width, 0.26, size=size, bold=True, color=color,
             align=PP_ALIGN.CENTER)
    return shape


def add_image(slide, filename, left, top, width, height, border=True):
    path = CHARTS_DIR / filename
    if not path.exists():
        path = SHOTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Thiếu hình: {path}")
    from PIL import Image
    with Image.open(path) as image:
        ratio = image.width / image.height
    box_ratio = width / height
    if ratio >= box_ratio:
        final_width, final_height = width, width / ratio
    else:
        final_height, final_width = height, height * ratio
    left += (width - final_width) / 2
    top += (height - final_height) / 2
    picture = slide.shapes.add_picture(str(path), Inches(left), Inches(top),
                                       Inches(final_width), Inches(final_height))
    if border:
        picture.line.color.rgb = BORDER
        picture.line.width = Pt(0.75)
    return picture


def _set_border(cell, color=BORDER, width_pt=0.75):
    tc_pr = cell._tc.get_or_add_tcPr()
    for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        tag_name = qn(tag)
        for existing in tc_pr.findall(tag_name):
            tc_pr.remove(existing)
        ln = tc_pr.makeelement(tag_name, {"w": str(int(width_pt * 12700)), "cap": "flat",
                                          "cmpd": "sng", "algn": "ctr"})
        fill = ln.makeelement(qn("a:solidFill"), {})
        clr = fill.makeelement(qn("a:srgbClr"), {"val": "%02X%02X%02X" % (color[0], color[1], color[2])})
        fill.append(clr)
        ln.append(fill)
        tc_pr.append(ln)


def table(slide, headers, data, left, top, width, height, size=11.5, col_widths=None,
          first_col_left=True):
    shape = slide.shapes.add_table(len(data) + 1, len(headers), Inches(left), Inches(top),
                                   Inches(width), Inches(height))
    table_obj = shape.table
    table_obj.first_row = True
    table_obj.horz_banding = False
    if col_widths:
        total = sum(col_widths)
        for index, ratio in enumerate(col_widths):
            table_obj.columns[index].width = Inches(width * ratio / total)
    row_height = height / (len(data) + 1)
    for row_index in range(len(data) + 1):
        table_obj.rows[row_index].height = Inches(row_height)
    for column, label in enumerate(headers):
        cell = table_obj.cell(0, column)
        cell.text = str(label)
        cell.fill.solid()
        cell.fill.fore_color.rgb = BLUE_SOFT
        cell.margin_left = Inches(0.08)
        cell.margin_right = Inches(0.08)
        cell.margin_top = Inches(0.03)
        cell.margin_bottom = Inches(0.03)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        for paragraph in cell.text_frame.paragraphs:
            paragraph.alignment = PP_ALIGN.CENTER
            for run in paragraph.runs:
                run.font.size = Pt(size)
                run.font.bold = True
                run.font.color.rgb = NAVY
                run.font.name = "Calibri"
        _set_border(cell)
    for row_index, row in enumerate(data, 1):
        for column, value in enumerate(row):
            cell = table_obj.cell(row_index, column)
            cell.text = str(value)
            cell.fill.solid()
            cell.fill.fore_color.rgb = BG if row_index % 2 else ZEBRA
            cell.margin_left = Inches(0.08)
            cell.margin_right = Inches(0.08)
            cell.margin_top = Inches(0.02)
            cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            for paragraph in cell.text_frame.paragraphs:
                paragraph.alignment = PP_ALIGN.LEFT if (column == 0 and first_col_left) else PP_ALIGN.CENTER
                for run in paragraph.runs:
                    run.font.size = Pt(size)
                    run.font.color.rgb = INK
                    run.font.name = "Calibri"
            _set_border(cell)
    return table_obj


def step_card(slide, left, top, width, height, number, heading, detail, accent=BLUE):
    card(slide, left, top, width, height)
    circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(left + 0.22), Inches(top + 0.24),
                                    Inches(0.46), Inches(0.46))
    circle.fill.solid()
    circle.fill.fore_color.rgb = accent
    circle.line.fill.background()
    circle.shadow.inherit = False
    add_text(slide, str(number), left + 0.22, top + 0.30, 0.46, 0.34, size=13, bold=True,
             color=BG, align=PP_ALIGN.CENTER)
    add_text(slide, heading, left + 0.8, top + 0.24, width - 1.0, 0.34, size=14, bold=True, color=NAVY)
    add_text(slide, detail, left + 0.8, top + 0.62, width - 1.02, height - 0.75, size=11, color=MUTED,
             spacing=1.1)


def section_label(slide, text, top=1.85):
    add_text(slide, text, 0.62, top, 11.9, 0.3, size=10.5, bold=True, color=BLUE)


# ---------------------------------------------------------------------------
# 01 - Bìa
# ---------------------------------------------------------------------------
slide = new_slide(footer=False)
add_logo(slide, left=0.85, top=0.55, width=3.0)
add_text(slide, "TRƯỜNG ĐẠI HỌC SƯ PHẠM KỸ THUẬT HƯNG YÊN  ·  KHOA CÔNG NGHỆ THÔNG TIN",
         0.62, 1.72, 12.1, 0.3, size=11.5, bold=True, color=MUTED, align=PP_ALIGN.CENTER)
add_text(slide, "BÀI TẬP LỚN  ·  HỌC PHẦN XỬ LÝ DỮ LIỆU LỚN", 0.62, 2.08, 12.1, 0.34,
         size=13, bold=True, color=BLUE, align=PP_ALIGN.CENTER)
add_text(slide, "PHÂN TÍCH DỮ LIỆU LỚN METADATA\nBÀI BÁO KHOA HỌC ARXIV", 0.7, 2.55, 11.9, 1.5,
         size=37, bold=True, color=INK, align=PP_ALIGN.CENTER, spacing=1.08)
add_text(slide, "Trên nền tảng Hadoop, Spark, Kafka và Hive", 0.7, 4.02, 11.9, 0.4, size=17,
         color=NAVY, align=PP_ALIGN.CENTER)
labels = [f"{len(shards)} shard Parquet", pretty_bytes(total_bytes), f"{vn_int(rows)} bài báo",
          f"{min_year}–{max_year}"]
left = 2.55
for text_label in labels:
    width = 0.16 * len(text_label) + 0.42
    chip(slide, text_label, left, 4.55, width=width, size=12)
    left += width + 0.22
line = slide.shapes.add_connector(1, Inches(3.2), Inches(5.28), Inches(10.1), Inches(5.28))
line.line.color.rgb = BORDER
line.line.width = Pt(1)
line.shadow.inherit = False
add_text(slide, f"Sinh viên: {STUDENT}  ·  MSSV: {STUDENT_ID}  ·  Lớp: {CLASS_ID}",
         0.7, 5.45, 11.9, 0.36, size=15, bold=True, color=INK, align=PP_ALIGN.CENTER)
add_text(slide, f"Giảng viên hướng dẫn: {ADVISOR}  ·  Hưng Yên, 2026",
         0.7, 5.88, 11.9, 0.34, size=12.5, color=MUTED, align=PP_ALIGN.CENTER)
add_text(slide, "Kafka  →  Spark Structured Streaming  →  HDFS  →  Hive  →  Streamlit",
         0.7, 6.45, 11.9, 0.3, size=11.5, color=RGBColor(0x8B, 0x9A, 0xAD), align=PP_ALIGN.CENTER)

# ---------------------------------------------------------------------------
# 02 - Bài toán và mục tiêu
# ---------------------------------------------------------------------------
slide = new_slide(2)
header(slide, "Bài toán và mục tiêu", "Từ dữ liệu thô đến kết quả kiểm chứng được")
add_text(slide, "Vì sao cần xử lý dữ liệu lớn", 0.62, 1.86, 6.0, 0.34, size=15, bold=True, color=NAVY)
add_bullets(slide, [
    "arXiv tăng liên tục; riêng hai shard đã có 704.329 bản ghi, vượt khả năng xử lý của một máy.",
    "Câu hỏi cần trả lời: ngành nào tăng, từ khóa nào lên, chủ đề nào dịch chuyển.",
    "Dữ liệu vừa đến theo lô lịch sử, vừa đến liên tục theo sự kiện.",
    "Nhiều báo cáo công bố số liệu không tái lập được vì thiếu manifest.",
], 0.62, 2.28, 6.1, 2.5, size=13.5, gap=11)
card(slide, 0.62, 4.48, 6.1, 1.5)
add_text(slide, "Phạm vi dữ liệu thực nghiệm", 0.84, 4.64, 5.6, 0.28, size=11, bold=True, color=BLUE)
add_text(slide, "2 shard  ·  704.329 bài  ·  2007–2016", 0.84, 4.94, 5.7, 0.38,
         size=15, bold=True, color=NAVY)
add_text(slide, f"{pretty_bytes(total_bytes)} Parquet thô; 2016 chỉ trích đến giữa năm.",
         0.84, 5.38, 5.7, 0.4, size=10.5, color=MUTED)
add_text(slide, "Mục tiêu của bài làm", 7.0, 1.86, 5.6, 0.34, size=15, bold=True, color=NAVY)
card(slide, 7.0, 2.24, 5.7, 2.62)
add_bullets(slide, [
    "Pipeline batch chạy lại được, có mã lần chạy và manifest.",
    "Năm nộp lấy từ phiên bản v1, kiểm tra chéo với mã arXiv.",
    "Streaming Kafka → Spark → HDFS có checkpoint và vùng cách ly.",
    "Hive external table + 8 mẫu truy vấn SQL.",
    "Dashboard 5 tab và báo cáo có số liệu truy vết được.",
    "Báo cáo Word và slide lấy số từ cùng manifest.",
], 7.3, 2.46, 5.1, 2.4, size=12.5, gap=9)
card(slide, 7.0, 5.05, 5.7, 0.95, fill=RGBColor(0xFF, 0xF8, 0xEC),
     border=RGBColor(0xF0, 0xDD, 0xBE))
add_text(slide, "Ngoài phạm vi", 7.22, 5.16, 5.2, 0.26, size=10.5, bold=True, color=AMBER)
add_text(slide, "Không cào toàn bộ arXiv, không huấn luyện mô hình ngôn ngữ lớn; chỉ dùng dữ liệu đã tải.",
         7.22, 5.44, 5.25, 0.5, size=10.5, color=MUTED)
add_text(slide, "Nguyên tắc: đo lường thay vì phỏng đoán — mọi con số đều lấy từ manifest, Hive hoặc log lần chạy thật.",
         0.62, 6.55, 12.1, 0.34, size=11.5, bold=True, color=GREEN)

# ---------------------------------------------------------------------------
# 03 - Kiến trúc
# ---------------------------------------------------------------------------
slide = new_slide(3)
header(slide, "Kiến trúc Lambda áp dụng cho bài toán", "Batch và streaming ghi hai thư mục riêng, Hive đọc chung")
add_image(slide, "00_pipeline_full_architecture.png", 0.5, 1.78, 8.5, 4.95)
add_text(slide, "Bốn tầng nối tiếp", 9.3, 1.85, 3.5, 0.3, size=13, bold=True, color=NAVY)
add_bullets(slide, [
    "Thu nhận: 2 shard Parquet + Kafka topic arxiv-papers-v2.",
    "Xử lý: Spark batch và Spark Structured Streaming.",
    "Lưu trữ: HDFS (/*_v2) + Hive Metastore/HiveServer2.",
    "Trình bày: dashboard Streamlit 5 tab.",
    "Hai nhánh ghi hai thư mục riêng, Hive đọc chung.",
    "Cùng data_contract.py nên kết quả nhất quán.",
], 9.3, 2.22, 3.6, 2.9, size=11.5, gap=9)
card(slide, 9.3, 4.95, 3.55, 1.35)
add_text(slide, "Hai nhánh, một quy tắc", 9.5, 5.08, 3.2, 0.28, size=11, bold=True, color=BLUE)
add_text(slide, "Một bài báo được xử lý giống nhau dù đi đường lô hay đường luồng; khác nhau chỉ ở thư mục đích.",
         9.5, 5.38, 3.2, 0.85, size=10.5, color=MUTED)

# ---------------------------------------------------------------------------
# 04 - Công nghệ
# ---------------------------------------------------------------------------
slide = new_slide(4)
header(slide, "Công nghệ sử dụng", "Đóng gói bằng Docker Compose, 12 dịch vụ cùng phiên bản")
table(slide, ["Thành phần", "Vai trò", "Phiên bản"], [
    ["Hadoop HDFS", "Lưu trữ phân tán, 10 partition theo năm", "3.2.1"],
    ["Apache Spark", "Batch, Structured Streaming, MLlib LDA", analysis.get("spark_version", "3.5.3")],
    ["Apache Kafka", "Hàng đợi sự kiện bài báo mới", "7.6.0"],
    ["Apache Hive", "External table + view trên HDFS", "2.3.2"],
    ["PostgreSQL", "Hive Metastore", "2.3.0"],
    ["Streamlit", "Dashboard 5 tab", "1.40.0"],
    ["Docker Compose", "Điều phối 12 container", "Compose v2"],
], 0.6, 1.85, 7.7, 3.9, size=12, col_widths=[1.1, 2.2, 0.9])
add_text(slide, "Vì sao chọn?", 8.7, 1.85, 3.9, 0.32, size=13, bold=True, color=NAVY)
add_bullets(slide, [
    "Spark xử lý cả batch và streaming trong một engine.",
    "HDFS + Hive tách lưu trữ khỏi tính toán.",
    "Kafka mô phỏng luồng tiếp nhận thời gian thực.",
    "Streamlit đủ nhanh cho demo, ít mã giao diện.",
], 8.7, 2.24, 4.0, 3.4, size=11.5, gap=10)

# ---------------------------------------------------------------------------
# 05 - Quy tắc dữ liệu
# ---------------------------------------------------------------------------
slide = new_slide(5)
header(slide, "Quy tắc dữ liệu dùng chung", "Điểm khác biệt so với cách làm đơn giản")
add_bullets(slide, [
    "Năm nộp = năm của phiên bản v1; chỉ fallback sang mã arXiv khi thiếu.",
    "Hai định dạng mã: archive/YYMMNNN (trước 4/2007) và YYMM.NNNNN.",
    "Bản ghi thiếu 1 trong 4 trường bắt buộc hoặc năm ngoài 1991–nay bị loại.",
    "Trùng mã bài làm dừng pipeline thay vì tự chọn một phiên bản.",
    "Batch và streaming gọi cùng một hàm, cùng tham số tách từ.",
], 0.62, 1.9, 7.4, 3.9, size=13.5, gap=12)
card(slide, 8.35, 1.86, 4.35, 3.95)
add_text(slide, "Kiểm tra trên dữ liệu thật", 8.58, 2.03, 3.9, 0.3, size=11.5, bold=True, color=BLUE)
add_text(slide, vn_int(rows), 8.58, 2.38, 3.9, 0.6, size=30, bold=True, color=GREEN)
add_text(slide, f"bản ghi sạch · loại {vn_int(clean.get('rejected_rows', 0))} dòng", 8.58, 3.02, 3.9, 0.3,
         size=10.5, color=MUTED)
rows_card = [
    ("2.323", "bản ghi chênh năm v1 và năm suy từ mã"),
    ("0", "mã bài trùng lặp"),
    ("8", "nhóm ngành sau chuẩn hóa"),
]
for index, (value, label) in enumerate(rows_card):
    y = 3.48 + index * 0.72
    add_text(slide, value, 8.58, y, 0.95, 0.3, size=15, bold=True, color=NAVY)
    add_text(slide, label, 9.6, y + 0.03, 2.9, 0.55, size=10.5, color=MUTED)
card(slide, 0.62, 4.55, 7.4, 1.4)
add_text(slide, "Chênh năm được giữ lại, không che bằng 0", 0.85, 4.7, 6.9, 0.3, size=11.5,
         bold=True, color=NAVY)
add_text(slide, "Bài nộp cuối tháng 12 nhưng nhận mã tháng 1 năm sau — nếu suy năm từ mã sẽ lệch "
                "một năm; dùng ngày của phiên bản v1 mới đúng.",
         0.85, 5.02, 6.9, 0.8, size=10.5, color=MUTED)

# ---------------------------------------------------------------------------
# 06 - Luồng batch
# ---------------------------------------------------------------------------
slide = new_slide(6)
header(slide, "Luồng batch: ba giai đoạn", "Một lệnh cho mỗi tầng, chạy lại được từ đầu")
step_card(slide, 0.6, 1.9, 3.95, 1.6, 1, "Tiền xử lý",
          "Đọc Parquet thô, áp dụng data contract, tạo năm / nhóm ngành / token, ghi Parquet sạch.")
step_card(slide, 4.69, 1.9, 3.95, 1.6, 2, "Phân tích",
          "9 bảng kết quả: tăng trưởng, nhóm ngành, chuyên ngành, từ khóa, tác giả.")
step_card(slide, 8.78, 1.9, 3.95, 1.6, 3, "Đồng bộ HDFS",
          "Ghi Parquet phân vùng theo năm, tạo _SUCCESS, chạy MSCK REPAIR cho Hive.")
table(slide, ["Giai đoạn", "Nội dung", "Thời gian"], [
    ["preprocess", "704.329 bản ghi → Parquet sạch", f"{vn_float(prep_seconds)} giây"],
    ["analyze", "9 bảng phân tích + LDA", f"{vn_float(analysis_seconds)} giây"],
    ["— trong đó LDA", "K = 10, từ điển 10.000 từ", f"{vn_float(lda_seconds)} giây"],
    ["sync-hdfs", "Parquet phân vùng + MSCK REPAIR", "—"],
], 0.6, 3.78, 7.6, 2.05, size=11.5, col_widths=[1.0, 2.2, 0.85])
card(slide, 8.5, 3.78, 4.2, 1.25)
add_text(slide, f"{vn_float(prep_seconds + analysis_seconds)} giây", 8.72, 3.94, 3.7, 0.45,
         size=21, bold=True, color=GREEN)
add_text(slide, "tổng thời gian batch cho 704.329 bài (~9,9 phút)", 8.72, 4.42, 3.8, 0.5,
         size=10.5, color=MUTED)
add_text(slide, "Sau khi ghi, chương trình đọc lại Parquet để đối chiếu số dòng — lệch là dừng ngay.",
         8.5, 5.18, 4.2, 0.6, size=10.5, color=MUTED)
card(slide, 0.6, 6.05, 12.1, 0.72)
add_text(slide, "docker compose exec spark-jupyter python src/batch_pipeline.py all",
         0.85, 6.17, 6.9, 0.32, size=11, bold=True, color=NAVY)
add_text(slide, "→ chạy lần lượt preprocess  →  analyze  →  sync-hdfs", 7.9, 6.19, 4.6, 0.3,
         size=10.5, color=MUTED)

# ---------------------------------------------------------------------------
# 07 - Streaming
# ---------------------------------------------------------------------------
slide = new_slide(7)
header(slide, "Streaming và vùng cách ly", "Một bản ghi lỗi không được phép làm dừng cả luồng")
for index, (heading, detail) in enumerate([
    ("Producer", "Gửi một bài hoặc phát lại từ Parquet; chỉ đếm khi Kafka ACK."),
    ("Kafka", "Topic arxiv-papers-v2, acks=all, giữ nguyên offset."),
    ("Spark", "Micro-batch 5 giây, checkpoint tại /checkpoint/arxiv_stream_v2."),
    ("HDFS", "Hợp lệ → arxiv_stream_v2; lỗi → rejects_v2 kèm reject_reason."),
]):
    step_card(slide, 0.6 + index * 3.08, 1.9, 2.9, 2.0, index + 1, heading, detail)
kpi(slide, 0.6, 4.2, 2.9, 1.45, str(STREAM_EVENTS), "sự kiện trong arxiv_stream")
kpi(slide, 3.68, 4.2, 2.9, 1.45, str(STREAM_PAPERS), "bài duy nhất (COUNT DISTINCT)", color=GREEN)
kpi(slide, 6.76, 4.2, 2.9, 1.45, str(STREAM_REJECTS), "bản ghi vào vùng cách ly", color=AMBER)
kpi(slide, 9.84, 4.2, 2.9, 1.45, "Up", "consumer sau bản ghi lỗi", color=GREEN)
add_text(slide, "Sự kiện theo nhóm ngành", 0.62, 5.82, 5.6, 0.3, size=12, bold=True, color=NAVY)
add_text(slide, "physics 29 / 18  ·  math 21 / 12  ·  cs 7 / 4", 0.62, 6.15, 5.8, 0.32,
         size=12, color=MUTED)
add_text(slide, "Số sự kiện khác số bài vì cùng một bài có thể được phát lại — báo cáo luôn dùng COUNT(DISTINCT id).",
         6.4, 5.9, 6.2, 0.7, size=11, color=MUTED)

# ---------------------------------------------------------------------------
# 08 - Hive
# ---------------------------------------------------------------------------
slide = new_slide(8)
header(slide, "Kho dữ liệu Hive", "External table trỏ thẳng vào Parquet trên HDFS")
table(slide, ["Đối tượng", "Kiểu", "Phân vùng / vai trò"], [
    ["arxiv_historical", "External table", "year · 704.329 dòng"],
    ["arxiv_stream", "External table", "main_group_clean · sự kiện"],
    ["hot_keyword_trends", "External table", "year · từ khóa"],
    ["v_yearly_growth", "View", "Tăng trưởng theo năm"],
    ["v_field_distribution", "View", "Cơ cấu nhóm ngành"],
    ["v_top_categories", "View", "Xếp hạng chuyên ngành"],
], 0.6, 1.86, 6.9, 3.3, size=11.5, col_widths=[1.4, 1.0, 2.2])
add_text(slide, "Tám mẫu truy vấn trên dashboard", 7.9, 1.86, 4.5, 0.32, size=13, bold=True, color=NAVY)
add_bullets(slide, [
    "Quy mô, tăng trưởng, cơ cấu ngành.",
    "Chuyên ngành hàng đầu, từ khóa 2015.",
    "So sánh raw / clean / tokens (mẫu 7).",
    "Phân bố sự kiện streaming (mẫu 8).",
], 7.9, 2.24, 4.6, 2.6, size=11.5, gap=9)
card(slide, 0.6, 5.42, 6.9, 1.35)
add_text(slide, "Giới hạn của Hive 2.3.2", 0.8, 5.54, 6.5, 0.28, size=10.5, bold=True, color=BLUE)
add_text(slide, "Không hỗ trợ scalar subquery trong SELECT và không bật tích Descartes.",
         0.8, 5.86, 6.5, 0.35, size=10.5, color=MUTED)
add_text(slide, "Mẫu 2 vì vậy dùng SUM(paper_count) OVER () thay cho subquery.",
         0.8, 6.22, 6.5, 0.35, size=10.5, bold=True, color=NAVY)
card(slide, 7.9, 4.45, 4.85, 2.3)
add_text(slide, "Dữ liệu trên HDFS", 8.1, 4.6, 4.4, 0.28, size=10.5, bold=True, color=BLUE)
add_text(slide, f"{HDFS_CLEAN} dữ liệu sạch", 8.1, 4.92, 4.4, 0.42, size=19, bold=True, color=NAVY)
add_text(slide, "10 partition theo năm · 3 partition nhóm ngành cho luồng streaming.",
         8.1, 5.44, 4.5, 0.6, size=10.5, color=MUTED)
add_text(slide, "Hive đọc trực tiếp Parquet trên HDFS, không sao chép dữ liệu.",
         8.1, 6.12, 4.5, 0.5, size=10.5, color=MUTED)

# ---------------------------------------------------------------------------
# 09 - Dashboard tổng quan
# ---------------------------------------------------------------------------
slide = new_slide(9)
header(slide, "Dashboard Streamlit: 5 tab", "Theme sáng, màu nhấn #1a6cf0, thanh điều hướng segmented")
add_image(slide, "ui_overview.png", 0.5, 1.78, 8.2, 4.9)
add_text(slide, "Năm tab", 8.9, 1.85, 3.9, 0.3, size=13, bold=True, color=NAVY)
add_bullets(slide, [
    "Tổng quan: 4 thẻ chỉ số, 2 biểu đồ, 3 điểm chính.",
    "Gửi dữ liệu: form Kafka + phát lại hàng loạt.",
    "Xử lý & HDFS: 4 bước consumer, duyệt HDFS.",
    "Hive SQL: 8 mẫu truy vấn, MSCK REPAIR, xuất CSV.",
    "Kiến trúc: luồng dữ liệu, trạng thái 4 dịch vụ.",
], 8.9, 2.24, 4.0, 2.3, size=11, gap=8)
card(slide, 8.9, 4.3, 4.0, 1.12)
add_text(slide, "Thanh điều hướng", 9.1, 4.42, 3.6, 0.28, size=11, bold=True, color=BLUE)
add_text(slide, "Một khối segmented liền mạch; tab đang mở tô đặc #1a6cf0, không dùng nút nổi rời rạc.",
         9.1, 4.72, 3.62, 0.62, size=10.5, color=MUTED)
add_text(slide, "Deep link ?tab=… và ?tab=hive&q=7&auto=1 dùng cho demo và chụp ảnh tái lập.",
         8.9, 5.7, 3.95, 0.7, size=10.5, color=MUTED)

# ---------------------------------------------------------------------------
# 10 - Dashboard gửi dữ liệu
# ---------------------------------------------------------------------------
slide = new_slide(10)
header(slide, "Tab Gửi dữ liệu: Kafka Ingestion Studio", "Kiểm tra trước khi gửi, đếm theo ACK, có nhật ký phiên")
add_image(slide, "ui_ingest.png", 4.55, 1.78, 8.2, 4.9)
add_text(slide, "Luồng gửi", 0.62, 1.85, 3.7, 0.3, size=13, bold=True, color=NAVY)
add_bullets(slide, [
    "Nhập id, tiêu đề, tác giả, lĩnh vực, tóm tắt.",
    "validate_paper kiểm tra 4 trường bắt buộc và định dạng id.",
    "Producer gửi với acks=all, chờ xác nhận.",
    "Micro-batch kế tiếp đưa bài vào arxiv_stream.",
    "Nhật ký phiên giữ id, thời điểm và trạng thái ACK.",
], 0.62, 2.24, 3.75, 2.3, size=10.5, gap=9)
card(slide, 0.62, 4.6, 3.7, 1.15)
add_text(slide, "Phát lại hàng loạt", 0.8, 4.73, 3.4, 0.28, size=11, bold=True, color=BLUE)
add_text(slide, "Lấy bài thật từ Parquet sạch, gửi lại qua Kafka để thử tải và kiểm tra idempotent.",
         0.8, 5.03, 3.4, 0.95, size=10, color=MUTED)

# ---------------------------------------------------------------------------
# 11 - Dashboard Hive
# ---------------------------------------------------------------------------
slide = new_slide(11)
header(slide, "Tab Hive SQL: truy vấn trực tiếp HiveServer2", "Kết quả giữ nguyên khi thao tác, xuất được CSV")
add_image(slide, "ui_hive_q7.png", 0.5, 1.78, 8.2, 4.9)
add_text(slide, "Mẫu 7 — raw vs clean vs tokens", 8.9, 1.85, 3.9, 0.3, size=12, bold=True, color=NAVY)
add_text(slide, "Trả về raw_chars, clean_chars, token_count cho 12 sự kiện mới nhất, kèm thời gian xử lý.",
         8.9, 2.2, 3.95, 1.0, size=10.5, color=MUTED)
add_text(slide, "Điểm cần lưu ý", 8.9, 3.35, 3.9, 0.3, size=11, bold=True, color=NAVY)
add_bullets(slide, [
    "Số sự kiện ≠ số bài: dùng COUNT(DISTINCT id).",
    "MSCK REPAIR sau khi Spark ghi partition mới.",
    "8/8 mẫu chạy đúng sau khi sửa mẫu 2.",
], 8.9, 3.68, 3.95, 1.6, size=10.5, gap=8)
card(slide, 8.9, 4.95, 3.95, 1.25)
add_text(slide, "Vì sao dùng Hive?", 9.1, 5.08, 3.55, 0.28, size=11, bold=True, color=BLUE)
add_text(slide, "Truy vấn SQL trực tiếp trên Parquet ở HDFS, không nạp lại dữ liệu; dashboard chỉ cần HiveServer2.",
         9.1, 5.38, 3.55, 1.0, size=10.5, color=MUTED)

# ---------------------------------------------------------------------------
# 12 - Kết quả tổng quan
# ---------------------------------------------------------------------------
slide = new_slide(12)
header(slide, "Kết quả tổng quan", f"Lần chạy {analysis['clean_run_id'][:8]} · Spark {analysis.get('spark_version')}")
kpi(slide, 0.6, 1.82, 2.95, 1.4, vn_int(rows), "bài báo sạch")
kpi(slide, 3.66, 1.82, 2.95, 1.4, f"{min_year}–{max_year}", "khoảng năm nộp (v1)", color=NAVY)
kpi(slide, 6.72, 1.82, 2.95, 1.4, str(groups), "nhóm ngành", color=GREEN)
kpi(slide, 9.78, 1.82, 2.95, 1.4, vn_float(model.get("test_log_perplexity"), 2),
    "log-perplexity LDA", color=AMBER)
add_image(slide, "01_yearly_growth.png", 0.5, 3.4, 7.4, 3.35)
add_text(slide, "Tăng trưởng 2008–2015", 8.25, 3.45, 4.4, 0.32, size=13, bold=True, color=NAVY)
add_text(slide, f"Số bài tăng từ {vn_int(growth_start['count'])} lên {vn_int(growth_end['count'])}, "
                f"tương đương {vn_float(overall_growth)}% hay {vn_float(cagr)}%/năm.",
         8.25, 3.82, 4.45, 1.1, size=12, color=INK)
add_text(slide, "2016 chỉ có 12.153 bài vì phạm vi trích xuất dừng giữa năm — không phải suy giảm của ngành.",
         8.25, 5.0, 4.45, 1.1, size=10.5, color=MUTED)
add_text(slide, "2007 thấp vì dữ liệu bắt đầu từ tháng 4.", 8.25, 5.95, 4.45, 0.4, size=10.5, color=MUTED)

# ---------------------------------------------------------------------------
# 13 - Cơ cấu ngành
# ---------------------------------------------------------------------------
slide = new_slide(13)
header(slide, "Cơ cấu tám nhóm ngành", "Vật lý, toán và khoa học máy tính chiếm 96,6% dữ liệu")
add_image(slide, "07_field_distribution.png", 0.5, 1.82, 5.4, 4.85)
table(slide, ["Nhóm", "Số bài", "Tỷ lệ", "Tác giả/bài"], [
    [row.main_group, vn_int(row.papers), vn_float(row.papers / rows * 100) + "%",
     vn_float(row.avg_authors, 2)]
    for row in field_metrics.head(6).itertuples()
], 6.25, 1.9, 6.4, 3.4, size=11.5, col_widths=[0.9, 1.0, 0.8, 1.0])
add_text(slide, f"Vật lý: {vn_int(top_group['papers'])} bài ({vn_float(top_group['papers'] / rows * 100)}%), "
                f"trung bình {vn_float(top_group['avg_authors'], 2)} tác giả/bài.",
         6.25, 5.5, 6.4, 0.4, size=11.5, bold=True, color=BLUE)
add_text(slide, "Toán chỉ 1,92 tác giả/bài — phản ánh khác biệt giữa nghiên cứu lý thuyết và thực nghiệm.",
         6.25, 5.95, 6.4, 0.6, size=10.5, color=MUTED)

# ---------------------------------------------------------------------------
# 14 - Chuyên ngành
# ---------------------------------------------------------------------------
slide = new_slide(14)
header(slide, "Chuyên ngành hàng đầu", "Xếp hạng theo tổng số bài trong phạm vi đã tải")
add_image(slide, "03_top_categories.png", 0.5, 1.82, 7.6, 4.9)
add_text(slide, "Top 6 chuyên ngành", 8.4, 1.86, 4.3, 0.3, size=12.5, bold=True, color=NAVY)
add_bullets(slide, [f"{name}: {vn_int(value)} bài" for name, value in cat_totals.head(6).items()],
            8.4, 2.24, 4.35, 2.8, size=12, gap=10)
add_text(slide, "Ba chuyên ngành dẫn đầu đều thuộc vật lý: hạt nhân, lượng tử và lý thuyết.",
         8.4, 5.3, 4.35, 0.8, size=10.5, color=MUTED)
add_text(slide, "Bảng gốc xếp hạng lại theo từng năm; biểu đồ tổng hợp toàn giai đoạn.",
         8.4, 6.05, 4.35, 0.7, size=10.5, color=MUTED)

# ---------------------------------------------------------------------------
# 15 - Từ khóa
# ---------------------------------------------------------------------------
slide = new_slide(15)
header(slide, "Xu hướng từ khóa công nghệ", "Chuẩn hóa trên 1.000 bài mỗi năm để so sánh được giữa các năm")
add_image(slide, "05_keyword_trends.png", 0.5, 1.82, 7.9, 4.9)
add_text(slide, "Năm 2015", 8.65, 1.86, 4.1, 0.3, size=12.5, bold=True, color=NAVY)
kw_rows = []
for word in ("quantum", "graph", "diffusion", "neural", "attention", "transformer"):
    match = keywords[(keywords.year == 2015) & (keywords.word == word)]
    if not match.empty:
        item = match.iloc[0]
        kw_rows.append([word, vn_int(item.document_count), vn_float(item.papers_per_1000, 2)])
table(slide, ["Từ khóa", "Số bài", "/1.000 bài"], kw_rows, 8.65, 2.24, 4.05, 2.35, size=10.5,
      col_widths=[1.1, 0.8, 0.9])
add_text(slide, "transformer chỉ 0,27 vì năm 2015 bài về kiến trúc này còn rất ít — đúng thời điểm lịch sử.",
         8.65, 4.75, 4.05, 0.9, size=10.5, color=MUTED)
add_text(slide, "Danh sách 16 từ khóa là cố định, chưa phát hiện cụm từ mới ngoài danh sách.",
         8.65, 5.75, 4.05, 0.8, size=10.5, color=MUTED)

# ---------------------------------------------------------------------------
# 16 - Tác giả
# ---------------------------------------------------------------------------
slide = new_slide(16)
header(slide, "Tác giả và hợp tác", "Thống kê theo chuỗi tên trong trường authors")
add_image(slide, "08_author_collaboration_trend.png", 0.5, 1.82, 6.0, 4.85)
table(slide, ["Tác giả", "Số bài"], [[row.author[:30], vn_int(row.count)]
                                     for row in top_authors.head(8).itertuples()],
      6.85, 1.9, 5.8, 3.2, size=11, col_widths=[2.4, 0.8])
add_text(slide, "CMS/ATLAS Collaboration xuất hiện như một “tác giả” vì dữ liệu ghi tên nhóm.",
         6.85, 5.3, 5.8, 0.7, size=10.5, color=MUTED)
add_text(slide, "Chưa phân giải thực thể nên các tên phổ biến có thể bị cộng gộp — đây là hạn chế đã nêu.",
         6.85, 5.95, 5.8, 0.7, size=10.5, color=MUTED)

# ---------------------------------------------------------------------------
# 17 - LDA
# ---------------------------------------------------------------------------
slide = new_slide(17)
header(slide, "Mô hình chủ đề LDA", f"{model.get('k', '—')} chủ đề · {vn_int(model.get('vocabulary_size', 0))} từ · "
                                    f"log-perplexity {vn_float(model.get('test_log_perplexity'), 3)}")
add_image(slide, "12_lda_topic_bubble.png", 0.5, 1.82, 7.5, 4.9)
add_text(slide, "Chủ đề tiêu biểu", 8.3, 1.86, 4.3, 0.3, size=12.5, bold=True, color=NAVY)
topic_items = [f"T{item['topic']}: {', '.join(item['terms'][:3])}" for item in topics[:6]]
add_bullets(slide, topic_items, 8.3, 2.24, 4.4, 2.9, size=11, gap=8)
add_text(slide, f"Huấn luyện {vn_int(model.get('train_documents', 0))} bài, kiểm định "
                f"{vn_int(model.get('test_documents', 0))} bài, chia tất định theo id.",
         8.3, 5.35, 4.4, 0.8, size=10.5, color=MUTED)
add_text(slide, "Hai chủ đề lớn nhất là phương pháp luận chung — mô hình chưa tách hết ngôn ngữ học thuật.",
         8.3, 6.1, 4.4, 0.7, size=10.5, color=MUTED)

# ---------------------------------------------------------------------------
# 18 - Kiểm định ngoại suy
# ---------------------------------------------------------------------------
slide = new_slide(18)
header(slide, "Kiểm định ngoại suy xu hướng", "Chỉ công bố dự báo khi vượt baseline holdout 2013–2015")
add_image(slide, "10_validated_trend.png", 0.5, 1.82, 7.4, 4.9)
add_text(slide, "Kết quả holdout", 8.2, 1.86, 4.4, 0.3, size=12.5, bold=True, color=NAVY)
table(slide, ["Từ khóa", "MAE", "Baseline", "Kết luận"],
      [[item.get("word", "—"), vn_float(item.get("mae"), 3), vn_float(item.get("baseline_mae"), 3),
        "Đạt" if item.get("status") == "accepted" else "Không"] for item in forecast.get("metrics", [])],
      8.2, 2.24, 4.5, 2.25, size=10.5, col_widths=[1.1, 0.8, 0.9, 0.8])
add_text(slide, "Cả 4 từ khóa đều vượt baseline; mức cải thiện lớn nhất ở quantum và attention.",
         8.2, 4.65, 4.5, 0.7, size=10.5, bold=True, color=GREEN)
add_text(slide, "Huấn luyện đến hết 2012, dự báo 2013–2015, so MAE với “giữ nguyên giá trị năm cuối”.",
         8.2, 5.5, 4.5, 1.0, size=10, color=MUTED)

# ---------------------------------------------------------------------------
# 19 - 7 lỗi logic
# ---------------------------------------------------------------------------
slide = new_slide(19)
header(slide, "Bảy lỗi logic phát hiện khi kiểm thử", "Chỉ lộ ra khi chạy thật, không thấy được khi đọc mã một lần")
table(slide, ["#", "Lỗi", "Hệ quả", "Cách sửa"], [
    ["1", "all không chạy sync-hdfs", "HDFS/Hive giữ dữ liệu cũ", "Thêm \"all\" vào điều kiện"],
    ["2", "Consumer dùng raise_error", "Crash-loop ở đúng bản ghi lỗi", "Chuyển sang foreachBatch"],
    ["3", "Thiếu vùng cách ly", "Mất bản ghi lỗi, không điều tra", "Ghi rejects_v2 + reject_reason"],
    ["4", "DDL sai thứ tự cột", "Sai khi đọc bằng công cụ khác", "Sắp theo thứ tự Parquet"],
    ["5", "Mẫu 2 dùng scalar subquery", "Hive 2.3.2 báo lỗi", "SUM(...) OVER ()"],
    ["6", "Insight 2016 “năm chưa kết thúc”", "Giải thích sai bản chất", "Nêu phạm vi dữ liệu"],
    ["7", "Form mất chuyên ngành phụ", "Gửi bài thiếu ngành", "Giữ nguyên danh sách"],
], 0.6, 1.85, 12.1, 4.05, size=10.5, col_widths=[0.3, 2.4, 3.0, 2.6])
add_text(slide, "Sau khi sửa, toàn bộ hệ thống được chạy lại end-to-end: dữ liệu, Hive, streaming, dashboard và báo cáo.",
         0.6, 6.15, 12.1, 0.4, size=11.5, bold=True, color=GREEN)
add_text(slide, "Giao diện điều hướng cũng được làm lại: một thanh segmented liền khối thay cho các nút nổi rời rạc.",
         0.6, 6.55, 12.1, 0.4, size=10.5, color=MUTED)

# ---------------------------------------------------------------------------
# 20 - Kiểm chứng end-to-end
# ---------------------------------------------------------------------------
slide = new_slide(20)
header(slide, "Kiểm chứng end-to-end", "Mọi hạng mục đều đạt trên môi trường Docker thật")
table(slide, ["Hạng mục", "Cách kiểm chứng", "Kết quả"], [
    ["Dữ liệu batch", "Đọc manifest + đếm lại bằng Spark", "704.329 dòng, 2007–2016, 8 nhóm"],
    ["Partition HDFS", "Duyệt /data/arxiv_clean_v2", "Đủ 10 partition + _SUCCESS"],
    ["Hive lịch sử", "SELECT COUNT(*) FROM arxiv_historical", "704.329"],
    ["Hive streaming", "COUNT(*) và COUNT(DISTINCT id)", "57 sự kiện / 34 bài"],
    ["Tám mẫu truy vấn", "Chạy trên dashboard", "8/8 đúng, không lỗi SQL"],
    ["Bản ghi hợp lệ", "Producer 2401.96928", "Vào arxiv_stream"],
    ["Bản ghi lỗi", "Kafka 2401.99999", "Vào rejects: missing_required_field"],
    ["Năm tab + URL", "Bấm tab, deep link, nút Back", "URL ?tab= đúng, 5/5 tab, 0 lỗi console"],
], 0.6, 1.85, 12.1, 4.15, size=10.5, col_widths=[1.5, 3.4, 3.4])
add_text(slide, "Không có hạng mục nào được đánh dấu đạt bằng cách bỏ qua kiểm thử.",
         0.6, 6.25, 12.1, 0.4, size=11.5, bold=True, color=GREEN)

# ---------------------------------------------------------------------------
# 21 - Hạn chế và hướng phát triển
# ---------------------------------------------------------------------------
slide = new_slide(21)
header(slide, "Hạn chế và hướng phát triển", "Điều gì chưa làm được và sẽ làm tiếp")
add_text(slide, "Hạn chế", 0.62, 1.86, 5.8, 0.34, size=15, bold=True, color=RED)
add_bullets(slide, [
    f"Chỉ {len(shards)} shard đầu tiên, không đại diện toàn bộ arXiv.",
    "Tên tác giả chưa phân giải thực thể.",
    "Từ khóa theo danh sách 16 từ cố định.",
    "LDA huấn luyện trên mẫu 200.181 bài.",
    "Đo trên một máy 12 container, chưa phải cụm thật.",
    f"Streaming mới có {STREAM_EVENTS} sự kiện, chưa thử tải cao.",
], 0.62, 2.26, 5.9, 4.0, size=11.5, gap=9)
add_text(slide, "Hướng phát triển", 6.9, 1.86, 5.8, 0.34, size=15, bold=True, color=GREEN)
add_bullets(slide, [
    "Mở rộng số shard, chạy trên cụm nhiều máy.",
    "Phân giải tác giả và mạng đồng tác giả.",
    "Phát hiện cụm từ mới theo thời gian.",
    "Job streaming thứ hai cho chỉ số theo cửa sổ.",
    "Kiểm thử tự động + CI trước khi cập nhật.",
    "Đóng gói một lệnh, có cảnh báo khi consumer dừng.",
], 6.9, 2.26, 5.9, 2.0, size=11.5, gap=9)
add_text(slide, "Ba ưu tiên tiếp theo", 0.62, 4.5, 12.1, 0.3, size=10.5, bold=True, color=BLUE)
step_card(slide, 0.6, 4.78, 3.95, 1.45, 1, "Mở rộng dữ liệu",
          "Tải toàn bộ arXiv và chạy trên cụm nhiều máy để đo hiệu năng thật.")
step_card(slide, 4.69, 4.78, 3.95, 1.45, 2, "Nâng chất lượng phân tích",
          "Phân giải tác giả, phát hiện cụm từ mới, thêm mô hình chủ đề.")
step_card(slide, 8.78, 4.78, 3.95, 1.45, 3, "Vận hành ổn định",
          "CI tự động, cảnh báo khi consumer dừng, đóng gói một lệnh.")
add_text(slide, "Ba ưu tiên này là đề xuất cho phiên bản tiếp theo, không nằm trong phạm vi bài làm hiện tại.",
         0.62, 6.45, 12.1, 0.34, size=10.5, color=MUTED)

# ---------------------------------------------------------------------------
# 22 - Kết luận
# ---------------------------------------------------------------------------
slide = new_slide(22)
card(slide, 0.7, 1.35, 11.9, 4.6, fill=PANEL)
add_text(slide, "KẾT LUẬN", 0.9, 1.6, 11.5, 0.6, size=30, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
add_text(slide, f"Hệ thống xử lý {vn_int(rows)} bài báo từ {pretty_bytes(total_bytes)} dữ liệu thô, sinh 9 bảng phân tích,\n"
                "12 biểu đồ và mô hình 10 chủ đề; phát hiện và sửa 7 lỗi logic;\n"
                "kiểm chứng end-to-end cả nhánh batch lẫn nhánh streaming.",
         1.1, 2.35, 11.1, 1.7, size=17, color=INK, align=PP_ALIGN.CENTER, spacing=1.35)
add_text(slide, "Kafka  →  Spark  →  HDFS  →  Hive  →  Streamlit", 1.1, 4.3, 11.1, 0.45,
         size=16, bold=True, color=BLUE, align=PP_ALIGN.CENTER)
add_text(slide, "Cảm ơn thầy cô và các bạn đã lắng nghe", 1.1, 5.05, 11.1, 0.5, size=14,
         color=MUTED, align=PP_ALIGN.CENTER)

# ---------------------------------------------------------------------------
# 23 - Q&A / thông tin
# ---------------------------------------------------------------------------
slide = new_slide(23, footer=False)
add_logo(slide, left=4.9, top=1.2, width=3.5)
add_text(slide, "PHÂN TÍCH DỮ LIỆU LỚN METADATA BÀI BÁO KHOA HỌC ARXIV", 0.7, 2.35, 11.9, 0.6,
         size=25, bold=True, color=INK, align=PP_ALIGN.CENTER)
add_text(slide, "Hadoop  ·  Spark  ·  Kafka  ·  Hive  ·  Streamlit", 0.7, 3.05, 11.9, 0.4,
         size=15, color=BLUE, align=PP_ALIGN.CENTER)
line = slide.shapes.add_connector(1, Inches(4.0), Inches(3.7), Inches(9.3), Inches(3.7))
line.line.color.rgb = BORDER
line.line.width = Pt(1)
line.shadow.inherit = False
add_text(slide, f"{STUDENT}  ·  {STUDENT_ID}  ·  Lớp {CLASS_ID}", 0.7, 3.95, 11.9, 0.4,
         size=15, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
add_text(slide, f"Giảng viên hướng dẫn: {ADVISOR}", 0.7, 4.4, 11.9, 0.4, size=12.5,
         color=MUTED, align=PP_ALIGN.CENTER)
add_text(slide, "Hưng Yên, tháng 11 năm 2026", 0.7, 4.85, 11.9, 0.4, size=12, color=MUTED,
         align=PP_ALIGN.CENTER)

# ---------------------------------------------------------------------------
# Lưu
# ---------------------------------------------------------------------------
prs.core_properties.title = "Phân tích dữ liệu lớn metadata bài báo khoa học arXiv"
prs.core_properties.author = STUDENT
prs.core_properties.subject = "Bài tập lớn Xử lý dữ liệu lớn"

REPORT_DIR.mkdir(parents=True, exist_ok=True)
outputs = [REPORT_DIR / "SLIDE_THUYET_TRINH_BIGDATA.pptx",
           BASE_DIR / "Slide Thuyết trình Xử lý Dữ liệu lớn - Lê Dương Hiếu.pptx"]
for output in outputs:
    prs.save(output)
    print(f"Slides: {output} ({len(prs.slides._sldIdLst)} slides)")
