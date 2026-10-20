# 15: Deliver signed Android APK, deployment documentation and recorded demo

Status: ready-for-agent
Type: task
Blocked by: 01, 14
Estimate: 8 hours
Target week: 8

## Outcome

Make the agreed college project installable, reviewable and reproducible within the ₹0 distribution plan.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

Ticket 14 must have no unresolved security/review blockers. Any unmet quality target remains explicit in the handoff and requires a documented user decision before calling the mandatory release complete. Hosting availability remains subject to student credits/renewal.

## Scope

- Produce a signed Android release APK; keep signing keys/passwords private and document owner/backup/update procedure without exposing values.
- Share via a free APK release/download route for classmates/examiners, targeting up to twenty authorized devices under applicable Android limited-distribution requirements. Recheck current regional verification/setup rules.
- Write local development, hosted provisioning/deployment/rollback, environment-name, seed/reset, expiry/export and student-benefit renewal instructions.
- Deliver architecture diagram, OpenAPI/API docs, dataset/evaluation commands and results, resource/cost notes, limitations and known missed targets.
- Record patient upload → hosted extraction → administrator assignment → doctor evidence/review → approved patient result on the actual installed APK, including proof the development laptop is off.
- Verify the documented setup from a clean environment or by an independent reader without including credentials or real patient data.

## Acceptance criteria

- [ ] Signed APK installs and completes the workflow on a representative Android device over the internet while the development laptop is off.
- [ ] Release contains no debug-auth bypass, test extraction adapter, API secret or signing material.
- [ ] All required handoff artifacts are linked from the project README; evaluation numbers match ticket 14.
- [ ] Distribution costs ₹0 and does not assume a newly paid Google Play developer account.
- [ ] Setup/deployment, expiry/credit limits and recovery instructions are reproducible; recording uses real hosted processing and synthetic records.

## Verification

Run a clean release install and laptop-off end-to-end smoke check; inspect packaged configuration and documentation links; reproduce the evaluation command and review the complete recording.

## Implementation record

Not started. Record actual changes, verification commands/results, measured findings, and any remaining gate here. A readiness label does not imply completion or override the Blocked by line.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.
