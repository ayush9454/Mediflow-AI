"""Explicit offline processing checks; no queue adapter, LLM, or clinical extraction."""

import argparse
import json
import platform
import subprocess
from pathlib import Path
from typing import Any

from mediflow.processing import process_pdf


def _cgroup(name: str) -> str | None:
    path = Path("/sys/fs/cgroup") / name
    return path.read_text().strip() if path.exists() else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fixtures", "extract", "benchmark"))
    parser.add_argument("input", type=Path, nargs="?")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "fixtures":
        from pydantic import TypeAdapter

        from mediflow.benchmark.models import SourceDocument
        from mediflow.benchmark.pdfs import write_pdf
        from mediflow.processing.fixtures import write_supplemental

        write_supplemental(args.output)
        if args.input:
            for split in ("development", "negative"):
                sources = TypeAdapter(list[SourceDocument]).validate_json(
                    (args.input / f"{split}.json").read_bytes()
                )
                if any(document.split != split for document in sources):
                    parser.error("Source definition contains a document from another split.")
                for document in sources:
                    write_pdf(document, args.output / f"{document.document_id}.pdf")
        return
    if args.input is None:
        parser.error("extract and benchmark require an input path.")
    if args.command == "extract":
        result = process_pdf(args.input.read_bytes())
        args.output.write_text(result.model_dump_json(indent=2))
        print(json.dumps({"outcome": result.outcome, "reason": result.reason}))
        return
    # Restrict offline benchmark to explicit allowlisted dev/negative names. Never
    # recursively glob evaluation/generated (it also contains frozen held-out data).
    paths = sorted(args.input.glob("dev-*.pdf")) + sorted(args.input.glob("neg-*.pdf"))
    paths += sorted(args.input.glob("supplemental-*.pdf"))
    if not paths:
        parser.error("No allowlisted development/negative/supplemental PDFs in input directory.")
    observations: list[dict[str, Any]] = []
    for path in paths:
        result = process_pdf(path.read_bytes())
        observations.append(
            {
                "document_id": path.stem,
                "outcome": result.outcome,
                "reason": result.reason,
                "category": result.category,
                "source_sha256": result.source_sha256,
                "pages": [
                    {
                        "page_number": page.page_number,
                        "origin": page.origin,
                        "native_adequate": page.native_adequate,
                        "flags": page.flags,
                    }
                    for page in result.pages
                ],
                "elapsed_seconds": result.elapsed_seconds,
                "peak_rss_bytes": result.peak_rss_bytes,
                "cpu_seconds": result.cpu_seconds,
            }
        )
        print(json.dumps(observations[-1]), flush=True)
    tesseract = subprocess.run(["tesseract", "--version"], capture_output=True, text=True)
    report = {
        "benchmark": "development-page-processing-v1",
        "held_out_used": False,
        "clinical_or_row_accuracy_measured": False,
        "platform": platform.platform(),
        "tesseract_version": tesseract.stdout.splitlines()[0],
        "cgroup_memory_max": _cgroup("memory.max"),
        "cgroup_memory_peak": _cgroup("memory.peak"),
        "cgroup_cpu_max": _cgroup("cpu.max"),
        "documents": observations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
