"""Run synthetic page processing once and return only metadata to private Blob."""

import json
import os
import subprocess
import sys
from pathlib import Path

from check_processing_report import check
from hosting_runtime import Storage


def main() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "mediflow.processing",
            "benchmark",
            "/smoke/fixtures",
            "--output",
            "/tmp/processing.json",
        ],
        check=True,
        timeout=260,
    )
    report = json.loads(Path("/tmp/processing.json").read_text())
    check(report)
    report["execution_location"] = "azure-container-apps-job-centralindia"
    report["synthetic_expectations_passed"] = True
    # Workload identity only: no storage keys or SAS tokens are embedded in image.
    Storage().request(
        "blob",
        "ocr-results/" + os.environ["SPIKE_ID"] + ".json",
        "PUT",
        json.dumps(report).encode(),
        {
            "x-ms-blob-type": "BlockBlob",
            "Content-Type": "application/json",
            "If-None-Match": "*",
        },
    )
    print(
        "Synthetic page-processing expectations passed; private result uploaded.",
        flush=True,
    )


if __name__ == "__main__":
    main()
