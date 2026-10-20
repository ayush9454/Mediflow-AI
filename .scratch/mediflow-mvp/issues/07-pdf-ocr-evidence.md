# 07: Extract bounded page text with native parsing and OCR fallback

Status: ready-for-agent
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

- [ ] Development fixtures for digital, scanned and mixed-content PDFs produce correctly numbered page text and inspectable provenance.
- [ ] Known low-quality/unreadable pages yield flags or explicit rejection rather than invented content.
- [ ] Ten-page inputs are exercised with measured runtime/memory; limits prevent excessive rendering/OCR consumption.
- [ ] Radiology/unsupported examples are rejected for the mandatory laboratory release.
- [ ] The OCR container can run in the available Azure job resources established by ticket 01.

## Verification

Run the development fixture set, inspect representative original pages against extracted text, and measure OCR resources in the target container. Keep held-out data unused for tuning.

## Implementation record

Not started. Record actual changes, verification commands/results, measured findings, and any remaining gate here. A readiness label does not imply completion or override the Blocked by line.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.
