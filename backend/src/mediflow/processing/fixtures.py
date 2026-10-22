"""Supplemental development-only mixed/ten-page fixtures, outside frozen dataset v1."""

import io
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-untyped]
from PIL import Image
from reportlab.lib.utils import ImageReader  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]

LAB_LINES = (
    "SYNTHETIC LABORATORY REPORT - DEVELOPMENT ONLY",
    "Analyte       Result      Unit      Reference interval",
    "Glucose       90.00       mg/dL     70-100",
    "Sodium        140         mmol/L    135-145",
    "Collection date 2026-10-23",
    "Invented document for processing tests; no patient records.",
)


def _page(canvas: Canvas, number: int) -> None:
    canvas.setFont("Helvetica", 14)
    for index, line in enumerate((*LAB_LINES, f"Source page {number}")):
        canvas.drawString(30, 780 - index * 40, line)


def supplemental_pdf(
    *,
    pages: int = 1,
    scanned: bool = True,
    mixed: bool = False,
    overlay: bool = False,
    blank: bool = False,
) -> bytes:
    """Raster-only pages, alternating native/raster pages, or header over scan body."""
    original = io.BytesIO()
    canvas = Canvas(original, invariant=1)
    _page(canvas, 1)
    canvas.showPage()
    canvas.save()
    with pdfium.PdfDocument(original.getvalue()) as pdf:
        page = pdf[0]
        bitmap = page.render(scale=150 / 72)
        image = bitmap.to_pil().copy()
        bitmap.close()
        page.close()
    if blank:
        image.close()
        image = Image.new("RGB", (1241, 1754), "white")
    output = io.BytesIO()
    canvas = Canvas(output, invariant=1)
    for number in range(1, pages + 1):
        if not scanned or (mixed and number % 2):
            _page(canvas, number)
        else:
            canvas.drawImage(ImageReader(image), 0, 0, 595.2756, 841.8898)
            if overlay:
                canvas.setFont("Helvetica", 10)
                canvas.drawString(
                    30, 820, "SYNTHETIC LABORATORY REPORT Analyte Result Unit Reference interval"
                )
        canvas.showPage()
    canvas.save()
    image.close()
    return output.getvalue()


def write_supplemental(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name, content in {
        "supplemental-scanned.pdf": supplemental_pdf(),
        "supplemental-mixed.pdf": supplemental_pdf(pages=2, mixed=True),
        "supplemental-overlay.pdf": supplemental_pdf(overlay=True),
        "supplemental-ten-page.pdf": supplemental_pdf(pages=10),
        "supplemental-unreadable.pdf": supplemental_pdf(blank=True),
    }.items():
        (output / name).write_bytes(content)
