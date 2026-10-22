"""One-command generation and explicit split-scoped offline evaluation."""

import argparse
import json
from pathlib import Path
from typing import Any

from mediflow.benchmark.dataset import SOURCES, annotate, json_bytes, load_sources, prepare
from mediflow.benchmark.models import DATASET_VERSION, PredictionFile
from mediflow.benchmark.scoring import evaluate


def markdown_report(report: dict[str, Any]) -> str:
    if report["mode"] == "harness_check_only":
        lines = [
            "# Synthetic benchmark preparation",
            "",
            "Extraction accuracy: **not measured**.",
            "No extractor, OCR engine or model was run. "
            "These files establish fixtures and scoring only.",
            "",
            "| Split | Digital | Scanned | Total |",
            "| --- | ---: | ---: | ---: |",
        ]
        for split, counts in report["counts"].items():
            lines.append(
                f"| {split} | {counts['digital']} | {counts['scanned']} | {sum(counts.values())} |"
            )
        lines += [
            "",
            "Development and held-out annotations are stored in separate directories.",
            "The 95% strict row precision/recall release target remains unmeasured.",
        ]
    else:
        lines = [
            "# Synthetic extraction evaluation",
            "",
            f"Dataset: `{report['dataset_version']}`",
            "",
            "| Split / medium | Samples | Correct / expected / predicted | "
            "Precision | Recall | Failures |",
            "| --- | ---: | --- | ---: | ---: | ---: |",
        ]
        for group, result in report["groups"].items():
            if not result["sample_count"]:
                continue
            metric = result["strict_rows"]
            precision = (
                "unmeasured" if metric["precision"] is None else f"{metric['precision']:.4f}"
            )
            recall = "unmeasured" if metric["recall"] is None else f"{metric['recall']:.4f}"
            lines.append(
                f"| {group} | {result['sample_count']} | {metric['correct']} / "
                f"{metric['expected']} / {metric['predicted']} | {precision} | "
                f"{recall} | {result['failures']} |"
            )
        lines += [
            "",
            "Missing submissions count as failures and remain in recall denominators.",
            "Null observations mean unmeasured. Complete field, evidence, classification, "
            "latency and resource metrics are in report.json.",
            "This small synthetic benchmark does not establish real-world clinical accuracy.",
        ]
        for group, result in report["groups"].items():
            if not result["sample_count"]:
                continue
            lines += [
                "",
                f"## {group}",
                "",
                "| Field | Correct / expected / predicted | Precision | Recall |",
                "| --- | --- | ---: | ---: |",
            ]
            for field, metric in result["fields"].items():
                precision = (
                    "unmeasured" if metric["precision"] is None else f"{metric['precision']:.4f}"
                )
                recall = "unmeasured" if metric["recall"] is None else f"{metric['recall']:.4f}"
                lines.append(
                    f"| {field} | {metric['correct']} / {metric['expected']} / "
                    f"{metric['predicted']} | {precision} | {recall} |"
                )
            lines += [
                "",
                f"Evidence mismatches: {result['evidence_mismatches']}. "
                f"Classification failures: {result['classification_failures']}. "
                f"Missing submissions: {result['missing_documents']}.",
                "",
                f"Latency in seconds: {json.dumps(result['latency_seconds'], sort_keys=True)}.",
                "",
                "| Observation | Total | Assessed documents |",
                "| --- | ---: | ---: |",
            ]
            for name, observation in result["observations"].items():
                value = observation["total"]
                total = "unmeasured" if value is None else str(value)
                lines.append(f"| {name} | {total} | {observation['assessed_documents']} |")
            lines += [
                "",
                f"Resource observations: {result['resource_measured_documents']} documents.",
            ]
            if result["resources"]:
                lines.append("")
            for resource in result["resources"]:
                lines.append(f"- {resource['name']}: {resource['amount']} {resource['unit']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "evaluate"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/generated"))
    parser.add_argument("--sources", type=Path, default=SOURCES)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument(
        "--split", choices=("development", "held-out", "negative"), default="development"
    )
    parser.add_argument(
        "--release-evaluation",
        action="store_true",
        help="Explicitly unlock held-out evaluation after tuning is frozen.",
    )
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            if args.predictions or args.release_evaluation or args.split != "development":
                parser.error(
                    "prepare only generates fixtures; use evaluate for predictions/splits."
                )
            manifest = prepare(args.output, args.sources)
            report = {
                "dataset_version": DATASET_VERSION,
                "mode": "harness_check_only",
                "measured_extraction_accuracy": None,
                "counts": manifest["counts"],
                "sample_count": len(manifest["documents"]),
                "provider_requests": 0,
                "held_out_frozen": True,
            }
        else:
            if args.split == "held-out" and not args.release_evaluation:
                parser.error(
                    "Held-out evaluation requires --release-evaluation; never use it for tuning."
                )
            if args.predictions is None:
                parser.error("evaluate requires --predictions.")
            predictions = PredictionFile.model_validate_json(args.predictions.read_bytes())
            documents = load_sources(args.sources, (args.split,))
            report = evaluate([annotate(doc) for doc in documents], predictions.documents)
            args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "report.json").write_bytes(json_bytes(report))
        (args.output / "report.md").write_text(markdown_report(report))
        print(json.dumps({"mode": report["mode"], "output": str(args.output)}))
    except (ValueError, OSError) as error:
        parser.exit(2, f"benchmark: {error}\n")


if __name__ == "__main__":
    main()
