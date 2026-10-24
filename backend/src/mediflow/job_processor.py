"""Deadline-bounded PDF and laboratory extraction inside the durable worker."""

import argparse
import base64
import json
import os
import signal
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime

from mediflow.config import Settings
from mediflow.contracts import AnalysisCandidate, AnalysisProvenance, ErrorCode, ValidationIssue
from mediflow.jobs import Lease
from mediflow.laboratory import GeminiProvider, extract_laboratory
from mediflow.laboratory.provider import CandidateProvider
from mediflow.processing import Limits, process_pdf
from mediflow.worker import ProcessingFailure


class LaboratoryProcessor:
    def __init__(self, provider: CandidateProvider):
        self.provider = provider

    def __call__(self, lease: Lease, source: bytes) -> AnalysisCandidate:
        remaining = (lease.deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 1:
            raise ProcessingFailure(ErrorCode.TEMPORARILY_UNAVAILABLE, transient=True)
        document = process_pdf(source, limits=Limits(deadline_seconds=min(200, remaining - 1)))
        if document.outcome == "failed":
            raise ProcessingFailure(ErrorCode.TEMPORARILY_UNAVAILABLE, transient=True)
        return extract_laboratory(lease, document, self.provider)


class SubprocessProcessor:
    def __init__(self, *, environment: str, test_adapter: bool = False) -> None:
        if test_adapter and environment != "test":
            raise ValueError(
                "A test adapter cannot serve development, demo or production analysis."
            )
        self.test_adapter = test_adapter
        self.environment = environment

    def __call__(self, lease: Lease, source: bytes) -> AnalysisCandidate:
        remaining = (lease.deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise ProcessingFailure(ErrorCode.TEMPORARILY_UNAVAILABLE, transient=True)
        payload = asdict(lease)
        payload["deadline"] = lease.deadline.isoformat()
        command = [sys.executable, "-m", "mediflow.job_processor"]
        if self.test_adapter:
            command.append("--test-adapter")
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=dict(os.environ, MEDIFLOW_ENV=self.environment),
        )
        try:
            stdout, _ = process.communicate(
                json.dumps(
                    {
                        "lease": payload,
                        "source": base64.b64encode(source).decode(),
                    }
                ).encode(),
                timeout=min(remaining, 270),
            )
            if process.returncode != 0 or len(stdout) > 2_000_000:
                raise ProcessingFailure(ErrorCode.INTERNAL_ERROR)
            result = json.loads(stdout)
            if "failureCode" in result:
                raise ProcessingFailure(
                    ErrorCode(result["failureCode"]), transient=result.get("transient") is True
                )
            return AnalysisCandidate.model_validate(result)
        except subprocess.TimeoutExpired:
            raise ProcessingFailure(ErrorCode.TEMPORARILY_UNAVAILABLE, transient=True) from None
        except (ValueError, KeyError, TypeError):
            raise ProcessingFailure(ErrorCode.INTERNAL_ERROR) from None
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-adapter", action="store_true")
    arguments = parser.parse_args()
    if not arguments.test_adapter:
        try:
            provider = GeminiProvider.from_settings(Settings.from_environment())
            data = json.loads(sys.stdin.buffer.read(14_000_000))
            lease = Lease(
                **{**data["lease"], "deadline": datetime.fromisoformat(data["lease"]["deadline"])}
            )
            result = LaboratoryProcessor(provider)(
                lease, base64.b64decode(data["source"], validate=True)
            )
            print(result.model_dump_json(by_alias=True))
        except ProcessingFailure as failure:
            print(json.dumps({"failureCode": failure.code.value, "transient": failure.transient}))
        except (ValueError, KeyError, TypeError, OSError):
            print(json.dumps({"failureCode": ErrorCode.INTERNAL_ERROR.value, "transient": False}))
        return
    if os.getenv("MEDIFLOW_ENV") != "test":
        print(json.dumps({"failureCode": ErrorCode.INTEGRATION_NOT_CONFIGURED.value}))
        return
    data = json.loads(sys.stdin.buffer.read(14_000_000))
    lease = data["lease"]
    # Deliberately no fabricated laboratory rows, quotations or summaries.
    candidate = AnalysisCandidate(
        analysis_id=lease["analysis_id"],
        report_id=lease["report_id"],
        job_id=lease["job_id"],
        version=lease["analysis_version"],
        rows=(),
        created_at=datetime.now(UTC),
        issues=(
            ValidationIssue(
                issue_id="test_adapter",
                field="analysis",
                code="test_adapter",
                severity="blocking",
                message="Test adapter; no clinical analysis.",
            ),
        ),
        provenance=AnalysisProvenance(
            pipeline_version=lease["pipeline_version"],
            prompt_version="test-only",
            model_provider="test-only",
            model_version="test-only",
        ),
    )
    print(candidate.model_dump_json(by_alias=True))


if __name__ == "__main__":
    main()
