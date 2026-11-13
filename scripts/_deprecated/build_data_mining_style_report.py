"""Build the Vietnamese final report (DOCX + Markdown) from verified pipeline outputs.

Every number is read from:
  data/clean_manifest.json
  data/source_manifest.json
  output/analysis_results/manifest.json + *.parquet
  output/analysis_results/topics.json
  output/forecast_validation.json
  output/charts/manifest.json

Nothing is hard-coded except the narrative text and the student/cover information.
Run after: batch_pipeline.py all -> visualization.py
"""
import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import docx
import pandas as pd
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RESULTS_DIR = BASE_DIR / "output" / "analysis_results"
CHARTS_DIR = BASE_DIR / "output" / "charts"
OUTPUT_DIR = BASE_DIR / "output"
REPORT_DIR = BASE_DIR / "output" / "reports"

STUDENT = "LÊ DƯƠNG HIẾU"
STUDENT_ID = "12423011"
CLASS_ID = "124231"
ADVISOR = "TS. NGUYỄN VĂN QUYẾT"
SCHOOL = "TRƯỜNG ĐẠI HỌC SƯ PHẠM KỸ THUẬT HƯNG YÊN"
FACULTY = "KHOA CÔNG NGHỆ THÔNG TIN"
TITLE = ("NGHIÊN CỨU VÀ XÂY DỰNG HỆ THỐNG PHÂN TÍCH DỮ LIỆU LỚN METADATA "
         "BÀI BÁO KHOA HỌC ARXIV TRÊN NỀN TẢNG HADOOP, SPARK, KAFKA VÀ HIVE")


def load_json(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Thiếu tệp kết quả: {path}. Hãy chạy lại pipeline.")
    return json.loads(path.read_text(encoding="utf-8"))


def load_parquet(name):
    path = RESULTS_DIR / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Thiếu bảng phân tích: {path}")
    return pd.read_parquet(path)


def vn_int(value):
    return f"{int(value):,}".replace(",", ".")


def vn_float(value, digits=2):
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


def shade(cell, hex_color):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def plain(text):
    """Markdown backticks are markdown-only; Word must not show them."""
    return str(text).replace("`", "")


def set_cell(cell, text, bold=False, size=11, align=WD_ALIGN_PARAGRAPH.LEFT):
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = align
    run = paragraph.add_run(plain(text))
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.font.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")


def add_table(doc, headers, rows, widths=None, caption=None):
    if caption:
        paragraph = doc.add_paragraph(plain(caption))
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.keep_with_next = True
        for run in paragraph.runs:
            run.font.size = Pt(11)
            run.font.bold = True
            run.font.italic = True
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for index, header in enumerate(headers):
        set_cell(table.rows[0].cells[index], header, bold=True, size=11,
                 align=WD_ALIGN_PARAGRAPH.CENTER)
        shade(table.rows[0].cells[index], "D9E2F3")
    # Repeat the header on every page and never split a row across pages.
    header_properties = table.rows[0]._tr.get_or_add_trPr()
    header_flag = OxmlElement("w:tblHeader")
    header_flag.set(qn("w:val"), "true")
    header_properties.append(header_flag)
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            set_cell(cells[index], value, size=11,
                     align=WD_ALIGN_PARAGRAPH.CENTER if index else WD_ALIGN_PARAGRAPH.LEFT)
        row_properties = table.rows[-1]._tr.get_or_add_trPr()
        cant_split = OxmlElement("w:cantSplit")
        row_properties.append(cant_split)
    if widths:
        for row in table.rows:
            for index, width in enumerate(widths):
                row.cells[index].width = Cm(width)
    # Never leave a header alone at the bottom of a page.
    for cell in table.rows[0].cells:
        for paragraph in cell.paragraphs:
            paragraph.paragraph_format.keep_with_next = True
    # Small tables read better on a single page.
    if len(rows) <= 8:
        for row in table.rows[:-1]:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.keep_with_next = True
    doc.add_paragraph()
    return table


def add_figure(doc, filename, caption, width=16.0):
    path = CHARTS_DIR / filename
    if not path.exists():
        path = OUTPUT_DIR / "screenshots" / filename
    if not path.exists():
        raise FileNotFoundError(f"Thiếu hình: {path}")
    doc.add_picture(str(path), width=Cm(width))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.paragraphs[-1].paragraph_format.keep_with_next = True
    paragraph = doc.add_paragraph(plain(caption))
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in paragraph.runs:
        run.font.size = Pt(11)
        run.font.italic = True


def add_body(doc, text):
    paragraph = doc.add_paragraph(plain(text))
    paragraph.paragraph_format.first_line_indent = Cm(1.0)
    paragraph.paragraph_format.space_after = Pt(6)
    return paragraph


def add_bullets(doc, items):
    for item in items:
        paragraph = doc.add_paragraph(plain(item), style="List Bullet")
        paragraph.paragraph_format.space_after = Pt(3)


def add_heading(doc, text, level=1):
    heading = doc.add_heading(text, level=level)
    for run in heading.runs:
        run.font.name = "Times New Roman"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
        run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    return heading


def page_break(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ---------------------------------------------------------------------------
# Load verified data
# ---------------------------------------------------------------------------
clean = load_json(DATA_DIR / "clean_manifest.json")
analysis = load_json(RESULTS_DIR / "manifest.json")
source = load_json(DATA_DIR / "source_manifest.json")
chart_manifest = load_json(CHARTS_DIR / "manifest.json")
forecast = load_json(BASE_DIR / "output" / "forecast_validation.json")
topics = load_json(RESULTS_DIR / "topics.json")
predictions = load_json(BASE_DIR / "output" / "forecast_predictions.json")

if clean.get("clean_run_id") != analysis.get("clean_run_id"):
    raise RuntimeError("clean_manifest và manifest phân tích không cùng một lần chạy.")
if chart_manifest.get("clean_run_id") != analysis.get("clean_run_id"):
    raise RuntimeError("Biểu đồ được tạo từ dữ liệu khác. Hãy chạy lại visualization.py.")

yearly = load_parquet("yearly_growth").sort_values("year")
fields = load_parquet("field_trends")
categories = load_parquet("top_categories_yearly")
keywords = load_parquet("hot_keyword_trends")
field_metrics = load_parquet("field_metrics").sort_values("papers", ascending=False)
top_authors = load_parquet("top_authors").sort_values("count", ascending=False)
author_trends = load_parquet("author_trends").sort_values("year")

shards = source.get("shards", [])
total_bytes = source.get("total_bytes") or sum(int(s.get("bytes", 0)) for s in shards)
rows = int(analysis["rows"])
min_year, max_year = int(analysis["min_year"]), int(analysis["max_year"])
span = max_year - min_year + 1
groups = int(analysis["groups"])
model = analysis.get("model") or {}
timings = analysis.get("timings_seconds") or {}
top_group_row = field_metrics.iloc[0]
keyword_peak_year = int(yearly.loc[yearly["count"].idxmax(), "year"])
keyword_peak_count = int(yearly["count"].max())
cat_totals = categories.groupby("primary_category")["count"].sum().sort_values(ascending=False)
top_cat = cat_totals.index[0]
top_cat_count = int(cat_totals.iloc[0])

# The first and last years of a downloaded shard can be partial, so growth claims use
# the interior years only; the boundary values stay in the table with a caveat.
stable_years = yearly[(yearly["year"] > min_year) & (yearly["year"] < max_year)]
if len(stable_years) >= 2:
    growth_start = stable_years.iloc[0]
    growth_end = stable_years.iloc[-1]
    avg_yoy = stable_years["yoy_growth_rate"].dropna().mean()
else:
    growth_start = yearly.iloc[0]
    growth_end = yearly.iloc[-1]
    avg_yoy = yearly["yoy_growth_rate"].dropna().mean()
overall_growth = (growth_end["count"] / growth_start["count"] - 1) * 100 if growth_start["count"] else None

hot_words = ["transformer", "attention", "diffusion", "quantum", "neural", "graph"]
# The final dataset year is partial, so keyword totals are quoted for the last complete year.
keyword_reference_year = int(max(year for year in yearly["year"] if min_year < year < max_year))
hot_rows = []
for word in hot_words:
    subset = keywords[(keywords["word"] == word) & (keywords["year"] == keyword_reference_year)]
    if subset.empty:
        continue
    last = subset.iloc[0]
    hot_rows.append([word, vn_float(last["document_count"], 0), vn_float(last["papers_per_1000"], 2)])

radar_groups = field_metrics.head(4)
accepted = [item for item in forecast.get("metrics", []) if item.get("status") == "accepted"]
held = [item for item in forecast.get("metrics", []) if item.get("status") != "accepted"]

total_seconds = analysis.get("total_analysis_seconds")
model_text = (
    f"LDA {model.get('k')} chủ đề, từ điển {vn_int(model.get('vocabulary_size', 0))} từ, "
    f"log-perplexity kiểm định {vn_float(model.get('test_log_perplexity'), 3)}"
    if model.get("status") == "trained" else "Chưa huấn luyện LDA"
)


# ---------------------------------------------------------------------------
# DOCX document
# ---------------------------------------------------------------------------
doc = docx.Document()
section = doc.sections[0]
section.page_height = Cm(29.7)
section.page_width = Cm(21.0)
section.top_margin = Cm(2.5)
section.bottom_margin = Cm(2.5)
section.left_margin = Cm(3.0)
section.right_margin = Cm(2.0)

style = doc.styles["Normal"]
style.font.name = "Times New Roman"
style.font.size = Pt(13)
style.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
style.paragraph_format.line_spacing = 1.5

for level, size in ((1, 16), (2, 14), (3, 13)):
    heading_style = doc.styles[f"Heading {level}"]
    heading_style.font.name = "Times New Roman"
    heading_style.font.size = Pt(size)
    heading_style.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")

# Cover -------------------------------------------------------------------
for text, size, bold in (("BỘ GIÁO DỤC VÀ ĐÀO TẠO", 14, True), (SCHOOL, 15, True), (FACULTY, 14, True)):
    paragraph = doc.add_paragraph(text)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in paragraph.runs:
        run.font.size = Pt(size)
        run.font.bold = bold

doc.add_paragraph()
paragraph = doc.add_paragraph("BÀI TẬP LỚN")
paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
paragraph.runs[0].font.size = Pt(20)
paragraph.runs[0].font.bold = True
paragraph = doc.add_paragraph("HỌC PHẦN: XỬ LÝ DỮ LIỆU LỚN (BIG DATA)")
paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
paragraph.runs[0].font.size = Pt(15)
paragraph.runs[0].font.bold = True

doc.add_paragraph()
paragraph = doc.add_paragraph("ĐỀ TÀI:")
paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
paragraph.runs[0].font.size = Pt(14)
paragraph = doc.add_paragraph(TITLE)
paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
paragraph.runs[0].font.size = Pt(16)
paragraph.runs[0].font.bold = True

doc.add_paragraph()
info = [
    ("Sinh viên thực hiện", STUDENT),
    ("Mã sinh viên", STUDENT_ID),
    ("Mã lớp", CLASS_ID),
    ("Giảng viên hướng dẫn", ADVISOR),
]
table = doc.add_table(rows=0, cols=2)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
for label, value in info:
    cells = table.add_row().cells
    set_cell(cells[0], label, bold=True, size=13)
    set_cell(cells[1], value, size=13)

doc.add_paragraph()
paragraph = doc.add_paragraph("HƯNG YÊN - 2026")
paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
paragraph.runs[0].font.size = Pt(14)
paragraph.runs[0].font.bold = True
page_break(doc)

# Table of contents (static, matching the generated headings) --------------
add_heading(doc, "MỤC LỤC", 1)
toc_rows = [
    ("LỜI CẢM ƠN", ""),
    ("CHƯƠNG 1. GIỚI THIỆU BÀI TOÁN VÀ PHẠM VI DỮ LIỆU", ""),
    ("CHƯƠNG 2. CƠ SỞ LÝ THUYẾT VÀ KIẾN TRÚC HỆ THỐNG", ""),
    ("CHƯƠNG 3. DỮ LIỆU VÀ PHƯƠNG PHÁP XỬ LÝ", ""),
    ("CHƯƠNG 4. KẾT QUẢ THỰC NGHIỆM", ""),
    ("CHƯƠNG 5. TRIỂN KHAI VÀ KIỂM CHỨNG HỆ THỐNG", ""),
    ("CHƯƠNG 6. ĐÁNH GIÁ, HẠN CHẾ VÀ HƯỚNG PHÁT TRIỂN", ""),
    ("KẾT LUẬN", ""),
    ("TÀI LIỆU THAM KHẢO", ""),
    ("PHỤ LỤC: CÁCH CHẠY LẠI PIPELINE", ""),
]
for item, _ in toc_rows:
    paragraph = doc.add_paragraph(item)
    paragraph.paragraph_format.space_after = Pt(4)
page_break(doc)

# Acknowledgements ----------------------------------------------------------
add_heading(doc, "LỜI CẢM ƠN", 1)
add_body(doc, "Em xin chân thành cảm ơn thầy " + ADVISOR + " đã hướng dẫn, góp ý và định hướng "
              "trong suốt quá trình thực hiện bài tập lớn. Em cũng xin cảm ơn các thầy cô trong "
              + FACULTY + ", " + SCHOOL + " đã trang bị kiến thức nền tảng về cơ sở dữ liệu, "
              "hệ phân tán và xử lý dữ liệu lớn để em có thể hoàn thành đề tài này.")
add_body(doc, "Đề tài được xây dựng trên dữ liệu công khai của arXiv. Mọi kết quả trong báo cáo đều "
              "được sinh tự động từ pipeline trong mã nguồn kèm theo; các con số, bảng và biểu đồ "
              "có thể kiểm tra lại bằng cách chạy đúng các lệnh ở phần phụ lục.")
page_break(doc)

# Chapter 1 -----------------------------------------------------------------
add_heading(doc, "CHƯƠNG 1. GIỚI THIỆU BÀI TOÁN VÀ PHẠM VI DỮ LIỆU", 1)
add_heading(doc, "1.1. Đặt vấn đề", 2)
add_body(doc, "arXiv là kho lưu trữ mở các bài báo khoa học, mỗi ngày tiếp nhận hàng nghìn bản thảo "
              "mới thuộc nhiều lĩnh vực. Việc theo dõi xu hướng nghiên cứu, cơ cấu ngành và mức độ "
              "hợp tác giữa các tác giả đòi hỏi xử lý một khối lượng metadata lớn, liên tục tăng. "
              "Các công cụ truy vấn đơn lẻ không đáp ứng được khi dữ liệu vượt quá bộ nhớ của một máy.")
add_body(doc, "Bài tập lớn xây dựng một hệ thống phân tích dữ liệu lớn hoàn chỉnh: dữ liệu Parquet "
              "được xử lý theo lô bằng Apache Spark, kết quả phân tích được lưu trên HDFS và truy vấn "
              "qua Apache Hive; song song, một luồng sự kiện Kafka → Spark Structured Streaming → HDFS "
              "mô phỏng việc tiếp nhận bài báo theo thời gian thực. Toàn bộ kết quả được trình bày "
              "trên dashboard Streamlit.")

add_heading(doc, "1.2. Mục tiêu", 2)
add_bullets(doc, [
    "Xây dựng pipeline batch có thể chạy lại từ đầu, có manifest ghi lại nguồn, số dòng, thời gian và mã định danh lần chạy.",
    "Chuẩn hóa năm nộp bài theo phiên bản v1 thay vì năm cập nhật metadata, có kiểm tra chéo với mã arXiv.",
    "Tính các chỉ số: tăng trưởng theo năm, cơ cấu nhóm ngành, chuyên ngành hàng đầu, từ khóa công nghệ, tác giả và mô hình chủ đề LDA.",
    "Kiểm định mô hình ngoại suy xu hướng bằng tập holdout thay vì công bố dự báo không kiểm chứng.",
    "Trực quan hóa kết quả bằng dashboard và bộ biểu đồ tĩnh phục vụ báo cáo, slide.",
])

add_heading(doc, "1.3. Phạm vi dữ liệu thực tế", 2)
add_body(doc, f"Nguồn dữ liệu là bộ {source.get('repo', 'VatsaDev/test_arxiv')} ở revision "
              f"{source.get('revision', '—')}. Bài làm sử dụng {len(shards)} shard Parquet đầu tiên, "
              f"tổng dung lượng {pretty_bytes(total_bytes)}. Đây là phạm vi có thật của dữ liệu đầu vào; "
              f"báo cáo không suy rộng ra toàn bộ arXiv.")
add_table(
    doc,
    ["Shard", "Tệp cục bộ", "Dung lượng", "SHA-256 (rút gọn)"],
    [[str(index + 1), item.get("local_name") or Path(item.get("path", "")).name,
      pretty_bytes(item.get("bytes", 0)), (item.get("sha256") or "—")[:16] + "…"]
     for index, item in enumerate(shards)],
    caption="Bảng 1.1. Các shard dữ liệu đầu vào và mã băm SHA-256",
)
add_body(doc, f"Sau khi làm sạch, tập phân tích gồm {vn_int(rows)} bài báo, năm nộp đầu tiên từ "
              f"{min_year} đến {max_year} ({span} năm), thuộc {groups} nhóm ngành. "
              f"Số dòng thô là {vn_int(clean.get('raw_rows', 0))}; "
              f"{vn_int(clean.get('rejected_rows', 0))} dòng bị loại vì thiếu trường bắt buộc hoặc năm không hợp lệ.")

add_heading(doc, "1.4. Đóng góp chính", 2)
add_bullets(doc, [
    "Quy tắc xác định năm nộp bài có kiểm thử cho cả mã arXiv cũ và mới, tách biệt với năm cập nhật.",
    "Pipeline batch sinh manifest và mã lần chạy để dashboard, báo cáo và slide chỉ đọc dữ liệu đã xác minh.",
    "Bộ 12 biểu đồ và mô hình LDA được sinh hoàn toàn từ kết quả Spark, không có chuỗi số liệu viết tay.",
    "Quy trình kiểm định holdout 3 năm cho mô hình ngoại suy, chỉ công bố dự báo khi vượt baseline.",
])
page_break(doc)

# Chapter 2 -----------------------------------------------------------------
add_heading(doc, "CHƯƠNG 2. CƠ SỞ LÝ THUYẾT VÀ KIẾN TRÚC HỆ THỐNG", 1)
add_heading(doc, "2.1. Các thành phần công nghệ", 2)
add_table(
    doc,
    ["Thành phần", "Vai trò trong hệ thống", "Phiên bản"],
    [
        ["Apache Hadoop HDFS", "Lưu trữ phân tán dữ liệu sạch và kết quả trung gian", "3.2.1"],
        ["Apache Spark", "Xử lý batch, Structured Streaming và MLlib LDA", analysis.get("spark_version", "3.5.3")],
        ["Apache Kafka", "Hàng đợi sự kiện cho luồng bài báo mô phỏng", "7.6.0"],
        ["Apache Hive", "External table trên HDFS, truy vấn HiveQL qua HiveServer2", "2.3.2"],
        ["Streamlit", "Dashboard tương tác đọc kết quả đã xác minh", "1.40.0"],
        ["Docker Compose", "Đóng gói và điều phối các dịch vụ", "Compose v2"],
    ],
    caption="Bảng 2.1. Thành phần công nghệ của hệ thống",
)

add_heading(doc, "2.2. Kiến trúc tổng thể", 2)
add_body(doc, "Hệ thống gồm hai luồng độc lập nhưng dùng chung tầng lưu trữ:")
add_bullets(doc, [
    "Luồng batch: Parquet → Spark (làm sạch, chuẩn hóa, phân tích) → Parquet sạch → HDFS → Hive external table → Dashboard và báo cáo.",
    "Luồng streaming: Producer đọc bài báo thật từ Parquet → Kafka → Spark Structured Streaming → Parquet trên HDFS, có checkpoint để chống mất dữ liệu.",
])
add_body(doc, "Hai luồng ghi vào hai thư mục khác nhau trên HDFS. Bảng Hive `arxiv_historical` đọc dữ liệu "
              "batch phân vùng theo năm; bảng `arxiv_stream` đọc dữ liệu sự kiện phân vùng theo nhóm ngành. "
              "Việc tách vị trí giúp metadata Hive không bị lẫn giữa hai schema.")
add_figure(doc, "00_pipeline_full_architecture.png", "Hình 2.1. Sơ đồ kiến trúc tổng thể của hệ thống", 15.5)

add_heading(doc, "2.3. Mô hình dữ liệu", 2)
add_body(doc, "Bản ghi sạch giữ các trường định danh và nội dung của bài báo, bổ sung các trường phái sinh:")
add_table(
    doc,
    ["Trường", "Ý nghĩa"],
    [
        ["id, title, abstract, authors, categories", "Thông tin gốc từ nguồn"],
        ["year / submission_year", "Năm nộp phiên bản v1, đối chiếu với mã arXiv"],
        ["update_year", "Năm cập nhật metadata, không dùng để phân tích xu hướng"],
        ["id_year, year_source", "Năm suy ra từ mã và nguồn xác định năm"],
        ["primary_category, main_group", "Chuyên ngành đầu tiên và nhóm ngành chuẩn hóa"],
        ["abstract_tokens, clean_abstract, token_count", "Kết quả làm sạch và tách từ phục vụ thống kê, LDA"],
        ["abstract_length, title_length", "Độ dài văn bản phục vụ so sánh giữa các nhóm"],
    ],
    caption="Bảng 2.2. Mô tả các trường của bảng dữ liệu sạch",
)
page_break(doc)

# Chapter 3 -----------------------------------------------------------------
add_heading(doc, "CHƯƠNG 3. DỮ LIỆU VÀ PHƯƠNG PHÁP XỬ LÝ", 1)
add_heading(doc, "3.1. Thu thập và kiểm soát nguồn", 2)
add_body(doc, "Dữ liệu được tải theo revision cụ thể của bộ dữ liệu và ghi lại mã băm SHA-256 cho từng tệp. "
              "Manifest nguồn lưu repo, revision, danh sách shard, dung lượng và hash, nhờ đó có thể "
              "phát hiện nếu dữ liệu đầu vào bị thay đổi giữa các lần chạy.")
add_body(doc, f"Tổng dung lượng đầu vào là {pretty_bytes(total_bytes)}, vượt yêu cầu tối thiểu 300 MB. "
              f"Hai shard chứa {vn_int(clean.get('raw_rows', 0))} bản ghi thô; sau kiểm tra trùng mã và "
              f"trường bắt buộc còn {vn_int(rows)} bản ghi sạch.")

add_heading(doc, "3.2. Quy tắc xác định năm nộp bài", 2)
add_body(doc, "Mỗi bài báo có danh sách phiên bản. Năm nộp được lấy từ ngày tạo của phiên bản v1. "
              "Nếu ngày đó không đọc được, hệ thống suy ra năm từ mã arXiv. Quy tắc xử lý riêng cho mã "
              "cũ (trước tháng 4/2007) và mã mới, đồng thời kiểm tra tháng để tránh nhận nhầm các mã "
              "không hợp lệ. Trường `id_year` lưu năm suy từ mã để so sánh với năm từ ngày v1.")
add_body(doc, f"Trong tập dữ liệu hiện tại có {vn_int(clean.get('v1_id_year_differences', 0))} bản ghi "
              "có năm v1 khác năm suy từ mã. Đây thường là các bài nộp cuối tháng 12 nhưng được cấp mã "
              "của tháng 1 năm sau; chênh lệch này được giữ lại thay vì loại bỏ, và được báo cáo công khai "
              "thay vì che bằng một giá trị 0 không đúng.")

add_heading(doc, "3.3. Làm sạch và chuẩn hóa", 2)
add_bullets(doc, [
    "Loại bản ghi thiếu id, tiêu đề, abstract hoặc categories.",
    "Loại bản ghi có năm nộp ngoài khoảng 1991 đến năm hiện tại.",
    "Từ chối toàn bộ lần chạy nếu phát hiện mã bài báo trùng, thay vì tự động chọn một phiên bản.",
    "Chuẩn hóa chuyên ngành đầu tiên thành nhóm ngành; các archive vật lý được gộp vào nhóm `physics`.",
    "Tách từ abstract, loại stopword, lưu danh sách token dùng chung cho thống kê và LDA.",
])

add_heading(doc, "3.4. Phương pháp phân tích", 2)
add_body(doc, "Các bảng kết quả được tính bằng phép toán tập hợp và window function của Spark:")
add_bullets(doc, [
    "Tăng trưởng: đếm bài theo năm, tính phần trăm thay đổi so với năm trước.",
    "Cơ cấu ngành: đếm bài theo năm và nhóm ngành, chia cho tổng số bài của năm để được tỷ trọng.",
    "Chuyên ngành: xếp hạng chuyên ngành theo số bài trong từng năm.",
    "Từ khóa: đếm số bài chứa từ khóa, chuẩn hóa trên 1.000 bài mỗi năm để so sánh giữa các năm có quy mô khác nhau.",
    "Tác giả: tách tên từ trường authors_parsed, đếm số bài và tính số tác giả trung bình mỗi bài.",
    "LDA: vector hóa abstract, giảm trọng số bằng IDF, huấn luyện LDA trên tập train; tập test dùng để tính log-perplexity.",
])

add_heading(doc, "3.5. Kiểm định mô hình ngoại suy", 2)
add_body(doc, "Với bốn từ khóa công nghệ, hệ thống dùng các năm không phải biên để huấn luyện hồi quy tuyến tính, "
              "sau đó dự báo 3 năm cuối và so sánh sai số tuyệt đối trung bình (MAE) với baseline giữ nguyên "
              "giá trị của năm trước. Mô hình chỉ được chấp nhận khi MAE nhỏ hơn baseline; nếu không, báo cáo "
              "ghi rõ là không đủ cơ sở ngoại suy. Dự báo được giới hạn tối đa 3 năm sau năm cuối của dữ liệu.")
page_break(doc)

# Chapter 4 -----------------------------------------------------------------
add_heading(doc, "CHƯƠNG 4. KẾT QUẢ THỰC NGHIỆM", 1)
add_body(doc, f"Chương này trình bày kết quả đọc trực tiếp từ các bảng Parquet do pipeline sinh ra. "
              f"Toàn bộ số liệu tương ứng lần chạy `{analysis['clean_run_id']}`, "
              f"thực hiện trên Spark {analysis.get('spark_version')}.")

add_heading(doc, "4.1. Tổng quan dữ liệu sạch", 2)
add_table(
    doc,
    ["Chỉ tiêu", "Giá trị"],
    [
        ["Số shard đầu vào", str(len(shards))],
        ["Dung lượng đầu vào", pretty_bytes(total_bytes)],
        ["Số bản ghi thô", vn_int(clean.get("raw_rows", 0))],
        ["Số bản ghi sạch", vn_int(rows)],
        ["Số bản ghi bị loại", vn_int(clean.get("rejected_rows", 0))],
        ["Khoảng năm nộp (v1)", f"{min_year} – {max_year} ({span} năm)"],
        ["Số nhóm ngành", str(groups)],
        ["Số cặp năm v1 khác năm mã", vn_int(clean.get("v1_id_year_differences", 0))],
        ["Thời gian tiền xử lý", f"{vn_float(clean.get('seconds'), 1)} giây"],
    ],
    caption="Bảng 4.1. Tổng quan dữ liệu sau tiền xử lý",
)

add_heading(doc, "4.2. Tăng trưởng số bài báo theo năm", 2)
add_body(doc, f"Trong các năm nội suy {int(growth_start['year'])}–{int(growth_end['year'])}, số bài tăng từ "
              f"{vn_int(growth_start['count'])} bài lên {vn_int(growth_end['count'])} bài, tương đương "
              f"{vn_float(overall_growth, 1)}%. Mức tăng trưởng trung bình mỗi năm là "
              f"{vn_float(avg_yoy, 1)}%. Năm có nhiều bài nhất là {keyword_peak_year} với "
              f"{vn_int(keyword_peak_count)} bài.")
add_table(
    doc,
    ["Năm", "Số bài", "Tăng trưởng so với năm trước (%)"],
    [[str(int(row.year)), vn_int(row.count), vn_float(row.yoy_growth_rate, 1)]
     for row in yearly.itertuples()],
    caption="Bảng 4.2. Số bài báo theo năm nộp đầu tiên",
)
add_figure(doc, "01_yearly_growth.png", "Hình 4.1. Số bài báo và tốc độ tăng trưởng theo năm")
add_body(doc, f"Hai năm biên {min_year} và {max_year} có thể chưa đầy đủ do phạm vi shard được chọn, "
              "nên tốc độ tăng trưởng ở hai đầu chuỗi thời gian không được dùng để kết luận xu hướng "
              "dài hạn của toàn bộ arXiv.")

add_heading(doc, "4.3. Cơ cấu nhóm ngành", 2)
add_body(doc, f"Nhóm ngành lớn nhất là `{top_group_row['main_group']}` với "
              f"{vn_int(top_group_row['papers'])} bài, chiếm "
              f"{vn_float(top_group_row['papers'] / rows * 100, 1)}% tập dữ liệu. "
              f"Bảng 4.3 so sánh các nhóm theo quy mô và đặc điểm nội dung.")
add_table(
    doc,
    ["Nhóm ngành", "Số bài", "Tỷ lệ (%)", "Tác giả/bài", "Độ dài abstract", "Số chuyên ngành"],
    [[row.main_group, vn_int(row.papers), vn_float(row.papers / rows * 100, 1),
      vn_float(row.avg_authors, 2), vn_float(row.avg_abstract_length, 0), vn_int(row.distinct_categories)]
     for row in field_metrics.itertuples()],
    caption="Bảng 4.3. Đặc điểm các nhóm ngành",
)
add_figure(doc, "02_field_trends.png", "Hình 4.2. Tỷ trọng các nhóm ngành theo năm")
add_figure(doc, "07_field_distribution.png", "Hình 4.3. Cơ cấu tổng thể các nhóm ngành", 11.5)
add_figure(doc, "11_field_radar_comparison.png", "Hình 4.4. So sánh chuẩn hóa bốn nhóm ngành lớn nhất", 11.5)

add_heading(doc, "4.4. Chuyên ngành hàng đầu", 2)
add_body(doc, f"Chuyên ngành có tổng số bài lớn nhất là `{top_cat}` với {vn_int(top_cat_count)} bài. "
              "Bảng 4.4 liệt kê 10 chuyên ngành đứng đầu; Hình 4.5 và 4.6 cho thấy quy mô và phân bố theo năm.")
add_table(
    doc,
    ["Hạng", "Chuyên ngành", "Tổng số bài"],
    [[str(index + 1), name, vn_int(value)] for index, (name, value) in enumerate(cat_totals.head(10).items())],
    caption="Bảng 4.4. Mười chuyên ngành có nhiều bài nhất",
)
add_figure(doc, "03_top_categories.png", "Hình 4.5. Top 15 chuyên ngành theo tổng số bài")
add_figure(doc, "04_heatmap.png", "Hình 4.6. Mật độ bài báo theo chuyên ngành và năm")

add_heading(doc, "4.5. Từ khóa công nghệ", 2)
add_body(doc, "Tần suất từ khóa được đo bằng số bài có chứa từ khóa trong abstract, sau đó chuẩn hóa trên "
              "1.000 bài của cùng năm. Cách đo này tránh việc một năm có ít bài nhưng tỷ lệ từ khóa cao "
              f"bị đánh giá thấp hơn so với năm nhiều bài. Bảng 4.5 lấy năm nội suy cuối ({keyword_reference_year}) "
              "làm mốc so sánh, vì năm cuối của tập dữ liệu chỉ chứa một phần dữ liệu.")
add_table(
    doc,
    ["Từ khóa", "Số bài chứa", f"Số bài trên 1.000 ({keyword_reference_year})"],
    hot_rows,
    caption=f"Bảng 4.5. Tần suất một số từ khóa công nghệ ở năm {keyword_reference_year}",
)
add_figure(doc, "05_keyword_trends.png", "Hình 4.7. Xu hướng các từ khóa công nghệ")
add_figure(doc, "06_wordclouds.png", "Hình 4.8. Các token phổ biến nhất theo nhóm ngành")

add_heading(doc, "4.6. Tác giả và hợp tác", 2)
add_body(doc, "Số tác giả trung bình mỗi bài được tính trên các bản ghi có trường authors_parsed. "
              "Tên tác giả được ghép từ họ và tên trong dữ liệu gốc; hệ thống chưa phân giải các trường hợp "
              "trùng tên, nên bảng xếp hạng tác giả chỉ mang tính tham khảo.")
add_table(
    doc,
    ["Hạng", "Tác giả", "Số bài"],
    [[str(index + 1), row.author, vn_int(row.count)] for index, row in enumerate(top_authors.head(15).itertuples())],
    caption="Bảng 4.6. Mười lăm tên tác giả xuất hiện nhiều nhất",
)
add_figure(doc, "08_author_collaboration_trend.png", "Hình 4.9. Số tác giả trung bình trên mỗi bài")
add_figure(doc, "09_top_authors.png", "Hình 4.10. Top 20 tên tác giả theo số bài")

add_heading(doc, "4.7. Mô hình chủ đề LDA", 2)
add_body(doc, f"{model_text}. Mỗi chủ đề được mô tả bằng 10 thuật ngữ có trọng số cao nhất. "
              "Tỷ lệ chủ đề (prevalence) được ước lượng trên một mẫu xác định của tập train, không dùng "
              "giá trị viết tay.")
topic_rows = []
for item in topics:
    topic_rows.append([
        f"T{item['topic']}",
        ", ".join(item["terms"][:5]),
        vn_float(float(item.get("prevalence", 0)) * 100, 2) + "%",
    ])
add_table(doc, ["Chủ đề", "Năm thuật ngữ đại diện", "Tỷ lệ ước lượng"], topic_rows,
          caption="Bảng 4.7. Các chủ đề LDA và thuật ngữ đại diện")
add_figure(doc, "12_lda_topic_bubble.png", "Hình 4.11. Phân bố chủ đề LDA")

add_heading(doc, "4.8. Kiểm định ngoại suy xu hướng", 2)
add_body(doc, "Bảng 4.8 trình bày MAE trên 3 năm holdout của mô hình tuyến tính và của baseline giữ giá trị "
              "năm trước. Chỉ các từ khóa có MAE mô hình nhỏ hơn baseline mới được phép ngoại suy.")
forecast_rows = []
for item in forecast.get("metrics", []):
    status = "Chấp nhận" if item.get("status") == "accepted" else "Không đủ cơ sở"
    forecast_rows.append([item.get("word", "—"), vn_float(item.get("mae"), 3),
                 vn_float(item.get("baseline_mae"), 3), status])
add_table(doc, ["Từ khóa", "MAE mô hình", "MAE baseline", "Kết luận"], forecast_rows,
          caption="Bảng 4.8. Kết quả kiểm định holdout")
if accepted:
    add_body(doc, "Các từ khóa được chấp nhận ngoại suy: " + ", ".join(item["word"] for item in accepted) +
                  ". Dự báo chỉ kéo dài tối đa 3 năm sau năm cuối của dữ liệu và được vẽ nét đứt để phân biệt "
                  "với dữ liệu thực đo.")
else:
    add_body(doc, "Không có từ khóa nào vượt được baseline trên tập holdout, vì vậy báo cáo không công bố "
                  "dự báo xa cho giai đoạn tiếp theo.")
add_figure(doc, "10_validated_trend.png", "Hình 4.12. Xu hướng thực đo và phần ngoại suy được kiểm định")
page_break(doc)

# Chapter 5 -----------------------------------------------------------------
add_heading(doc, "CHƯƠNG 5. TRIỂN KHAI VÀ KIỂM CHỨNG HỆ THỐNG", 1)
add_heading(doc, "5.1. Tổ chức mã nguồn", 2)
add_table(
    doc,
    ["Thư mục / tệp", "Chức năng"],
    [
        ["src/data_contract.py", "Quy tắc năm nộp, nhóm ngành, tách từ, kiểm tra bản ghi"],
        ["src/batch_pipeline.py", "Tiền xử lý, phân tích, ghi manifest, đồng bộ HDFS"],
        ["src/visualization.py", "Sinh 12 biểu đồ và kiểm định ngoại suy"],
        ["src/spark_streaming_consumer.py", "Đọc Kafka, làm sạch, ghi Parquet có checkpoint"],
        ["src/kafka_producer.py", "Phát lại bài báo thật từ Parquet vào Kafka"],
        ["src/hive_client.py + src/hive_init.sql", "Tạo external table, truy vấn và làm mới phân vùng"],
        ["src/dashboard_app.py", "Dashboard Streamlit 5 tab"],
        ["notebooks/00–07", "Quy trình thực hành theo từng bước"],
        ["tests/test_correctness.py", "Kiểm thử quy tắc dữ liệu và tính toàn vẹn của kết quả"],
    ],
    caption="Bảng 5.1. Tổ chức mã nguồn",
)

add_heading(doc, "5.2. Cấu hình cụm Docker", 2)
add_body(doc, "Cấu hình mặc định chạy 11 dịch vụ: NameNode, DataNode, Zookeeper, Kafka, PostgreSQL "
              "metastore, Hive Metastore, HiveServer2, Spark Master, một Spark Worker (2 core, 2 GB), "
              "Spark Jupyter và Dashboard. Worker thứ hai và dịch vụ streaming nằm trong profile riêng "
              "để giảm tải cho máy cá nhân khi demo.")
add_table(
    doc,
    ["Dịch vụ", "Cổng", "Vai trò"],
    [
        ["namenode", "9870, 9000", "Quản lý metadata HDFS"],
        ["datanode", "9864", "Lưu block dữ liệu"],
        ["kafka + zookeeper", "9092", "Hàng đợi sự kiện"],
        ["hive-server", "10000", "HiveServer2, nơi dashboard gửi HiveQL"],
        ["spark-master + worker", "8080, 7077, 8081", "Tính toán phân tán"],
        ["spark-jupyter", "8888", "Chạy notebook và pipeline batch"],
        ["dashboard", "8501", "Giao diện Streamlit"],
    ],
    caption="Bảng 5.2. Các dịch vụ chính trong Docker Compose",
)

add_heading(doc, "5.3. Quy trình chạy", 2)
add_body(doc, "Thứ tự thực hiện được ghi trong README và notebook 07:")
add_bullets(doc, [
    "Tải shard và tạo source_manifest.json (notebook 00).",
    "Chạy tiền xử lý: python src/batch_pipeline.py preprocess.",
    "Chạy phân tích: python src/batch_pipeline.py analyze.",
    "Sinh biểu đồ và kiểm định: python src/visualization.py.",
    "Đồng bộ HDFS: python src/batch_pipeline.py sync-hdfs.",
    "Khởi tạo Hive và làm mới phân vùng: initialize_hive(), refresh_historical_partitions().",
    "Mở dashboard: streamlit run src/dashboard_app.py.",
])

add_heading(doc, "5.4. Kiểm chứng", 2)
add_body(doc, f"Pipeline hoàn tất trong {vn_float(total_seconds, 1)} giây cho phần phân tích, "
              f"bao gồm cả huấn luyện LDA. Bảng 5.3 là thời gian đo bằng perf_counter cho từng bảng kết quả.")
add_table(
    doc,
    ["Công đoạn", "Thời gian (giây)"],
    [[name, vn_float(value, 2)] for name, value in timings.items()],
    caption="Bảng 5.3. Thời gian thực thi các bước phân tích",
)
add_body(doc, "Bộ kiểm thử tự động kiểm tra: quy tắc năm cho mã cũ/mới, loại mã không hợp lệ, cách gộp nhóm "
              "ngành, schema dữ liệu sạch, sự tồn tại của đủ 12 biểu đồ và tính nhất quán giữa các manifest. "
              "Dashboard chỉ hiển thị số liệu khi manifest phân tích và manifest dữ liệu sạch có cùng mã lần chạy.")
page_break(doc)

# Chapter 6 -----------------------------------------------------------------
add_heading(doc, "CHƯƠNG 6. ĐÁNH GIÁ, HẠN CHẾ VÀ HƯỚNG PHÁT TRIỂN", 1)
add_heading(doc, "6.1. Kết quả đạt được", 2)
add_bullets(doc, [
    f"Xử lý {vn_int(rows)} bài báo từ {pretty_bytes(total_bytes)} dữ liệu thô, sinh đầy đủ bảng phân tích và 12 biểu đồ.",
    "Mọi kết quả đều gắn với một mã lần chạy và có thể tái lập bằng lệnh trong phụ lục.",
    "Quy tắc năm nộp bài được kiểm thử cho cả mã arXiv cũ và mới; chênh lệch với năm suy từ mã được báo cáo thay vì che giấu.",
    "Mô hình ngoại suy có kiểm định holdout, không công bố dự báo khi không vượt baseline.",
])

add_heading(doc, "6.2. Hạn chế", 2)
add_bullets(doc, [
    f"Dữ liệu chỉ gồm {len(shards)} shard đầu tiên, không đại diện cho toàn bộ arXiv; các kết luận về xu hướng chỉ đúng trong phạm vi này.",
    "Tên tác giả chưa được phân giải thực thể, nên thống kê tác giả có thể gộp nhiều người trùng tên.",
    "Từ khóa theo danh sách cố định; LDA huấn luyện trên tập con để vừa tài nguyên, số chủ đề do người dùng chọn.",
    "Các phép đo được thực hiện ở chế độ local[*] trên máy cá nhân; chưa phải benchmark trên cụm nhiều worker.",
    "HDFS, Hive và streaming chưa chạy trên cụm Docker; kết quả số đến từ phần batch.",
])

add_heading(doc, "6.3. Hướng phát triển", 2)
add_bullets(doc, [
    "Mở rộng số shard và chạy trên cụm nhiều worker để kiểm chứng khả năng mở rộng.",
    "Bổ sung phân giải tên tác giả và mạng đồng tác giả ở cấp tổ chức.",
    "Thay danh sách từ khóa cố định bằng mô hình phát hiện cụm từ mới theo thời gian.",
    "Đưa dashboard lên môi trường có xác thực và lưu lịch sử truy vấn.",
    "Tự động hóa kiểm thử tích hợp với Docker để xác nhận luồng Kafka → HDFS → Hive trước khi nộp.",
])
page_break(doc)

add_heading(doc, "KẾT LUẬN", 1)
add_body(doc, f"Bài tập lớn đã xây dựng được một pipeline phân tích dữ liệu lớn hoàn chỉnh cho metadata arXiv, "
              f"từ khâu tải và kiểm soát nguồn, làm sạch theo quy tắc rõ ràng, phân tích bằng Spark, "
              f"cùng cấu hình lưu trữ HDFS và truy vấn Hive, đến trực quan hóa trên dashboard. Trên phạm vi "
              f"{pretty_bytes(total_bytes)} dữ liệu đầu vào và {vn_int(rows)} bài báo sạch, hệ thống đã tạo ra "
              f"các bảng phân tích, 12 biểu đồ, mô hình chủ đề và kết quả kiểm định ngoại suy có thể tái lập. "
              f"Các hạn chế về phạm vi dữ liệu, phân giải tác giả, tài nguyên tính toán và phần chưa chạy "
              f"trên cụm Docker đã được nêu rõ để định hướng phát triển tiếp theo.")

add_heading(doc, "TÀI LIỆU THAM KHẢO", 1)
references = [
    "Apache Software Foundation. Apache Spark 3.5.3 Documentation. https://spark.apache.org/docs/3.5.3/",
    "Apache Software Foundation. Apache Hadoop 3.2.1 Documentation. https://hadoop.apache.org/docs/r3.2.1/",
    "Apache Software Foundation. Apache Hive 2.3 Documentation. https://cwiki.apache.org/confluence/display/Hive/",
    "Apache Software Foundation. Apache Kafka 7.6 Documentation. https://kafka.apache.org/documentation/",
    "VatsaDev. test_arxiv dataset. Hugging Face Datasets. https://huggingface.co/datasets/VatsaDev/test_arxiv",
    "Blei, D. M., Ng, A. Y., Jordan, M. I. (2003). Latent Dirichlet Allocation. JMLR, 3, 993–1022.",
    "Zaharia, M. et al. (2016). Apache Spark: A Unified Engine for Big Data Processing. CACM, 59(11).",
]
for index, item in enumerate(references, 1):
    paragraph = doc.add_paragraph(f"[{index}] {item}")
    paragraph.paragraph_format.space_after = Pt(4)

add_heading(doc, "PHỤ LỤC: CÁCH CHẠY LẠI PIPELINE", 1)
add_body(doc, "Trên máy có Docker, chạy toàn bộ cụm bằng `docker compose up -d --build`. "
              "Trong container `spark-jupyter`, thực hiện:")
for command in (
    "python src/batch_pipeline.py all",
    "python src/visualization.py",
    "python src/batch_pipeline.py sync-hdfs",
    "python src/hive_client.py",
    "streamlit run src/dashboard_app.py",
):
    paragraph = doc.add_paragraph(command, style="No Spacing")
    for run in paragraph.runs:
        run.font.name = "Consolas"
        run.font.size = Pt(10)
add_body(doc, "Trên máy không có Docker, có thể chạy batch và biểu đồ bằng Python trong `.venv` với Java và "
              "winutils; phần Hive và streaming cần cụm Docker tương ứng. Báo cáo này được sinh bằng lệnh "
              "`python scripts/build_data_mining_style_report.py` sau khi pipeline hoàn tất.")

REPORT_DIR.mkdir(parents=True, exist_ok=True)
docx_path = REPORT_DIR / "BAO_CAO_BAI_TAP_LON_BIGDATA.docx"
doc.save(docx_path)

# ---------------------------------------------------------------------------
# Markdown mirror (same content, generated from the same loaded data)
# ---------------------------------------------------------------------------
lines = []
lines += [f"# {SCHOOL}", f"## {FACULTY}", "", "# BÀI TẬP LỚN",
          "## HỌC PHẦN: XỬ LÝ DỮ LIỆU LỚN (BIG DATA)", "", f"## ĐỀ TÀI: {TITLE}", "",
          f"- **Sinh viên thực hiện:** {STUDENT}", f"- **Mã sinh viên:** {STUDENT_ID}",
          f"- **Mã lớp:** {CLASS_ID}", f"- **Giảng viên hướng dẫn:** {ADVISOR}", "", "---", ""]

lines += ["## LỜI CẢM ƠN", "", "Em xin chân thành cảm ơn thầy " + ADVISOR + " đã hướng dẫn và góp ý trong suốt quá trình thực hiện bài tập lớn.", ""]
lines += ["## CHƯƠNG 1. GIỚI THIỆU BÀI TOÁN VÀ PHẠM VI DỮ LIỆU", "",
          "### 1.1. Đặt vấn đề", "",
          "arXiv là kho lưu trữ mở các bài báo khoa học với khối lượng metadata lớn và tăng liên tục. "
          "Bài tập lớn xây dựng hệ thống phân tích dữ liệu lớn gồm luồng batch (Spark → HDFS → Hive) và "
          "luồng sự kiện (Kafka → Spark Structured Streaming → HDFS), kết quả hiển thị trên dashboard Streamlit.", "",
          "### 1.2. Mục tiêu", "",
          "- Pipeline batch chạy lại được, có manifest và mã lần chạy.",
          "- Chuẩn hóa năm nộp theo phiên bản v1, kiểm tra chéo với mã arXiv.",
          "- Tính toán tăng trưởng, cơ cấu ngành, từ khóa, tác giả và chủ đề LDA.",
          "- Kiểm định ngoại suy bằng holdout trước khi công bố dự báo.", "",
          "### 1.3. Phạm vi dữ liệu", "",
          f"Nguồn: `{source.get('repo')}` tại revision `{source.get('revision')}`. "
          f"Sử dụng {len(shards)} shard, tổng {pretty_bytes(total_bytes)}.", ""]

lines += ["| Shard | Tệp | Dung lượng | SHA-256 |", "|---|---|---|---|"]
for index, item in enumerate(shards):
    lines.append(f"| {index + 1} | `{item.get('local_name') or item.get('path')}` | {pretty_bytes(item.get('bytes', 0))} | `{(item.get('sha256') or '')[:16]}…` |")
lines += ["", f"Sau làm sạch: **{vn_int(rows)}** bài, năm **{min_year}–{max_year}** ({span} năm), **{groups}** nhóm ngành; "
          f"loại {vn_int(clean.get('rejected_rows', 0))} dòng.", ""]

lines += ["## CHƯƠNG 2. CƠ SỞ LÝ THUYẾT VÀ KIẾN TRÚC", "",
          "Hệ thống dùng HDFS (lưu trữ), Spark (batch, streaming, MLlib), Kafka (sự kiện), Hive (external table) "
          "và Streamlit (dashboard). Hai luồng batch và streaming ghi vào hai thư mục HDFS riêng.", "",
          "![Kiến trúc tổng thể](../screenshots/00_pipeline_full_architecture.png)", ""]

lines += ["## CHƯƠNG 3. DỮ LIỆU VÀ PHƯƠNG PHÁP", "",
          "Năm nộp lấy từ ngày tạo phiên bản v1, fallback theo mã arXiv, có xử lý riêng cho mã cũ trước 4/2007. "
          "Bản ghi thiếu trường bắt buộc hoặc năm không hợp lệ bị loại; mã trùng làm dừng pipeline.", "",
          f"Trong dữ liệu hiện tại có **{vn_int(clean.get('v1_id_year_differences', 0))}** bản ghi có năm v1 khác năm suy từ mã "
          "(thường do nộp cuối tháng 12 nhưng nhận mã tháng 1 năm sau).", "",
          "Phân tích dùng window function của Spark cho tăng trưởng, tỷ trọng ngành, xếp hạng chuyên ngành. "
          "LDA dùng CountVectorizer + IDF trên tập chia xác định 80/20 theo mã bài; mỗi phía được lấy mẫu "
          "tất định (tối đa 200.000 bài huấn luyện, 50.000 bài kiểm định) để vừa tài nguyên máy.", ""]

lines += ["## CHƯƠNG 4. KẾT QUẢ THỰC NGHIỆM", "",
          f"Lần chạy: `{analysis['clean_run_id']}` · Spark {analysis.get('spark_version')} · {vn_float(total_seconds, 1)} giây phân tích.", "",
          "### 4.1. Tổng quan", "",
          "| Chỉ tiêu | Giá trị |", "|---|---|",
          f"| Số shard | {len(shards)} |", f"| Dung lượng đầu vào | {pretty_bytes(total_bytes)} |",
          f"| Bản ghi thô | {vn_int(clean.get('raw_rows', 0))} |", f"| Bản ghi sạch | {vn_int(rows)} |",
          f"| Bản ghi bị loại | {vn_int(clean.get('rejected_rows', 0))} |",
          f"| Khoảng năm | {min_year}–{max_year} |", f"| Nhóm ngành | {groups} |",
          f"| Năm v1 khác năm mã | {vn_int(clean.get('v1_id_year_differences', 0))} |", ""]

lines += ["### 4.2. Tăng trưởng theo năm", "",
          f"Trong các năm nội suy {int(growth_start['year'])}–{int(growth_end['year'])}, số bài tăng từ "
          f"{vn_int(growth_start['count'])} lên {vn_int(growth_end['count'])}, tương đương "
          f"{vn_float(overall_growth, 1)}%; tăng trưởng trung bình {vn_float(avg_yoy, 1)}%/năm. "
          f"Hai năm biên {min_year} và {max_year} có thể chưa đầy đủ.", "",
          "| Năm | Số bài | YoY (%) |", "|---|---|---|"]
for row in yearly.itertuples():
    lines.append(f"| {int(row.year)} | {vn_int(row.count)} | {vn_float(row.yoy_growth_rate, 1)} |")
lines += ["", "![Tăng trưởng](../charts/01_yearly_growth.png)", ""]

lines += ["### 4.3. Cơ cấu nhóm ngành", "",
          "| Nhóm | Số bài | Tỷ lệ (%) | Tác giả/bài | Abstract (ký tự) |", "|---|---|---|---|---|"]
for row in field_metrics.itertuples():
    lines.append(f"| {row.main_group} | {vn_int(row.papers)} | {vn_float(row.papers / rows * 100, 1)} | "
                 f"{vn_float(row.avg_authors, 2)} | {vn_float(row.avg_abstract_length, 0)} |")
lines += ["", "![Tỷ trọng ngành](../charts/02_field_trends.png)", "",
          "![Cơ cấu ngành](../charts/07_field_distribution.png)", "",
          "![Radar](../charts/11_field_radar_comparison.png)", ""]

lines += ["### 4.4. Chuyên ngành hàng đầu", "",
          f"Chuyên ngành lớn nhất: **{top_cat}** với {vn_int(top_cat_count)} bài.", "",
          "| Hạng | Chuyên ngành | Số bài |", "|---|---|---|"]
for index, (name, value) in enumerate(cat_totals.head(10).items(), 1):
    lines.append(f"| {index} | {name} | {vn_int(value)} |")
lines += ["", "![Top chuyên ngành](../charts/03_top_categories.png)", "",
          "![Heatmap](../charts/04_heatmap.png)", ""]

lines += ["### 4.5. Từ khóa công nghệ", "",
          f"| Từ khóa | Số bài chứa ({keyword_reference_year}) | Trên 1.000 bài |", "|---|---|---|"]
lines += [f"| {row[0]} | {row[1]} | {row[2]} |" for row in hot_rows]
lines += ["", "![Từ khóa](../charts/05_keyword_trends.png)", "",
          "![Word clouds](../charts/06_wordclouds.png)", ""]

lines += ["### 4.6. Tác giả và hợp tác", "",
          "| Hạng | Tác giả | Số bài |", "|---|---|---|"]
for index, row in enumerate(top_authors.head(15).itertuples(), 1):
    lines.append(f"| {index} | {row.author} | {vn_int(row.count)} |")
lines += ["", "![Hợp tác](../charts/08_author_collaboration_trend.png)", "",
          "![Top tác giả](../charts/09_top_authors.png)", ""]

lines += ["### 4.7. Mô hình chủ đề LDA", "", f"{model_text}.", "",
          "| Chủ đề | Thuật ngữ đại diện | Tỷ lệ |", "|---|---|---|"]
for item in topics:
    lines.append(f"| T{item['topic']} | {', '.join(item['terms'][:5])} | {vn_float(float(item.get('prevalence', 0)) * 100, 2)}% |")
lines += ["", "![LDA](../charts/12_lda_topic_bubble.png)", ""]

lines += ["### 4.8. Kiểm định ngoại suy", "",
          "| Từ khóa | MAE mô hình | MAE baseline | Kết luận |", "|---|---|---|---|"]
for item in forecast.get("metrics", []):
    lines.append(f"| {item.get('word')} | {vn_float(item.get('mae'), 3)} | {vn_float(item.get('baseline_mae'), 3)} | "
                 f"{'Chấp nhận' if item.get('status') == 'accepted' else 'Không đủ cơ sở'} |")
lines += ["", "![Ngoại suy](../charts/10_validated_trend.png)", ""]

lines += ["## CHƯƠNG 5. TRIỂN KHAI VÀ KIỂM CHỨNG", "",
          "Cấu hình Docker Compose chạy 12 dịch vụ mặc định; Spark Worker thứ hai nằm trong profile `full` "
          "để giảm tải máy cá nhân. Pipeline được điều khiển bằng các lệnh trong phụ lục.", "",
          "Thời gian phân tích từng bảng:", "",
          "| Công đoạn | Giây |", "|---|---|"]
lines += [f"| {name} | {vn_float(value, 2)} |" for name, value in timings.items()]
lines += [""]

lines += ["## CHƯƠNG 6. ĐÁNH GIÁ VÀ HẠN CHẾ", "",
          "- Dữ liệu chỉ gồm các shard đã tải, không đại diện toàn bộ arXiv.",
          "- Tên tác giả chưa phân giải thực thể.",
          "- Danh sách từ khóa cố định, chưa phát hiện cụm từ mới.",
          "- Hiệu năng phụ thuộc cấu hình máy, không phải benchmark chuẩn.", "",
          "## KẾT LUẬN", "",
          f"Hệ thống xử lý {vn_int(rows)} bài báo từ {pretty_bytes(total_bytes)} dữ liệu, sinh đầy đủ bảng phân tích, "
          "12 biểu đồ và kết quả kiểm định ngoại suy có thể tái lập.", "",
          "## PHỤ LỤC: CÁCH CHẠY LẠI", "",
          "```bash", "python src/batch_pipeline.py all", "python src/visualization.py",
          "python src/batch_pipeline.py sync-hdfs", "python src/hive_client.py",
          "python scripts/build_data_mining_style_report.py",
          "python scripts/build_presentation_slides.py", "```", ""]

md_path = REPORT_DIR / "BAO_CAO_BAI_TAP_LON_BIGDATA.md"
md_path.write_text("\n".join(lines), encoding="utf-8")

print(f"DOCX: {docx_path}")
print(f"MD:   {md_path}")
print(f"rows={rows} years={min_year}-{max_year} groups={groups} charts={len(chart_manifest['charts'])}")
