"""Page evidence to immutable laboratory candidates; never clinical approval."""

from datetime import UTC, datetime

from mediflow.contracts import (
    AnalysisCandidate,
    AnalysisProvenance,
    ErrorCode,
    SourcePage,
    ValidationIssue,
)
from mediflow.jobs import Lease
from mediflow.laboratory.provider import PROMPT_VERSION, CandidateProvider, GeminiProvider
from mediflow.laboratory.validation import flag_conflicts, validate_row
from mediflow.processing import ProcessingResult
from mediflow.worker import ProcessingFailure

__all__ = ["GeminiProvider", "extract_laboratory"]


def extract_laboratory(
    lease: Lease, document: ProcessingResult, provider: CandidateProvider
) -> AnalysisCandidate:
    remaining = (lease.deadline - datetime.now(UTC)).total_seconds()
    if remaining <= 0:
        raise ProcessingFailure(ErrorCode.TEMPORARILY_UNAVAILABLE, transient=True)
    if (
        document.outcome != "succeeded"
        or document.category != "laboratory"
        or not document.pages
        or len(document.pages) > 10
        or [p.page_number for p in document.pages] != list(range(1, len(document.pages) + 1))
    ):
        raise ProcessingFailure(ErrorCode.INVALID_UPLOAD)
    if sum(len(p.original_text) for p in document.pages) > 60_000:
        raise ProcessingFailure(ErrorCode.PROCESSING_LIMIT_EXCEEDED)
    response = provider.extract(document.pages, timeout=min(40, remaining))
    pages = {page.page_number: page for page in document.pages}
    rows = flag_conflicts(
        tuple(
            validate_row(row, index, pages) for index, row in enumerate(response.extraction.rows, 1)
        )
    )
    candidate = AnalysisCandidate(
        analysis_id=lease.analysis_id,
        report_id=lease.report_id,
        job_id=lease.job_id,
        version=lease.analysis_version,
        rows=rows,
        created_at=datetime.now(UTC),
        provider_output=response.output_json,
        issues=tuple(
            ValidationIssue(
                issue_id=f"page_{page.page_number}_{flag}",
                field="source_pages",
                code=flag,
                severity="warning",
                message="Source page requires visual verification.",
            )
            for page in document.pages
            for flag in page.flags
        ),
        summary=(
            f"Extracted {len(rows)} laboratory row(s) from {len(document.pages)} page(s). "
            f"{sum(bool(row.issues) for row in rows)} row(s) have validation issues. "
            "Doctor review is required."
        ),
        source_pages=tuple(
            SourcePage(
                page=page.page_number,
                extraction_method=page.origin,
                original_text=page.original_text,
                native_text=page.native_text,
                flags=page.flags,
            )
            for page in document.pages
        ),
        provenance=AnalysisProvenance(
            pipeline_version=lease.pipeline_version,
            prompt_version=PROMPT_VERSION,
            model_provider=provider.name,
            model_version=response.model_version,
            model_name=provider.model,
            usage=response.usage,
            configuration=provider.configuration,
            source_sha256=document.source_sha256,
            page_processing_seconds=document.elapsed_seconds,
            page_processing_peak_rss_bytes=document.peak_rss_bytes,
        ),
    )
    # Keep the whole transaction record below Firestore's 1-MiB document limit.
    if len(candidate.model_dump_json(by_alias=True).encode()) > 750_000:
        raise ProcessingFailure(ErrorCode.PROCESSING_LIMIT_EXCEEDED)
    return candidate
