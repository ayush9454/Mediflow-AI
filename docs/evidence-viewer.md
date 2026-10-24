# Laboratory results and PDF evidence

Ticket 10 implements a read-only result/evidence viewer. Assignment and review
writes belong to ticket 11; the viewer must consume their persisted versions
without constructing an approval from an AI candidate on the device.

## Renderer decision

Reuse the existing Android `ReportPlatform.render` bridge to the platform
`android.graphics.pdf.PdfRenderer`. No additional Flutter PDF package is needed.
The [Android API reference](https://developer.android.com/reference/android/graphics/pdf/PdfRenderer)
documents Android support from API 21, a page count, and zero-based
`openPage(index)` navigation. Evidence references use one-based page numbers;
the viewer must validate the reference against the report page count before
converting it to the renderer index. The
[AOSP source](https://android.googlesource.com/platform/frameworks/base/+/525a66b/graphics/java/android/graphics/pdf/PdfRenderer.java)
carries the Apache 2.0 license. These sources were checked for ticket 10.

The renderer takes local bytes, not a URL. The application obtains those bytes
through the backend's authenticated `/api/v1/reports/{id}/document` endpoint.
The existing bridge uses bounded private temporary files, closes the renderer,
deletes the file after rendering, and produces one bounded page bitmap at a time.
This supports scanned and digital pages without an external document application
or public storage link. Pinch zoom operates on the rendered page; bounding-box
highlighting is deferred.

## Verification boundaries

- Flutter result/evidence screens: printed values, validation issues, explicit
  missing evidence, exact page selection, and sensitive-content clearing.
- Authenticated API client: result kind/report identity, bounded PDF responses,
  and expired-session behavior.
- Backend HTTP endpoints: role-specific result payloads and denial after expiry
  or reassignment.

The user confirmed these boundaries and the review baseline on 2026-10-25.
Android rendering is inspected separately on the representative phone emulator;
widget tests alone cannot verify the native renderer.


## Result and integration contract

`GET /api/v1/reports/{id}/result` defaults to the current AI candidate for the
assigned doctor and the saved approval for its patient. The explicit `kind=draft`
query is forbidden for patients. Assigned doctors can request `kind=approved`
separately. The tagged `ReportResult` contains exactly one payload; the client
checks kind, report ID and analysis pointer against fresh metadata before display.
The backend rereads the report and authoritative case in a transaction, checking
hospital, ownership/current assignment and retention before reading the payload.
Responses use `Cache-Control: no-store`; document URLs carry no bearer credentials.

Immutable candidates live in `analyses/{analysisId}`. The read contract for ticket
11 is `approvedResults/{reportId}` containing an `ApprovedResult`, updated atomically
with `reports.approvedAnalysisId` by the future review writer. It must copy approved
rows and qualifications into the snapshot rather than point at the latest draft.
`correctedRowIds` identifies the snapshot's clinician-corrected rows; `provenance`
retains candidate generation metadata without including the original provider
payload. Both fields have backward-compatible defaults. Review ID, reviewer,
review time and analysis version are always displayed. A replacement candidate
never supplies patient-visible rows or removes the saved approval.

The authenticated `/results/:reportId` route owns the viewer. Its complete widget
and HTTP client are keyed to hospital, user, role and report. The patient report
detail links to an existing approved snapshot. Until ticket 11 supplies assigned
case discovery, doctors can open an assigned report by its server-created reference
from their workspace. Administrators and anonymous/preview sessions cannot open
this route. No assignment, approval, correction or rejection writes are added here.

The viewer preserves printed strings and shows absent fields, validation issues,
field-level unresolved qualifications, source methods, summary and provenance.
Invalid/missing page references or quotations never enable a source link. Native
rendering failures and actual page-count disagreements produce an explicit evidence
issue. Narrow screens have Results/Source PDF tabs; widths of at least 840 logical
pixels show both panes. Quotations scroll in a bounded area and pages support zoom.

Every page selection downloads through the authenticated document endpoint; PDF
bytes are zeroed after rendering and are not reused for another page. Only the
currently rendered PNG remains in memory. Backgrounding, disposal, logout and
identity/hospital/role changes discard the result, quotation and image. A retention
timer clears them at the report deadline. Foreground result revalidation runs every
15 seconds and every resume; authorization or connection errors clear displayed
content and require a refresh. A former doctor may have seen already downloaded
content before reassignment; the backend denies subsequent requests immediately,
and the viewer clears it on the next foreground recheck or page request. This is
not a claim that remote reassignment can erase content already seen on a device.

## Reproduction and limits

Focused checks:

```sh
backend/.venv/bin/python -m pytest backend/tests/test_results.py
cd app
../tools/flutterw test --no-pub test/result_api_test.dart test/evidence_screen_test.dart test/navigation_test.dart
```

Manual Android verification uses the normal development APK, real synthetic Firebase
sign-in, and a **local test API** with invented in-memory cases/candidates/snapshots.
The actual backend HTTP routes, result reader and Android renderer run normally;
no model call or cloud clinical-payload write is involved. Its representative source
is `mediflow.processing.fixtures.supplemental_pdf(pages=2, mixed=True)`: one native
page and one scanned page. These viewer checks do not measure extraction accuracy
or replace the later hosted, full-workflow release gate. Test wiring and credentials
stay under ignored `.tooling/issue-10/`; production configuration cannot select the
in-memory adapters. See the sanitized [Android evidence](../evaluation/reports/evidence-viewer-android.json).
