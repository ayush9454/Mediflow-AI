# 03: Build synthetic PDFs, independent annotations and evaluation harness

Status: ready-for-agent
Type: task
Blocked by: 02
Estimate: 8 hours
Target week: 1–2

## Outcome

Make extraction quality measurable before prompts and processing behavior are tuned.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

The small synthetic dataset supports a college benchmark, not a clinical effectiveness claim. If package selection affects generated PDFs, keep the fixture schema stable.

## Scope

- Create a reproducible manifest of forty synthetic documents: twenty development (ten digital/ten scanned), ten valid held-out (five digital/five scanned), and ten negative cases.
- Generate expected fields from independently authored fixture definitions. Include numeric/qualitative values, inequalities, missing units/ranges, printed flags, repeated analytes, collection dates and multipage tables.
- Create reproducibly degraded scanned versions and negative cases covering unsupported category/language, corrupt/unreadable PDFs, password protection and upload limits. Include realistic size/page-limit fixtures without adding large unnecessary binaries to source control.
- Implement strict row matching, row precision/recall, per-field metrics, evidence checks and split-specific reports. Document formatting-only normalization; omitted and additional rows must count.
- Freeze/version the held-out set and keep it out of model prompt examples and tuning runs. Add result fields for latency, failures, unsupported summary claims and consumed resources.

## Acceptance criteria

- [ ] Manifest counts match the agreed 20/10/10 split, and all names/identifiers/content are synthetic.
- [ ] Ground truth is independent of AI output and traceable to fixture definitions.
- [ ] A known missing row lowers recall; an invented row lowers precision; a changed unit/value/inequality fails the strict match.
- [ ] One command regenerates fixtures and produces a machine-readable and Markdown evaluation report with sample counts and digital/scanned breakdowns.
- [ ] The held-out manifest/version is fixed before extraction tuning begins; no measured accuracy claim is made yet.

## Verification

Run harness checks using deliberately correct, omitted, extra and altered rows. Inspect representative rendered digital/scanned PDFs and verify annotations against their source fixture.

## Implementation record

Not started. Record actual changes, verification commands/results, measured findings, and any remaining gate here. A readiness label does not imply completion or override the Blocked by line.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.
