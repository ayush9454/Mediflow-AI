"""Load frozen source definitions and generate traceable PDFs/annotations."""

import hashlib
import json
from collections import Counter
from importlib.metadata import version
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from mediflow.benchmark.models import DATASET_VERSION, Annotation, SourceDocument, Split
from mediflow.benchmark.pdfs import RENDER_VERSION, scan_recipe, write_pdf
from mediflow.contracts import EvidenceReference, LaboratoryRow, ValidationIssue

SOURCES = Path(__file__).resolve().parents[4] / "evaluation" / "fixtures" / "v1"
SPLITS: tuple[Split, ...] = ("development", "held-out", "negative")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
    ).encode()


def verify_freeze(sources: Path = SOURCES) -> dict[str, Any]:
    freeze = json.loads((sources / "freeze.json").read_text())
    if freeze["dataset_version"] != DATASET_VERSION or freeze["render_version"] != RENDER_VERSION:
        raise ValueError("Dataset/render version differs from the frozen manifest.")
    if set(freeze["held_out_artifacts"]) != {f"hold-{index:02d}" for index in range(1, 11)}:
        raise ValueError("The frozen manifest must pin all ten held-out PDF hashes.")
    for split in SPLITS:
        name = f"{split}.json"
        if digest((sources / name).read_bytes()) != freeze["definition_sha256"][name]:
            raise ValueError(f"Frozen source changed: {name}. Create a new dataset version.")
    return freeze


def load_sources(
    sources: Path = SOURCES, splits: tuple[Split, ...] = SPLITS
) -> list[SourceDocument]:
    verify_freeze(sources)
    documents = []
    for split in splits:
        entries = TypeAdapter(list[SourceDocument]).validate_json(
            (sources / f"{split}.json").read_bytes()
        )
        if any(document.split != split for document in entries):
            raise ValueError("Definition file contains a document from another split.")
        documents.extend(entries)
    if len({document.document_id for document in documents}) != len(documents):
        raise ValueError("Source document IDs must be unique.")
    return documents


def annotate(document: SourceDocument) -> Annotation:
    """Ground truth comes only from authored source fields, never PDF/OCR/model output."""
    rows = []
    pages = []
    for page_number, page in enumerate(document.pages, 1):
        pages.append("\n".join(row.quotation() for row in page))
        for row_number, row in enumerate(page, 1):
            row_id = f"{document.document_id}-p{page_number}-r{row_number}"
            issues = tuple(
                ValidationIssue(
                    issue_id=f"{row_id}-{field}",
                    field=field,
                    code="not_printed",
                    severity="warning",
                    message="Not printed in the authored synthetic source.",
                )
                for field in ("unit", "reference_range", "collection_date")
                if getattr(row, field) is None
            )
            rows.append(
                LaboratoryRow(
                    row_id=row_id,
                    **row.model_dump(),
                    issues=issues,
                    evidence=(
                        EvidenceReference(
                            page=page_number,
                            quotation=row.quotation(),
                            extraction_method="ocr" if document.medium == "scanned" else "native",
                        ),
                    ),
                )
            )
    return Annotation(
        document_id=document.document_id,
        split=document.split,
        medium=document.medium,
        expected_outcome="succeeded" if document.kind == "valid" else "rejected",
        rejection_reason=None if document.kind == "valid" else document.kind,
        rows=tuple(rows),
        pages=tuple(pages),
    )


def prepare(output: Path, sources: Path = SOURCES) -> dict[str, Any]:
    """Regenerate all forty documents without running an extractor or provider."""
    if output.resolve().is_relative_to(sources.resolve()):
        raise ValueError("Generated output must be outside frozen source definitions.")
    freeze = verify_freeze(sources)
    documents = load_sources(sources)
    counts = {
        split: dict(Counter(doc.medium for doc in documents if doc.split == split))
        for split in SPLITS
    }
    if counts != {
        "development": {"digital": 10, "scanned": 10},
        "held-out": {"digital": 5, "scanned": 5},
        "negative": {"digital": 7, "scanned": 3},
    }:
        raise ValueError("Source counts differ from the frozen 20/10/10 partition.")
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    for document in documents:
        directory = output / document.split
        directory.mkdir(exist_ok=True)
        path = directory / f"{document.document_id}.pdf"
        write_pdf(document, path)
        annotation = annotate(document).model_dump(mode="json", by_alias=True)
        entries.append(
            {
                "document_id": document.document_id,
                "split": document.split,
                "medium": document.medium,
                "kind": document.kind,
                "seed": document.seed,
                "layout": document.layout,
                "path": path.relative_to(output).as_posix(),
                "byte_count": path.stat().st_size,
                "sha256": digest(path.read_bytes()),
                "annotation_sha256": digest(json_bytes(annotation)),
                "definition_file": f"{document.split}.json",
                "definition_sha256": freeze["definition_sha256"][f"{document.split}.json"],
                "scan_recipe": scan_recipe(document),
                "expected_pages": 11
                if document.kind == "over_pages"
                else (
                    None
                    if document.kind in ("corrupt", "truncated")
                    else len(document.pages) or (3 if document.kind == "over_size" else 1)
                ),
            }
        )
    for split in SPLITS:
        annotations = [
            annotate(doc).model_dump(mode="json", by_alias=True)
            for doc in documents
            if doc.split == split
        ]
        (output / split / "annotations.json").write_bytes(json_bytes(annotations))
    manifest = {
        "dataset_version": DATASET_VERSION,
        "render_version": RENDER_VERSION,
        "synthetic_only": True,
        "counts": counts,
        "documents": entries,
        "freeze_sha256": digest((sources / "freeze.json").read_bytes()),
        "generator_sha256": digest(
            b"".join(
                Path(__file__).with_name(name).read_bytes()
                for name in ("dataset.py", "pdfs.py", "models.py")
            )
        ),
        "dependencies": {
            name: version(name) for name in ("reportlab", "pillow", "pypdf", "pypdfium2")
        },
    }
    actual = {
        entry["document_id"]: entry["sha256"] for entry in entries if entry["split"] == "held-out"
    }
    if actual != freeze["held_out_artifacts"]:
        raise ValueError(
            "Held-out PDFs differ from the frozen hashes. Check locked rendering dependencies."
        )
    (output / "manifest.json").write_bytes(json_bytes(manifest))
    return manifest
