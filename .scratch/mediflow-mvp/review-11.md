# Ticket 11 corrective review

Comparison point confirmed by the user: `8e7ebd3`.
Initial implementation: `5f5f97f`; corrective implementation: `49baa1f`.
The implement skill invokes code-review. Standards and Spec were reviewed in
separate parallel read-only agents; both reviewed the final three-dot diff.

## Standards

Initial review: no documented-standard breaches. One minor judgment call,
**Mysterious Name**: `patient_cases` now served all three roles. Renamed to
`role_scoped_cases` and updated the caller.

The reviewer also noticed a correctness edge case: a publicly valid long correction
field could raise a provider-schema ValidationError. An HTTP regression reproduced
the internal error; the server now translates invalid correction shape into a safe
422 `invalid_request` without leaking provider details.

Final report:

> No remaining documented-standard breaches or actionable baseline smells found in
> `git diff 8e7ebd3...49baa1f`. The misleading case-list name is fixed. The correction
> validation exception is now translated to a safe 422 response and covered by an
> API regression. Standards: 0 unresolved findings.

## Spec

Initial review identified three P2 issues:

1. Correcting one field could reject another unchanged field even with an explicit
   unresolved acknowledgement. Validation now permits pre-existing unchanged
   blockers only with matching acknowledgement, while changed fields and every
   quotation must validate. An HTTP regression verifies correction plus qualified
   approval, original AI row preservation and retained unresolved flags.
2. Android row corrections kept only the first citation. The editor now preserves
   and edits all original source references and can add citations. A screen test
   verifies a corrected row retains both page references.
3. Resume during an in-flight request could leave a cleared, busy review screen.
   Clearing now invalidates the request generation and resets busy state; an old
   request cannot release a new operation's busy state. A screen regression resumes
   before the original request completes and verifies the authoritative reload.

An installed-app check additionally exposed polling invalidating a doctor chooser.
Polling pauses while that chooser is open; the assignment screen test holds it open
across the refresh interval before submitting successfully.

Final report:

> No unresolved Spec findings in `8e7ebd3...49baa1f`. All three original findings are
> addressed: mixed correction/qualification validation, preservation and editing of
> multiple source references, and authoritative reload after background/resume with
> in-flight requests. The assignment chooser also now remains valid across polling
> intervals. Spec: 0 unresolved findings; no scope creep identified.

Standards: 0 unresolved findings; Spec: 0 unresolved findings.
