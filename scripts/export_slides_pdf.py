"""Export a PowerPoint deck to PDF (PowerPoint COM), then render slide PNGs."""
import sys
from pathlib import Path

import fitz
import win32com.client as win32

pptx = Path(sys.argv[1]).resolve()
pdf = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else pptx.with_suffix(".pdf")
out_dir = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else None

app = win32.gencache.EnsureDispatch("PowerPoint.Application")
app.Visible = True
presentation = None
try:
    presentation = app.Presentations.Open(str(pptx), WithWindow=False)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    presentation.SaveAs(str(pdf), 32)  # ppSaveAsPDF
finally:
    if presentation is not None:
        presentation.Close()
    app.Quit()

print("pdf:", pdf, pdf.stat().st_size)

if out_dir:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf)
    for index, page in enumerate(doc, 1):
        page.get_pixmap(dpi=110).save(str(out_dir / f"slide_{index:02d}.png"))
    print("pages:", doc.page_count, "->", out_dir)
