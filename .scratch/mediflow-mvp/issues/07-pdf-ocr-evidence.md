# 07: Extract bounded page text with native parsing and OCR fallback

Status: in-progress
Progress: actual Azure OCR acceptance passed; temporary resource deletion confirmation pending
Type: task
Blocked by: 03
Estimate: 12 hours
Target week: 3

## Outcome

Produce inspectable page-level source text for both digital and scanned PDFs within the accepted resource envelope.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

Native text/quote agreement is not proof of table association or medical correctness. Do not invent a confidence percentage from parser or OCR heuristics.

## Scope

- Implement native PDF text extraction and a measurable adequacy check that triggers page-level OCR where needed.
- Render/OCR with bounded resolution, page count, memory, concurrency and timeouts; package Tesseract and required document libraries in the worker container.
- Preserve original PDFs, page numbers, native/OCR origin, original text and documented normalization for quote matching.
- Classify laboratory versus unsupported/uncertain document categories without pretending uncertain documents are confidently supported.
- Return explicit unreadable, corrupt, encrypted, unsupported and timeout outcomes. Do not feed embedded document instructions into system/control instructions.

## Acceptance criteria

- [x] Development fixtures for digital, scanned and mixed-content PDFs produce correctly numbered page text and inspectable provenance.
- [x] Known low-quality/unreadable pages yield flags or explicit rejection rather than invented content.
- [x] Ten-page inputs are exercised with measured runtime/memory; limits prevent excessive rendering/OCR consumption.
- [x] Radiology/unsupported examples are rejected for the mandatory laboratory release.
- [x] The OCR container can run in the available Azure job resources established by ticket 01.

## Verification

Run the development fixture set, inspect representative original pages against extracted text, and measure OCR resources in the target container. Keep held-out data unused for tuning.

## Implementation record

Implemented the isolated `mediflow.processing.process_pdf` page-evidence interface, native adequacy routing, sequential real Tesseract adapter, source/provenance retention, conservative category checks, and bounded Linux worker image. Supplemental development fixtures cover mixed-page content, native headings over scans, ten scanned pages, and unreadable raster content. See `docs/document-processing.md`.

Verification: backend suite **56 passed / one host-only real-OCR test skipped**; Ruff formatting/lint and mypy pass. The integration agent separately runs the real-OCR test in the Linux worker container. Focused public-interface tests cover native page numbering/original text, strict whitespace-only quote matching, all ten native development PDFs, corrupt/truncated/encrypted/oversize/over-page rejections, uncertain/unsupported categories, instruction-as-data handling, deadline/resource bounds, descendant termination, and stale OCR output rejection. Real OCR behavior is additionally exercised in the bounded container below. Held-out PDFs and annotations have not been used for extraction tuning.

Measured on 2026-10-23 in the actual worker image, Linux x86-64 under Rosetta on an ARM Mac, Tesseract 5.5.0, **0.5 vCPU / 1 GiB** cgroup limits, PID limit 64:

- All 20 development PDFs succeeded with the expected native/OCR page origins and one-based page numbering.
- All ten negative fixtures rejected as expected. Truncated maps to `corrupt`; password-protected maps to `encrypted`; no invented success was returned for the unreadable scans.
- All five supplemental development fixtures behaved as expected, including mixed-page origins and full-page OCR for native headings over scan bodies.
- Ten scanned pages: **10.71 seconds**, pages 1–10 all OCR. Aggregate container memory peak across the 35-document run: **172,625,920 bytes (164.6 MiB)**; enforced ceiling **1,073,741,824 bytes**. `cpu.max` was `50000 100000`; the container exited successfully without OOM.
- Machine-readable observations: `evaluation/reports/page-processing.json`. This measures page processing/classification, not clinical or strict-row accuracy. Native per-process RSS observations are not aggregate memory measurements.

The initial capped Linux/amd64 run established compatibility with the modeled allocation but did not establish actual Azure execution. That operational gate was subsequently verified in the follow-up below. The durable worker was integrated by ticket 06 and remains fail-closed for the unavailable ticket-08 candidate provider.

## Azure acceptance follow-up — 2026-10-24

The final private Linux/amd64 worker ran as an actual Central India Consumption
Job, pinned by image digest. Execution status was **Succeeded**, and collection
independently checked the actual ARM allocation of **0.5 vCPU / 1 GiB** and the
full expected-outcome report. Parallelism/completion count were one, timeout was
300 seconds, and platform retries were zero.

- All **35** allowlisted fixtures passed: 24 successful supported documents and
  11 explicit expected rejections; no held-out fixtures were used.
- Ten scanned pages produced OCR evidence numbered 1–10 in **10.01 seconds**.
  Mixed native/OCR pages and native headings over scanned bodies passed.
- The successful Azure execution exposed cgroup v1 CPU quota/period
  `50000 100000` (a strict 0.5-core cap), a **1,073,741,824-byte** memory limit,
  and **150,245,376 bytes (143.3 MiB)** aggregate peak memory.
- The follow-up fixed v2-only resource reporting after a failed hosted probe.
  Azure diagnostic runs exposed both 0.5-core and 4-core visible quotas for the
  same requested allocation. The cloud gate permits only these observed values,
  verifies the ARM allocation independently, and preserves the actual measured
  quota in evidence; the offline gate still requires a strict 0.5-core cap.
- The final offline worker passed all 35 outcomes at **0.5 cores / 1 GiB**,
  with **189,313,024 bytes (180.5 MiB)** peak memory and **10.56 seconds** for the
  ten-page scan. The final full Linux backend suite with real Tesseract passed
  **115 tests**, with one opt-in Firebase emulator test skipped. Flutter: **19
  passed**, analysis clean. Mypy: **33 sources**; Ruff lint/format, compileall,
  eight contract artifacts, Dart contract smoke and both cloud guard tests passed.
- Separate Standards and Spec reviews found **0 actionable findings**; see
  [review-07.md](../review-07.md). The successful hosted run resolves their known
  operational acceptance gate. No new unit-test seam was assumed; the existing
  Azure acceptance command provided the failing and successful regression runs.

Sanitized measurements and cleanup evidence:
[`page-processing-azure.json`](../../../evaluation/reports/page-processing-azure.json).
These results measure bounded page processing, not laboratory-row or clinical
accuracy. Raw cloud responses, identities, execution IDs and credentials remain
only in ignored private probe state. Student spending protection was verified On
before mutation; no subscription conversion or public document access was added.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.

- 2026-10-23: Implementation active on isolated `implement/ticket-07` worktree while ticket 04 proceeds independently. Container/resource verification is coordinated by the integration agent.

- 2026-10-23: Integrated with ticket 04. Combined Linux suite: 74 passed, one opt-in emulator skip; real OCR exercised. Standards and Spec implementation reviews found no actionable findings. Azure guard stopped at owner authentication error `AADSTS530035` before mutation; no temporary resources were created. Guarded cloud build/run/collection/cleanup tooling is in `tools/processing_smoke/`. Actual Azure job acceptance remains unchecked.

- 2026-10-23: Owner browser reauthentication succeeded during ticket 05; its independent real private-Blob checks passed and temporary groups were deleted. This does not run or satisfy ticket 07's actual Azure OCR job acceptance gate.
