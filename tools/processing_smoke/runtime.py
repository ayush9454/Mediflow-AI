"""Run synthetic page processing once and return only metadata to private Blob."""

import json
import os
import subprocess
import sys
from pathlib import Path

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
    expected_rejections = {
        "neg-01": "corrupt",
        "neg-02": "corrupt",
        "neg-03": "unreadable",
        "neg-04": "unreadable",
        "neg-05": "unsupported_category",
        "neg-06": "unsupported_category",
        "neg-07": "unsupported_language",
        "neg-08": "encrypted",
        "neg-09": "over_size",
        "neg-10": "over_pages",
        "supplemental-unreadable": "unreadable",
    }
    for document in report["documents"]:
        expected_reason = expected_rejections.get(document["document_id"])
        expected_outcome = "rejected" if expected_reason else "succeeded"
        if document["outcome"] != expected_outcome or document["reason"] != expected_reason:
            raise RuntimeError("Synthetic processing outcome disagrees with expected fixture")
    ten_page = next(d for d in report["documents"] if d["document_id"] == "supplemental-ten-page")
    if [p["page_number"] for p in ten_page["pages"]] != list(range(1, 11)):
        raise RuntimeError("Ten-page evidence numbering mismatch")
    if any(p["origin"] != "ocr" for p in ten_page["pages"]):
        raise RuntimeError("Ten-page scan requires real OCR")
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
