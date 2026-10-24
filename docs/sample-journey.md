# Synthetic sample journey

Use the five trusted accounts `patient_a`, `patient_b`, `doctor_a`, `doctor_b`
and `administrator`. Keep their email/password file owner-readable and outside
version control. Account provisioning is described in [authentication](authentication.md).
Every PDF must contain invented data. Use development examples from the
[evaluation dataset](../evaluation/README.md); held-out examples are reserved for
the extraction release gate.

## Repeatable demonstration

1. Start from the sign-in screen. Sign in as patient A, acknowledge invented data,
   and upload a development laboratory PDF through the Android system picker.
   Note the submitted case. Processing runs independently of the app. Before
   approval, only status and the protected original PDF are available to the patient.
2. Sign out and sign in as patient B. Patient A's case must be absent. Upload a
   different development PDF as patient B so the demonstration has two owners.
3. Sign in as the administrator. Find the two cases and assign them to doctor A.
   Only assignment/workflow metadata is available; the administrator has no
   document, evidence, AI candidate or clinical review access.
4. Sign in as doctor A. Open patient A's assigned case and compare the AI candidate
   with the original source pages. Begin review. Sign out before submitting a decision.
5. As administrator, reassign patient A's case to doctor B. Doctor A must lose
   subsequent access to that case while retaining access to patient B's case.
6. As doctor B, review patient A's case. Correct a field only when the printed
   source supports it. Every blocking issue needs a source-grounded correction
   or an explicit unresolved reason. Approve and note the review attribution.
7. As patient A, open the approved result. Check the reviewed rows, summary,
   corrected-field labels, explicit unresolved qualifications and reviewer/time.
   Refresh in the app; switching accounts must clear the previous result.
8. As doctor B, request reprocessing with a reason. As patient A, confirm the
   existing approved snapshot remains visible while its replacement processes.
   As doctor B, reject the replacement with a reason. Patient A must still see
   the prior approved version and understand that the replacement was not approved.
9. After the server's reprocessing cooldown, request another replacement. Review
   and approve it. Patient A must now see the new approved snapshot and its own
   attribution. Previous AI candidates and review history remain available only
   to the currently assigned doctor.

Never insert a successful analysis or approval directly into the database to make
this journey pass. If extraction fails or provider quota is exhausted, retain the
actual safe status and retry through the assigned doctor's authorized action.
Failed, rejected and expired results must remain distinguishable from medical
urgency. An expired report cannot be opened even if cleanup has not run yet.

## Hosted verification record

Use actual hosted API, private storage, Firestore, queue and configured worker.
The existing [temporary hosted probe](../tools/patient_smoke/README.md) documents
deployment, Android configuration, spending-protection checks and cleanup. A
temporary probe endpoint is not a permanent deployment. Record the APK build,
server image, account roles, observed transitions and sanitized assertions without
passwords, tokens, raw provider payloads or credentials. Preserve truthful quota
usage and remove only run-owned synthetic payloads and temporary infrastructure.

HTTP and Flutter tests verify behavior at their public boundaries. Passing those
tests alone does not establish the hosted Android journey or extraction accuracy.
