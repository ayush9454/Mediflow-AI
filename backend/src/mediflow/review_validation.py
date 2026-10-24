"""Validate review corrections against preserved source text and original blockers."""

from pydantic import ValidationError

from mediflow.contracts import (
    AnalysisCandidate,
    ErrorCode,
    IssueSeverity,
    LaboratoryRow,
    ReviewRequest,
)
from mediflow.errors import ApplicationError
from mediflow.laboratory.provider import Citation, PrintedRow
from mediflow.laboratory.validation import flag_conflicts, validate_row
from mediflow.processing.models import PageText

PRINTED_FIELDS = (
    "analyte",
    "result",
    "unit",
    "reference_range",
    "abnormality_flag",
    "collection_date",
)


def invalid() -> ApplicationError:
    return ApplicationError(
        ErrorCode.INVALID_REQUEST,
        422,
        "Correct each blocking issue with source evidence, "
        "or acknowledge it unresolved with a reason.",
    )


def approved_rows(candidate: AnalysisCandidate, body: ReviewRequest) -> tuple[LaboratoryRow, ...]:
    originals = {row.row_id: row for row in candidate.rows}
    if len(originals) != len(candidate.rows):
        raise invalid()
    issues = [*candidate.issues, *(issue for row in candidate.rows for issue in row.issues)]
    known = {issue.issue_id for issue in issues}
    acknowledgements = {item.issue_id for item in body.unresolved_acknowledgements}
    if not acknowledgements <= known:
        raise invalid()
    pages = {
        page.page: PageText(
            page_number=page.page,
            origin=page.extraction_method.value,
            original_text=page.original_text,
            native_text=page.native_text,
            native_adequate=True,
            alphabetic_characters=0,
            printable_ratio=1,
            flags=page.flags,
        )
        for page in candidate.source_pages
    }
    corrections = {}
    changed_fields: dict[str, set[str]] = {}
    for correction in body.corrections:
        original = originals.get(correction.row_id)
        row = correction.corrected_row
        if not original or not row.evidence:
            raise invalid()
        changed = {
            field
            for field in (*PRINTED_FIELDS, "evidence")
            if getattr(original, field) != getattr(row, field)
        }
        if not changed:
            raise invalid()
        for reference in row.evidence:
            if (
                reference.page not in pages
                or pages[reference.page].origin != reference.extraction_method.value
                or not pages[reference.page].supports_quote(reference.quotation)
            ):
                raise invalid()
        try:
            validated = validate_row(
                PrintedRow.model_validate(
                    {
                        **row.model_dump(
                            mode="json", by_alias=True, exclude={"row_id", "issues", "evidence"}
                        ),
                        "resultKind": "qualitative",
                        "evidence": [
                            Citation(page=item.page, quotation=item.quotation).model_dump(
                                by_alias=True
                            )
                            for item in row.evidence
                        ],
                    }
                ),
                0,
                pages,
            )
        except ValidationError:
            raise invalid() from None
        for issue in validated.issues:
            if issue.severity != IssueSeverity.BLOCKING:
                continue
            explicitly_unresolved = any(
                prior.field == issue.field
                and prior.issue_id in acknowledgements
                and prior.severity == IssueSeverity.BLOCKING
                for prior in original.issues
            )
            if issue.field in changed or not explicitly_unresolved:
                raise invalid()
        corrections[row.row_id] = row
        changed_fields[row.row_id] = changed
    proposed = tuple(corrections.get(row.row_id, row) for row in candidate.rows)
    conflicting_ids = {
        row.row_id
        for row in flag_conflicts(tuple(row.model_copy(update={"issues": ()}) for row in proposed))
        if any(issue.code == "conflicting_values" for issue in row.issues)
    }
    for issue in candidate.issues:
        if issue.severity == IssueSeverity.BLOCKING and issue.issue_id not in acknowledgements:
            raise invalid()
    result = []
    for original, row in zip(candidate.rows, proposed, strict=True):
        retained = []
        for issue in original.issues:
            field = {
                "referenceRange": "reference_range",
                "abnormalityFlag": "abnormality_flag",
                "collectionDate": "collection_date",
            }.get(issue.field, issue.field)
            changed = changed_fields.get(row.row_id, set())
            resolved = field in changed or (
                field == "row" and issue.code == "conflicting_values" and bool(changed)
            )
            if issue.code == "conflicting_values" and row.row_id in conflicting_ids:
                resolved = False
            if issue.issue_id in acknowledgements or not resolved:
                retained.append(issue)
            if (
                issue.severity == IssueSeverity.BLOCKING
                and not resolved
                and issue.issue_id not in acknowledgements
            ):
                raise invalid()
        result.append(row.model_copy(update={"issues": tuple(retained)}))
    # A correction must not introduce a new conflicting row silently.
    for uid in conflicting_ids:
        if uid in corrections and not any(
            issue.code == "conflicting_values" and issue.issue_id in acknowledgements
            for issue in originals[uid].issues
        ):
            raise invalid()
    return tuple(result)
