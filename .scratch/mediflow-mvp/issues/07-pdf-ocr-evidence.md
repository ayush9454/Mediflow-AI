# 07: Extract bounded page text with native parsing and OCR fallback

Status: in-progress
Progress: integrated and locally verified; actual Azure job execution awaits owner reauthentication
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
- [ ] The OCR container can run in the available Azure job resources established by ticket 01.

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

The exact capped Linux/amd64 worker fits the allocation modeled in ticket 01. Actual Azure Job execution remains pending and is coordinated by the integration agent; do not equate the local capped-container result with an Azure deployment. Completion remains gated on recording that actual cloud compatibility observation. The durable worker entry point intentionally remains fail-closed for ticket 06.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.

- 2026-10-23: Implementation active on isolated `implement/ticket-07` worktree while ticket 04 proceeds independently. Container/resource verification is coordinated by the integration agent.

- 2026-10-23: Integrated with ticket 04. Combined Linux suite: 74 passed, one opt-in emulator skip; real OCR exercised. Standards and Spec implementation reviews found no actionable findings. Azure guard stopped at owner authentication error `AADSTS530035` before mutation; no temporary resources were created. Guarded cloud build/run/collection/cleanup tooling is in `tools/processing_smoke/`. Actual Azure job acceptance remains unchecked.
