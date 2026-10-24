"""Explicit live synthetic-development benchmark; never opens held-out examples."""

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from mediflow.benchmark.__main__ import markdown_report
from mediflow.benchmark.dataset import SOURCES, annotate, json_bytes
from mediflow.benchmark.models import (
    DATASET_VERSION,
    Prediction,
    PredictionFile,
    Resource,
    SourceDocument,
)
from mediflow.benchmark.pdfs import write_pdf
from mediflow.benchmark.scoring import evaluate
from mediflow.config import Settings
from mediflow.job_processor import LaboratoryProcessor
from mediflow.jobs import Lease
from mediflow.laboratory import GeminiProvider, extract_laboratory
from mediflow.processing import ProcessingResult
from mediflow.worker import ProcessingFailure


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pdfs", type=Path)
    parser.add_argument(
        "--page-results",
        type=Path,
        help="Explicit real PDF/OCR results, verified against each source hash.",
    )
    args = parser.parse_args()
    try:
        provider = GeminiProvider.from_settings(Settings.from_environment())
        source_bytes = (SOURCES / "development.json").read_bytes()
        frozen = json.loads((SOURCES / "freeze.json").read_bytes())
        if (
            hashlib.sha256(source_bytes).hexdigest()
            != frozen["definition_sha256"]["development.json"]
        ):
            raise ValueError("Development definitions changed from their frozen version.")
        documents = TypeAdapter(list[SourceDocument]).validate_json(source_bytes)
        manifest = json.loads((SOURCES.parents[1] / "manifest.json").read_bytes())
        expected_hashes = {
            item["document_id"]: item["sha256"]
            for item in manifest["documents"]
            if item["split"] == "development"
        }
        if {doc.document_id for doc in documents} != {f"dev-{i:02d}" for i in range(1, 21)} or any(
            doc.split != "development" or doc.kind != "valid" for doc in documents
        ):
            raise ValueError("Only the 20 frozen synthetic development documents are permitted.")
        args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
        predictions = []
        observations = []
        for index, doc in enumerate(documents):
            if index:
                time.sleep(5)  # Remain below the verified 15-request/minute free-tier limit.
            path = (args.pdfs or args.output / "pdfs") / f"{doc.document_id}.pdf"
            if args.pdfs is None:
                write_pdf(doc, path)
            source = path.read_bytes()
            if hashlib.sha256(source).hexdigest() != expected_hashes.get(doc.document_id):
                raise ValueError(
                    "PDF bytes do not match the frozen synthetic development manifest."
                )
            started = time.monotonic()
            now = datetime.now(UTC)
            lease = Lease(
                doc.document_id,
                doc.document_id,
                "development",
                doc.document_id,
                1,
                "laboratory-v1",
                "jobs-v1",
                now + timedelta(seconds=270),
            )
            observation: dict[str, Any] = {"document_id": doc.document_id, "model": provider.model}
            try:
                if args.page_results:
                    pages = ProcessingResult.model_validate_json(
                        (args.page_results / f"{doc.document_id}.json").read_bytes()
                    )
                    if pages.source_sha256 != hashlib.sha256(source).hexdigest():
                        raise ValueError("Cached page evidence does not match the source PDF.")
                    candidate = extract_laboratory(lease, pages, provider)
                else:
                    candidate = LaboratoryProcessor(provider)(lease, source)
                (args.output / f"{doc.document_id}-candidate.json").write_text(
                    candidate.model_dump_json(by_alias=True, indent=2)
                )
                usage = candidate.provenance.usage
                assert usage is not None
                prediction = Prediction(
                    document_id=doc.document_id,
                    outcome="succeeded",
                    rows=candidate.rows,
                    latency_seconds=time.monotonic() - started,
                    flagged_rows=sum(bool(row.issues) for row in candidate.rows),
                    unresolved_rows=sum(bool(row.issues) for row in candidate.rows),
                    provider_cost_usd=0,
                    out_of_pocket_usd=0,
                    resources=(
                        Resource(
                            name="provider_input_tokens", unit="tokens", amount=usage.input_tokens
                        ),
                        Resource(
                            name="provider_output_tokens", unit="tokens", amount=usage.output_tokens
                        ),
                        Resource(
                            name="provider_thinking_tokens",
                            unit="tokens",
                            amount=usage.thinking_tokens,
                        ),
                    ),
                )
                observation.update(
                    outcome="succeeded",
                    model_version=candidate.provenance.model_version,
                    usage=usage.model_dump(),
                    row_count=len(candidate.rows),
                )
            except ProcessingFailure as error:
                prediction = Prediction(
                    document_id=doc.document_id,
                    outcome="failed",
                    latency_seconds=time.monotonic() - started,
                )
                observation.update(
                    outcome="failed", code=error.code.value, transient=error.transient
                )
            predictions.append(prediction)
            observations.append(observation)
            # Persist completed observations before continuing; never print payloads or quotes.
            (args.output / "predictions.json").write_text(
                PredictionFile(
                    dataset_version=DATASET_VERSION, documents=tuple(predictions)
                ).model_dump_json(indent=2)
            )
            print(json.dumps(observation), flush=True)
            if observation.get("code") == "quota_exhausted":
                break
        report = evaluate([annotate(doc) for doc in documents], predictions)
        (args.output / "report.json").write_bytes(json_bytes(report))
        (args.output / "report.md").write_text(markdown_report(report))
        (args.output / "run.json").write_bytes(
            json_bytes(
                {
                    "benchmark": "laboratory-development-v1",
                    "held_out_used": False,
                    "page_results_reused": bool(args.page_results),
                    "documents": observations,
                    "configuration": provider.configuration.model_dump(),
                    "provider_cost_basis": (
                        "Confirmed free-tier project; billing disabled before run."
                    ),
                }
            )
        )
    except (ValueError, OSError, ProcessingFailure):
        parser.exit(2, "Development benchmark unavailable; check configuration and input paths.\n")


if __name__ == "__main__":
    main()
