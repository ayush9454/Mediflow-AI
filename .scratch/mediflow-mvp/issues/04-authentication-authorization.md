# 04: Implement seeded authentication and deny-by-default permissions

Status: ready-for-agent
Type: task
Blocked by: 02
Estimate: 8 hours
Target week: 1–2

## Outcome

Make role and resource authorization a shared backend boundary before exposing documents or clinical data.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

Use synthetic account information and secrets via environment/secret storage. Auth token verification must be real in the deployed environment; test overrides cannot be enabled there.

## Scope

- Configure Firebase email/password authentication, trusted seed/bootstrap for one hospital and active patient/doctor/administrator accounts, and no public signup UI.
- Verify Firebase ID tokens and server-controlled active status/role/hospital membership on protected endpoints. Add authorization helpers for patient ownership and current doctor assignment.
- Use backend-only clinical record access; deny direct mobile Firestore clinical reads/writes and client audit mutations. Do not rely on client navigation to protect endpoints.
- Add Android sign-in, sign-out, role navigation and session-expiry behavior. Clear temporary sensitive state/cache when signing out or switching accounts.
- Create safe authorization audit events without exposing document contents or secrets; keep administrator operational metadata distinct from clinical payloads.

## Acceptance criteria

- [ ] Each seeded role signs in and lands on the intended navigation shell.
- [ ] Missing/invalid tokens, inactive users, forged role/patient fields and cross-hospital/resource access are denied consistently.
- [ ] Patient A cannot read patient B's records; unassigned doctors and administrators cannot read clinical documents/results.
- [ ] Seed scripts require trusted execution and never enable self-promotion from the client.
- [ ] Firestore rules and backend checks both reject their respective bypass attempts.

## Verification

Use API authorization tests and Firebase emulator/rules checks for direct access. Include reassignment authorization through a representative seeded case, even before full assignment UI exists.

## Implementation record

Not started. Record actual changes, verification commands/results, measured findings, and any remaining gate here. A readiness label does not imply completion or override the Blocked by line.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.
