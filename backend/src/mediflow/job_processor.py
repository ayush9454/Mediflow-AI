"""Bounded provider process. The real candidate provider is supplied by ticket 08."""

import argparse
import base64
import json
import os
import signal
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime

from mediflow.contracts import AnalysisCandidate, AnalysisProvenance, ErrorCode, ValidationIssue
from mediflow.jobs import Lease
from mediflow.worker import ProcessingFailure


class SubprocessProcessor:
    def __init__(self, *, environment: str, test_adapter: bool = False) -> None:
        if test_adapter and environment != "test":
            raise ValueError(
                "A test adapter cannot serve development, demo or production analysis."
            )
        self.test_adapter = test_adapter

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
                raise ProcessingFailure(ErrorCode(result["failureCode"]))
            return AnalysisCandidate.model_validate(result)
        except subprocess.TimeoutExpired:
            raise ProcessingFailure(ErrorCode.TEMPORARILY_UNAVAILABLE, transient=True) from None
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
