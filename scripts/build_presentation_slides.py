"""Build the presentation deck from verified pipeline outputs.

Every figure and number comes from output/analysis_results, output/charts and the
manifests. No slide contains a hand-written statistic.
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
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RESULTS_DIR = BASE_DIR / "output" / "analysis_results"
CHARTS_DIR = BASE_DIR / "output" / "charts"
REPORT_DIR = BASE_DIR / "output" / "reports"

NAVY = RGBColor(0x0B, 0x1F, 0x3A)
BLUE = RGBColor(0x1D, 0x4E, 0xD8)
ACCENT = RGBColor(0x0E, 0x9F, 0x6E)
MUTED = RGBColor(0x47, 0x55, 0x69)
LIGHT = RGBColor(0xF1, 0xF5, 0xF9)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARKTEXT = RGBColor(0x1F, 0x29, 0x37)

STUDENT = "LÊ DƯƠNG HIẾU"
STUDENT_ID = "12423011"
CLASS_ID = "124231"
ADVISOR = "TS. NGUYỄN VĂN QUYẾT"
SCHOOL = "TRƯỜNG ĐẠI HỌC SƯ PHẠM KỸ THUẬT HƯNG YÊN"


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
fields = load_parquet("field_trends")
categories = load_parquet("top_categories_yearly")
keywords = load_parquet("hot_keyword_trends")
field_metrics = load_parquet("field_metrics").sort_values("papers", ascending=False)
top_authors = load_parquet("top_authors").sort_values("count", ascending=False)

rows = int(analysis["rows"])
min_year, max_year = int(analysis["min_year"]), int(analysis["max_year"])
span = max_year - min_year + 1
groups = int(analysis["groups"])
shards = source.get("shards", [])
total_bytes = source.get("total_bytes") or sum(int(s.get("bytes", 0)) for s in shards)
model = analysis.get("model") or {}
cat_totals = categories.groupby("primary_category")["count"].sum().sort_values(ascending=False)
top_group = field_metrics.iloc[0]
# Boundary years can be partial; growth is quoted on interior years only.
stable_years = yearly[(yearly["year"] > min_year) & (yearly["year"] < max_year)]
growth_start, growth_end = (stable_years.iloc[0], stable_years.iloc[-1]) if len(stable_years) >= 2 else (yearly.iloc[0], yearly.iloc[-1])
overall_growth = (growth_end["count"] / growth_start["count"] - 1) * 100 if growth_start["count"] else None
accepted = [item for item in forecast.get("metrics", []) if item.get("status") == "accepted"]


prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def new_slide():
    return prs.slides.add_slide(BLANK)


def background(slide, color=WHITE):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def add_text(slide, text, left, top, width, height, size=18, bold=False, color=DARKTEXT,
             align=PP_ALIGN.LEFT, font="Calibri", line_spacing=1.15):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = 1
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    paragraph.line_spacing = line_spacing
    run = paragraph.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font
    return box


def title_bar(slide, title, subtitle=None, number=None):
    background(slide)
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(0.95))
    bar.fill.solid()
    bar.fill.fore_color.rgb = NAVY
    bar.line.fill.background()
    accent = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(0.95), prs.slide_width, Inches(0.06))
    accent.fill.solid()
    accent.fill.fore_color.rgb = ACCENT
    accent.line.fill.background()
    add_text(slide, title, 0.55, 0.16, 10.9, 0.62, size=27, bold=True, color=WHITE)
    if number is not None:
        add_text(slide, f"{number:02d}", 11.9, 0.2, 0.95, 0.5, size=20, bold=True,
                 color=RGBColor(0x93, 0xC5, 0xFD), align=PP_ALIGN.RIGHT)
    if subtitle:
        add_text(slide, subtitle, 0.6, 1.15, 12.1, 0.5, size=14, color=MUTED)


def add_bullets(slide, items, left=0.7, top=1.7, width=6.0, height=5.0, size=17, gap=10):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    for index, item in enumerate(items):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.space_after = Pt(gap)
        paragraph.line_spacing = 1.2
        run = paragraph.add_run()
        run.text = "•  " + item
        run.font.size = Pt(size)
        run.font.color.rgb = DARKTEXT
        run.font.name = "Calibri"
    return box


def add_image_fit(slide, filename, left, top, width, height, border=True):
    path = CHARTS_DIR / filename
    if not path.exists():
        path = BASE_DIR / "output" / "screenshots" / filename
    if not path.exists():
        raise FileNotFoundError(f"Thiếu hình: {path}")
    from PIL import Image
    with Image.open(path) as image:
        ratio = image.width / image.height
    box_ratio = width / height
    if ratio >= box_ratio:
        final_width = width
        final_height = width / ratio
    else:
        final_height = height
        final_width = height * ratio
    left = left + (width - final_width) / 2
    top = top + (height - final_height) / 2
    picture = slide.shapes.add_picture(str(path), Inches(left), Inches(top),
                                       Inches(final_width), Inches(final_height))
    if border:
        picture.line.color.rgb = RGBColor(0xCB, 0xD5, 0xE1)
    return picture


def kpi_card(slide, left, top, width, height, value, label, color=BLUE):
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top),
                                  Inches(width), Inches(height))
    card.fill.solid()
    card.fill.fore_color.rgb = LIGHT
    card.line.color.rgb = RGBColor(0xDB, 0xE3, 0xEE)
    card.shadow.inherit = False
    add_text(slide, value, left + 0.15, top + 0.18, width - 0.3, 0.55, size=26, bold=True, color=color)
    add_text(slide, label, left + 0.15, top + 0.78, width - 0.3, height - 0.85, size=12, color=MUTED)


def table(slide, headers, rows, left, top, width, height, size=12, col_widths=None):
    shape = slide.shapes.add_table(len(rows) + 1, len(headers), Inches(left), Inches(top),
                                   Inches(width), Inches(height))
    table_obj = shape.table
    if col_widths:
        for index, ratio in enumerate(col_widths):
            table_obj.columns[index].width = Emu(int(Inches(width) * ratio))
    for column, header in enumerate(headers):
        cell = table_obj.cell(0, column)
        cell.text = header
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
        for paragraph in cell.text_frame.paragraphs:
            paragraph.alignment = PP_ALIGN.CENTER
            for run in paragraph.runs:
                run.font.size = Pt(size)
                run.font.bold = True
                run.font.color.rgb = WHITE
                run.font.name = "Calibri"
    for row_index, row in enumerate(rows, 1):
        for column, value in enumerate(row):
            cell = table_obj.cell(row_index, column)
            cell.text = str(value)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if row_index % 2 else LIGHT
            for paragraph in cell.text_frame.paragraphs:
                paragraph.alignment = PP_ALIGN.CENTER if column else PP_ALIGN.LEFT
                for run in paragraph.runs:
                    run.font.size = Pt(size)
                    run.font.color.rgb = DARKTEXT
                    run.font.name = "Calibri"
    return table_obj


def footer(slide, text):
    add_text(slide, text, 0.6, 7.05, 12.1, 0.3, size=10, color=RGBColor(0x94, 0xA3, 0xB8))


# 01 - Title ---------------------------------------------------------------
slide = new_slide()
background(slide, NAVY)
band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(5.05), prs.slide_width, Inches(0.08))
band.fill.solid()
band.fill.fore_color.rgb = ACCENT
band.line.fill.background()
add_text(slide, SCHOOL, 0.8, 0.55, 11.8, 0.4, size=16, bold=True, color=RGBColor(0xBF, 0xDB, 0xFE),
         align=PP_ALIGN.CENTER)
add_text(slide, "BÀI TẬP LỚN — XỬ LÝ DỮ LIỆU LỚN", 0.8, 1.15, 11.8, 0.45, size=15,
         color=RGBColor(0xCB, 0xD5, 0xE1), align=PP_ALIGN.CENTER)
add_text(slide,
         "PHÂN TÍCH METADATA BÀI BÁO KHOA HỌC ARXIV\nTRÊN NỀN TẢNG HADOOP, SPARK, KAFKA VÀ HIVE",
         0.9, 1.95, 11.6, 1.5, size=32, bold=True, color=WHITE, align=PP_ALIGN.CENTER, line_spacing=1.2)
add_text(slide, f"{len(shards)} shard · {pretty_bytes(total_bytes)} · {vn_int(rows)} bài báo · "
                f"{min_year}–{max_year}",
         0.9, 3.75, 11.6, 0.45, size=17, color=RGBColor(0x86, 0xEF, 0xAC), align=PP_ALIGN.CENTER)
add_text(slide, f"Sinh viên: {STUDENT}  ·  MSSV: {STUDENT_ID}  ·  Lớp: {CLASS_ID}",
         0.9, 5.35, 11.6, 0.4, size=15, color=WHITE, align=PP_ALIGN.CENTER)
add_text(slide, f"Giảng viên hướng dẫn: {ADVISOR}  ·  Hưng Yên, 2026",
         0.9, 5.8, 11.6, 0.4, size=13, color=RGBColor(0xCB, 0xD5, 0xE1), align=PP_ALIGN.CENTER)

# 02 - Problem and objectives ---------------------------------------------
slide = new_slide()
title_bar(slide, "Bài toán và mục tiêu", "Từ dữ liệu thô đến kết quả có thể kiểm chứng", 2)
add_bullets(slide, [
    "arXiv tăng trưởng liên tục, metadata vượt khả năng xử lý của một máy.",
    "Cần theo dõi xu hướng nghiên cứu, cơ cấu ngành, mức độ hợp tác.",
    "Nhiều bài làm công bố số liệu không tái lập được, biểu đồ không rõ nguồn.",
], left=0.7, top=1.6, width=6.2, height=2.6, size=16)
add_text(slide, "Mục tiêu của bài làm", 7.2, 1.65, 5.4, 0.4, size=19, bold=True, color=BLUE)
add_bullets(slide, [
    "Pipeline batch chạy lại được, có manifest và mã lần chạy.",
    "Năm nộp bài lấy từ phiên bản v1, kiểm tra chéo với mã arXiv.",
    "12 biểu đồ và mô hình LDA sinh tự động từ Spark.",
    "Ngoại suy xu hướng chỉ công bố khi vượt baseline holdout.",
], left=7.2, top=2.15, width=5.5, height=3.6, size=14, gap=12)
add_text(slide, "Nguyên tắc: mọi con số trong báo cáo và slide đều truy vết được về một tệp kết quả.",
         0.7, 5.55, 12.0, 0.6, size=14, bold=True, color=ACCENT)

# 03 - Data scope ----------------------------------------------------------
slide = new_slide()
title_bar(slide, "Phạm vi dữ liệu thực tế", f"Nguồn {source.get('repo')} · revision {source.get('revision', '')[:12]}…", 3)
kpi_card(slide, 0.6, 1.55, 2.85, 1.25, pretty_bytes(total_bytes), "Dung lượng 2 shard Parquet")
kpi_card(slide, 3.63, 1.55, 2.85, 1.25, vn_int(clean.get("raw_rows", 0)), "Bản ghi thô")
kpi_card(slide, 6.66, 1.55, 2.85, 1.25, vn_int(rows), "Bản ghi sạch", ACCENT)
kpi_card(slide, 9.69, 1.55, 2.85, 1.25, f"{min_year}–{max_year}", "Năm nộp v1")
table(slide,
      ["Shard", "Tệp", "Dung lượng", "SHA-256"],
      [[str(index + 1), item.get("local_name") or Path(item.get("path", "")).name,
        pretty_bytes(item.get("bytes", 0)), (item.get("sha256") or "—")[:20] + "…"]
       for index, item in enumerate(shards)],
      0.6, 3.05, 12.1, 1.2, size=12, col_widths=[0.08, 0.25, 0.17, 0.5])
add_text(slide,
         f"Đã loại {vn_int(clean.get('rejected_rows', 0))} bản ghi thiếu trường bắt buộc hoặc năm không hợp lệ. "
         f"{groups} nhóm ngành. Dữ liệu chỉ gồm các shard đã tải, không đại diện toàn bộ arXiv.",
         0.6, 4.55, 12.1, 0.8, size=13, color=MUTED)
add_text(slide, f"{vn_int(clean.get('v1_id_year_differences', 0))} bản ghi có năm v1 khác năm suy từ mã "
                "(nộp cuối tháng 12, nhận mã tháng 1 năm sau) — được giữ lại và báo cáo, không che bằng 0.",
         0.6, 5.35, 12.1, 0.7, size=13, color=DARKTEXT)
footer(slide, "Nguồn: data/source_manifest.json và data/clean_manifest.json")

# 04 - Architecture --------------------------------------------------------
slide = new_slide()
title_bar(slide, "Kiến trúc hệ thống", "Batch và streaming dùng chung tầng lưu trữ HDFS", 4)
add_image_fit(slide, "00_pipeline_full_architecture.png", 0.55, 1.45, 8.3, 5.35)
add_bullets(slide, [
    "Batch: Parquet → Spark → HDFS → Hive → Dashboard.",
    "Streaming: Producer → Kafka → Spark → HDFS.",
    "Kiểm tra manifest trước khi hiển thị.",
    "Checkpoint bảo vệ luồng sự kiện.",
], left=9.15, top=1.65, width=3.8, height=4.2, size=13, gap=12)

# 05 - Tech stack ----------------------------------------------------------
slide = new_slide()
title_bar(slide, "Công nghệ sử dụng", "Cùng phiên bản trong Docker Compose và môi trường chạy", 5)
table(slide, ["Thành phần", "Vai trò", "Phiên bản"], [
    ["Hadoop HDFS", "Lưu trữ phân tán", "3.2.1"],
    ["Apache Spark", "Batch, streaming, MLlib LDA", analysis.get("spark_version", "3.5.3")],
    ["Apache Kafka", "Hàng đợi sự kiện", "7.6.0"],
    ["Apache Hive", "External table trên HDFS", "2.3.2"],
    ["Streamlit", "Dashboard 5 tab", "1.40.0"],
    ["Docker Compose", "Điều phối dịch vụ", "Compose v2"],
], 0.7, 1.6, 7.4, 3.9, size=14, col_widths=[0.32, 0.48, 0.2])
add_text(slide, "Vì sao chọn?", 8.5, 1.62, 4.2, 0.4, size=18, bold=True, color=BLUE)
add_bullets(slide, [
    "Spark xử lý cả batch và streaming trong một engine.",
    "HDFS + Hive tách lưu trữ khỏi tính toán.",
    "Kafka mô phỏng luồng tiếp nhận thời gian thực.",
    "Streamlit phù hợp demo học thuật, ít mã giao diện.",
], left=8.5, top=2.1, width=4.3, height=3.6, size=13, gap=10)

# 06 - Data contract -------------------------------------------------------
slide = new_slide()
title_bar(slide, "Quy tắc dữ liệu", "Điểm khác biệt so với cách làm đơn giản", 6)
add_bullets(slide, [
    "Năm nộp = ngày tạo phiên bản v1; fallback theo mã arXiv.",
    "Mã cũ trước 4/2007 và mã mới được xử lý riêng, có kiểm tra tháng.",
    "update_year chỉ là năm cập nhật metadata, không dùng phân tích xu hướng.",
    "Bản ghi thiếu trường bắt buộc hoặc năm ngoài 1991–năm hiện tại bị loại.",
    "Mã bài báo trùng làm dừng pipeline thay vì tự chọn một phiên bản.",
], left=0.7, top=1.6, width=7.3, height=4.5, size=16, gap=12)
box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.35), Inches(1.75),
                             Inches(4.3), Inches(3.4))
box.fill.solid()
box.fill.fore_color.rgb = LIGHT
box.line.color.rgb = RGBColor(0xDB, 0xE3, 0xEE)
add_text(slide, "Kết quả kiểm tra trên dữ liệu thật", 8.6, 1.95, 3.8, 0.4, size=14, bold=True, color=NAVY)
add_text(slide, f"{vn_int(clean.get('raw_rows', 0))} → {vn_int(rows)}",
         8.6, 2.42, 3.8, 0.5, size=21, bold=True, color=ACCENT)
add_text(slide, f"bản ghi sạch · loại {vn_int(clean.get('rejected_rows', 0))} dòng",
         8.6, 2.98, 3.8, 0.4, size=12.5, color=MUTED)
add_text(slide, f"{vn_int(clean.get('v1_id_year_differences', 0))} bản ghi chênh năm v1/mã",
         8.6, 3.45, 3.8, 0.4, size=13, color=MUTED)
add_text(slide, "0 mã trùng", 8.6, 3.9, 3.8, 0.4, size=13, color=MUTED)
add_text(slide, "Quy tắc này được kiểm thử tự động cho cả mã cũ và mã mới.",
         8.6, 4.35, 3.8, 0.6, size=12, color=NAVY)

# 07 - Pipeline stages -----------------------------------------------------
slide = new_slide()
title_bar(slide, "Các bước thực hiện", "Một lệnh cho mỗi tầng, có thể chạy lại từ đầu", 7)
stages = [
    ("1", "Tải & kiểm soát nguồn", "2 shard, SHA-256, revision"),
    ("2", "Tiền xử lý", "Làm sạch, chuẩn hóa năm, tách từ"),
    ("3", "Phân tích", "8 bảng kết quả + LDA"),
    ("4", "Biểu đồ & kiểm định", "12 hình + holdout 3 năm"),
    ("5", "HDFS & Hive", "Parquet phân vùng theo năm"),
    ("6", "Dashboard & báo cáo", "Đọc manifest đã xác minh"),
]
for index, (number, heading, detail) in enumerate(stages):
    column, row = index % 3, index // 3
    left = 0.7 + column * 4.2
    top = 1.65 + row * 2.35
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top),
                                  Inches(3.85), Inches(2.0))
    card.fill.solid()
    card.fill.fore_color.rgb = WHITE
    card.line.color.rgb = RGBColor(0xCB, 0xD5, 0xE1)
    circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(left + 0.22), Inches(top + 0.22),
                                    Inches(0.62), Inches(0.62))
    circle.fill.solid()
    circle.fill.fore_color.rgb = BLUE
    circle.line.fill.background()
    add_text(slide, number, left + 0.22, top + 0.27, 0.62, 0.5, size=18, bold=True,
             color=WHITE, align=PP_ALIGN.CENTER)
    add_text(slide, heading, left + 0.95, top + 0.24, 2.75, 0.45, size=15, bold=True, color=NAVY)
    add_text(slide, detail, left + 0.95, top + 0.75, 2.75, 1.0, size=12, color=MUTED)

# 08 - Results overview ----------------------------------------------------
slide = new_slide()
title_bar(slide, "Kết quả tổng quan", f"Lần chạy {analysis['clean_run_id'][:8]} · Spark {analysis.get('spark_version')}", 8)
kpi_card(slide, 0.6, 1.5, 3.0, 1.35, vn_int(rows), "Bài báo sạch")
kpi_card(slide, 3.75, 1.5, 3.0, 1.35, f"{span} năm", f"{min_year}–{max_year}", ACCENT)
kpi_card(slide, 6.9, 1.5, 3.0, 1.35, f"{groups}", "Nhóm ngành", BLUE)
kpi_card(slide, 10.05, 1.5, 2.7, 1.35, f"{vn_float(analysis.get('total_analysis_seconds'), 0)}s",
         "Thời gian phân tích", MUTED)
add_image_fit(slide, "01_yearly_growth.png", 0.6, 3.1, 7.6, 3.7)
add_text(slide, "Tăng trưởng", 8.5, 3.15, 4.3, 0.4, size=17, bold=True, color=NAVY)
add_text(slide,
         f"Trong các năm nội suy {int(growth_start['year'])}–{int(growth_end['year'])}, số bài tăng từ "
         f"{vn_int(growth_start['count'])} lên {vn_int(growth_end['count'])}, tương đương "
         f"{vn_float(overall_growth, 1)}%.",
         8.5, 3.65, 4.3, 1.1, size=15, color=DARKTEXT)
add_text(slide, "Hai năm biên có thể chưa đầy đủ do phạm vi shard, nên không diễn giải như xu hướng toàn arXiv.",
         8.5, 4.9, 4.3, 1.0, size=12, color=MUTED)

# 09 - Fields --------------------------------------------------------------
slide = new_slide()
title_bar(slide, "Cơ cấu nhóm ngành", f"{groups} nhóm sau chuẩn hóa archive", 9)
add_image_fit(slide, "07_field_distribution.png", 0.55, 1.45, 5.3, 5.3)
table(slide, ["Nhóm", "Số bài", "Tỷ lệ", "Tác giả/bài"],
      [[row.main_group, vn_int(row.papers), vn_float(row.papers / rows * 100, 1) + "%",
        vn_float(row.avg_authors, 2)]
       for row in field_metrics.head(6).itertuples()],
      6.15, 1.6, 6.4, 3.8, size=13, col_widths=[0.3, 0.25, 0.2, 0.25])
add_text(slide, f"Nhóm lớn nhất: {top_group['main_group']} với {vn_int(top_group['papers'])} bài "
                f"({vn_float(top_group['papers'] / rows * 100, 1)}%).",
         6.15, 5.6, 6.4, 0.6, size=14, bold=True, color=BLUE)

# 10 - Categories ----------------------------------------------------------
slide = new_slide()
title_bar(slide, "Chuyên ngành hàng đầu", "Xếp hạng theo tổng số bài trong phạm vi đã tải", 10)
add_image_fit(slide, "03_top_categories.png", 0.55, 1.45, 7.5, 5.25)
add_text(slide, "Top 6 chuyên ngành", 8.35, 1.6, 4.4, 0.4, size=16, bold=True, color=NAVY)
add_bullets(slide, [f"{name}: {vn_int(value)} bài" for name, value in cat_totals.head(6).items()],
            left=8.35, top=2.1, width=4.4, height=3.4, size=14, gap=12)
add_text(slide, "Chuyên ngành được xếp hạng lại theo từng năm trong bảng gốc, "
                "biểu đồ tổng hợp toàn giai đoạn.",
         8.35, 5.5, 4.4, 0.9, size=12, color=MUTED)

# 11 - Keywords ------------------------------------------------------------
slide = new_slide()
title_bar(slide, "Xu hướng từ khóa công nghệ", "Chuẩn hóa trên 1.000 bài mỗi năm", 11)
add_image_fit(slide, "05_keyword_trends.png", 0.55, 1.45, 8.4, 5.3)
add_text(slide, "Cách đo", 9.2, 1.6, 3.7, 0.4, size=16, bold=True, color=NAVY)
add_text(slide,
         "Đếm số bài có chứa từ khóa trong abstract, chia cho tổng số bài cùng năm. "
         "Cách này tránh việc năm ít bài bị đánh giá thấp hơn năm nhiều bài.",
         9.2, 2.05, 3.7, 1.9, size=13, color=DARKTEXT)
add_text(slide, "Ghi chú", 9.2, 4.0, 3.7, 0.4, size=14, bold=True, color=NAVY)
add_text(slide, "Danh sách 16 từ khóa là cố định, chưa phát hiện cụm từ mới ngoài danh sách.",
         9.2, 4.4, 3.7, 1.2, size=12, color=MUTED)
footer(slide, "Nguồn: output/analysis_results/hot_keyword_trends.parquet")

# 12 - Authors -------------------------------------------------------------
slide = new_slide()
title_bar(slide, "Tác giả và hợp tác", "Thống kê theo tên trong authors_parsed", 12)
add_image_fit(slide, "08_author_collaboration_trend.png", 0.55, 1.45, 6.3, 5.2)
table(slide, ["Tác giả", "Số bài"],
      [[row.author[:32], vn_int(row.count)] for row in top_authors.head(8).itertuples()],
      7.15, 1.65, 5.4, 3.6, size=13, col_widths=[0.72, 0.28])
add_text(slide, "Tên chưa được phân giải thực thể nên có thể gộp nhiều người trùng tên.",
         7.15, 5.55, 5.4, 0.7, size=12, color=MUTED)

# 13 - LDA -----------------------------------------------------------------
slide = new_slide()
title_bar(slide, "Mô hình chủ đề LDA", f"{model.get('k', '—')} chủ đề · {vn_int(model.get('vocabulary_size', 0))} từ",
          13)
add_image_fit(slide, "12_lda_topic_bubble.png", 0.55, 1.45, 7.6, 5.3)
add_text(slide, "Chủ đề tiêu biểu", 8.4, 1.6, 4.4, 0.4, size=16, bold=True, color=NAVY)
topic_items = [f"T{item['topic']}: {', '.join(item['terms'][:3])}" for item in topics[:6]]
add_bullets(slide, topic_items, left=8.4, top=2.05, width=4.4, height=3.6, size=12, gap=8)
add_text(slide, f"Log-perplexity kiểm định: {vn_float(model.get('test_log_perplexity'), 3)}",
         8.4, 5.65, 4.4, 0.4, size=13, bold=True, color=ACCENT)
add_text(slide, f"Huấn luyện trên {vn_int(model.get('train_documents', 0))} bài mẫu xác định.",
         8.4, 6.05, 4.4, 0.5, size=11, color=MUTED)

# 14 - Forecast ------------------------------------------------------------
slide = new_slide()
title_bar(slide, "Kiểm định ngoại suy xu hướng", "Chỉ công bố dự báo khi vượt baseline holdout", 14)
add_image_fit(slide, "10_validated_trend.png", 0.55, 1.45, 7.5, 5.2)
add_text(slide, "Kết quả holdout 3 năm", 8.3, 1.6, 4.5, 0.4, size=16, bold=True, color=NAVY)
rows_table = []
for item in forecast.get("metrics", []):
    rows_table.append([item.get("word", "—"), vn_float(item.get("mae"), 3),
                       vn_float(item.get("baseline_mae"), 3),
                       "Đạt" if item.get("status") == "accepted" else "Không"])
table(slide, ["Từ khóa", "MAE", "Baseline", "Kết luận"], rows_table,
      8.3, 2.1, 4.5, 2.2, size=11, col_widths=[0.3, 0.22, 0.26, 0.22])
add_text(slide, ("Được phép ngoại suy: " + ", ".join(item["word"] for item in accepted))
         if accepted else "Không từ khóa nào vượt baseline, nên không công bố dự báo xa.",
         8.3, 4.55, 4.5, 1.0, size=12, bold=True, color=ACCENT)
add_text(slide, "Dự báo giới hạn tối đa 3 năm sau năm cuối của dữ liệu.",
         8.3, 5.6, 4.5, 0.7, size=12, color=MUTED)

# 15 - Verification --------------------------------------------------------
slide = new_slide()
title_bar(slide, "Kiểm chứng và tái lập", "Cùng một mã lần chạy cho dữ liệu, biểu đồ, báo cáo", 15)
add_bullets(slide, [
    "manifest.json và clean_manifest.json phải trùng clean_run_id.",
    "chart manifest phải trùng clean_run_id với kết quả phân tích.",
    "Báo cáo và slide dừng lại nếu mã lần chạy không khớp.",
    "Kiểm thử tự động cho quy tắc năm, nhóm ngành, schema và đủ 12 biểu đồ.",
], left=0.7, top=1.6, width=6.7, height=3.8, size=15, gap=14)
add_text(slide, "Chạy lại toàn bộ", 7.6, 1.6, 5.0, 0.4, size=16, bold=True, color=NAVY)
commands = [
    "python src/batch_pipeline.py all",
    "python src/visualization.py",
    "python src/batch_pipeline.py sync-hdfs",
    "python src/hive_client.py",
    "python scripts/build_data_mining_style_report.py",
    "python scripts/build_presentation_slides.py",
]
for index, command in enumerate(commands):
    add_text(slide, command, 7.6, 2.1 + index * 0.55, 5.2, 0.4, size=11, color=DARKTEXT,
             font="Consolas")

# 16 - Limitations ---------------------------------------------------------
slide = new_slide()
title_bar(slide, "Hạn chế và hướng phát triển", "Điều gì chưa làm được và vì sao", 16)
add_text(slide, "Hạn chế", 0.7, 1.55, 6.0, 0.4, size=18, bold=True, color=RGBColor(0xB9, 0x1C, 0x1C))
add_bullets(slide, [
    f"Chỉ {len(shards)} shard đầu tiên, không đại diện toàn bộ arXiv.",
    "Tên tác giả chưa phân giải thực thể.",
    "Từ khóa theo danh sách cố định.",
    "LDA huấn luyện trên mẫu để vừa tài nguyên máy.",
    "Đo ở chế độ local[*], chưa benchmark trên cụm.",
    "HDFS, Hive, streaming mới ở mức cấu hình; chưa chạy trên cụm Docker.",
], left=0.7, top=2.02, width=6.3, height=4.4, size=12.5, gap=8)
add_text(slide, "Hướng phát triển", 7.2, 1.55, 5.6, 0.4, size=18, bold=True, color=ACCENT)
add_bullets(slide, [
    "Mở rộng số shard, chạy nhiều worker.",
    "Phân giải tác giả và mạng đồng tác giả.",
    "Phát hiện cụm từ mới theo thời gian.",
    "Kiểm thử tích hợp Docker cho toàn luồng.",
], left=7.2, top=2.05, width=5.5, height=3.6, size=13, gap=12)

# 17 - Conclusion ----------------------------------------------------------
slide = new_slide()
background(slide, NAVY)
add_text(slide, "KẾT LUẬN", 0.8, 1.0, 11.7, 0.7, size=36, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
add_text(slide,
         f"Hệ thống xử lý {vn_int(rows)} bài báo từ {pretty_bytes(total_bytes)} dữ liệu,\n"
         f"sinh {len(chart_manifest['charts'])} biểu đồ, bảng phân tích và mô hình chủ đề\n"
         "theo một quy trình có thể chạy lại và kiểm chứng.",
         0.9, 2.15, 11.5, 1.6, size=21, color=RGBColor(0xE2, 0xE8, 0xF0), align=PP_ALIGN.CENTER,
         line_spacing=1.35)
add_text(slide, "Cảm ơn thầy cô và các bạn đã lắng nghe", 0.9, 4.35, 11.5, 0.6, size=20,
         bold=True, color=RGBColor(0x86, 0xEF, 0xAC), align=PP_ALIGN.CENTER)
add_text(slide, f"{STUDENT} · {STUDENT_ID} · {CLASS_ID}", 0.9, 5.15, 11.5, 0.4, size=14,
         color=RGBColor(0xCB, 0xD5, 0xE1), align=PP_ALIGN.CENTER)

REPORT_DIR.mkdir(parents=True, exist_ok=True)
output = REPORT_DIR / "SLIDE_THUYET_TRINH_BIGDATA.pptx"
prs.save(output)
print(f"Slides: {output} ({len(prs.slides._sldIdLst)} slides)")
