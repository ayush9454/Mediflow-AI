"""Fail the offline container gate on wrong outcomes or unenforced cgroup limits."""

import argparse
import json
from pathlib import Path
from typing import Any

AZURE_CONSUMPTION_CPU_QUOTAS = ("50000 100000", "400000 100000")


def check(report: dict[str, Any], *, allowed_cpu_max: tuple[str, ...] = ("50000 100000",)) -> None:
    if report.get("held_out_used") is not False:
        raise ValueError("Processing verification must exclude held-out data.")
    if report.get("clinical_or_row_accuracy_measured") is not False:
        raise ValueError("Page processing does not measure clinical or row accuracy.")
    if report.get("cgroup_memory_max") != str(1024**3):
        raise ValueError("Worker verification requires the 1 GiB memory limit.")
    if not 0 < int(report.get("cgroup_memory_peak") or 0) <= 1024**3:
        raise ValueError("Aggregate cgroup peak memory is missing or exceeds the limit.")
    if report.get("cgroup_cpu_max") not in allowed_cpu_max:
        raise ValueError(f"Worker verification requires CPU quota/period in {allowed_cpu_max}.")
    documents = report.get("documents", [])
    observed = {document["document_id"]: document for document in documents}
    negative_reasons = (
        "corrupt",
        "corrupt",
        "unreadable",
        "unreadable",
        "unsupported_category",
        "unsupported_category",
        "unsupported_language",
        "encrypted",
        "over_size",
        "over_pages",
    )
    expected = {f"dev-{number:02d}": None for number in range(1, 21)}
    expected.update(
        {f"neg-{number:02d}": reason for number, reason in enumerate(negative_reasons, 1)}
    )
    expected.update(
        {f"supplemental-{name}": None for name in ("mixed", "overlay", "scanned", "ten-page")}
    )
    expected["supplemental-unreadable"] = "unreadable"
    if set(observed) != set(expected) or len(documents) != len(expected):
        raise ValueError(
            "Expected exactly 35 unique development/negative/supplemental observations."
        )
    for identifier, reason in expected.items():
        document = observed[identifier]
        outcome = "succeeded" if reason is None else "rejected"
        if document["outcome"] != outcome or document["reason"] != reason:
            raise ValueError(f"Unexpected processing outcome for {identifier}.")
        if reason is None and not document["pages"]:
            raise ValueError(f"Successful document has no page evidence: {identifier}.")
        if reason is None and [page["page_number"] for page in document["pages"]] != list(
            range(1, len(document["pages"]) + 1)
        ):
            raise ValueError(f"Nonsequential page evidence: {identifier}.")
    ten_pages = observed["supplemental-ten-page"]["pages"]
    if len(ten_pages) != 10 or any(page["origin"] != "ocr" for page in ten_pages):
        raise ValueError("Ten-page OCR input was not fully exercised.")
    if [page["origin"] for page in observed["supplemental-mixed"]["pages"]] != ["native", "ocr"]:
        raise ValueError("Mixed-content processing did not exercise both origins.")
    if observed["supplemental-overlay"]["pages"][0]["origin"] != "ocr":
        raise ValueError("A native heading suppressed OCR of the scanned table.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        check(json.loads(args.report.read_text()))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"processing verification: {error}\n")
    print("PASS: 35 outcomes, numbered mixed/ten-page evidence, and enforced CPU/memory limits.")


if __name__ == "__main__":
    main()
