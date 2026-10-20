# 08: Implement structured laboratory extraction, validation and summaries

Status: ready-for-agent
Type: task
Blocked by: 03, 06, 07
Estimate: 12 hours
Target week: 4

## Outcome

Turn page text into versioned, evidence-linked laboratory candidates without unsupported clinical interpretation.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

Do not log full model/document payloads. The 95% target is measured formally in ticket 14; do not present development performance as held-out accuracy.

## Scope

- Integrate the current benchmarked Gemini free model through a provider interface, versioned schema/prompt/model settings and server-only credentials.
- Extract printed analyte, numeric/qualitative result, unit, interval, abnormality flag, collection date and source page/quote. Preserve original strings, inequalities, uncertainty and missing fields.
- Validate schema/types, numeric syntax, page bounds, quote matching and detectable source inconsistencies; attach explicit field/row issues. Do not claim these checks establish semantic correctness.
- Generate source-grounded descriptive summaries from structured information; no diagnosis, treatment advice, inferred ranges, unit conversions or fabricated confidence percentages.
- Persist immutable candidate data and version/config/usage metadata through the durable job commit path.
- Translate quota/unavailable/provider/schema failures into safe states and bounded retry classifications. Treat document prompt injection as untrusted content and give the model no tools or clinical write access.

## Acceptance criteria

- [ ] Development examples return schema-valid candidates with preserved printed data and valid source references, or an explicit processing failure.
- [ ] Missing/conflicting information is flagged rather than filled with assumptions.
- [ ] AI/provider versions and extraction resource use can be traced for every completed candidate.
- [ ] Quota exhaustion/unavailability never returns a canned successful analysis or silently uses a paid model.
- [ ] Development evaluation reports and error analysis guide improvements without using held-out examples.

## Verification

Run development benchmarks and cases for omitted ranges, inequalities, qualitative/negative results, wrong evidence, schema failure, prompt-injection text and quota exhaustion. Inspect summaries for unsupported claims.

## Implementation record

Not started. Record actual changes, verification commands/results, measured findings, and any remaining gate here. A readiness label does not imply completion or override the Blocked by line.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.
