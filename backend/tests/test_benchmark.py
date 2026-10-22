"""Behavior checks at the offline evaluation and fixture-generation interfaces."""

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from mediflow.benchmark.scoring import evaluate


def test_missing_and_invented_rows_reduce_recall_and_precision():
    gold = {
        "document_id": "example",
        "split": "development",
        "medium": "digital",
        "expected_outcome": "succeeded",
        "pages": ["Glucose <0.50 mg/dL 0.00-1.00 2026-01-01\nProtein Negative"],
        "rows": [
            {
                "rowId": "gold-1",
                "analyte": "Glucose",
                "result": "<0.50",
                "unit": "mg/dL",
                "referenceRange": "0.00-1.00",
                "collectionDate": "2026-01-01",
                "evidence": [
                    {
                        "page": 1,
                        "quotation": "Glucose <0.50 mg/dL 0.00-1.00 2026-01-01",
                        "extractionMethod": "native",
                    }
                ],
            },
            {
                "rowId": "gold-2",
                "analyte": "Protein",
                "result": "Negative",
                "evidence": [
                    {"page": 1, "quotation": "Protein Negative", "extractionMethod": "native"}
                ],
            },
        ],
    }
    actual = dict(gold["rows"][0], rowId="arbitrary-provider-id")
    invented = dict(actual, rowId="extra", analyte="Imaginary")
    report = evaluate(
        [gold], [{"document_id": "example", "outcome": "succeeded", "rows": [actual, invented]}]
    )
    group = report["groups"]["development/all"]
    assert group["strict_rows"] == {
        "expected": 2,
        "predicted": 2,
        "correct": 1,
        "precision": 0.5,
        "recall": 0.5,
    }


def test_a_failed_run_cannot_earn_correct_rows_from_partial_output():
    gold = {
        "document_id": "failure",
        "split": "held-out",
        "medium": "scanned",
        "expected_outcome": "succeeded",
        "pages": ["Protein Negative"],
        "rows": [
            {
                "rowId": "r1",
                "analyte": "Protein",
                "result": "Negative",
                "evidence": [
                    {"page": 1, "quotation": "Protein Negative", "extractionMethod": "ocr"}
                ],
            }
        ],
    }
    report = evaluate(
        [gold], [{"document_id": "failure", "outcome": "failed", "rows": gold["rows"]}]
    )
    group = report["groups"]["held-out/scanned"]
    assert group["strict_rows"]["recall"] == 0
    assert group["failures"] == 1


@pytest.fixture
def repeated_rows():
    rows = [
        {
            "rowId": "one",
            "analyte": "Marker",
            "result": "<0.50",
            "unit": "mg/dL",
            "referenceRange": "0.00-1.00",
            "abnormalityFlag": "L",
            "collectionDate": "01/02/2026",
            "evidence": [
                {
                    "page": 1,
                    "quotation": "Marker <0.50 mg/dL 0.00-1.00 L 01/02/2026",
                    "extractionMethod": "native",
                }
            ],
        },
        {
            "rowId": "two",
            "analyte": "Marker",
            "result": ">5.00",
            "unit": "mg/dL",
            "referenceRange": "0.00-1.00",
            "abnormalityFlag": "H",
            "collectionDate": "02/02/2026",
            "evidence": [
                {
                    "page": 2,
                    "quotation": "Marker >5.00 mg/dL 0.00-1.00 H 02/02/2026",
                    "extractionMethod": "native",
                }
            ],
        },
    ]
    return {
        "document_id": "example",
        "split": "development",
        "medium": "digital",
        "expected_outcome": "succeeded",
        "pages": [r["evidence"][0]["quotation"] for r in rows],
        "rows": rows,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("unit", "mmol/L"),
        ("result", "0.50"),
        ("result", "<0.5"),
        ("result", ">0.50"),
        ("analyte", "marker"),
        ("referenceRange", "0.0-1.0"),
        ("abnormalityFlag", None),
        ("collectionDate", "2026-02-01"),
    ],
)
def test_meaningful_field_changes_fail_strict_matching(repeated_rows, field, value):
    actual = copy.deepcopy(repeated_rows["rows"])
    actual[0][field] = value
    group = evaluate(
        [repeated_rows], [{"document_id": "example", "outcome": "succeeded", "rows": actual}]
    )["groups"]["development/all"]
    assert group["strict_rows"]["correct"] == 1
    assert (
        group["fields"][
            {
                "referenceRange": "reference_range",
                "abnormalityFlag": "abnormality_flag",
                "collectionDate": "collection_date",
            }.get(field, field)
        ]["correct"]
        == 1
    )


def test_reordering_and_whitespace_are_allowed_but_duplicate_rows_cannot_reuse_gold(repeated_rows):
    actual = copy.deepcopy(repeated_rows["rows"][::-1])
    actual[0]["analyte"] = "  Marker\n"
    actual[0]["evidence"][0]["quotation"] = "Marker\n>5.00  mg/dL 0.00-1.00 H 02/02/2026"
    actual.append(actual[0])
    group = evaluate(
        [repeated_rows], [{"document_id": "example", "outcome": "succeeded", "rows": actual}]
    )["groups"]["development/all"]
    assert group["strict_rows"]["correct"] == 2
    assert group["strict_rows"]["precision"] == 2 / 3
    assert group["strict_rows"]["recall"] == 1


@pytest.mark.parametrize(
    ("page", "quotation"),
    [
        (2, "Marker <0.50 mg/dL 0.00-1.00 L 01/02/2026"),
        (1, "Marker"),
        (3, "Marker <0.50 mg/dL 0.00-1.00 L 01/02/2026"),
        (1, "Marker <0.50 mg/dL 0.00-1.00 L 01/02/2026 invented"),
    ],
)
def test_bad_or_incomplete_evidence_fails_matching(repeated_rows, page, quotation):
    actual = copy.deepcopy(repeated_rows["rows"])
    actual[0]["evidence"][0].update(page=page, quotation=quotation)
    group = evaluate(
        [repeated_rows], [{"document_id": "example", "outcome": "succeeded", "rows": actual}]
    )["groups"]["development/all"]
    assert group["strict_rows"]["correct"] == 1
    assert group["evidence_mismatches"] == 1


def test_missing_documents_are_failures_and_unknown_observations_remain_unknown(repeated_rows):
    group = evaluate([repeated_rows], [])["groups"]["development/all"]
    assert group["strict_rows"]["recall"] == 0
    assert group["strict_rows"]["precision"] is None
    assert group["classification_failures"] == group["missing_documents"] == group["failures"] == 1
    assert group["observations"]["out_of_pocket_usd"]["total"] is None
    assert group["observations"]["unsupported_summary_claims"]["assessed_documents"] == 0


def test_duplicate_or_out_of_split_documents_are_rejected(repeated_rows):
    with pytest.raises(ValueError, match="Duplicate"):
        evaluate([repeated_rows, repeated_rows], [])
    with pytest.raises(ValueError, match="outside"):
        evaluate([repeated_rows], [{"document_id": "hold-01", "outcome": "succeeded"}])


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("benchmark")
    result = subprocess.run(
        [sys.executable, "-m", "mediflow.benchmark", "prepare", "--output", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return tmp_path


def test_prepare_command_generates_all_splits_and_labels_the_report_unmeasured(generated):
    tmp_path = generated
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert len(manifest["documents"]) == 40
    assert len(list(tmp_path.rglob("*.pdf"))) == 40
    assert manifest["counts"] == {
        "development": {"digital": 10, "scanned": 10},
        "held-out": {"digital": 5, "scanned": 5},
        "negative": {"digital": 7, "scanned": 3},
    }
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["mode"] == "harness_check_only"
    assert report["measured_extraction_accuracy"] is None
    assert "not measured" in (tmp_path / "report.md").read_text().lower()
    assert Path(tmp_path / "held-out" / "annotations.json").exists()


def test_native_annotations_match_actual_pages_and_scans_have_no_hidden_text(generated):
    manifest = json.loads((generated / "manifest.json").read_text())
    for split in ("development", "held-out"):
        annotations = {
            doc["document_id"]: doc
            for doc in json.loads((generated / split / "annotations.json").read_text())
        }
        for entry in manifest["documents"]:
            if entry["split"] != split:
                continue
            pdf = PdfReader(generated / entry["path"])
            assert len(pdf.pages) == entry["expected_pages"]
            if entry["medium"] == "scanned":
                assert all(
                    not page.extract_text().strip() and len(page.images) >= 1 for page in pdf.pages
                )
            else:
                for number, page in enumerate(pdf.pages):
                    expected_text = annotations[entry["document_id"]]["pages"][number]
                    assert " ".join(expected_text.split()) == " ".join(page.extract_text().split())
                for row in annotations[entry["document_id"]]["rows"]:
                    reference = row["evidence"][0]
                    text = " ".join(pdf.pages[reference["page"] - 1].extract_text().split())
                    assert reference["quotation"] in text
    first = json.loads((generated / "development" / "annotations.json").read_text())[0]["rows"][0]
    assert (first["analyte"], first["result"], first["unit"], first["referenceRange"]) == (
        "Hemoglobin",
        "12.30",
        "g/dL",
        "12.00-16.00",
    )


def test_authentic_full_page_quotations_with_headers_are_valid_evidence(generated):
    gold = json.loads((generated / "development" / "annotations.json").read_text())[0]
    rows = copy.deepcopy(gold["rows"])
    pdf = PdfReader(generated / "development" / "dev-01.pdf")
    for row in rows:
        evidence = row["evidence"][0]
        evidence["quotation"] = pdf.pages[evidence["page"] - 1].extract_text()
    group = evaluate([gold], [{"document_id": "dev-01", "outcome": "succeeded", "rows": rows}])[
        "groups"
    ]["development/all"]
    assert group["strict_rows"]["correct"] == 7
    assert group["evidence_mismatches"] == 0


def test_negative_artifacts_exercise_real_parser_encryption_and_upload_limits(generated):
    for name in ("neg-01", "neg-02"):
        with pytest.raises(PdfReadError):
            PdfReader(generated / "negative" / f"{name}.pdf", strict=True)
    encrypted = PdfReader(generated / "negative" / "neg-08.pdf")
    assert encrypted.is_encrypted
    assert encrypted.decrypt("wrong-password") == 0
    assert encrypted.decrypt("synthetic-fixture-only") != 0
    oversized = generated / "negative" / "neg-09.pdf"
    assert oversized.stat().st_size > 10_000_000
    assert len(PdfReader(oversized).pages) <= 10
    assert len(PdfReader(generated / "negative" / "neg-10.pdf").pages) == 11
    french = PdfReader(generated / "negative" / "neg-07.pdf").pages[0].extract_text()
    assert "français" in french and "LABORATOIRE FICTIF" in french


def test_generation_is_byte_reproducible(generated, tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "mediflow.benchmark", "prepare", "--output", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "manifest.json").read_bytes() == (generated / "manifest.json").read_bytes()
    manifest = json.loads((generated / "manifest.json").read_text())
    for entry in manifest["documents"]:
        assert (
            hashlib.sha256((tmp_path / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]
        )


def test_changed_frozen_definitions_and_implicit_held_out_runs_are_refused(tmp_path):
    sources = Path(__file__).resolve().parents[2] / "evaluation" / "fixtures" / "v1"
    copied = tmp_path / "sources"
    shutil.copytree(sources, copied)
    with (copied / "held-out.json").open("a") as stream:
        stream.write("\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mediflow.benchmark",
            "prepare",
            "--sources",
            str(copied),
            "--output",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "Frozen source changed: held-out.json" in result.stderr
    assert not (tmp_path / "out").exists()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mediflow.benchmark",
            "evaluate",
            "--split",
            "held-out",
            "--output",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "requires --release-evaluation" in result.stderr


def test_evaluate_command_keeps_missing_documents_and_resource_assessment_counts(
    generated, tmp_path
):
    annotations = json.loads((generated / "development" / "annotations.json").read_text())
    predictions = {
        "dataset_version": "synthetic-labs-v1",
        "documents": [
            {
                "document_id": "dev-01",
                "outcome": "succeeded",
                "rows": annotations[0]["rows"],
                "latency_seconds": 2.5,
                "unsupported_summary_claims": 1,
                "flagged_rows": 2,
                "unresolved_rows": 1,
                "provider_cost_usd": 0,
                "student_credit_charge_usd": 0.03,
                "out_of_pocket_usd": 0,
                "resources": [{"name": "provider_input_tokens", "unit": "tokens", "amount": 120}],
            }
        ],
    }
    source = tmp_path / "run.json"
    source.write_text(json.dumps(predictions))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mediflow.benchmark",
            "evaluate",
            "--predictions",
            str(source),
            "--output",
            str(tmp_path / "report"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "report" / "report.json").read_text())
    group = report["groups"]["development/all"]
    assert group["sample_count"] == 20
    assert group["missing_documents"] == group["failures"] == 19
    assert group["strict_rows"]["correct"] == 7
    assert group["strict_rows"]["recall"] < 0.1
    assert group["observations"]["unsupported_summary_claims"] == {
        "total": 1,
        "assessed_documents": 1,
    }
    assert group["observations"]["out_of_pocket_usd"] == {"total": 0, "assessed_documents": 1}
    assert group["observations"]["student_credit_charge_usd"]["total"] == 0.03
    assert group["resources"] == [
        {"name": "provider_input_tokens", "unit": "tokens", "amount": 120}
    ]
