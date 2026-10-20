from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from mediflow.contracts import (
    EvidenceReference,
    LaboratoryRow,
    ProcessingJob,
    ReportRegistration,
    ReportResult,
    ReviewRequest,
    RowCorrection,
    ValidationIssue,
)


def row(**overrides):
    values = dict(
        row_id="row_1",
        analyte="Synthetic Marker",
        result="<0.50",
        unit=None,
        reference_range=None,
        evidence=(
            EvidenceReference(page=1, quotation="Synthetic Marker <0.50", extraction_method="ocr"),
        ),
    )
    values.update(overrides)
    return LaboratoryRow(**values)


def test_printed_values_remain_exact_and_missing_ranges_are_not_inferred():
    value = row(result="  <0.50 ", unit="SYN-U", reference_range="0.00–1.00")
    payload = value.model_dump(mode="json", by_alias=True)
    assert payload["result"] == "  <0.50 "
    assert payload["referenceRange"] == "0.00–1.00"
    assert row().reference_range is None
    with pytest.raises(ValidationError):
        row(result=0.50)


def test_ungrounded_row_requires_an_explicit_blocking_issue():
    with pytest.raises(ValidationError):
        row(evidence=())
    issue = ValidationIssue(
        issue_id="issue_1",
        field="evidence",
        code="missing_evidence",
        severity="blocking",
        message="Original page needs review.",
    )
    assert row(evidence=(), issues=(issue,)).issues == (issue,)


@pytest.mark.parametrize("page", [0, 11])
def test_evidence_cannot_point_outside_document_scope(page):
    with pytest.raises(ValidationError):
        EvidenceReference(page=page, quotation="Synthetic text", extraction_method="native")


def test_original_candidate_is_frozen_and_correction_has_same_identity():
    original = row()
    with pytest.raises(ValidationError):
        original.result = "99"
    with pytest.raises(ValidationError):
        RowCorrection(row_id="row_other", corrected_row=original, reason="Source correction")


def test_rejection_requires_a_reason_and_cannot_apply_hidden_corrections():
    with pytest.raises(ValidationError):
        ReviewRequest(
            analysis_id="analysis_1",
            expected_analysis_version=1,
            expected_case_version=1,
            expected_review_version=0,
            decision="rejected",
        )
    with pytest.raises(ValidationError):
        ReviewRequest(
            analysis_id="analysis_1",
            expected_analysis_version=1,
            expected_case_version=1,
            expected_review_version=0,
            decision="rejected",
            comment=" ",
            corrections=(),
        )
    correction = RowCorrection(row_id="row_1", corrected_row=row(), reason="Source checked")
    with pytest.raises(ValidationError):
        ReviewRequest(
            analysis_id="analysis_1",
            expected_analysis_version=1,
            expected_case_version=1,
            expected_review_version=0,
            decision="rejected",
            comment="Not reliable",
            corrections=(correction,),
        )


def test_duplicate_corrections_are_rejected_before_a_review_can_be_saved():
    correction = RowCorrection(row_id="row_1", corrected_row=row(), reason="Source checked")
    with pytest.raises(ValidationError):
        ReviewRequest(
            analysis_id="analysis_1",
            expected_analysis_version=1,
            expected_case_version=1,
            expected_review_version=0,
            decision="approved",
            corrections=(correction, correction),
        )


def test_patient_result_cannot_contain_a_draft_or_ambiguous_kind():
    with pytest.raises(ValidationError):
        ReportResult(kind="approved", approved=None, draft=None)
    with pytest.raises(ValidationError):
        ReportResult(kind="draft", approved=None, draft=None)


def test_registration_cannot_supply_patient_identity_or_opt_out_of_synthetic_scope():
    base = dict(file_name="synthetic.pdf", byte_count=100, synthetic_data_acknowledged=True)
    with pytest.raises(ValidationError):
        ReportRegistration(**base, patient_id="another_patient")
    with pytest.raises(ValidationError):
        ReportRegistration(**dict(base, synthetic_data_acknowledged=False))
    with pytest.raises(ValidationError):
        ReportRegistration(**dict(base, byte_count=10_000_001))


def test_job_attempt_ceiling_and_timezone_are_explicit():
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        ProcessingJob(
            job_id="job_1",
            report_id="report_1",
            status="processing",
            attempt_count=4,
            created_at=now,
            updated_at=now,
        )
    with pytest.raises(ValidationError):
        ProcessingJob(
            job_id="job_1",
            report_id="report_1",
            status="processing",
            created_at=now.replace(tzinfo=None),
            updated_at=now,
        )
