"""Private subprocess: bounded native parser, sequential page rendering and OCR."""

import hashlib
import math
import re
import resource
import subprocess
import sys
from pathlib import Path

from mediflow.processing.models import Limits, PageText, ProcessingResult, rejected


def _adequacy(text: str) -> tuple[bool, int, float]:
    visible = [character for character in text if not character.isspace()]
    letters = sum(character.isalpha() for character in text)
    ratio = sum(character.isprintable() for character in visible) / max(1, len(visible))
    adequate = letters >= 40 and len(text.split()) >= 8 and ratio >= 0.98 and "\ufffd" not in text
    return adequate, letters, ratio


def _category(text: str) -> tuple[str, str | None]:
    words = set(re.findall(r"[a-z]+", text.lower()))
    if words & {"radiology", "radiograph", "mri", "ct", "appointment", "receipt"}:
        return "unsupported", "unsupported_category"
    if words & {"laboratoire", "resultats", "résultats", "patientenbericht"}:
        return "unsupported", "unsupported_language"
    laboratory = bool(words & {"laboratory", "lab", "haematology", "hematology"})
    headers = "result" in words and bool(words & {"reference", "interval", "range"})
    analytes = words & {
        "glucose",
        "sodium",
        "potassium",
        "hemoglobin",
        "haemoglobin",
        "creatinine",
        "platelets",
        "cholesterol",
        "tsh",
        "protein",
        "calcium",
        "alt",
        "ast",
        "bilirubin",
        "albumin",
        "crp",
        "esr",
        "ferritin",
        "iron",
        "hba1c",
        "culture",
    }
    if laboratory and headers and analytes:
        return "laboratory", None
    return "uncertain", "uncertain_category"


def _extract(root: Path, source: bytes, limits: Limits) -> ProcessingResult:
    import pypdfium2 as pdfium  # type: ignore[import-untyped]
    from pypdf import PdfReader

    if not source.startswith(b"%PDF-") or b"%%EOF" not in source[-1024:]:
        return rejected(source, "corrupt")
    try:
        reader = PdfReader(root / "source.pdf", strict=True)
        if reader.is_encrypted:
            return rejected(source, "encrypted")
        if len(reader.pages) > limits.max_pages:
            return rejected(source, "over_pages")
        if not reader.pages:
            return rejected(source, "unreadable")
        pdf = pdfium.PdfDocument(source)
    except MemoryError:
        raise
    except Exception:
        return rejected(source, "corrupt")
    pages = []
    try:
        for number, page in enumerate(reader.pages, 1):
            native = page.extract_text() or ""
            if len(native) > limits.max_page_characters:
                return rejected(source, "resource_limit")
            adequate, letters, ratio = _adequacy(native)
            rendered_page = pdf[number - 1]
            try:
                width, height = rendered_page.get_size()
                if not (0 < width <= 14_400 and 0 < height <= 14_400):
                    return rejected(source, "render_limit")
                # A text heading over a scanned table must not suppress OCR.
                image_area = sum(
                    max(0, obj.get_bounds()[2] - obj.get_bounds()[0])
                    * max(0, obj.get_bounds()[3] - obj.get_bounds()[1])
                    for obj in rendered_page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE])
                )
                large_image = image_area >= width * height * 0.15
                flags = []
                origin = "native"
                text = native
                if not adequate or large_image:
                    origin = "ocr"
                    scale = min(
                        limits.dpi / 72,
                        math.sqrt(limits.max_pixels / (width * height)),
                        math.sqrt(limits.max_pixels) / max(width, height),
                    )
                    if math.ceil(width * scale) * math.ceil(height * scale) > limits.max_pixels:
                        scale *= 0.999
                    bitmap = rendered_page.render(scale=scale)
                    image = bitmap.to_pil()
                    image.save(root / "page.png")
                    image.close()
                    bitmap.close()
                    output = root / "ocr.txt"
                    output.unlink(missing_ok=True)
                    try:
                        completed = subprocess.run(
                            [
                                "tesseract",
                                str(root / "page.png"),
                                str(root / "ocr"),
                                "-l",
                                "eng",
                                "--oem",
                                "1",
                                "--psm",
                                "3",
                            ],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=limits.ocr_seconds,
                            check=False,
                        )
                    except subprocess.TimeoutExpired:
                        return rejected(source, "timeout", failed=True)
                    except FileNotFoundError:
                        return rejected(source, "ocr_unavailable", failed=True)
                    if completed.returncode != 0 or not output.exists():
                        return rejected(source, "ocr_failed", failed=True)
                    if output.stat().st_size > limits.max_page_characters * 4:
                        return rejected(source, "resource_limit")
                    text = output.read_text()
                    if len(text) > limits.max_page_characters:
                        return rejected(source, "resource_limit")
                    if not _adequacy(text)[0]:
                        flags.append("unreadable")
                    flags.append("ocr_requires_visual_review")
                    if large_image:
                        flags.append("substantial_raster_content")
                if re.search(
                    r"ignore\s+(?:all\s+)?(?:previous|system)|system\s+prompt", text, re.I
                ):
                    flags.append("embedded_instructions_untrusted")
                pages.append(
                    PageText(
                        page_number=number,
                        origin=origin,
                        original_text=text,
                        native_text=native,
                        native_adequate=adequate,
                        alphabetic_characters=letters,
                        printable_ratio=ratio,
                        flags=tuple(flags),
                    )
                )
            finally:
                rendered_page.close()
    finally:
        pdf.close()
    category, reason = _category("\n".join(page.original_text for page in pages))
    if any("unreadable" in page.flags for page in pages):
        reason = "unreadable"
    return ProcessingResult(
        outcome="succeeded" if reason is None else "rejected",
        reason=reason,
        category=category,
        pages=tuple(pages),
        source_sha256=hashlib.sha256(source).hexdigest(),
    )


def main() -> None:
    root = Path(sys.argv[1])
    limits = Limits.model_validate_json((root / "limits.json").read_text())
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (limits.memory_bytes, limits.memory_bytes))
        cpu_limit = math.ceil(limits.deadline_seconds)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
    source = (root / "source.pdf").read_bytes()
    try:
        result = _extract(root, source, limits)
    except MemoryError:
        result = rejected(source, "resource_limit", failed=True)
    except Exception:
        result = rejected(source, "corrupt")
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    rss_scale = 1 if sys.platform == "darwin" else 1024
    result = result.model_copy(
        update={
            "peak_rss_bytes": int(max(own.ru_maxrss, children.ru_maxrss) * rss_scale),
            "cpu_seconds": own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime,
        }
    )
    (root / "result.json").write_text(result.model_dump_json())


if __name__ == "__main__":
    main()
