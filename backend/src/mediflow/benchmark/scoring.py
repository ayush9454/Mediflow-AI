"""Offline strict matching. Row identifiers/order never determine correctness."""

from collections import Counter
from collections.abc import Callable, Sequence
from statistics import mean
from typing import Any

from mediflow.benchmark.models import DATASET_VERSION, Annotation, Prediction
from mediflow.contracts import LaboratoryRow

FIELDS = (
    "analyte",
    "result",
    "unit",
    "reference_range",
    "abnormality_flag",
    "collection_date",
)


def normalize(value: str | None) -> str | None:
    """Only trim/collapse whitespace, including line breaks and nonbreaking spaces."""
    return " ".join(value.split()) if value is not None else None


def _values(row: LaboratoryRow) -> tuple[str | None, ...]:
    return tuple(normalize(getattr(row, field)) for field in FIELDS)


def _supported(gold: LaboratoryRow, predicted: LaboratoryRow, pages: tuple[str, ...]) -> bool:
    # Every supplied citation must point to a real page and its text. At least one
    # must include the whole annotated row, on the correct page (not another row).
    if not predicted.evidence:
        return False
    for evidence in predicted.evidence:
        if not 1 <= evidence.page <= len(pages):
            return False
        quote = normalize(evidence.quotation)
        if not quote or quote not in (normalize(pages[evidence.page - 1]) or ""):
            return False
    return any(
        actual.page == expected.page
        and (normalize(expected.quotation) or "") in (normalize(actual.quotation) or "")
        for actual in predicted.evidence
        for expected in gold.evidence
    )


def _matching_count(
    expected: Sequence[LaboratoryRow],
    predicted: Sequence[LaboratoryRow],
    matches: Callable[[LaboratoryRow, LaboratoryRow], bool],
) -> int:
    """Maximum bipartite matching prevents greedy reuse of repeated analytes."""
    edges = [[i for i, gold in enumerate(expected) if matches(gold, row)] for row in predicted]
    owners: dict[int, int] = {}

    def assign(candidate: int, seen: set[int]) -> bool:
        for target in edges[candidate]:
            if target in seen:
                continue
            seen.add(target)
            if target not in owners or assign(owners[target], seen):
                owners[target] = candidate
                return True
        return False

    return sum(assign(i, set()) for i in range(len(predicted)))


def _metric(expected: int, predicted: int, correct: int) -> dict[str, int | float | None]:
    return {
        "expected": expected,
        "predicted": predicted,
        "correct": correct,
        "precision": correct / predicted if predicted else None,
        "recall": correct / expected if expected else None,
    }


def _group(documents: Sequence[Annotation], predictions: dict[str, Prediction]) -> dict[str, Any]:
    expected_count = predicted_count = correct_count = evidence_mismatches = 0
    fields: Counter[str] = Counter()
    failures = classification_failures = missing = 0
    observed = []
    for document in documents:
        prediction = predictions.get(document.document_id)
        rows = prediction.rows if prediction else ()
        eligible = bool(
            prediction
            and prediction.outcome == "succeeded"
            and document.expected_outcome == "succeeded"
        )
        expected_count += len(document.rows)
        predicted_count += len(rows)

        def strict_match(
            gold: LaboratoryRow,
            row: LaboratoryRow,
            eligible: bool = eligible,
            document: Annotation = document,
        ) -> bool:
            return (
                eligible and _values(gold) == _values(row) and _supported(gold, row, document.pages)
            )

        correct_count += _matching_count(document.rows, rows, strict_match)
        for field in FIELDS:
            # Independent multiset matches scoped to analyte + collection date.
            # The date score itself is scoped only to analyte. This does not
            # claim that independent field matches make a correct complete row.
            def key(row: LaboratoryRow, field: str = field) -> tuple[str | None, ...]:
                identity: tuple[str | None, ...] = (normalize(row.analyte),)
                if field != "collection_date":
                    identity += (normalize(row.collection_date),)
                return (*identity, normalize(getattr(row, field)))

            if eligible:
                fields[field] += sum(
                    (Counter(map(key, document.rows)) & Counter(map(key, rows))).values()
                )
        evidence_mismatches += sum(
            not any(
                _values(gold) == _values(row) and _supported(gold, row, document.pages)
                for gold in document.rows
            )
            for row in rows
        )
        missing += prediction is None
        failures += prediction is None or prediction.outcome == "failed"
        classification_failures += (
            prediction is None
            or prediction.outcome != document.expected_outcome
            or (
                document.expected_outcome == "rejected"
                and prediction.rejection_reason != document.rejection_reason
            )
        )
        if prediction:
            observed.append(prediction)
    latencies = [p.latency_seconds for p in observed if p.latency_seconds is not None]
    resources: dict[tuple[str, str], float] = {}
    for prediction in observed:
        for resource in prediction.resources:
            key_pair = resource.name, resource.unit
            resources[key_pair] = resources.get(key_pair, 0.0) + resource.amount
    observations = {}
    for field in (
        "unsupported_summary_claims",
        "flagged_rows",
        "unresolved_rows",
        "provider_cost_usd",
        "student_credit_charge_usd",
        "out_of_pocket_usd",
    ):
        values = [getattr(p, field) for p in observed if getattr(p, field) is not None]
        observations[field] = {
            "total": sum(values) if values else None,
            "assessed_documents": len(values),
        }
    return {
        "sample_count": len(documents),
        "submitted_documents": len(observed),
        "missing_documents": missing,
        "failures": failures,
        "failure_rate": failures / len(documents) if documents else None,
        "classification_failures": classification_failures,
        "strict_rows": _metric(expected_count, predicted_count, correct_count),
        "fields": {
            field: _metric(expected_count, predicted_count, fields[field]) for field in FIELDS
        },
        "evidence_mismatches": evidence_mismatches,
        "latency_seconds": {
            "measured_documents": len(latencies),
            "mean": mean(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "observations": observations,
        "resources": [
            {"name": name, "unit": unit, "amount": amount}
            for (name, unit), amount in sorted(resources.items())
        ],
        "resource_measured_documents": sum(bool(p.resources) for p in observed),
    }


def evaluate(
    annotations: Sequence[Annotation | dict[str, Any]],
    predictions: Sequence[Prediction | dict[str, Any]],
) -> dict[str, Any]:
    """Score every selected annotation; missing submissions remain in denominators."""
    documents = [Annotation.model_validate(doc) for doc in annotations]
    submitted = [Prediction.model_validate(prediction) for prediction in predictions]
    expected_ids = {doc.document_id for doc in documents}
    ids = [prediction.document_id for prediction in submitted]
    if len(expected_ids) != len(documents) or len(set(ids)) != len(ids):
        raise ValueError("Duplicate document IDs are not allowed.")
    if set(ids) - expected_ids:
        raise ValueError("Predictions contain documents outside the selected split.")
    index = {prediction.document_id: prediction for prediction in submitted}
    groups = {}
    for split in ("development", "held-out", "negative"):
        for medium in ("all", "digital", "scanned"):
            selection = [
                doc
                for doc in documents
                if doc.split == split and (medium == "all" or doc.medium == medium)
            ]
            groups[f"{split}/{medium}"] = _group(selection, index)
    return {"dataset_version": DATASET_VERSION, "mode": "extraction_evaluation", "groups": groups}
