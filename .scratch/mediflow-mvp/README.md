# MediFlow AI: agreed project plan

Agreed: 2026-10-20

A ₹0 college project: an Android app with a hosted backend for evidence-linked extraction from synthetic laboratory PDFs and simulated doctor review.

- [Specification](spec.md): scope, behavior, architecture, permissions, lifecycle, and acceptance criteria.
- [Eight-week roadmap](roadmap.md): milestones, effort, dependencies, and release gates.
- [Decisions and source checks](decisions.md): interview decisions, hosting constraints, and official references.
- [Implementation tickets](#implementation-tickets): one numbered Markdown file per ticket.

This directory records the shared understanding confirmed by the user. The original planning task created no application or infrastructure. The user subsequently authorized implementation; see the ticket index for current progress and validation gates.

## Implementation tickets

| Ticket | Work | Status | Blocked by |
| --- | --- | --- | --- |
| [01](issues/01-verify-student-hosting.md) | Verify student hosting and deploy a minimal cloud slice | completed | None |
| [02](issues/02-foundation-contracts-ci.md) | App/backend foundation, contracts, and checks | completed | None |
| [03](issues/03-synthetic-dataset-evaluation.md) | Synthetic documents, annotations, and evaluation harness | completed | 02 |
| [04](issues/04-authentication-authorization.md) | Authentication, seeded accounts, and permissions | completed | 02 |
| [05](issues/05-private-report-upload.md) | Private upload, verification, duplicates, and upload limits | completed | 01, 04 |
| [06](issues/06-durable-processing-jobs.md) | Durable jobs, queue delivery, retries, and recovery | completed | 01, 04 |
| [07](issues/07-pdf-ocr-evidence.md) | Native PDF extraction, OCR, and page evidence | completed | 03 |
| [08](issues/08-laboratory-ai-validation.md) | Laboratory extraction, validation, and summaries | completed | 03, 06, 07 |
| [09](issues/09-android-upload-status.md) | Android upload and processing-status workflow | completed | 05, 06 |
| [10](issues/10-evidence-result-viewer.md) | Extracted results and PDF evidence viewer | completed | 08, 09 |
| [11](issues/11-assignment-doctor-review.md) | Administrator assignment and versioned doctor review | completed | 04, 10 |
| [12](issues/12-role-workflows-patient-results.md) | Complete role workflows and approved patient results | ready-for-agent | 09, 11 |
| [13](issues/13-retention-operations.md) | Retention, expiry, operational limits, and diagnostics | ready-for-agent | 05, 06, 08, 11 |
| [14](issues/14-release-evaluation-hardening.md) | Held-out evaluation and release verification | ready-for-agent | 03, 07, 08, 10, 11, 12, 13 |
| [15](issues/15-android-release-handoff.md) | Signed APK, documentation, and recorded demonstration | ready-for-agent | 01, 14 |

A readiness label describes whether the ticket is specified for its intended implementer. It does not override dependencies: start a ticket only when every listed blocker is completed. Review the acceptance criteria before marking work complete. Tickets 01–11 are complete, including actual Azure OCR/Android acceptance and confirmed temporary-resource deletion. Ticket 08 records live development measurements and the remaining scanned-quality limitation for ticket 14; no held-out release gate is claimed passed. Ticket 09 records real hosted upload/recovery, protected originals, account separation and cold-start retry. Ticket 11 adds assignment and immutable version-specific review; ticket 10 records the read-only evidence viewer. Ticket 12's implementation, independent reviews and actual hosted three-role journey pass; its temporary empty Azure environment is finishing deletion. Tickets 13–15 remain unimplemented, and their listed dependencies still apply.

## Design tree

```text
College demonstration; synthetic records; ₹0
├── Delivery: Android APK shared free with classmates/examiners
│   └── One APK, three role-specific experiences
├── Availability: hosted backend; laptop may be off
│   ├── Azure student benefits verified; track credit expiry and quotas
│   ├── Cold starts accepted
│   └── Stop at allowance/credit exhaustion; no paid upgrade
├── Mandatory workflow: one laboratory PDF → one case
│   ├── Private upload → durable PDF/OCR processing
│   ├── Structured extraction → evidence and validation
│   ├── Administrator assignment → doctor review
│   └── Approved patient result → retained authorship/audit
├── Trust: scoped access, synthetic inputs, original AI versions preserved
├── Limits: 10 pages/10 MB; 5 uploads/patient/day; 20/hospital/day
├── Retention: PDF and analysis content expires after 30 days
└── Proof: fixed 40-document dataset, held-out results, working APK/demo
```

Detailed decisions are in [decisions.md](decisions.md). Radiology and all other stretch features remain outside the mandatory ticket backlog.
