# Eight-week implementation roadmap

Baseline: one developer, 15–20 hours/week. Weeks are relative to kickoff; no calendar submission deadline was provided. Estimated ticket effort totals **144 hours**, within the agreed 120–160-hour planning range. Estimates require adjustment after the cloud and OCR spikes; they are not delivery guarantees.

## Weekly milestones

| Week | Visible outcome | Main tickets |
| --- | --- | --- |
| 1 | Hosted feasibility demonstrated; Android/backend skeleton, contracts and seeded auth started; synthetic fixture design begins | 01, 02, 03, 04 |
| 2 | Authorized private upload produces one case, a durable job and observable status | 03, 04, 05, 06, 09 |
| 3 | Digital and scanned PDFs yield bounded page-level text/evidence; jobs recover from interruption | 06, 07, 09 |
| 4 | Hosted laboratory extraction produces validated/versioned rows and source-grounded summaries | 08, 09 |
| 5 | Doctor opens source pages and records approval, corrections or rejection; assignment enforced | 10, 11 |
| 6 | All three roles complete their journeys; expiry, operational controls and recovery are demonstrable | 12, 13 |
| 7 | Held-out metrics, authorization, concurrency, expiry and failure tests run; release-blocking defects fixed | 14 |
| 8 | Signed APK works with laptop off; documentation, cost notes, results and recorded demo delivered | 15 |

Tests, permission checks, resource bounds and development fixtures accompany the feature that introduces them. Week 7 consolidates release evidence rather than starting security/evaluation work.

## Effort and dependencies

| Ticket | Hours | Blocked by |
| --- | ---: | --- |
| 01 | 8 | None |
| 02 | 10 | None |
| 03 | 8 | 02 |
| 04 | 8 | 02 |
| 05 | 8 | 01, 04 |
| 06 | 12 | 01, 04 |
| 07 | 12 | 03 |
| 08 | 12 | 03, 06, 07 |
| 09 | 10 | 05, 06 |
| 10 | 8 | 08, 09 |
| 11 | 12 | 04, 10 |
| 12 | 8 | 09, 11 |
| 13 | 10 | 05, 06, 08, 11 |
| 14 | 10 | 03, 07, 08, 10, 11, 12, 13 |
| 15 | 8 | 01, 14 |
| **Total** | **144** | |

Ticket labels describe readiness for the intended implementer; dependencies still gate starting work. Account activation in 01 needs the human owner. Agent work can begin on 02 while the account gate is handled. Subsequent implementation should be scheduled by satisfied dependencies and available weekly hours, not by starting every ticket listed in a week simultaneously.

## Gates

1. **Cloud feasibility, week 1:** Azure student eligibility and a permitted region are confirmed; an HTTPS API, private object and queue-triggered job work within available quotas. Produce a resource estimate and keep spending protection. If unavailable, resolve a verified ₹0 hosted alternative before cloud-dependent implementation.
2. **Upload/processing slice, weeks 2–3:** one private upload creates one case and recoverable job, returns page evidence, and cannot be accessed by another account.
3. **Reviewed-result slice, week 5:** a doctor can verify/correct an extraction; the patient receives only the approved snapshot; repeated and stale requests are safe.
4. **Release quality, week 7:** run the frozen held-out evaluation; target 95% strict row precision and recall, with digital/scanned results reported separately. All defined authorization/review tests pass and no known data-exposure or lost-review defect remains.
5. **Delivery, week 8:** a signed APK completes the workflow using hosted services while the laptop is off; a new developer can follow the setup/deployment documentation.

If a target is missed, report it accurately and fix within available time. Do not claim a failed gate passed.

## Stretch rule

Radiology, bounding-box highlights and all other deferred features receive no mandatory implementation tickets. Start a stretch feature only after mandatory gates pass, required handoff materials are complete, remaining hours are known, and the user accepts its scope. A deadline does not justify weakening permissions, replacing real AI output with demo data, or omitting failure handling.

## Operational handoff

Record account ownership, student benefit activation/expiry, resource region and quotas, current Gemini model/free limits, renewal/export instructions, release signing-key ownership, cleanup jobs, measured resource consumption, and the exact commands needed to reproduce fixtures/evaluation. Link to secrets by their configuration names only; never include secret values.
