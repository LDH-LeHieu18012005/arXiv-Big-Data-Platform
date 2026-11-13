"""Cập nhật mục lục, đánh lại số trang và thu thập số trang của hình/bảng.

Dùng Microsoft Word (COM) để Word thực sự tính lại bố cục, cập nhật field TOC
và trả về số trang chính xác của từng caption (style HinhVe / Bang).

Cách dùng:
    python scripts/update_report_fields.py <docx> <pages.json> [out.pdf]

Kết quả: docx đã cập nhật field, pages.json chứa {caption: page}, PDF (tuỳ chọn).
"""
import json
import sys
from pathlib import Path

import win32com.client as win32
from pywintypes import com_error

WD_ACTIVE_END_PAGE_NUMBER = 3
WD_EXPORT_FORMAT_PDF = 17
WD_DO_NOT_SAVE_CHANGES = 0
WD_STATISTIC_PAGES = 2


def collect_pages(doc):
    pages = {}
    total = doc.Paragraphs.Count
    for i in range(1, total + 1):
        para = doc.Paragraphs(i)
        try:
            style = para.Style.NameLocal
        except com_error:
            continue
        if style not in ("HinhVe", "Bang"):
            continue
        text = para.Range.Text.replace("\r", "").replace("\x07", "").strip()
        if not text:
            continue
        page = para.Range.Information(WD_ACTIVE_END_PAGE_NUMBER)
        pages.setdefault(text, int(page))
    return pages


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    docx = Path(sys.argv[1]).resolve()
    pages_out = Path(sys.argv[2]).resolve()
    pdf_out = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else None

    word = win32.gencache.EnsureDispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = None
    try:
        doc = word.Documents.Open(str(docx), ReadOnly=False, AddToRecentFiles=False)
        # Cập nhật toàn bộ field, sau đó cập nhật riêng mục lục.
        try:
            doc.Fields.Update()
        except com_error as exc:
            print("Fields.Update warning:", exc, file=sys.stderr)
        for idx in range(1, doc.TablesOfContents.Count + 1):
            doc.TablesOfContents(idx).Update()
        doc.Repaginate()
        doc.Save()

        pages = collect_pages(doc)
        pages_out.write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")
        print("captions:", len(pages))
        print("pages:", doc.ComputeStatistics(WD_STATISTIC_PAGES))

        if pdf_out is not None:
            pdf_out.parent.mkdir(parents=True, exist_ok=True)
            doc.ExportAsFixedFormat(str(pdf_out), WD_EXPORT_FORMAT_PDF)
            print("pdf:", pdf_out)
    finally:
        if doc is not None:
            doc.Close(SaveChanges=WD_DO_NOT_SAVE_CHANGES)
        word.Quit()


if __name__ == "__main__":
    main()
