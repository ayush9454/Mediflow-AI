"""Deterministic local PDF fixtures, including image-only simulated scans."""

import io
import random
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium  # type: ignore[import-untyped]
import reportlab  # type: ignore[import-untyped]
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.lib.utils import ImageReader  # type: ignore[import-untyped]
from reportlab.pdfbase.pdfmetrics import (  # type: ignore[import-untyped]
    getRegisteredFontNames,
    registerFont,
    stringWidth,
)
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]

from mediflow.benchmark.models import SourceDocument

RENDER_VERSION = "1"
SCAN_RECIPES = (
    {"dpi": 110, "rotation": -0.6, "contrast": 0.82, "blur": 0.35, "jpeg_quality": 50},
    {"dpi": 125, "rotation": 0.45, "contrast": 0.76, "blur": 0.45, "jpeg_quality": 58},
    {"dpi": 140, "rotation": -0.25, "contrast": 0.90, "blur": 0.25, "jpeg_quality": 65},
)


def scan_recipe(document: SourceDocument) -> dict[str, Any] | None:
    if document.medium != "scanned" or document.kind != "valid":
        return None
    return dict(SCAN_RECIPES[document.seed % len(SCAN_RECIPES)], seed=document.seed)


def _canvas(buffer: io.BytesIO, title: str) -> Canvas:
    if "Fixture" not in getRegisteredFontNames():
        fonts = Path(reportlab.__file__).parent / "fonts"
        for name, file in (
            ("Fixture", "Vera.ttf"),
            ("FixtureBold", "VeraBd.ttf"),
            ("FixtureLedger", "VeraIt.ttf"),
        ):
            registerFont(TTFont(name, str(fonts / file)))
    canvas = Canvas(buffer, pagesize=A4, invariant=1, pageCompression=1)
    canvas.setTitle(title)
    canvas.setAuthor("MediFlow synthetic fixture generator")
    return canvas


def _native(document: SourceDocument) -> bytes:
    buffer = io.BytesIO()
    canvas = _canvas(buffer, document.document_id)
    pages = document.pages or ((),)
    if document.kind == "over_pages":
        pages = ((),) * 11
    columns = (44, 178, 281, 335, 418, 445)
    widths = (130, 99, 50, 79, 23, 106)
    font = "FixtureLedger" if document.layout == "ledger" else "Fixture"
    french = document.kind == "unsupported_language"
    heading = (
        "LABORATOIRE FICTIF"
        if french
        else {
            "unsupported_category": "SYNTHETIC DOCUMENT",
        }.get(document.kind, "SYNTHETIC LABORATORY")
    )
    for page_number, rows in enumerate(pages, 1):
        canvas.setFillColorRGB(0.10, 0.23, 0.29)
        canvas.rect(0, 746, A4[0], 96, fill=1, stroke=0)
        canvas.setFillColorRGB(1, 1, 1)
        canvas.setFont("FixtureBold", 17)
        canvas.drawString(44, 801, heading)
        canvas.setFont("Fixture", 10)
        canvas.drawString(
            44,
            779,
            "Exercice fictif - aucune utilisation clinique"
            if french
            else "Teaching fixture - invented records - no clinical use",
        )
        canvas.setFillColorRGB(0.15, 0.15, 0.15)
        canvas.setFont("Fixture", 10)
        canvas.drawString(
            44,
            720,
            f"Document: {document.document_id}   Patient: "
            f"{'FICTIF' if french else 'SYNTHETIC'}-{document.document_id}",
        )
        canvas.drawString(
            44,
            700,
            f"Page {page_number} / {len(pages)}"
            if french
            else f"Layout: {document.layout}   Source page {page_number} of {len(pages)}",
        )
        canvas.setFont("FixtureBold", 8)
        for x, label in zip(
            columns,
            ("Analyte", "Result", "Unit", "Printed interval", "Flag", "Collected"),
            strict=True,
        ):
            if rows:
                canvas.drawString(x, 661, label)
        y = 626
        spacing = 40 if document.layout == "compact" else 58
        for index, row in enumerate(rows):
            if document.layout != "ledger" and index % 2 == 0:
                canvas.setFillColorRGB(0.94, 0.96, 0.97)
                canvas.rect(40, y - 14, 515, 32, fill=1, stroke=0)
            canvas.setFillColorRGB(0.08, 0.08, 0.08)
            for x, width, value in zip(columns, widths, row.model_dump().values(), strict=True):
                if value is None:
                    continue
                size = 8.0
                while stringWidth(value, font, size) > width and size > 6:
                    size -= 0.25
                if stringWidth(value, font, size) > width:
                    raise ValueError(f"Fixture cell does not fit: {document.document_id}: {value}")
                canvas.setFont(font, size)
                canvas.drawString(x, y, value)
            y -= spacing
        canvas.setFont("Fixture", 11)
        for line in document.text_lines:
            canvas.drawString(44, y, line)
            y -= 28
        canvas.setStrokeColorRGB(0.65, 0.70, 0.72)
        canvas.line(44, 80, 551, 80)
        canvas.setFont("Fixture", 9)
        canvas.drawString(
            44,
            60,
            "Tous les noms et résultats sont fictifs."
            if french
            else "All names, identifiers and findings are invented for software evaluation.",
        )
        canvas.drawRightString(551, 40, f"{page_number} / {len(pages)}")
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def _scanned(document: SourceDocument, original: bytes) -> bytes:
    recipe = SCAN_RECIPES[document.seed % len(SCAN_RECIPES)]
    rng = random.Random(document.seed)
    buffer = io.BytesIO()
    canvas = _canvas(buffer, document.document_id)
    with pdfium.PdfDocument(original) as pdf:
        for page in pdf:
            bitmap = page.render(scale=recipe["dpi"] / 72)
            image = bitmap.to_pil().convert("L")
            bitmap.close()
            image = ImageEnhance.Contrast(image).enhance(recipe["contrast"])
            image = image.rotate(
                recipe["rotation"], resample=Image.Resampling.BICUBIC, fillcolor=255
            )
            image = image.filter(ImageFilter.GaussianBlur(recipe["blur"]))
            for _ in range(900):
                image.putpixel(
                    (rng.randrange(image.width), rng.randrange(image.height)),
                    rng.randrange(100, 240),
                )
            jpeg = io.BytesIO()
            image.save(jpeg, format="JPEG", quality=int(recipe["jpeg_quality"]), optimize=False)
            canvas.drawImage(ImageReader(io.BytesIO(jpeg.getvalue())), 0, 0, *A4)
            canvas.showPage()
            page.close()
    canvas.save()
    return buffer.getvalue()


def _unreadable(document: SourceDocument) -> bytes:
    buffer = io.BytesIO()
    canvas = _canvas(buffer, document.document_id)
    # Severe downsampling destroys letters; no recoverable hidden text layer.
    image = Image.new("L", (420, 595), 245)
    draw = ImageDraw.Draw(image)
    draw.text((30, 180), "Glucose 90.00 mg/dL", fill=50, font_size=12)
    image = image.resize((18, 25)).resize((840, 1190)).filter(ImageFilter.GaussianBlur(8))
    if document.seed % 2:
        ImageDraw.Draw(image).rectangle((0, 0, 840, 1050), fill=12)
    canvas.drawImage(ImageReader(image), 0, 0, *A4)
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def _oversized(document: SourceDocument) -> bytes:
    # Dense sensor noise in real raster streams, not bytes appended after EOF.
    rng = random.Random(document.seed)
    buffer = io.BytesIO()
    canvas = _canvas(buffer, document.document_id)
    for page in range(3):
        image = Image.frombytes("RGB", (1400, 1900), rng.randbytes(1400 * 1900 * 3))
        image = image.point(lambda value: 220 + value // 8)
        draw = ImageDraw.Draw(image)
        draw.text(
            (100, 150), "SYNTHETIC LABORATORY - LOSSLESS NOISY SCAN", fill=(0, 0, 0), font_size=36
        )
        draw.text(
            (100, 270), f"Glucose 90.00 mg/dL    Page {page + 1}", fill=(0, 0, 0), font_size=34
        )
        canvas.drawImage(ImageReader(image), 0, 0, *A4)
        canvas.showPage()
    canvas.save()
    content = buffer.getvalue()
    if len(content) <= 10_000_000:
        raise ValueError("Size-limit fixture did not exceed 10,000,000 bytes.")
    return content


def write_pdf(document: SourceDocument, path: Path) -> None:
    """Write one valid or intentionally invalid fixture from its source definition."""
    match document.kind:
        case "corrupt":
            content = b"%PDF-1.7\nSYNTHETIC CORRUPT FILE\nnot a PDF object table\n%%EOF\n"
        case "truncated":
            content = _native(document)[:300]
        case "unreadable":
            content = _unreadable(document)
        case "over_size":
            content = _oversized(document)
        case "password_protected":
            writer = PdfWriter(clone_from=PdfReader(io.BytesIO(_native(document))))
            # Deliberately public test password; RC4 keeps this rejection fixture
            # deterministic. This is not the application's document encryption.
            writer.encrypt("synthetic-fixture-only", algorithm="RC4-128")
            output = io.BytesIO()
            writer.write(output)
            content = output.getvalue()
        case _:
            content = _native(document)
            if document.medium == "scanned":
                content = _scanned(document, content)
    path.write_bytes(content)
