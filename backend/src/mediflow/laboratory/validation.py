"""Deterministic checks establish traceability, not semantic correctness."""

import re

from mediflow.contracts import EvidenceReference, LaboratoryRow, ValidationIssue
from mediflow.laboratory.provider import PrintedRow
from mediflow.processing import PageText
from mediflow.processing.models import normalize_quote


def flag_conflicts(rows: tuple[LaboratoryRow, ...]) -> tuple[LaboratoryRow, ...]:
    values: dict[tuple[str, str | None], set[tuple[str | None, ...]]] = {}
    for row in rows:
        key = (normalize_quote(row.analyte), row.collection_date)
        values.setdefault(key, set()).add(
            (row.result, row.unit, row.reference_range, row.abnormality_flag)
        )
    return tuple(
        row.model_copy(
            update={
                "issues": (
                    *row.issues,
                    ValidationIssue(
                        issue_id=f"{row.row_id}_conflict",
                        field="row",
                        code="conflicting_values",
                        severity="blocking",
                        message="Repeated analyte/date has different values; verify the source.",
                    ),
                )
            }
        )
        if len(values[(normalize_quote(row.analyte), row.collection_date)]) > 1
        else row
        for row in rows
    )


def validate_row(row: PrintedRow, index: int, pages: dict[int, PageText]) -> LaboratoryRow:
    row_id = f"row_{index}"
    issues = []

    def flag(field: str, code: str, message: str, *, blocking: bool = True) -> None:
        issues.append(
            ValidationIssue(
                issue_id=f"{row_id}_{field}_{code}",
                field=field,
                code=code,
                severity="blocking" if blocking else "warning",
                message=message,
            )
        )

    numeric_looking = re.match(r"^[<>≤≥=+−-]*\s*(?:\d|\.\d)", row.result.strip())
    if (row.result_kind == "numeric" or numeric_looking) and not re.fullmatch(
        r"(?:<=|>=|<|>|≤|≥)?\s*[+−-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+−-]?\d+)?",
        row.result.strip(),
    ):
        flag(
            "result",
            "invalid_numeric_syntax",
            "Numeric text is ambiguous; verify the printed value.",
        )

    if row.collection_date and re.fullmatch(
        r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", row.collection_date
    ):
        flag(
            "collection_date",
            "ambiguous_date",
            "Date order was not interpreted; inspect the printed date.",
            blocking=False,
        )

    for field in ("unit", "reference_range", "abnormality_flag", "collection_date"):
        if getattr(row, field) is None:
            issues.append(
                ValidationIssue(
                    issue_id=f"{row_id}_{field}_not_printed",
                    field=field,
                    code="not_printed",
                    severity="warning",
                    message="No printed value extracted; verify the original source.",
                )
            )
    evidence = []
    for reference in row.evidence:
        page = pages.get(reference.page)
        if page is None:
            flag("evidence", "invalid_evidence_page", "Citation refers to an absent source page.")
            continue
        if not page.supports_quote(reference.quotation):
            flag("evidence", "evidence_mismatch", "Quotation does not match the cited page text.")
            continue
        evidence.append(
            EvidenceReference(
                page=reference.page,
                quotation=reference.quotation,
                extraction_method=page.origin,
            )
        )
    if not evidence:
        flag("evidence", "missing_evidence", "No citation identifies an available source page.")
    supported_quotes = [
        normalize_quote(item.quotation)
        for item in evidence
        if pages[item.page].supports_quote(item.quotation)
    ]
    for field in (
        "analyte",
        "result",
        "unit",
        "reference_range",
        "abnormality_flag",
        "collection_date",
    ):
        value = getattr(row, field)
        if value is None:
            continue
        # Token boundaries prevent '0.5' from claiming support from '0.50'.
        pattern = r"(?<![\w.,<>=+−-])" + re.escape(normalize_quote(value)) + r"(?![\w.,])"
        if not any(re.search(pattern, quote) for quote in supported_quotes):
            flag(
                field,
                "field_not_in_evidence",
                "Printed field is not supported by a valid citation.",
            )
    if any(
        pages[reference.page].origin == "ocr"
        for reference in row.evidence
        if reference.page in pages
    ):
        issues.append(
            ValidationIssue(
                issue_id=f"{row_id}_ocr",
                field="evidence",
                code="ocr_requires_visual_review",
                severity="warning",
                message="OCR text may differ from the original page.",
            )
        )
    return LaboratoryRow(
        row_id=row_id,
        analyte=row.analyte,
        result=row.result,
        unit=row.unit,
        reference_range=row.reference_range,
        abnormality_flag=row.abnormality_flag,
        collection_date=row.collection_date,
        evidence=tuple(evidence),
        issues=tuple(issues),
    )
