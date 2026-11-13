"""Build the arXiv Big Data report by reusing the RAID report's styles and layout.

The RAID document is used only as a template: its styles (Bìa, CHUONG, Mục lớn,
MucNho, Nội dung, HinhVe, Bang, toc 1..3), page size and headers are kept, while
all body content is replaced by the arXiv pipeline report.

Usage:
    python scripts/build_arxiv_report.py [pages.json]

``pages.json`` is produced by ``scripts/update_report_fields.py`` and supplies the
page number of every figure/table caption so the two lists can be filled in.
"""
import json
import shutil
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "report_template.docx"
OUTPUT = ROOT / "output" / "reports" / "BAO_CAO_BAI_TAP_LON_BIGDATA.docx"
CHART = ROOT / "output" / "charts"
SHOT = ROOT / "output" / "screenshots"

TITLE_1 = "NGHIÊN CỨU VÀ XÂY DỰNG HỆ THỐNG PHÂN TÍCH DỮ LIỆU LỚN"
TITLE_2 = "METADATA BÀI BÁO KHOA HỌC ARXIV TRÊN NỀN TẢNG HADOOP, SPARK, KAFKA VÀ HIVE"
HEADER_TEXT = "BÀI TẬP LỚN: PHÂN TÍCH DỮ LIỆU LỚN METADATA ARXIV"

STUDENT = "LÊ DƯƠNG HIẾU"
STUDENT_ID = "12423011"
CLASS_ID = "124231"
LECTURER = "TS. NGUYỄN VĂN QUYẾT"


# ---------------------------------------------------------------------------
# Low level helpers
# ---------------------------------------------------------------------------
def clear_body(doc):
    body = doc.element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def set_run_font(run, size=None, bold=None, italic=None, name="Times New Roman", color=None):
    if name:
        run.font.name = name
        rpr = run._element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rfonts.set(qn(attr), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)


def add_para(doc, text="", style="Nội dung", bold=None, italic=None, size=None,
             align=None, space_after=None, space_before=None, line_spacing=None,
             first_line_indent=None, left_indent=None, font="Times New Roman",
             keep_with_next=False):
    p = doc.add_paragraph(style=style)
    if text:
        run = p.add_run(text)
        set_run_font(run, size=size, bold=bold, italic=italic, name=font)
    pf = p.paragraph_format
    if align is not None:
        p.alignment = align
    if space_after is not None:
        pf.space_after = Pt(space_after)
    if space_before is not None:
        pf.space_before = Pt(space_before)
    if line_spacing is not None:
        pf.line_spacing = line_spacing
    if first_line_indent is not None:
        pf.first_line_indent = Cm(first_line_indent)
    if left_indent is not None:
        pf.left_indent = Cm(left_indent)
    if keep_with_next:
        pf.keep_with_next = True
    return p


def body(doc, text):
    return add_para(doc, text, style="Nội dung", align=WD_ALIGN_PARAGRAPH.JUSTIFY)


def bullet(doc, text):
    p = add_para(doc, "•\t" + text, style="Nội dung", align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                 left_indent=0.75, first_line_indent=-0.5)
    p.paragraph_format.tab_stops.add_tab_stop(Cm(0.75))
    return p


def h1(doc, text):
    return add_para(doc, text, style="CHUONG")


def h1_front(doc, text):
    """Front-matter heading: same look as CHUONG but excluded from the TOC."""
    return add_para(doc, text, style="CHUONG phu")


def h2(doc, text):
    return add_para(doc, text, style="Mục lớn", keep_with_next=True)


def h3(doc, text):
    return add_para(doc, text, style="MucNho")


def caption(doc, text, style="HinhVe"):
    return add_para(doc, text, style=style, keep_with_next=(style == "Bang"))


def figure(doc, filename, text, width_cm=15.2):
    path = (SHOT if (SHOT / filename).exists() else CHART) / filename
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    p.add_run().add_picture(str(path), width=Cm(width_cm))
    p.paragraph_format.keep_with_next = True
    caption(doc, text)


def code_block(doc, text):
    for line in text.strip("\n").split("\n"):
        p = add_para(doc, line if line else " ", style="Normal", font="Consolas", size=9.5,
                     align=WD_ALIGN_PARAGRAPH.LEFT, space_after=0, space_before=0,
                     line_spacing=1.0, left_indent=0.6)
        p.paragraph_format.keep_together = True
        for run in p.runs:
            run.font.color.rgb = RGBColor(0x1A, 0x3A, 0x5E)


def shade(cell, fill):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcpr.append(shd)


def cell_text(cell, text, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT, size=12.0):
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p = cell.paragraphs[0]
    p.style = cell.part.document.styles["Normal"]
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(2)
    pf.space_after = Pt(2)
    pf.line_spacing = 1.05
    pf.first_line_indent = Cm(0)
    run = p.add_run(str(text))
    set_run_font(run, size=size, bold=bold)


def table(doc, text, headers, rows, widths, numeric=(), size=12.0):
    caption(doc, text, style="Bang")
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    hdr = t.rows[0]
    trpr = hdr._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    trpr.append(tbl_header)
    for i, name in enumerate(headers):
        cell_text(hdr.cells[i], name, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=size)
        shade(hdr.cells[i], "C6D9F1")
    for row in rows:
        cells = t.add_row().cells
        for i, value in enumerate(row):
            align = WD_ALIGN_PARAGRAPH.CENTER if i in numeric else WD_ALIGN_PARAGRAPH.LEFT
            cell_text(cells[i], value, align=align, size=size)
    for row in t.rows:
        for i, width in enumerate(widths):
            row.cells[i].width = Cm(width)
    add_para(doc, "", style="Normal", space_after=2, size=1)
    return t


def add_toc(doc):
    p = doc.add_paragraph()
    run = p.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = ' TOC \\o "1-3" \\h \\z \\u '
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    placeholder = OxmlElement("w:t")
    placeholder.text = "Mục lục sẽ được cập nhật tự động khi mở bằng Microsoft Word (F9)."
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run2 = p.add_run()
    run2._r.append(instr)
    run3 = p.add_run()
    run3._r.append(fld_sep)
    run4 = p.add_run()
    run4._r.append(placeholder)
    run5 = p.add_run()
    run5._r.append(fld_end)
    return p


def page_entry(doc, label, page=None):
    p = doc.add_paragraph(style="toc 2")
    p.paragraph_format.space_after = Pt(4)
    p.add_run(label)
    p.add_run("\t")
    p.add_run(str(page if page is not None else "00"))
    return p


def section_headers(doc, cover_section, rest_section):
    cover_section.left_margin = Cm(3.0)
    cover_section.right_margin = Cm(2.0)
    cover_section.top_margin = Cm(2.0)
    cover_section.bottom_margin = Cm(2.0)
    rest_section.left_margin = Cm(3.5)
    rest_section.right_margin = Cm(2.0)
    rest_section.top_margin = Cm(3.0)
    rest_section.bottom_margin = Cm(3.0)
    # Same header/footer offsets as the template's body section.
    rest_section.header_distance = Cm(0.76)
    rest_section.footer_distance = Cm(0.76)

    # The template header is a two-paragraph block: an empty tab line, then the
    # title with an anchored rule below it. Replace only the text so the rule,
    # the "Tên đề tài" style and the footer PAGE field stay untouched.
    for p in rest_section.header.paragraphs:
        if p._p.findall(".//" + qn("w:t")):
            set_paragraph_text(p._p, HEADER_TEXT)
            break


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------
def take_cover(doc):
    """Snapshot the template's cover paragraphs before the body is cleared.

    The template cover is not plain text: every paragraph carries the page
    border (``w:pBdr``) and paragraph 1 carries the anchored school logo. The
    only reliable way to keep those is to clone the paragraphs themselves and
    replace their text.
    """
    cover = []
    for p in doc.paragraphs:
        if p.style.name == "Bìa":
            cover.append(p._p)
            continue
        if cover:
            if p.text.strip().upper().startswith("HƯNG YÊN"):
                cover.append(p._p)
            break
    return cover


def set_paragraph_text(p_el, text):
    """Replace the visible text of a paragraph, keeping its first run format."""
    nodes = p_el.findall(".//" + qn("w:t"))
    if not nodes:
        return False
    nodes[0].text = text
    nodes[0].set(qn("xml:space"), "preserve")
    for extra in nodes[1:]:
        extra.text = ""
    return True


def cover(doc, template_paras):
    paras = [deepcopy(el) for el in template_paras]
    if len(paras) < 25:
        raise ValueError(f"Template cover has {len(paras)} paragraphs, expected 25")

    set_paragraph_text(paras[0], "BỘ GIÁO DỤC VÀ ĐÀO TẠO")
    set_paragraph_text(paras[1], "TRƯỜNG ĐẠI HỌC SƯ PHẠM KỸ THUẬT HƯNG YÊN")
    set_paragraph_text(paras[7], "BÀI TẬP LỚN")
    set_paragraph_text(paras[9], "NGHIÊN CỨU VÀ XÂY DỰNG HỆ THỐNG PHÂN TÍCH")
    set_paragraph_text(paras[10], "DỮ LIỆU LỚN METADATA BÀI BÁO KHOA HỌC ARXIV")
    set_paragraph_text(paras[12], "KHOA: CÔNG NGHỆ THÔNG TIN")
    set_paragraph_text(paras[13], "HỌC PHẦN: XỬ LÝ DỮ LIỆU LỚN (BIG DATA)")
    set_paragraph_text(paras[15], "SINH VIÊN: " + STUDENT)
    set_paragraph_text(paras[16], "MÃ SINH VIÊN: " + STUDENT_ID)
    set_paragraph_text(paras[17], "MÃ LỚP: " + CLASS_ID)
    set_paragraph_text(paras[18], "GIẢNG VIÊN HƯỚNG DẪN: " + LECTURER)
    set_paragraph_text(paras[24], "HƯNG YÊN – 2026")

    # The template has two title lines; the arXiv title needs three. Clone the
    # 16 pt centred line and drop one blank line above the title block so the
    # rest of the cover keeps the template's vertical rhythm.
    third = deepcopy(paras[10])
    set_paragraph_text(third, "TRÊN NỀN TẢNG HADOOP, SPARK, KAFKA VÀ HIVE")
    paras.insert(11, third)
    del paras[2]

    body = doc.element.body
    for el in paras:
        body.insert_element_before(el, "w:sectPr")



def review_page(doc):
    h1_front(doc, "NHẬN XÉT")
    add_para(doc, "Nhận xét của giảng viên hướng dẫn:", style="Normal", bold=True, space_before=10)
    for _ in range(17):
        add_para(doc, "." * 100, style="Normal", space_after=6, line_spacing=1.2)
    add_para(doc, "GIẢNG VIÊN HƯỚNG DẪN", style="Normal", bold=True,
             align=WD_ALIGN_PARAGRAPH.RIGHT, space_before=16)
    add_para(doc, "(Ký và ghi rõ họ tên)", style="Normal", italic=True,
             align=WD_ALIGN_PARAGRAPH.RIGHT)


def declaration(doc):
    h1_front(doc, "LỜI CAM ĐOAN")
    body(doc, "Bài tập lớn với đề tài “" + TITLE_1.lower() + " " + TITLE_2.lower() +
         "” là công trình nghiên cứu, thiết kế và cài đặt do chính em thực hiện dưới sự hướng dẫn "
         "của thầy " + LECTURER + ".")
    body(doc, "Toàn bộ nội dung báo cáo, mã nguồn, số liệu thực nghiệm và kết quả đánh giá được trình bày "
         "trong bài tập lớn này hoàn toàn trung thực. Các con số thống kê đều được trích xuất trực tiếp từ "
         "manifest của lần chạy thật trên hệ thống Docker gồm 12 dịch vụ, không phải số liệu mô phỏng.")
    body(doc, "Bộ dữ liệu sử dụng là hai shard công khai của bộ VatsaDev/test_arxiv trên Hugging Face, "
         "có ghi rõ revision và mã băm SHA-256 để bảo đảm khả năng tái lập. Các tài liệu tham khảo "
         "(bài báo khoa học, tài liệu kỹ thuật, bộ dữ liệu) đã được trích dẫn đầy đủ trong danh mục "
         "Tài liệu tham khảo.")
    body(doc, "Em không sao chép, không sử dụng trái phép kết quả hay ý tưởng của người khác dưới bất kỳ "
         "hình thức nào. Em hoàn toàn chịu trách nhiệm trước Khoa Công nghệ thông tin, Hội đồng chấm bài tập "
         "và Nhà trường về tính trung thực của toàn bộ nội dung bài tập lớn này.")
    for _ in range(2):
        add_para(doc, "", style="Normal")
    add_para(doc, f"Hưng Yên, ngày {datetime.now().day} tháng {datetime.now().month} năm {datetime.now().year}",
             style="Normal", italic=True, align=WD_ALIGN_PARAGRAPH.RIGHT)
    add_para(doc, "Sinh viên thực hiện", style="Normal", bold=True,
             align=WD_ALIGN_PARAGRAPH.RIGHT)
    add_para(doc, "(Ký và ghi rõ họ tên)", style="Normal", italic=True,
             align=WD_ALIGN_PARAGRAPH.RIGHT)
    add_para(doc, "", style="Normal")
    add_para(doc, STUDENT, style="Normal", bold=True, align=WD_ALIGN_PARAGRAPH.RIGHT)


def thanks(doc):
    h1_front(doc, "LỜI CẢM ƠN")
    body(doc, "Em xin trân trọng gửi lời cảm ơn sâu sắc nhất tới:")
    body(doc, "Thầy " + LECTURER + " – giảng viên học phần Xử lý dữ liệu lớn, người đã tận tình hướng dẫn, "
         "định hướng đề tài và đưa ra những nhận xét quý báu trong suốt quá trình em thực hiện bài tập lớn này. "
         "Những góp ý của thầy về tính tái lập của pipeline, về việc kiểm chứng số liệu bằng manifest và về "
         "cách trình bày kết quả đã giúp em hoàn thiện hệ thống một cách có hệ thống.")
    body(doc, "Quý thầy cô Khoa Công nghệ thông tin đã truyền đạt những kiến thức nền tảng về hệ phân tán, "
         "cơ sở dữ liệu, học máy và xử lý dữ liệu lớn, giúp em có đủ cơ sở để triển khai một hệ thống hoàn chỉnh "
         "trên nền Hadoop, Spark, Kafka và Hive.")
    body(doc, "Em cũng xin cảm ơn các tác giả của bộ dữ liệu VatsaDev/test_arxiv và cộng đồng mã nguồn mở "
         "Apache Spark, Apache Kafka, Apache Hive, Streamlit đã công bố tài liệu và mã nguồn để em có thể "
         "học tập, kế thừa và đối chiếu.")
    body(doc, "Mặc dù đã nỗ lực hết sức, song do kiến thức và thời gian còn hạn chế, bài tập lớn khó tránh khỏi "
         "những thiếu sót. Em kính mong nhận được những ý kiến đóng góp của quý thầy cô để đề tài được hoàn thiện hơn.")
    body(doc, "Một lần nữa, em xin trân trọng cảm ơn!")


def toc_page(doc):
    h1_front(doc, "MỤC LỤC")
    add_toc(doc)


def glossary(doc):
    h1(doc, "DANH MỤC CÁC THUẬT NGỮ")
    rows = [
        ("HDFS", "Hadoop Distributed File System – hệ thống tệp phân tán của Hadoop."),
        ("NameNode", "Tiến trình quản lý metadata của HDFS (danh sách tệp, khối và vị trí khối)."),
        ("DataNode", "Tiến trình lưu trữ khối dữ liệu thật trên từng máy của cụm HDFS."),
        ("Parquet", "Định dạng lưu trữ dạng cột, nén tốt và chỉ đọc những cột cần truy vấn."),
        ("Spark DataFrame", "Trừu tượng dữ liệu phân tán có lược đồ của Apache Spark."),
        ("Structured Streaming", "Mô hình xử lý luồng dữ liệu trên DataFrame của Spark."),
        ("Micro-batch", "Lô dữ liệu nhỏ được Structured Streaming xử lý theo từng chu kỳ."),
        ("Checkpoint", "Vị trí lưu tiến độ xử lý để luồng tiếp tục đúng chỗ sau khi khởi động lại."),
        ("Kafka topic", "Kênh logic chứa các bản ghi sự kiện, được chia thành nhiều partition."),
        ("Offset", "Số thứ tự của bản ghi trong một partition của Kafka."),
        ("Hive Metastore", "Kho metadata lưu định nghĩa database, bảng, cột và partition của Hive."),
        ("External table", "Bảng Hive chỉ quản lý metadata, dữ liệu vẫn nằm trên HDFS."),
        ("Partition", "Cách chia dữ liệu theo giá trị của một cột (ví dụ năm hoặc nhóm ngành)."),
        ("LDA", "Latent Dirichlet Allocation – mô hình chủ đề xác suất."),
        ("Perplexity", "Chỉ số đo mức độ phù hợp của mô hình chủ đề với dữ liệu kiểm định."),
        ("Data contract", "Bộ quy tắc dùng chung cho batch và streaming để dữ liệu nhất quán."),
        ("Quarantine", "Vùng cách ly chứa các bản ghi lỗi, tách khỏi luồng dữ liệu hợp lệ."),
        ("Idempotent", "Thao tác chạy lại nhiều lần vẫn cho cùng một kết quả."),
        ("Manifest", "Tệp JSON ghi lại số liệu, thời gian và mã lần chạy để kiểm chứng kết quả."),
        ("Dashboard", "Bảng điều khiển trực quan hóa dữ liệu và thao tác vận hành."),
    ]
    table(doc, "Bảng 0.1. Các thuật ngữ dùng trong báo cáo", ["Thuật ngữ", "Giải thích"],
          rows, [4.0, 11.5])


def figures_index(doc, pages):
    h1(doc, "DANH MỤC CÁC HÌNH VẼ, ĐỒ THỊ")
    items = [
        "Hình 2.1. Kiến trúc Lambda áp dụng cho bài toán arXiv",
        "Hình 3.1. Kiến trúc tổng thể của hệ thống",
        "Hình 3.2. Sơ đồ luồng dữ liệu của dashboard",
        "Hình 4.1. Số bài báo theo năm nộp (2007–2016)",
        "Hình 4.2. Cơ cấu bài báo theo tám nhóm ngành",
        "Hình 4.3. Xu hướng số bài theo nhóm ngành",
        "Hình 4.4. Mười chuyên ngành có nhiều bài nhất",
        "Hình 4.5. Bản đồ nhiệt số bài theo năm và nhóm ngành",
        "Hình 4.6. Xu hướng các từ khóa công nghệ",
        "Hình 4.7. Đám mây từ khóa theo nhóm ngành",
        "Hình 4.8. Mười lăm tác giả có nhiều bài nhất",
        "Hình 4.9. Xu hướng hợp tác tác giả",
        "Hình 4.10. Mười chủ đề LDA và tỷ lệ xuất hiện",
        "Hình 4.11. Kiểm định ngoại suy xu hướng từ khóa",
        "Hình 4.12. So sánh các nhóm ngành theo bốn chỉ số",
        "Hình 5.1. Tab Tổng quan của dashboard",
        "Hình 5.2. Tab Gửi dữ liệu – Kafka Ingestion Studio",
        "Hình 5.3. Kết quả mẫu truy vấn 7 – so sánh raw, clean và tokens",
        "Hình 5.4. Kết quả mẫu truy vấn 8 – phân bố sự kiện theo nhóm ngành",
        "Hình 5.5. Tab Kiến trúc – sơ đồ luồng và trạng thái dịch vụ",
    ]
    for label in items:
        page_entry(doc, label, (pages or {}).get(label))


def tables_index(doc, pages):
    h1(doc, "DANH MỤC CÁC BẢNG")
    items = [
        "Bảng 0.1. Các thuật ngữ dùng trong báo cáo",
        "Bảng 1.1. So sánh xử lý truyền thống và xử lý dữ liệu lớn",
        "Bảng 1.2. Hai shard dữ liệu và thông tin kiểm chứng",
        "Bảng 2.1. Quy tắc dữ liệu áp dụng cho batch và streaming",
        "Bảng 2.2. Thành phần công nghệ và phiên bản sử dụng",
        "Bảng 3.1. Tổ chức mã nguồn",
        "Bảng 3.2. Mười hai dịch vụ trong Docker Compose",
        "Bảng 3.3. Các giai đoạn của luồng batch và thời gian chạy",
        "Bảng 3.4. Các lỗi logic phát hiện khi kiểm thử và cách khắc phục",
        "Bảng 4.1. Tổng quan lần chạy thực nghiệm",
        "Bảng 4.2. Số bài và tăng trưởng theo năm",
        "Bảng 4.3. Cơ cấu tám nhóm ngành",
        "Bảng 4.4. Mười chuyên ngành hàng đầu",
        "Bảng 4.5. Từ khóa công nghệ trên 1.000 bài năm 2015",
        "Bảng 4.6. Mười lăm tác giả có nhiều bài nhất",
        "Bảng 4.7. Mười chủ đề LDA",
        "Bảng 4.8. Kết quả kiểm định ngoại suy",
        "Bảng 4.9. Sự kiện streaming theo nhóm ngành",
        "Bảng 5.1. Danh mục kiểm chứng end-to-end",
    ]
    for label in items:
        page_entry(doc, label, (pages or {}).get(label))


def introduction(doc):
    h1(doc, "MỞ ĐẦU")
    h2(doc, "Lý do chọn đề tài")
    body(doc, "arXiv là kho lưu trữ mở lớn nhất thế giới cho các bài báo khoa học, với hơn hai triệu bản ghi "
         "và hàng chục nghìn bài mới mỗi tháng. Mỗi bài báo mang theo một lượng metadata có cấu trúc: mã bài, "
         "tiêu đề, danh sách tác giả, chuyên ngành, ngày nộp và tóm tắt. Khi gom đủ lớn, metadata này trả lời "
         "được những câu hỏi mà đọc từng bài không thể trả lời: ngành nào đang tăng trưởng, từ khóa công nghệ "
         "nào đang lên, chủ đề nghiên cứu dịch chuyển ra sao theo thời gian.")
    body(doc, "Tuy nhiên, khối lượng dữ liệu vượt xa khả năng xử lý của một máy tính cá nhân. Chỉ hai shard đầu "
         "tiên của bộ dữ liệu đã chiếm 543 MiB nén và 704.329 bản ghi; toàn bộ arXiv lớn hơn nhiều lần. Việc đọc, "
         "làm sạch, nhóm và huấn luyện mô hình trên dữ liệu này đòi hỏi một kiến trúc phân tán thực sự, không chỉ "
         "là một script pandas chạy trên laptop.")
    body(doc, "Bên cạnh đó, dữ liệu khoa học không chỉ đến theo lô mà còn đến liên tục. Mỗi ngày có bài mới được "
         "công bố, và một hệ thống phân tích chỉ có giá trị khi vừa xử lý được dữ liệu lịch sử, vừa tiếp nhận được "
         "sự kiện mới mà không phải dừng lại. Đây chính là bài toán mà kiến trúc Lambda giải quyết: một nhánh batch "
         "xử lý toàn bộ dữ liệu, một nhánh streaming xử lý sự kiện theo thời gian thực, cả hai cùng ghi vào một "
         "tầng lưu trữ và cùng được truy vấn qua một lớp kho dữ liệu.")
    body(doc, "Về mặt học thuật, đề tài vận dụng trực tiếp và đồng thời các nội dung cốt lõi của học phần Xử lý dữ "
         "liệu lớn: hệ thống tệp phân tán HDFS, tính toán song song với Spark, hàng đợi sự kiện Kafka, kho dữ liệu "
         "Hive và trực quan hóa kết quả. Vì vậy, đề tài vừa có ý nghĩa thực tiễn, vừa là một bài tổng hợp kiến thức "
         "có thể kiểm chứng được bằng số liệu cụ thể.")

    h2(doc, "Mục tiêu của đề tài")
    body(doc, "Mục tiêu chung là xây dựng một hệ thống phân tích dữ liệu lớn hoàn chỉnh cho metadata bài báo khoa học "
         "arXiv, chạy được cả theo lô và theo luồng, có khả năng tái lập và có giao diện demo. Cụ thể:")
    for text in [
        "Xây dựng pipeline batch đọc hai shard Parquet, chuẩn hóa dữ liệu theo một bộ quy tắc thống nhất và lưu kết "
        "quả trung gian dưới dạng Parquet trên HDFS.",
        "Thiết kế bộ quy tắc dữ liệu (data contract) dùng chung cho batch và streaming, đặc biệt là quy tắc xác định "
        "năm nộp bài theo phiên bản v1 và kiểm tra chéo với mã arXiv.",
        "Tính các chỉ số phân tích: tăng trưởng theo năm, cơ cấu nhóm ngành, xếp hạng chuyên ngành, từ khóa công nghệ, "
        "tác giả và mô hình chủ đề LDA.",
        "Xây dựng nhánh streaming bằng Kafka và Spark Structured Streaming, có checkpoint và cơ chế cách ly bản ghi "
        "lỗi để luồng không bị dừng.",
        "Tạo lớp kho dữ liệu Hive gồm các bảng external và view, cho phép truy vấn SQL trực tiếp trên HDFS.",
        "Xây dựng dashboard Streamlit năm tab, hiển thị kết quả, gửi dữ liệu thử và duyệt HDFS.",
        "Kiểm chứng end-to-end bằng số liệu thật, ghi lại mọi lỗi phát hiện trong quá trình kiểm thử và cách khắc phục.",
    ]:
        bullet(doc, text)

    h2(doc, "Giới hạn và phạm vi nghiên cứu")
    body(doc, "Đối tượng nghiên cứu là metadata của các bài báo khoa học trong bộ VatsaDev/test_arxiv. Phạm vi có một "
         "số giới hạn được nêu rõ để tránh diễn giải sai kết quả:")
    for text in [
        "Về dữ liệu: chỉ sử dụng hai shard đầu tiên với 704.329 bản ghi, tương ứng 543 MiB nén và 615,6 MB trên HDFS. "
        "Đây không phải mẫu đại diện cho toàn bộ arXiv, nên các kết luận chỉ có giá trị trong phạm vi đã tải.",
        "Về thời gian: dữ liệu trải từ 2007 đến 2016. Hai năm biên bị ảnh hưởng bởi cách chia shard, nên không dùng "
        "để kết luận xu hướng.",
        "Về tài nguyên: hệ thống chạy trên một máy cá nhân với Docker Desktop, 12 container chia sẻ CPU và RAM. Các phép "
        "đo thời gian phản ánh xu hướng, không phải benchmark chuẩn của một cụm thật.",
        "Về mô hình: chỉ dùng các thuật toán có sẵn trong Spark MLlib, không huấn luyện mô hình ngôn ngữ lớn. LDA được "
        "huấn luyện trên mẫu tất định 200.181 bài để vừa tài nguyên.",
        "Về ngôn ngữ: dữ liệu là tiếng Anh; quy tắc tách từ và danh sách stopword chỉ áp dụng cho tiếng Anh.",
    ]:
        bullet(doc, text)

    h2(doc, "Phương pháp tiếp cận")
    body(doc, "Đề tài được thực hiện theo hướng thực nghiệm có kiểm chứng, với bốn nguyên tắc xuyên suốt:")
    for text in [
        "Một nguồn quy tắc duy nhất: batch và streaming cùng gọi các hàm trong data_contract.py, nhờ đó một bài báo "
        "được xử lý giống nhau dù đi qua đường lô hay đường luồng.",
        "Chạy lại được: mỗi giai đoạn ghi tệp đánh dấu _SUCCESS, dùng ghi đè có kiểm soát và lưu mã lần chạy trong "
        "manifest. Không có kết quả nào được coi là hợp lệ nếu manifest không khớp với dữ liệu sạch.",
        "Đo lường thay vì phỏng đoán: mọi con số trong báo cáo đều lấy từ manifest, từ Hive hoặc từ log của lần chạy thật.",
        "Kiểm chứng end-to-end: sau khi sửa lỗi, hệ thống được chạy lại từ đầu đến cuối, bao gồm cả việc gửi một bản "
        "ghi hợp lệ và một bản ghi lỗi để xác nhận cơ chế cách ly hoạt động.",
    ]:
        bullet(doc, text)
    body(doc, "Bố cục báo cáo gồm năm chương: Chương 1 giới thiệu bài toán và dữ liệu; Chương 2 trình bày cơ sở lý "
         "thuyết và công nghệ; Chương 3 trình bày thiết kế và triển khai; Chương 4 trình bày kết quả thực nghiệm; "
         "Chương 5 trình bày kiểm chứng, đánh giá và hạn chế. Phần kết luận tổng hợp kết quả và hướng phát triển.")


def chapter1(doc):
    h1(doc, "CHƯƠNG 1: GIỚI THIỆU BÀI TOÁN VÀ DỮ LIỆU ARXIV")
    h2(doc, "1.1. Bài toán phân tích metadata bài báo khoa học")
    body(doc, "Bài toán được phát biểu như sau: cho một tập lớn metadata bài báo khoa học, cần xây dựng một quy trình "
         "tự động biến dữ liệu thô thành các bảng phân tích có thể trả lời các câu hỏi về quy mô, cơ cấu và xu hướng "
         "nghiên cứu, đồng thời tiếp nhận được bài báo mới theo thời gian thực.")
    body(doc, "Đầu vào là các bản ghi có các trường id, title, abstract, authors, categories, versions và update_date. "
         "Đầu ra gồm: (i) bảng sạch trên HDFS; (ii) các bảng phân tích theo năm, theo nhóm ngành, theo chuyên ngành, "
         "theo từ khóa và theo tác giả; (iii) mô hình chủ đề LDA; (iv) kết quả kiểm định ngoại suy; (v) kho dữ liệu "
         "Hive cho phép truy vấn SQL; và (vi) dashboard trực quan.")
    body(doc, "Điểm khó của bài toán không nằm ở từng phép tính, mà ở chỗ các phép tính phải nhất quán với nhau trên "
         "cùng một định nghĩa dữ liệu. Ví dụ, nếu bước batch tính năm theo ngày tạo phiên bản v1 nhưng bước streaming "
         "lại tính năm theo mã bài, thì cùng một bài báo sẽ xuất hiện ở hai năm khác nhau trong hai bảng. Vì vậy, "
         "đề tài đặt data contract làm trung tâm của thiết kế.")

    h2(doc, "1.2. Vì sao cần xử lý dữ liệu lớn")
    body(doc, "Bài toán hội đủ các đặc trưng của dữ liệu lớn:")
    for text in [
        "Khối lượng (Volume): chỉ hai shard đã có 704.329 bản ghi và 615,6 MB trên HDFS; toàn bộ arXiv lớn hơn nhiều lần. "
        "Các phép group theo nhóm ngành và theo từ khóa phải quét toàn bộ dữ liệu.",
        "Tốc độ (Velocity): bài báo mới được công bố liên tục, đòi hỏi nhánh streaming có checkpoint và khả năng phục hồi.",
        "Đa dạng (Variety): dữ liệu gồm chuỗi, mảng, cấu trúc lồng (versions), ngày tháng ở nhiều định dạng và danh sách "
        "chuyên ngành phân tách bằng khoảng trắng.",
        "Độ tin cậy (Veracity): dữ liệu thật có mã bài cũ trước tháng 4/2007, có bài nộp cuối tháng 12 nhưng nhận mã tháng "
        "1 năm sau, và có bản ghi thiếu trường bắt buộc.",
    ]:
        bullet(doc, text)
    body(doc, "Bảng 1.1 tóm tắt khác biệt giữa cách xử lý truyền thống và cách xử lý dữ liệu lớn mà đề tài áp dụng.")
    table(doc, "Bảng 1.1. So sánh xử lý truyền thống và xử lý dữ liệu lớn",
          ["Tiêu chí", "Xử lý truyền thống", "Xử lý dữ liệu lớn (đề tài)"],
          [("Đơn vị lưu trữ", "Một tệp CSV trên ổ đĩa cục bộ", "Nhiều tệp Parquet phân vùng trên HDFS"),
           ("Cách tính", "Một tiến trình, tuần tự", "Nhiều partition chạy song song trên Spark"),
           ("Dữ liệu mới", "Chạy lại toàn bộ", "Batch cho lịch sử, streaming cho sự kiện mới"),
           ("Truy vấn", "Đọc lại toàn bộ tệp", "Hive external table + partition pruning"),
           ("Khả năng phục hồi", "Mất tiến trình là mất kết quả", "Checkpoint, _SUCCESS, chạy lại theo giai đoạn"),
           ("Kiểm chứng", "Khó tái lập", "Manifest ghi mã lần chạy, số dòng, thời gian")],
          [3.2, 5.4, 6.9])

    h2(doc, "1.3. Nguồn dữ liệu và phạm vi trích xuất")
    body(doc, "Dữ liệu được lấy từ bộ VatsaDev/test_arxiv trên Hugging Face tại revision "
         "adef1f1e891574774660683f0f4548e50f5d551f (nhánh refs/convert/parquet). Đề tài tải hai shard đầu tiên, "
         "ghi lại đường dẫn, dung lượng và mã băm SHA-256 để bảo đảm cùng một đầu vào cho mọi lần chạy.")
    table(doc, "Bảng 1.2. Hai shard dữ liệu và thông tin kiểm chứng",
          ["Shard", "Tệp", "Dung lượng (byte)", "SHA-256"],
          [("1", "default/train/0000.parquet", "283.355.969", "99922809dfa2e73b…"),
           ("2", "default/train/0001.parquet", "286.042.960", "7d3f5349ddfb8edb…")],
          [1.6, 5.4, 4.0, 4.5], numeric=(0, 2))
    body(doc, "Sau khi làm sạch, dữ liệu có 704.329 bản ghi, trải từ năm 2007 đến 2016 và thuộc tám nhóm ngành. "
         "Không có bản ghi nào bị loại ở bước batch, nhưng có 2.323 bản ghi mà năm suy từ ngày v1 khác năm suy từ mã "
         "bài — chính là nhóm bài nộp cuối tháng 12 nhưng nhận mã tháng 1 năm sau. Đây là lý do phải ưu tiên ngày v1 "
         "thay vì mã bài khi xác định năm.")

    h2(doc, "1.4. Khó khăn và thách thức")
    body(doc, "Quá trình triển khai gặp năm nhóm khó khăn chính:")
    for text in [
        "Chuẩn hóa năm nộp: mã arXiv chứa năm và tháng, nhưng không phải lúc nào cũng trùng với ngày tạo phiên bản v1. "
        "Nếu chỉ dùng một nguồn, khoảng 2.323 bài sẽ bị xếp sai năm.",
        "Mã bài cũ: trước tháng 4/2007, arXiv dùng định dạng archive/YYMMNNN thay vì YYMM.NNNNN. Bộ quy tắc phải nhận "
        "diện được cả hai định dạng và trả về None cho mã không hợp lệ.",
        "Dữ liệu lỗi trong luồng: một bản ghi thiếu trường hoặc sai năm có thể làm cả micro-batch thất bại. Nếu để "
        "ngoại lệ nổi lên, consumer sẽ khởi động lại và kẹt mãi ở cùng một offset.",
        "Hiệu năng trên máy cá nhân: 12 container chia sẻ tài nguyên, nên các phép join và group phải được thiết kế "
        "để tránh shuffle không cần thiết.",
        "Tính tái lập: kết quả phải gắn với đúng phiên bản dữ liệu và đúng mã lần chạy, nếu không các con số trong báo "
        "cáo sẽ không kiểm chứng được.",
    ]:
        bullet(doc, text)

    h2(doc, "1.5. Nội dung thực hiện")
    body(doc, "Công việc được tổ chức thành chín giai đoạn, mỗi giai đoạn là một chương trình hoặc notebook độc lập:")
    for text in [
        "Giai đoạn 0 – Chuẩn bị môi trường: viết Docker Compose cho 12 dịch vụ, cấu hình mạng, volume và biến môi trường.",
        "Giai đoạn 1 – Tải dữ liệu: tải hai shard, ghi source_manifest.json với revision, dung lượng và SHA-256.",
        "Giai đoạn 2 – Khảo sát dữ liệu: kiểm tra lược đồ, số dòng, khoảng năm, các trường thiếu và phân bố ban đầu.",
        "Giai đoạn 3 – Tiền xử lý: áp dụng data contract, tạo cột dẫn xuất, tách từ và ghi Parquet sạch.",
        "Giai đoạn 4 – Phân tích: tính các bảng theo năm, nhóm ngành, chuyên ngành, từ khóa, tác giả và huấn luyện LDA.",
        "Giai đoạn 5 – Trực quan hóa: sinh 12 biểu đồ PNG từ kết quả phân tích.",
        "Giai đoạn 6 – Streaming: dựng Kafka, producer và Spark Structured Streaming ghi xuống HDFS.",
        "Giai đoạn 7 – Kho dữ liệu và dashboard: tạo bảng Hive, view và dashboard Streamlit năm tab.",
        "Giai đoạn 8 – Kiểm chứng: chạy lại toàn bộ, đối chiếu số liệu, gửi thử bản ghi hợp lệ và bản ghi lỗi.",
    ]:
        bullet(doc, text)

    h2(doc, "1.6. Kết chương")
    body(doc, "Chương này đã trình bày bài toán phân tích metadata arXiv, lý do cần một kiến trúc xử lý dữ liệu lớn, "
         "phạm vi hai shard và năm nhóm khó khăn chính. Trên cơ sở đó, Chương 2 trình bày cơ sở lý thuyết về HDFS, "
         "Spark, Kafka, Hive, Parquet, data contract và các phương pháp phân tích được sử dụng.")


def chapter2(doc):
    h1(doc, "CHƯƠNG 2: CƠ SỞ LÝ THUYẾT VÀ CÔNG NGHỆ")
    h2(doc, "2.1. Kiến trúc xử lý dữ liệu lớn theo lô và theo luồng")
    h3(doc, "2.1.1. Mô hình Lambda và lựa chọn kiến trúc")
    body(doc, "Kiến trúc Lambda chia hệ thống thành ba tầng: tầng batch xử lý toàn bộ dữ liệu lịch sử, tầng speed xử lý "
         "sự kiện mới với độ trễ thấp, và tầng serving hợp nhất kết quả của hai tầng để phục vụ truy vấn. Đề tài áp "
         "dụng mô hình này ở dạng gọn nhẹ: batch dùng Spark ghi Parquet lên HDFS; speed dùng Kafka và Spark Structured "
         "Streaming ghi Parquet lên một thư mục riêng; serving dùng Hive external table trỏ tới cả hai thư mục và "
         "dashboard Streamlit đọc qua HiveServer2.")
    body(doc, "Cách tách hai thư mục (/data/arxiv_clean_v2 và /data/arxiv_stream_v2) có ba lợi ích: không ghi đè dữ liệu "
         "lịch sử khi streaming chạy; có thể xóa và tạo lại từng bảng Hive mà không mất dữ liệu; và phân vùng của hai "
         "luồng được tối ưu theo cách truy vấn khác nhau (theo năm cho lịch sử, theo nhóm ngành cho sự kiện).")
    figure(doc, "00_pipeline_full_architecture.png", "Hình 2.1. Kiến trúc Lambda áp dụng cho bài toán arXiv", 15.5)

    h3(doc, "2.1.2. Hệ thống tệp phân tán HDFS")
    body(doc, "HDFS là hệ thống tệp phân tán của Hadoop, cho phép lưu các tệp rất lớn trên nhiều máy thông thường. Mỗi "
         "tệp được chia thành các khối (mặc định 128 MB), mỗi khối được nhân bản trên nhiều DataNode. NameNode quản lý "
         "metadata (tệp gồm những khối nào, khối nằm ở đâu), còn DataNode lưu dữ liệu thật và định kỳ gửi báo cáo "
         "tình trạng.")
    body(doc, "Trong đề tài, HDFS là tầng lưu trữ duy nhất cho cả batch và streaming. Dữ liệu sạch được ghi vào "
         "/data/arxiv_clean_v2 và phân vùng theo năm; dữ liệu sự kiện được ghi vào /data/arxiv_stream_v2 và phân vùng "
         "theo nhóm ngành; bản ghi lỗi được ghi vào /data/arxiv_stream_rejects_v2. Hệ số nhân bản mặc định của cụm "
         "là 3, nên dung lượng thực tế trên đĩa lớn hơn dung lượng logic.")

    h3(doc, "2.1.3. Apache Spark và Spark Structured Streaming")
    body(doc, "Spark là nền tảng tính toán phân tán hoạt động chủ yếu trên bộ nhớ. Một ứng dụng Spark gồm Driver xây dựng "
         "kế hoạch thực thi, Cluster Manager cấp phát tài nguyên và các Executor thực thi task trên từng partition. "
         "Spark thực thi lười: các phép biến đổi chỉ ghi nhận kế hoạch, chỉ khi gặp hành động như count hoặc write thì "
         "Catalyst mới tối ưu và chạy.")
    body(doc, "Spark Structured Streaming xem một luồng dữ liệu như một bảng không ngừng được nối thêm. Mỗi chu kỳ "
         "(micro-batch), Spark đọc các bản ghi mới từ nguồn, áp dụng cùng một cây truy vấn và ghi kết quả ra sink. "
         "Checkpoint lưu offset đã đọc và trạng thái tính toán, nhờ đó sau khi khởi động lại, luồng tiếp tục đúng chỗ "
         "thay vì đọc lại từ đầu hoặc bỏ sót dữ liệu. Đề tài dùng trigger 5 giây và chế độ append.")
    body(doc, "Một điểm kỹ thuật quan trọng: một truy vấn streaming chỉ có một sink. Để vừa ghi dữ liệu hợp lệ vừa ghi "
         "bản ghi lỗi, đề tài dùng foreachBatch — hàm nhận từng DataFrame của micro-batch và có thể thực hiện nhiều "
         "thao tác ghi bên trong. Đây là cơ chế then chốt giúp consumer không bị dừng khi gặp dữ liệu xấu.")

    h3(doc, "2.1.4. Apache Kafka")
    body(doc, "Kafka là hệ thống hàng đợi phân tán hoạt động theo mô hình publish–subscribe. Dữ liệu được tổ chức thành "
         "các topic, mỗi topic chia thành nhiều partition để ghi và đọc song song. Mỗi bản ghi có khóa, giá trị và "
         "offset — số thứ tự tăng dần trong partition. Producer gửi bản ghi và có thể yêu cầu xác nhận ACK; consumer "
         "đọc theo offset và tự quản lý tiến độ.")
    body(doc, "Trong đề tài, topic arxiv-papers-v2 nhận các bài báo mới. Producer dùng acks=all để chỉ báo thành công khi "
         "bản ghi đã được ghi bền vững, nhờ đó con số “đã gửi” trên dashboard là số bản ghi Kafka thực sự nhận, không "
         "phải số lần gọi hàm.")

    h3(doc, "2.1.5. Apache Hive và HiveServer2")
    body(doc, "Hive là lớp kho dữ liệu cho phép truy vấn SQL trên dữ liệu nằm trên HDFS. Hive Metastore lưu định nghĩa "
         "database, bảng, cột và partition; HiveServer2 nhận truy vấn từ client qua giao thức Thrift. Với external "
         "table, Hive chỉ quản lý metadata, còn dữ liệu vẫn do Spark ghi ra — nhờ đó có thể xóa và tạo lại bảng mà "
         "không mất dữ liệu.")
    body(doc, "Đề tài dùng bốn bảng external: arxiv_historical (phân vùng theo năm), arxiv_stream (phân vùng theo nhóm "
         "ngành), hot_keyword_trends và arxiv_stream_rejects — bảng cách ly chứa các sự kiện không vượt qua kiểm tra "
         "cùng lý do loại bỏ. Ba view v_yearly_growth, v_field_distribution, v_top_categories được tạo sẵn "
         "để dashboard và người dùng cuối truy vấn nhanh.")

    h2(doc, "2.2. Định dạng Parquet và phân vùng dữ liệu")
    body(doc, "Parquet lưu dữ liệu theo cột thay vì theo dòng. Cách tổ chức này cho phép truy vấn chỉ đọc những cột cần "
         "thiết, và nén tốt hơn nhờ các giá trị trong cùng một cột thường giống nhau. Parquet còn lưu lược đồ kèm dữ "
         "liệu nên Spark không phải quét để suy đoán kiểu.")
    body(doc, "Phân vùng (partition) chia dữ liệu thành các thư mục con theo giá trị của một cột, ví dụ year=2015 hoặc "
         "main_group_clean=physics. Khi truy vấn có điều kiện trên cột phân vùng, Hive chỉ đọc đúng thư mục cần thiết "
         "(partition pruning), giảm mạnh lượng dữ liệu phải quét. Đề tài chọn phân vùng theo năm cho dữ liệu lịch sử "
         "vì hầu hết truy vấn đều lọc theo năm, và theo nhóm ngành cho dữ liệu sự kiện vì dashboard thường so sánh "
         "giữa các nhóm.")

    h2(doc, "2.3. Quy tắc dữ liệu dùng chung")
    h3(doc, "2.3.1. Chuẩn hóa năm nộp")
    body(doc, "Năm nộp được hiểu là năm của lần nộp đầu tiên (phiên bản v1). Quy tắc gồm ba bước: (i) lấy ngày tạo của "
         "phiên bản v1 trong trường versions; (ii) nếu không có, suy ra năm từ mã arXiv; (iii) kiểm tra năm nằm trong "
         "khoảng 1991 đến năm hiện tại.")
    body(doc, "Mã arXiv hiện đại có dạng YYMM.NNNNN (từ tháng 4/2007), mã cũ có dạng archive/YYMMNNN (trước tháng "
         "4/2007). Quy tắc xử lý riêng hai định dạng, bao gồm quy ước hai chữ số năm nhỏ hơn 91 thuộc thế kỷ 20. "
         "Khi cả hai nguồn đều có, ngày v1 được ưu tiên; mã bài chỉ dùng làm phương án dự phòng. Chênh lệch giữa hai "
         "nguồn được đếm và ghi vào manifest (2.323 bản ghi trong lần chạy này) để người đọc biết quy tắc đã thực sự "
         "có tác dụng.")

    h3(doc, "2.3.2. Phân nhóm ngành")
    body(doc, "Mỗi bài có một danh sách chuyên ngành, phần tử đầu tiên là chuyên ngành chính. Từ tiền tố của chuyên "
         "ngành chính, hệ thống ánh xạ về tám nhóm: physics (gồm toàn bộ các archive vật lý như astro-ph, cond-mat, "
         "quant-ph, hep-*, gr-qc, math-ph, nlin, physics), math, cs, stat, q-bio, q-fin, eess, econ. Các archive không "
         "thuộc danh sách được gán nhãn other. Cách gộp này giữ được ý nghĩa vật lý của dữ liệu, thay vì để hàng chục "
         "archive rời rạc làm loãng biểu đồ.")

    h3(doc, "2.3.3. Làm sạch và tách từ")
    body(doc, "Tóm tắt được chuyển về chữ thường, thay mọi ký tự không phải chữ cái, chữ số, khoảng trắng hoặc dấu gạch "
         "nối bằng khoảng trắng, rồi tách theo khoảng trắng với độ dài tối thiểu ba ký tự. Danh sách stopword tiếng "
         "Anh của Spark MLlib được loại bỏ. Kết quả là một mảng token dùng cho thống kê từ khóa và cho LDA. Việc giữ "
         "lại cả clean_abstract và abstract_tokens cho phép dashboard so sánh trực quan giữa dữ liệu thô, dữ liệu sạch "
         "và số token.")

    h3(doc, "2.3.4. Kiểm tra hợp lệ và vùng cách ly")
    body(doc, "Một bản ghi được coi là hợp lệ khi có đủ bốn trường bắt buộc (id, title, abstract, categories) và năm "
         "nộp xác định được. Trong batch, bản ghi không hợp lệ bị loại và đếm vào rejected_rows. Trong streaming, bản "
         "ghi không hợp lệ không bị ném ngoại lệ mà được gắn nhãn lý do và ghi sang thư mục cách ly "
         "(/data/arxiv_stream_rejects_v2) với cột reject_reason. Cách xử lý này giữ nguyên nguyên tắc “không mất dữ "
         "liệu âm thầm”: bản ghi lỗi vẫn được lưu để điều tra, nhưng không làm hỏng luồng.")
    table(doc, "Bảng 2.1. Quy tắc dữ liệu áp dụng cho batch và streaming",
          ["Quy tắc", "Batch", "Streaming"],
          [("Bốn trường bắt buộc", "Loại bản ghi, tăng rejected_rows", "Ghi sang vùng cách ly, reason=missing_required_field"),
           ("Năm hợp lệ (1991..nay)", "Loại bản ghi", "Ghi sang vùng cách ly, reason=invalid_year"),
           ("Năm gửi kèm khác năm tính lại", "Không áp dụng", "Ghi sang vùng cách ly, reason=invalid_year"),
           ("Trùng id", "Dừng pipeline để xử lý phiên bản", "Giữ nguyên sự kiện, đếm DISTINCT id khi báo cáo"),
           ("Tách từ", "RegexTokenizer + StopWordsRemover", "Cùng hai bước, cùng tham số"),
           ("Phân nhóm ngành", "Từ chuyên ngành chính", "Từ chuyên ngành chính")],
          [4.3, 5.6, 5.6])

    h2(doc, "2.4. Các phương pháp phân tích")
    h3(doc, "2.4.1. Tăng trưởng theo năm")
    body(doc, "Số bài theo năm được tính bằng groupBy(year). Tăng trưởng so với năm trước dùng hàm lag trên window sắp "
         "theo năm: yoy = (count_n / count_{n-1} - 1) × 100. Hàm with_growth được viết để mọi năm trong khoảng đều "
         "xuất hiện, kể cả năm không có bài, tránh việc biểu đồ nối sai hai năm cách xa nhau.")
    h3(doc, "2.4.2. Mô hình chủ đề LDA")
    body(doc, "LDA là mô hình sinh xác suất, giả định mỗi văn bản là hỗn hợp của K chủ đề và mỗi chủ đề là phân bố trên "
         "từ vựng. Đề tài dùng CountVectorizer với từ điển 10.000 từ, áp dụng IDF để giảm trọng số các từ quá phổ "
         "biến, rồi huấn luyện LDA với K = 10. Tập huấn luyện và kiểm định được chia tất định theo id bài để bảo đảm "
         "chạy lại cho cùng kết quả; mỗi phía được lấy mẫu tối đa 200.000 và 50.000 bài để vừa tài nguyên.")
    body(doc, "Chất lượng mô hình được đánh giá bằng log-perplexity trên tập kiểm định. Giá trị càng thấp càng tốt; "
         "kết quả 7,7619 được dùng làm chỉ số tham chiếu khi so sánh các cấu hình K khác nhau.")
    h3(doc, "2.4.3. Kiểm định ngoại suy xu hướng")
    body(doc, "Trước khi công bố một dự báo, đề tài kiểm tra xem phương pháp dự báo có thực sự tốt hơn baseline hay "
         "không. Cách làm: huấn luyện trên giai đoạn 2007–2012, dự báo ba năm 2013–2015, so sánh sai số tuyệt đối "
         "trung bình (MAE) với baseline “giữ nguyên giá trị năm cuối”. Nếu MAE của mô hình nhỏ hơn baseline, dự báo "
         "được chấp nhận; ngược lại, báo cáo nêu rõ là không đủ cơ sở.")
    h2(doc, "2.5. Dashboard và các chỉ số vận hành")
    body(doc, "Dashboard là lớp giao diện cuối cùng, nhưng không chỉ để trình bày. Nó còn là công cụ vận hành: hiển thị "
         "trạng thái bốn dịch vụ (Kafka, HDFS, Hive, Spark), cho phép gửi một bài báo hoặc phát lại hàng loạt, duyệt "
         "HDFS và chạy tám mẫu truy vấn Hive. Các chỉ số vận hành quan trọng gồm: số sự kiện streaming, số bài duy "
         "nhất (COUNT DISTINCT id), số bản ghi bị cách ly và thời gian thực thi truy vấn.")
    h2(doc, "2.6. Kết chương")
    body(doc, "Chương này đã trình bày kiến trúc Lambda, HDFS, Spark Structured Streaming, Kafka, Hive, Parquet, bộ quy "
         "tắc dữ liệu, các phương pháp phân tích và vai trò vận hành của dashboard. Đây là cơ sở để Chương 3 trình "
         "bày thiết kế và cài đặt cụ thể.")
    table(doc, "Bảng 2.2. Thành phần công nghệ và phiên bản sử dụng",
          ["Thành phần", "Phiên bản", "Vai trò trong hệ thống"],
          [("Hadoop HDFS", "3.2.1", "Lưu trữ phân tán cho batch và streaming"),
           ("Apache Spark", "3.5.3", "Tiền xử lý, phân tích, streaming, LDA"),
           ("Apache Kafka", "7.6.0 (Confluent)", "Hàng đợi sự kiện bài báo mới"),
           ("Apache Hive", "2.3.2", "Kho dữ liệu SQL trên HDFS"),
           ("PostgreSQL (metastore)", "2.3.0", "Lưu metadata của Hive"),
           ("Python", "3.11", "Ngôn ngữ cài đặt pipeline và dashboard"),
           ("Streamlit", "1.40.0", "Dashboard năm tab"),
           ("Docker Compose", "Desktop", "Điều phối 12 container")],
          [4.6, 4.0, 6.9])


def chapter3(doc):
    h1(doc, "CHƯƠNG 3: THIẾT KẾ VÀ TRIỂN KHAI HỆ THỐNG")
    h2(doc, "3.1. Kiến trúc tổng thể và tổ chức mã nguồn")
    body(doc, "Hệ thống gồm bốn tầng nối tiếp: tầng thu nhận (Parquet đầu vào và Kafka), tầng xử lý (Spark batch và "
         "Spark Structured Streaming), tầng lưu trữ và kho dữ liệu (HDFS, Hive Metastore, HiveServer2) và tầng trình "
         "bày (Streamlit). Mỗi tầng chỉ phụ thuộc vào tầng phía trước thông qua dữ liệu hoặc giao thức đã định nghĩa.")
    figure(doc, "ui_architecture.png", "Hình 3.1. Kiến trúc tổng thể của hệ thống", 15.2)
    body(doc, "Mã nguồn được tổ chức theo trách nhiệm, không theo notebook, để có thể chạy lại bằng dòng lệnh và tái sử "
         "dụng giữa batch và streaming:")
    table(doc, "Bảng 3.1. Tổ chức mã nguồn",
          ["Tệp", "Trách nhiệm"],
          [("project_config.py", "Đường dẫn, schema version, đọc manifest"),
           ("data_contract.py", "Quy tắc năm, nhóm ngành, tách từ, kiểm tra hợp lệ"),
           ("spark_common.py", "Tạo SparkSession với cấu hình thống nhất"),
           ("batch_pipeline.py", "Ba giai đoạn preprocess, analyze, sync-hdfs"),
           ("visualization.py", "Sinh 12 biểu đồ PNG từ kết quả phân tích"),
           ("kafka_producer.py", "Gửi một bài hoặc phát lại từ Parquet"),
           ("spark_streaming_consumer.py", "Đọc Kafka, ghi Parquet, cách ly bản ghi lỗi"),
           ("hive_client.py + hive_init.sql", "Tạo bảng, view, làm mới partition, truy vấn"),
           ("hdfs_helper.py", "Kiểm tra trạng thái và duyệt thư mục HDFS"),
           ("dashboard_app.py + dashboard_theme.css", "Dashboard năm tab, theme sáng")],
          [5.6, 9.9])

    h2(doc, "3.2. Môi trường triển khai")
    body(doc, "Toàn bộ hệ thống chạy bằng Docker Compose với 12 dịch vụ. Việc đóng gói bằng container bảo đảm mọi thành "
         "phần dùng đúng phiên bản và có thể dựng lại từ đầu bằng một lệnh. Bảng 3.2 liệt kê các dịch vụ và vai trò.")
    table(doc, "Bảng 3.2. Mười hai dịch vụ trong Docker Compose",
          ["Nhóm", "Dịch vụ", "Cổng", "Vai trò"],
          [("HDFS", "namenode", "9870, 9000", "Quản lý metadata HDFS"),
           ("HDFS", "datanode", "9864", "Lưu khối dữ liệu"),
           ("Spark", "spark-master", "8080, 7077", "Điều phối tài nguyên"),
           ("Spark", "spark-worker-1", "8081", "Thực thi task"),
           ("Spark", "spark-jupyter", "8888", "Chạy pipeline và notebook"),
           ("Kafka", "zookeeper", "2181", "Điều phối cụm Kafka"),
           ("Kafka", "kafka", "9092, 29092", "Hàng đợi sự kiện"),
           ("Kafka", "streaming-consumer", "—", "Spark Streaming đọc Kafka"),
           ("Hive", "hive-metastore-postgresql", "5432", "Lưu metadata Hive"),
           ("Hive", "hive-metastore", "9083", "Dịch vụ metadata"),
           ("Hive", "hive-server", "10000", "HiveServer2 nhận truy vấn"),
           ("UI", "dashboard", "8501", "Dashboard Streamlit")],
          [2.2, 5.0, 2.6, 5.7])

    h2(doc, "3.3. Luồng batch")
    h3(doc, "3.3.1. Tiền xử lý")
    body(doc, "Giai đoạn preprocess đọc Parquet thô, kiểm tra sự hiện diện của bốn cột bắt buộc, áp dụng data contract "
         "để tạo năm nộp, nhóm ngành, chuyên ngành chính và token. Sau đó dữ liệu được lọc theo điều kiện hợp lệ, "
         "kiểm tra trùng id và ghi ra Parquet sạch. Bước kiểm tra trùng id cố ý dừng pipeline thay vì tự động chọn "
         "một phiên bản, vì việc chọn ngẫu nhiên một bản ghi trong các phiên bản của cùng một bài sẽ làm sai lệch "
         "kết quả mà không ai phát hiện.")
    body(doc, "Sau khi ghi, chương trình đọc lại tệp vừa ghi để đối chiếu số dòng với số dòng hợp lệ đã đếm. Nếu lệch, "
         "pipeline dừng ngay. Đây là biện pháp chống lỗi âm thầm ở tầng lưu trữ.")
    h3(doc, "3.3.2. Phân tích")
    body(doc, "Giai đoạn analyze tính chín bảng kết quả: tăng trưởng theo năm, xu hướng theo nhóm ngành, chuyên ngành "
         "theo năm, từ khóa công nghệ, chỉ số theo nhóm, thuật ngữ theo nhóm, thuật ngữ hàng đầu, tác giả hàng đầu "
         "và xu hướng tác giả. Riêng bảng từ khóa phải quét toàn bộ 704.329 tóm tắt nên tốn 110,13 giây, chiếm phần "
         "lớn thời gian phân tích.")
    body(doc, "Mô hình LDA được huấn luyện trong cùng giai đoạn nhưng có thể bỏ qua bằng tham số --skip-topics khi chỉ "
         "cần các bảng thống kê. Kết quả chủ đề được ghi vào topics.json, kèm trọng số từ và tỷ lệ xuất hiện của "
         "từng chủ đề.")
    h3(doc, "3.3.3. Đồng bộ HDFS")
    body(doc, "Giai đoạn sync-hdfs ghi dữ liệu sạch vào /data/arxiv_clean_v2, phân vùng theo năm, và ghi bảng từ khóa "
         "vào /data/hot_keyword_trends_v2. Mỗi thư mục partition có tệp _SUCCESS để các bước sau biết dữ liệu đã "
         "hoàn tất. Sau khi ghi, chương trình gọi MSCK REPAIR để Hive nhận diện partition mới.")
    body(doc, "Một lỗi logic đã được phát hiện ở đây: lệnh batch_pipeline.py all trước đây chỉ chạy preprocess và "
         "analyze, không chạy sync-hdfs. Hệ quả là người dùng chạy “all” tưởng đã hoàn tất nhưng HDFS và Hive vẫn "
         "giữ dữ liệu cũ. Lỗi đã được sửa bằng cách đổi điều kiện thành args.stage in (\"sync-hdfs\", \"all\").")
    table(doc, "Bảng 3.3. Các giai đoạn của luồng batch và thời gian chạy",
          ["Giai đoạn", "Nội dung", "Thời gian (giây)"],
          [("preprocess", "Đọc 704.329 bản ghi, áp dụng data contract, ghi Parquet", "129,90"),
           ("analyze", "Chín bảng phân tích + LDA", "464,69"),
           ("— trong đó LDA", "CountVectorizer, IDF, LDA K=10, đánh giá perplexity", "280,18"),
           ("sync-hdfs", "Ghi Parquet phân vùng lên HDFS, MSCK REPAIR", "—"),
           ("Tổng (không tính sync)", "Preprocess + analyze", "594,59")],
          [4.0, 8.4, 3.1], numeric=(2,))

    h2(doc, "3.4. Luồng streaming")
    h3(doc, "3.4.1. Producer")
    body(doc, "Producer có hai chế độ: gửi một bài báo do người dùng nhập trên dashboard, và phát lại hàng loạt từ "
         "Parquet sạch. Trước khi gửi, mỗi bản ghi được kiểm tra bằng validate_paper: bốn trường bắt buộc phải là "
         "chuỗi không rỗng, id phải đúng định dạng arXiv, và nếu có trường year thì phải khớp với năm suy ra từ id "
         "hoặc ngày v1. Chỉ bản ghi đã xác nhận ACK mới được đếm là đã gửi.")
    h3(doc, "3.4.2. Consumer và checkpoint")
    body(doc, "Consumer đọc topic arxiv-papers-v2 ở chế độ earliest, phân tích JSON theo lược đồ tường minh, áp dụng "
         "cùng data contract với batch rồi ghi Parquet phân vùng theo main_group_clean. Checkpoint đặt tại "
         "/checkpoint/arxiv_stream_v2 trên HDFS. Nếu consumer dừng, khởi động lại sẽ đọc tiếp từ offset đã ghi trong "
         "checkpoint.")
    h3(doc, "3.4.3. Cách ly bản ghi lỗi")
    body(doc, "Phiên bản đầu tiên của consumer dùng raise_error khi gặp bản ghi thiếu trường. Cách làm này sai ở chỗ: "
         "lỗi làm cả micro-batch thất bại, checkpoint không tiến lên, consumer khởi động lại và gặp đúng bản ghi đó, "
         "tạo vòng lặp crash vô hạn. Sau khi sửa, mỗi micro-batch được chia làm hai: bản ghi hợp lệ ghi vào "
         "/data/arxiv_stream_v2, bản ghi lỗi ghi vào /data/arxiv_stream_rejects_v2 kèm cột reject_reason. Consumer "
         "vẫn chạy, dữ liệu lỗi vẫn được lưu để điều tra.")
    body(doc, "Việc chia batch được thực hiện trong foreachBatch. Trong một micro-batch, DataFrame được giữ trong bộ "
         "nhớ (persist) để tránh tính lại hai lần, sau đó lọc hai nhánh và ghi riêng. Cả hai lần ghi hoàn tất thì "
         "checkpoint mới được cập nhật.")

    h2(doc, "3.5. Tầng kho dữ liệu Hive")
    body(doc, "Hive được khởi tạo bằng một script SQL duy nhất (hive_init.sql) để bảo đảm mọi môi trường có cùng lược "
         "đồ. Script tạo database arxiv_db, bốn bảng external (lịch sử, streaming, từ khóa và bảng cách ly "
         "arxiv_stream_rejects) và ba view. Mỗi lần khởi tạo, bảng "
         "được xóa và tạo lại nhưng dữ liệu trên HDFS không bị ảnh hưởng vì là external table.")
    body(doc, "Một lỗi logic đã được phát hiện: thứ tự cột trong DDL của arxiv_stream không khớp thứ tự cột trong tệp "
         "Parquet do Spark ghi ra. Hive đọc Parquet theo tên nên kết quả vẫn đúng, nhưng điều này tiềm ẩn rủi ro khi "
         "đọc bằng công cụ khác hoặc khi tạo bảng mới. DDL đã được sắp xếp lại đúng thứ tự: id, title, authors, "
         "categories, abstract, submitted_at, timestamp, year, primary_category, main_group, clean_abstract, "
         "abstract_tokens, processed_time.")
    body(doc, "Bảng arxiv_historical có 704.329 dòng sau khi MSCK REPAIR, đủ mười partition year=2007 đến year=2016. "
         "Bảng arxiv_stream có 57 sự kiện và 34 bài duy nhất tại thời điểm kiểm chứng, thuộc ba nhóm ngành physics, "
         "math và cs.")

    h2(doc, "3.6. Dashboard Streamlit")
    body(doc, "Dashboard gồm năm tab, mỗi tab tương ứng một phần của câu chuyện demo. Thanh điều hướng được thiết kế "
         "thành một khối segmented liền mạch: các mục phẳng trên nền trắng, mục đang chọn tô màu xanh đặc, không "
         "dùng hiệu ứng phát sáng. Cách thiết kế này tránh cảm giác “các nút rời rạc” và giữ được sự nhất quán với "
         "hệ thống màu sáng của toàn dashboard.")
    for text in [
        "Tổng quan: bốn thẻ chỉ số (704.329 bài, giai đoạn 2007–2016, 8 nhóm ngành, 10 chủ đề LDA), biểu đồ tăng trưởng "
        "theo năm, cơ cấu nhóm ngành và ba điểm chính để trình bày.",
        "Gửi dữ liệu: form gửi một bài báo mới vào Kafka, nút phát lại hàng loạt từ Parquet và nhật ký phiên hiện tại. "
        "Mỗi sự kiện ghi lại partition, offset và trạng thái ACK.",
        "Xử lý & HDFS: sơ đồ bốn bước của consumer, lệnh khởi động và trình duyệt HDFS có phân trang, hiển thị tên, "
        "loại, kích thước, thời gian sửa và quyền.",
        "Hive SQL: tám mẫu truy vấn dựng sẵn, ô soạn SQL, nút MSCK REPAIR, bảng kết quả và xuất CSV.",
        "Kiến trúc: sơ đồ luồng Kafka → Spark → HDFS → Hive → Dashboard, trạng thái bốn dịch vụ và bảng thành phần.",
    ]:
        bullet(doc, text)
    body(doc, "Dashboard hỗ trợ deep link qua query string: ?tab=overview, ?tab=ingest, ?tab=pipeline, ?tab=hive, "
         "?tab=architecture; và ?tab=hive&q=7&auto=1 để mở đúng mẫu truy vấn và chạy một lần. Tính năng này dùng cho "
         "demo và cho việc chụp ảnh báo cáo một cách tái lập.")
    figure(doc, "ui_pipeline.png", "Hình 3.2. Sơ đồ luồng dữ liệu của dashboard", 15.2)

    h2(doc, "3.7. Các lỗi logic phát hiện khi kiểm thử và cách khắc phục")
    body(doc, "Trong quá trình kiểm thử end-to-end, bảy lỗi logic đã được phát hiện. Điểm chung của chúng là chỉ xuất "
         "hiện khi chạy thật, không thể thấy bằng cách đọc mã nguồn một lần. Bảng 3.4 ghi lại từng lỗi, hệ quả và "
         "cách sửa đã áp dụng.")
    table(doc, "Bảng 3.4. Các lỗi logic phát hiện khi kiểm thử và cách khắc phục",
          ["STT", "Lỗi", "Hệ quả", "Cách khắc phục"],
          [("1", "Lệnh all không chạy sync-hdfs", "HDFS và Hive giữ dữ liệu cũ dù người dùng tưởng đã cập nhật",
            "Đổi điều kiện thành args.stage in (\"sync-hdfs\", \"all\")"),
           ("2", "Consumer dùng raise_error", "Một bản ghi lỗi làm consumer crash-loop mãi mãi",
            "Chuyển sang foreachBatch, tách nhánh hợp lệ và nhánh lỗi"),
           ("3", "Thiếu vùng cách ly", "Bản ghi lỗi bị mất, không điều tra được", "Ghi vào /data/arxiv_stream_rejects_v2 kèm reject_reason"),
           ("4", "DDL arxiv_stream sai thứ tự cột", "Đúng khi đọc bằng Hive, sai khi đọc bằng công cụ khác",
            "Sắp xếp lại cột đúng thứ tự Parquet"),
           ("5", "Mẫu truy vấn 2 dùng scalar subquery", "Hive 2.3.2 báo lỗi, tab Hive SQL không trả kết quả",
            "Thay bằng window function SUM(paper_count) OVER ()"),
           ("6", "Insight “năm chưa kết thúc” cho 2016", "Giải thích sai bản chất dữ liệu",
            "Đổi thành giải thích theo phạm vi dữ liệu dừng ở 2016"),
           ("7", "Form chỉ lấy chuyên ngành đầu tiên", "Mất các chuyên ngành phụ khi gửi bài",
            "Giữ toàn bộ danh sách trước dấu ngoặc")],
          [1.2, 4.3, 5.1, 4.9], numeric=(0,))
    body(doc, "Ngoài bảy lỗi trên, giao diện điều hướng cũng được thiết kế lại. Phiên bản đầu dùng các nút nổi có viền "
         "và quầng sáng cho mục đang chọn, tạo cảm giác không đồng bộ với các thẻ chỉ số phẳng. Phiên bản hiện tại "
         "dùng một thanh segmented duy nhất, mục đang chọn là một khối màu xanh đặc — cùng ngôn ngữ thiết kế với "
         "phần còn lại của dashboard.")
    body(doc, "Khi soát lại giao diện bằng cách đo trực tiếp trên trình duyệt, hai lỗi hiển thị đã được phát hiện và "
         "sửa. Thứ nhất, Streamlit gán margin-bottom âm cho khối chữ bên trong nút, đẩy chữ xuống sát đáy nút; lỗi "
         "này không thấy được bằng mắt thường ở một số kích thước màn hình. Cách sửa là đặt chiều cao nút cố định "
         "38 px, căn giữa bằng flex và đưa margin, padding của khối chữ về 0. Thứ hai, bấm tab chỉ đổi nội dung mà "
         "không cập nhật tham số ?tab= trên URL, nên không thể chia sẻ liên kết tới một tab và nút Back của trình "
         "duyệt không hoạt động. Dashboard nay đồng bộ hai chiều: bấm tab ghi ?tab= vào URL, còn khi URL đổi từ bên "
         "ngoài (deep link hoặc Back) thì segmented control theo đúng tab đó. Thanh điều hướng cũng được kiểm tra ở "
         "các độ rộng 390–1920 px và luôn giữ một hàng.")

    h2(doc, "3.8. Kết chương")
    body(doc, "Chương này đã trình bày kiến trúc bốn tầng, cách tổ chức mã nguồn, môi trường 12 container, ba giai đoạn "
         "batch, luồng streaming có checkpoint và vùng cách ly, tầng kho dữ liệu Hive và dashboard năm tab. Đặc biệt, "
         "bảy lỗi logic phát hiện khi kiểm thử đã được ghi lại kèm cách khắc phục, làm cơ sở cho phần kiểm chứng ở "
         "Chương 5.")


def chapter4(doc):
    h1(doc, "CHƯƠNG 4: KẾT QUẢ THỰC NGHIỆM")
    h2(doc, "4.1. Tổng quan lần chạy")
    body(doc, "Lần chạy được báo cáo có mã 492bef9d-74a6-4f51-9298-a46f7b35b300, thực hiện trên Spark 3.5.3 ở chế độ "
         "local[*]. Toàn bộ số liệu dưới đây được đọc trực tiếp từ manifest và từ Hive, không nhập tay.")
    table(doc, "Bảng 4.1. Tổng quan lần chạy thực nghiệm",
          ["Chỉ tiêu", "Giá trị"],
          [("Số shard đầu vào", "2"),
           ("Dung lượng đầu vào", "543,0 MiB (569.398.929 byte)"),
           ("Dung lượng trên HDFS (dữ liệu sạch)", "615,6 MB"),
           ("Bản ghi thô", "704.329"),
           ("Bản ghi sạch", "704.329"),
           ("Bản ghi bị loại", "0"),
           ("Khoảng năm", "2007–2016"),
           ("Số nhóm ngành", "8"),
           ("Số bài có năm v1 khác năm mã", "2.323"),
           ("Thời gian tiền xử lý", "129,90 giây"),
           ("Thời gian phân tích", "464,69 giây"),
           ("Mô hình LDA", "K=10, từ điển 10.000, log-perplexity 7,7619")],
          [7.5, 8.0])

    h2(doc, "4.2. Tăng trưởng theo năm")
    body(doc, "Số bài tăng đều từ 2008 đến 2015, từ 58.810 lên 104.991 bài, tương đương mức tăng 78,5% trong bảy năm "
         "hay tốc độ tăng trưởng kép 8,6%/năm. Năm 2007 và 2016 là hai năm biên: 2007 thấp vì dữ liệu chỉ bắt đầu từ "
         "tháng 4, còn 2016 chỉ có 12.153 bài vì phạm vi trích xuất dừng giữa năm. Vì vậy, mức giảm −88,4% của năm "
         "2016 phản ánh giới hạn dữ liệu, không phải xu hướng suy giảm của ngành.")
    table(doc, "Bảng 4.2. Số bài và tăng trưởng theo năm",
          ["Năm", "Số bài", "Tăng trưởng so với năm trước (%)"],
          [("2007", "42.576", "—"), ("2008", "58.810", "38,1"), ("2009", "64.071", "8,9"),
           ("2010", "70.288", "9,7"), ("2011", "76.602", "9,0"), ("2012", "84.374", "10,1"),
           ("2013", "92.875", "10,1"), ("2014", "97.589", "5,1"), ("2015", "104.991", "7,6"),
           ("2016", "12.153", "−88,4")],
          [3.4, 4.4, 7.7], numeric=(0, 1, 2))
    figure(doc, "01_yearly_growth.png", "Hình 4.1. Số bài báo theo năm nộp (2007–2016)", 15.0)

    h2(doc, "4.3. Cơ cấu nhóm ngành")
    body(doc, "Vật lý chiếm ưu thế tuyệt đối với 433.867 bài (61,6%), tiếp theo là toán 167.901 bài (23,8%) và khoa "
         "học máy tính 78.553 bài (11,2%). Ba nhóm này chiếm 96,6% toàn bộ dữ liệu. Các nhóm còn lại đều dưới 2%. "
         "Sự chênh lệch này phản ánh lịch sử của arXiv — kho dữ liệu vốn bắt đầu từ vật lý và toán — chứ không phải "
         "mức độ quan tâm hiện tại của từng ngành.")
    table(doc, "Bảng 4.3. Cơ cấu tám nhóm ngành",
          ["Nhóm", "Số bài", "Tỷ lệ (%)", "Tác giả/bài", "Độ dài tóm tắt (ký tự)"],
          [("physics", "433.867", "61,6", "5,52", "936"),
           ("math", "167.901", "23,8", "1,92", "628"),
           ("cs", "78.553", "11,2", "2,82", "989"),
           ("stat", "10.546", "1,5", "2,70", "1.008"),
           ("q-bio", "9.211", "1,3", "3,29", "1.151"),
           ("q-fin", "4.237", "0,6", "2,26", "884"),
           ("eess", "9", "0,0", "3,00", "903"),
           ("econ", "5", "0,0", "1,80", "1.342")],
          [2.7, 3.2, 2.7, 3.2, 3.7], numeric=(1, 2, 3, 4))
    body(doc, "Một quan sát đáng chú ý: số tác giả trung bình mỗi bài của vật lý là 5,52, cao gấp gần ba lần toán "
         "(1,92). Đây là đặc trưng của nghiên cứu thực nghiệm vật lý, nơi các bài báo thường có hàng trăm tác giả "
         "trong các hợp tác lớn như CMS hay ATLAS. Độ dài tóm tắt cũng khác nhau rõ rệt: q-bio có tóm tắt dài nhất "
         "(1.151 ký tự), toán ngắn nhất (628 ký tự).")
    figure(doc, "07_field_distribution.png", "Hình 4.2. Cơ cấu bài báo theo tám nhóm ngành", 14.6)
    figure(doc, "02_field_trends.png", "Hình 4.3. Xu hướng số bài theo nhóm ngành", 15.0)

    h2(doc, "4.4. Chuyên ngành hàng đầu")
    body(doc, "Ở mức chuyên ngành, vật lý hạt nhân và vật lý lượng tử dẫn đầu: hep-ph có 39.691 bài, quant-ph có "
         "32.812 bài, hep-th có 30.459 bài. Điều này nhất quán với cơ cấu nhóm ngành và cho thấy vật lý không chỉ "
         "đông về số bài mà còn tập trung vào một số chuyên ngành lớn.")
    table(doc, "Bảng 4.4. Mười chuyên ngành hàng đầu",
          ["Hạng", "Chuyên ngành", "Số bài"],
          [("1", "hep-ph", "39.691"), ("2", "quant-ph", "32.812"), ("3", "hep-th", "30.459"),
           ("4", "astro-ph.CO", "23.606"), ("5", "cond-mat.mes-hall", "23.422"),
           ("6", "astro-ph.SR", "20.290"), ("7", "cond-mat.mtrl-sci", "19.308"),
           ("8", "gr-qc", "19.287"), ("9", "astro-ph", "17.812"), ("10", "cond-mat.str-el", "16.194")],
          [2.0, 7.5, 6.0], numeric=(0, 2))
    figure(doc, "03_top_categories.png", "Hình 4.4. Mười chuyên ngành có nhiều bài nhất", 15.0)
    figure(doc, "04_heatmap.png", "Hình 4.5. Bản đồ nhiệt số bài theo năm và nhóm ngành", 15.0)

    h2(doc, "4.5. Từ khóa công nghệ")
    body(doc, "Bảng 4.5 chuẩn hóa số bài chứa từ khóa trên 1.000 bài của năm 2015 để so sánh được giữa các từ có tần "
         "suất rất khác nhau. quantum dẫn đầu với 98,33 bài trên 1.000 bài — gần 10% số bài năm 2015 có nhắc tới "
         "quantum. graph đứng thứ hai với 32,92, tiếp theo là diffusion 17,28, neural 14,02 và attention 13,98. "
         "transformer chỉ đạt 0,27, phản ánh đúng thời điểm: năm 2015 bài báo về kiến trúc này còn rất ít.")
    table(doc, "Bảng 4.5. Từ khóa công nghệ trên 1.000 bài năm 2015",
          ["Từ khóa", "Số bài chứa", "Trên 1.000 bài"],
          [("quantum", "10.324", "98,33"), ("graph", "3.456", "32,92"),
           ("diffusion", "1.814", "17,28"), ("neural", "1.472", "14,02"),
           ("attention", "1.468", "13,98"), ("transformer", "28", "0,27")],
          [4.6, 5.4, 5.5], numeric=(1, 2))
    figure(doc, "05_keyword_trends.png", "Hình 4.6. Xu hướng các từ khóa công nghệ", 15.0)
    figure(doc, "06_wordclouds.png", "Hình 4.7. Đám mây từ khóa theo nhóm ngành", 14.6)

    h2(doc, "4.6. Tác giả và hợp tác")
    body(doc, "Thống kê theo tên trong trường tác giả cho thấy các tên phổ biến như Y. Zhang (715 bài) hay Y. Li "
         "(539 bài) đứng đầu, nhưng cần đọc cẩn thận: đây là số bài gắn với một chuỗi tên, không phải số bài của "
         "một người sau khi phân giải thực thể. Các hợp tác lớn như CMS Collaboration (470) và ATLAS Collaboration "
         "(457) cũng xuất hiện như một “tác giả” vì dữ liệu ghi tên nhóm trong trường authors.")
    table(doc, "Bảng 4.6. Mười lăm tác giả có nhiều bài nhất",
          ["Hạng", "Tác giả", "Số bài"],
          [("1", "Y. Zhang", "715"), ("2", "Y. Li", "539"), ("3", "L. Zhang", "482"),
           ("4", "CMS Collaboration", "470"), ("5", "ATLAS Collaboration", "457"),
           ("6", "J. Wang", "451"), ("7", "Y. Gao", "444"), ("8", "S. Eidelman", "438"),
           ("9", "O. Schneider", "430"), ("10", "S. Ricciardi", "428"),
           ("11", "J. Anderson", "417"), ("12", "P. Krokovny", "413"),
           ("13", "A. Bondar", "406"), ("14", "M. Shapkin", "388"), ("15", "T. Shears", "370")],
          [2.0, 7.5, 6.0], numeric=(0, 2))
    figure(doc, "09_top_authors.png", "Hình 4.8. Mười lăm tác giả có nhiều bài nhất", 15.0)
    figure(doc, "08_author_collaboration_trend.png", "Hình 4.9. Xu hướng hợp tác tác giả", 15.0)

    h2(doc, "4.7. Mô hình chủ đề LDA")
    body(doc, "LDA với 10 chủ đề tách được các cụm ngữ nghĩa khá rõ: chủ đề 4 tập trung vào sao và quan sát thiên văn "
         "(stars, emission, x-ray), chủ đề 3 vào vật lý lượng tử và từ tính (quantum, phase, magnetic), chủ đề 8 vào "
         "thiên hà (galaxies, cluster, redshift). Hai chủ đề lớn nhất (T1 và T2, mỗi chủ đề gần 19%) là các chủ đề "
         "phương pháp luận chung, phản ánh việc mô hình chưa tách hoàn toàn ngôn ngữ học thuật phổ biến khỏi nội dung "
         "chuyên ngành.")
    table(doc, "Bảng 4.7. Mười chủ đề LDA",
          ["Chủ đề", "Thuật ngữ đại diện", "Tỷ lệ (%)"],
          [("T0", "model, higgs, channel, new, standard", "3,83"),
           ("T1", "model, data, paper, algorithm, problem", "18,58"),
           ("T2", "show, space, group, also, paper", "18,85"),
           ("T3", "quantum, phase, magnetic, state, states", "13,69"),
           ("T4", "stars, star, emission, observations, x-ray", "7,77"),
           ("T5", "equation, theory, model, equations, quantum", "13,99"),
           ("T6", "alpha, lambda, gamma, graph, delta", "5,51"),
           ("T7", "field, magnetic, model, matter, dark", "5,46"),
           ("T8", "galaxies, galaxy, mass, cluster, clusters", "3,72"),
           ("T9", "data, energy, results, model, using", "8,59")],
          [2.2, 9.8, 3.5], numeric=(0, 2))
    figure(doc, "12_lda_topic_bubble.png", "Hình 4.10. Mười chủ đề LDA và tỷ lệ xuất hiện", 14.6)

    h2(doc, "4.8. Kiểm định ngoại suy")
    body(doc, "Bốn từ khóa được kiểm định trên giai đoạn 2013–2015 với mô hình huấn luyện đến hết 2012. Cả bốn đều "
         "vượt baseline, tức là đường xu hướng tuyến tính dự báo tốt hơn việc giữ nguyên giá trị năm cuối. Mức cải "
         "thiện lớn nhất thuộc về quantum (MAE 0,813 so với 4,029) và attention (0,418 so với 1,877).")
    table(doc, "Bảng 4.8. Kết quả kiểm định ngoại suy",
          ["Từ khóa", "MAE mô hình", "MAE baseline", "Kết luận"],
          [("transformer", "0,069", "0,091", "Chấp nhận"),
           ("attention", "0,418", "1,877", "Chấp nhận"),
           ("diffusion", "0,237", "0,910", "Chấp nhận"),
           ("quantum", "0,813", "4,029", "Chấp nhận")],
          [4.3, 3.7, 3.7, 3.8], numeric=(1, 2))
    figure(doc, "10_validated_trend.png", "Hình 4.11. Kiểm định ngoại suy xu hướng từ khóa", 15.0)
    figure(doc, "11_field_radar_comparison.png", "Hình 4.12. So sánh các nhóm ngành theo bốn chỉ số", 14.6)

    h2(doc, "4.9. Kết quả streaming")
    body(doc, "Tại thời điểm kiểm chứng, bảng arxiv_stream có 57 sự kiện và 34 bài duy nhất, thuộc ba nhóm ngành. "
         "Chênh lệch giữa số sự kiện và số bài là do cùng một bài có thể được phát lại nhiều lần — đây là hành vi "
         "đúng của một luồng sự kiện, và vì vậy mọi báo cáo phải dùng COUNT(DISTINCT id) khi muốn đếm số bài. "
         "Ngoài ra, vùng cách ly ghi nhận một bản ghi lỗi với lý do missing_required_field, chứng minh cơ chế "
         "cách ly hoạt động trong thực tế.")
    table(doc, "Bảng 4.9. Sự kiện streaming theo nhóm ngành",
          ["Nhóm ngành", "Số sự kiện", "Số bài duy nhất"],
          [("physics", "29", "18"), ("math", "21", "12"), ("cs", "7", "4"),
           ("Tổng", "57", "34")],
          [5.2, 5.0, 5.3], numeric=(1, 2))

    h2(doc, "4.10. Hiệu năng")
    body(doc, "Tổng thời gian xử lý batch là 594,59 giây, tức khoảng 9,9 phút cho 704.329 bài. Tính theo số dòng, "
         "bước tiền xử lý đạt khoảng 5.421 dòng/giây; bước phân tích chậm hơn nhiều vì phải quét toàn bộ tóm tắt "
         "cho thống kê từ khóa (110,13 giây) và huấn luyện LDA (280,18 giây). Trên một máy cá nhân chạy 12 container, "
         "con số này là chấp nhận được cho mục đích học tập và demo.")
    body(doc, "Thời gian streaming phụ thuộc vào kích thước micro-batch. Với trigger 5 giây, một micro-batch chứa vài "
         "chục bản ghi được xử lý trong khoảng 1–3 giây, bao gồm cả thời gian ghi Parquet và cập nhật checkpoint.")

    h2(doc, "4.11. Kết chương")
    body(doc, "Chương này đã trình bày kết quả thực nghiệm: quy mô dữ liệu, tăng trưởng theo năm, cơ cấu ngành, "
         "chuyên ngành hàng đầu, từ khóa, tác giả, chủ đề LDA, kiểm định ngoại suy và kết quả streaming. Các con số "
         "đều gắn với mã lần chạy và có thể kiểm chứng lại. Chương 5 trình bày quy trình kiểm chứng end-to-end, "
         "đánh giá ưu nhược điểm và hướng phát triển.")


def chapter5(doc):
    h1(doc, "CHƯƠNG 5: KIỂM CHỨNG, ĐÁNH GIÁ VÀ HẠN CHẾ")
    h2(doc, "5.1. Quy trình kiểm chứng end-to-end")
    body(doc, "Sau khi sửa bảy lỗi logic, hệ thống được kiểm chứng lại theo một quy trình sáu bước, chạy trên đúng "
         "môi trường Docker của báo cáo:")
    for text in [
        "Khởi động lại toàn bộ 12 container và xác nhận bốn dịch vụ Kafka, HDFS, Hive, Spark đều ONLINE.",
        "Chạy lại preprocess và analyze, đối chiếu số dòng, khoảng năm và mã lần chạy trong manifest.",
        "Tạo lại bảng Hive từ hive_init.sql, chạy MSCK REPAIR và kiểm tra số dòng của arxiv_historical và arxiv_stream.",
        "Chạy lần lượt tám mẫu truy vấn trên dashboard để chắc chắn không còn lỗi SQL.",
        "Gửi một bản ghi hợp lệ qua producer và một bản ghi lỗi trực tiếp vào Kafka; kiểm tra bản ghi hợp lệ vào Hive, "
        "bản ghi lỗi vào vùng cách ly và consumer vẫn chạy.",
        "Mở cả năm tab, kiểm tra console trình duyệt không có lỗi và chụp ảnh giao diện cho báo cáo.",
    ]:
        bullet(doc, text)

    h2(doc, "5.2. Kết quả kiểm chứng")
    body(doc, "Bảng 5.1 tóm tắt từng hạng mục kiểm chứng và kết quả thực tế. Mọi hạng mục đều đạt.")
    table(doc, "Bảng 5.1. Danh mục kiểm chứng end-to-end",
          ["Hạng mục", "Cách kiểm chứng", "Kết quả"],
          [("Dữ liệu batch", "Đọc manifest và đếm lại bằng Spark", "704.329 dòng, 2007–2016, 8 nhóm"),
           ("Partition HDFS", "Duyệt /data/arxiv_clean_v2", "Đủ 10 partition year=2007..2016 và _SUCCESS"),
           ("Bảng Hive lịch sử", "SELECT COUNT(*) FROM arxiv_historical", "704.329"),
           ("Bảng Hive streaming", "COUNT(*) và COUNT(DISTINCT id)", "57 sự kiện / 34 bài"),
           ("Mẫu truy vấn 1–8", "Chạy trên dashboard", "8/8 trả kết quả, không lỗi SQL"),
           ("Gửi bản ghi hợp lệ", "Producer + chờ micro-batch", "Xuất hiện trong arxiv_stream"),
           ("Gửi bản ghi lỗi", "Gửi trực tiếp vào Kafka", "Vào vùng cách ly, consumer vẫn chạy"),
           ("Bảng cách ly", "SELECT * FROM arxiv_stream_rejects", "1 bản ghi, reason=missing_required_field"),
           ("Consumer sau bản ghi lỗi", "docker compose ps", "Vẫn Up, không crash-loop"),
           ("Năm tab + URL", "Bấm tab, deep link, nút Back", "URL ?tab= đúng, 5/5 tab, 0 lỗi console"),
           ("Trạng thái dịch vụ", "Sidebar dashboard", "4/4 ONLINE")],
          [3.8, 6.0, 5.7])

    h2(doc, "5.3. Giao diện dashboard")
    body(doc, "Năm ảnh dưới đây được chụp từ chính hệ thống đang chạy, không phải ảnh dựng. Giao diện dùng theme sáng, "
         "màu nhấn xanh #1a6cf0, logo CogAI Lab và thanh điều hướng segmented liền khối.")
    figure(doc, "ui_overview.png", "Hình 5.1. Tab Tổng quan của dashboard", 15.2)
    figure(doc, "ui_ingest.png", "Hình 5.2. Tab Gửi dữ liệu – Kafka Ingestion Studio", 15.2)
    figure(doc, "ui_hive_q7.png", "Hình 5.3. Kết quả mẫu truy vấn 7 – so sánh raw, clean và tokens", 15.2)
    figure(doc, "ui_hive_q8.png", "Hình 5.4. Kết quả mẫu truy vấn 8 – phân bố sự kiện theo nhóm ngành", 15.2)
    figure(doc, "ui_architecture.png", "Hình 5.5. Tab Kiến trúc – sơ đồ luồng và trạng thái dịch vụ", 15.2)

    h2(doc, "5.4. Đánh giá ưu điểm")
    for text in [
        "Tính nhất quán: batch và streaming dùng chung data contract, nên cùng một bài báo được xử lý giống nhau ở cả "
        "hai đường. Đây là điểm thường bị bỏ qua khi xây dựng hai pipeline riêng.",
        "Tính tái lập: manifest ghi mã lần chạy, số dòng, thời gian và mã băm của shard; mọi con số trong báo cáo đều "
        "truy vết được.",
        "Khả năng chịu lỗi: checkpoint giữ tiến độ, vùng cách ly giữ bản ghi xấu, consumer không bao giờ rơi vào vòng "
        "lặp crash vì một bản ghi.",
        "Kiến trúc rõ ràng: bốn tầng tách biệt, mỗi tầng có hợp đồng dữ liệu riêng, dễ thay thế hoặc mở rộng.",
        "Demo trực quan: dashboard năm tab cho phép trình bày cả kết quả phân tích lẫn hoạt động vận hành trong cùng "
        "một giao diện.",
    ]:
        bullet(doc, text)

    h2(doc, "5.5. Hạn chế")
    for text in [
        "Phạm vi dữ liệu: chỉ hai shard, không đại diện cho toàn bộ arXiv; các kết luận về xu hướng chỉ đúng trong "
        "phạm vi 2007–2016 đã tải.",
        "Phân giải tác giả: thống kê theo chuỗi tên, chưa phân giải thực thể, nên các tên phổ biến bị cộng gộp và "
        "các hợp tác lớn được tính như một tác giả.",
        "Từ khóa cố định: danh sách 16 từ khóa được chọn trước, chưa phát hiện cụm từ mới hay từ đồng nghĩa.",
        "LDA lấy mẫu: huấn luyện trên 200.181 bài thay vì toàn bộ, nên chủ đề có thể bỏ sót các cụm nhỏ.",
        "Hiệu năng: các phép đo chịu ảnh hưởng của việc 12 container chia sẻ tài nguyên một máy, không phải benchmark "
        "của cụm thật.",
        "Luồng streaming: số sự kiện còn nhỏ (57), chưa kiểm tra được hành vi dưới tải cao hoặc khi Kafka mất "
        "partition.",
    ]:
        bullet(doc, text)

    h2(doc, "5.6. Hướng phát triển")
    for text in [
        "Mở rộng phạm vi sang toàn bộ arXiv hoặc nhiều shard hơn, chạy trên cụm nhiều máy để đánh giá khả năng mở rộng "
        "thực sự.",
        "Bổ sung phân giải thực thể tác giả (author disambiguation) để thống kê theo người thay vì theo chuỗi tên.",
        "Thay danh sách từ khóa cố định bằng cụm từ phát hiện tự động (n-gram, topic model động theo thời gian).",
        "Thêm job streaming thứ hai để tính chỉ số theo cửa sổ thời gian và hợp nhất với kết quả batch trong một bảng "
        "serving duy nhất.",
        "Bổ sung kiểm thử tự động cho data contract và các mẫu truy vấn Hive, chạy trong CI trước khi cập nhật "
        "dashboard.",
        "Đóng gói dashboard và pipeline thành một lệnh duy nhất, kèm healthcheck và cảnh báo khi consumer dừng.",
    ]:
        bullet(doc, text)

    h2(doc, "5.7. Kết chương")
    body(doc, "Chương này đã trình bày quy trình kiểm chứng sáu bước, kết quả kiểm chứng mười hạng mục, ảnh giao diện "
         "thực tế, cùng đánh giá ưu điểm, hạn chế và hướng phát triển. Các kết quả này khẳng định hệ thống không chỉ "
         "chạy đúng trên giấy mà đã được kiểm tra end-to-end trên môi trường thật.")


def conclusion(doc):
    h1(doc, "KẾT LUẬN")
    h2(doc, "Kết quả đạt được")
    body(doc, "Đề tài đã xây dựng được một hệ thống phân tích dữ liệu lớn hoàn chỉnh cho metadata bài báo khoa học "
         "arXiv, gồm cả nhánh batch và nhánh streaming, với các kết quả định lượng cụ thể:")
    for text in [
        "Xử lý 704.329 bài báo từ 543,0 MiB dữ liệu thô, làm sạch không loại bản ghi nào, ghi 615,6 MB Parquet phân "
        "vùng lên HDFS.",
        "Sinh chín bảng phân tích, 12 biểu đồ và một mô hình LDA 10 chủ đề với log-perplexity kiểm định 7,7619.",
        "Xây dựng luồng streaming Kafka → Spark → HDFS với checkpoint và vùng cách ly, đã kiểm chứng bằng cả bản ghi "
        "hợp lệ lẫn bản ghi lỗi.",
        "Tạo kho dữ liệu Hive với hai bảng external, một bảng từ khóa và ba view; dashboard năm tab chạy ổn định với "
        "bốn dịch vụ ONLINE.",
        "Phát hiện và sửa bảy lỗi logic, trong đó có hai lỗi nghiêm trọng: lệnh all không đồng bộ HDFS và consumer "
        "crash-loop khi gặp bản ghi lỗi.",
    ]:
        bullet(doc, text)
    h2(doc, "Hạn chế của nghiên cứu")
    body(doc, "Hạn chế lớn nhất là phạm vi dữ liệu: hai shard không đại diện cho toàn bộ arXiv, nên các kết luận về "
         "xu hướng chỉ có giá trị trong khoảng 2007–2016 đã tải. Bên cạnh đó, thống kê tác giả chưa phân giải thực "
         "thể, danh sách từ khóa cố định và LDA huấn luyện trên mẫu là những điểm cần cải thiện nếu muốn mở rộng "
         "quy mô.")
    h2(doc, "Hướng phát triển trong tương lai")
    body(doc, "Trong thời gian tới, hệ thống có thể được mở rộng theo ba hướng: tăng quy mô dữ liệu và chạy trên cụm "
         "nhiều máy; bổ sung phân giải thực thể và phát hiện cụm từ tự động; và tự động hóa kiểm thử, giám sát để "
         "hệ thống có thể vận hành liên tục mà không cần thao tác thủ công.")


def references(doc):
    h1(doc, "TÀI LIỆU THAM KHẢO")
    refs = [
        "[1] arXiv. arXiv.org e-Print archive. https://arxiv.org (truy cập 11/11/2026).",
        "[2] VatsaDev. test_arxiv [Data set]. Hugging Face, revision adef1f1e891574774660683f0f4548e50f5d551f. "
        "https://huggingface.co/datasets/VatsaDev/test_arxiv",
        "[3] K. Shvachko, H. Kuang, S. Radia, R. Chansler. The Hadoop Distributed File System. Proc. MSST, 2010.",
        "[4] M. Zaharia, M. Chowdhury, T. Das, A. Dave, J. Ma, M. McCauley, M. Franklin, S. Shenker, I. Stoica. "
        "Resilient Distributed Datasets: A Fault-Tolerant Abstraction for In-Memory Cluster Computing. Proc. NSDI, 2012.",
        "[5] J. Kreps, N. Narkhede, J. Rao. Kafka: a Distributed Messaging System for Log Processing. Proc. NetDB, 2011.",
        "[6] A. Thusoo, J. S. Sarma, N. Jain, Z. Shao, P. Chakka, S. Anthony, H. Liu, P. Wyckoff, R. Murthy. "
        "Hive – A Warehousing Solution over a Map-Reduce Framework. Proc. VLDB, 2009.",
        "[7] D. M. Blei, A. Y. Ng, M. I. Jordan. Latent Dirichlet Allocation. Journal of Machine Learning Research, "
        "3:993–1022, 2003.",
        "[8] Apache Software Foundation. Apache Spark 3.5.3 Documentation. https://spark.apache.org/docs/3.5.3/",
        "[9] Apache Software Foundation. Apache Hive Language Manual. https://cwiki.apache.org/confluence/display/Hive",
        "[10] Apache Parquet. Parquet File Format. https://parquet.apache.org/docs/",
        "[11] N. Marz, J. Warren. Big Data: Principles and Best Practices of Scalable Realtime Data Systems. "
        "Manning, 2015.",
        "[12] Streamlit. Streamlit Documentation. https://docs.streamlit.io",
        "[13] Docker Inc. Docker Compose Documentation. https://docs.docker.com/compose/",
    ]
    for ref in refs:
        p = add_para(doc, ref, style="Normal", space_after=6,
                     left_indent=1.0, first_line_indent=-1.0)


def appendix(doc):
    h1(doc, "PHỤ LỤC A: CÁCH CHẠY LẠI PIPELINE")
    body(doc, "Toàn bộ hệ thống chạy bằng Docker Compose. Các lệnh dưới đây được chạy tại thư mục gốc của dự án.")
    code_block(doc, """
# 1. Dựng cụm 12 dịch vụ
docker compose up -d

# 2. Tiền xử lý + phân tích + đồng bộ HDFS (lệnh all đã bao gồm sync-hdfs)
docker compose exec spark-jupyter python src/batch_pipeline.py all

# 3. Sinh biểu đồ
docker compose exec spark-jupyter python src/visualization.py

# 4. Khởi tạo Hive và làm mới partition
docker compose exec dashboard python /app/src/hive_client.py
docker compose exec dashboard python -c "import sys; sys.path.insert(0,'/app/src'); from hive_client import refresh_all_partitions; print(refresh_all_partitions())"

# 5. Streaming
docker compose --profile streaming up -d streaming-consumer

# 6. Dashboard
docker compose restart dashboard
# mở http://localhost:8501
""")

    h1(doc, "PHỤ LỤC B: CẤU TRÚC THƯ MỤC")
    code_block(doc, """
BigData/
├── docker-compose.yml          # 12 dịch vụ
├── Dockerfile, Dockerfile.dashboard
├── data/
│   ├── arxiv_data.parquet      # dữ liệu thô (2 shard)
│   ├── arxiv_clean.parquet     # dữ liệu sạch
│   ├── source_manifest.json    # revision, SHA-256
│   └── clean_manifest.json     # số dòng, thời gian, mã lần chạy
├── src/
│   ├── project_config.py
│   ├── data_contract.py
│   ├── spark_common.py
│   ├── batch_pipeline.py
│   ├── visualization.py
│   ├── kafka_producer.py
│   ├── spark_streaming_consumer.py
│   ├── hive_client.py
│   ├── hive_init.sql
│   ├── hdfs_helper.py
│   ├── dashboard_app.py
│   └── dashboard_theme.css
├── notebooks/                  # 00..07
├── scripts/                    # dựng báo cáo, kiểm chứng
└── output/
    ├── analysis_results/       # manifest.json, topics.json
    ├── charts/                 # 12 biểu đồ PNG
    ├── screenshots/            # ảnh dashboard
    └── reports/                # báo cáo Word, PPT
""")

    h1(doc, "PHỤ LỤC C: TÁM MẪU TRUY VẤN HIVE")
    body(doc, "Dashboard cung cấp tám mẫu truy vấn dựng sẵn. Dưới đây là hai mẫu tiêu biểu.")
    code_block(doc, """
-- Mẫu 7: so sánh độ dài raw / clean và số token
SELECT id, main_group_clean, year,
       LENGTH(abstract)      AS raw_chars,
       LENGTH(clean_abstract) AS clean_chars,
       SIZE(abstract_tokens) AS token_count,
       processed_time
FROM arxiv_stream
ORDER BY processed_time DESC, id DESC
LIMIT 12;

-- Mẫu 8: phân bố sự kiện streaming theo nhóm ngành
SELECT main_group_clean,
       COUNT(*)                 AS events,
       COUNT(DISTINCT id)       AS papers,
       ROUND(AVG(SIZE(abstract_tokens)), 1) AS avg_tokens,
       ROUND(AVG(LENGTH(clean_abstract)), 0) AS avg_clean_chars
FROM arxiv_stream
GROUP BY main_group_clean
ORDER BY events DESC;
""")
    body(doc, "Lưu ý: với bảng arxiv_stream, số sự kiện và số bài là hai khái niệm khác nhau. Cùng một bài có thể "
         "được phát lại nhiều lần, nên khi báo cáo số bài phải dùng COUNT(DISTINCT id).")


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def build(pages=None):
    tmp = OUTPUT.with_suffix(".build.docx")
    shutil.copyfile(TEMPLATE, tmp)
    doc = Document(tmp)
    cover_paras = take_cover(doc)
    clear_body(doc)

    cover(doc, cover_paras)
    rest = doc.sections[1]
    section_headers(doc, doc.sections[0], rest)

    review_page(doc)
    declaration(doc)
    thanks(doc)
    toc_page(doc)
    glossary(doc)
    figures_index(doc, pages)
    tables_index(doc, pages)
    introduction(doc)
    chapter1(doc)
    chapter2(doc)
    chapter3(doc)
    chapter4(doc)
    chapter5(doc)
    conclusion(doc)
    references(doc)
    appendix(doc)

    doc.save(OUTPUT)
    tmp.unlink(missing_ok=True)
    print("saved", OUTPUT)


if __name__ == "__main__":
    pages = None
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        pages = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    build(pages)
