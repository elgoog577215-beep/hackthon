# Validation

## Initial evidence

- Production version before this change: `f92582f404ccb8dd9d46e7dd00604d129b5a7dc1`.
- Representative course: `afb29754-6842-437b-af1b-5866bfb53b41`.
- Browser evidence: `D:/lingzhi/.codex_tmp/course-open-20260913/course-production-final-cold-browser.json`.
- Workspace shell visible: 5.53 s.
- Blueprint response complete: 12.84 s from navigation.
- Full lesson-authoring response complete: 14.93 s from navigation.
- This evidence is a production read-only sample, not a controlled load test or strict server cold-cache benchmark.

## Required evidence per batch

- Exact commit, CI run, deployed version and rollback target.
- Browser timings for target text readable and editor enabled, with sample count and failures.
- Request list proving unused full-content endpoints are absent from the critical path.
- Authorization, revision conflict, task recovery, stale response and last-good regression results.
- Server timing breakdown and response sizes without content or identity-sensitive logs.

## Batch A implementation checkpoint

- The blueprint source reader now loads the raw course record and applies the existing current-outline selector without projecting teacher handouts. A generation workspace remains readable before the formal shell exists.
- `courseWorkspace` coalesces concurrent blueprint reads, reuses the successful course snapshot, and rejects a previous course's late response.
- The foundation route makes blueprint loading critical and moves the full formal course and lesson-authoring reads behind the first outline response.
- The returned blueprint nodes are applied to the existing course navigation projection before the workbench mounts, so the formal outline component is selected without waiting for the full course projection.
- Focused verification: 34 backend blueprint/version tests passed; 37 frontend blueprint/workspace tests passed; production-path frontend build passed; strict change validation passed.
- Production timing and tasks 1.1, 2.5 remain open until this checkpoint is published and measured with target-text readiness.

## First production read and correction

- `c2cdd8d360de36e5cd20fb031aa03cbcb0738470` reduced the blueprint request itself from 7.63 s to 1.80 s and made the workspace shell visible at 3.02 s.
- That first publication exposed an integration gap: the workbench still selected the outline surface from `courseStore.nodes`, while the direct blueprint snapshot lived only in `courseWorkspace`. It rendered the course-information form instead of mounting the formal outline component, so target-text readiness was not achieved and task 2.5 remains open.
- `81b65259d03965f6ae212be1316230fd21b2b0c6` applies the returned blueprint nodes to the existing navigation projection before workbench mount and removes the competing full-course read from the foundation path. Focused frontend tests and the production build passed locally.
- The push workflow for `81b65259` received a GitHub `startup_failure` before any job existed; its rerun remained queued without jobs and manual dispatch returned HTTP 500. A later normal push is used to retry the same deployment through the existing protected pipeline.

## Batch A production result

- Final production version: `4ba7a413e43da1a8dcb1af932ba19bc463a4e74d`; protected deployment run `34749204853` succeeded after one GitHub startup failure and a later normal push.
- The representative direct-link sample made the workspace visible at 3.151 s and the formal outline text readable at 3.176 s. The previous same-course evidence completed the blueprint request at 12.84 s from navigation, so target-text readiness improved by about 75% in this sample.
- The critical requests were `/blueprint` (1.76 s, 28,386 transferred bytes) and `/course-information` (1.75 s, 1,638 bytes), both started at 0.90 s. No full teacher generation preview or course document appeared in the outline critical path.
- Full lesson-authoring started at 2.68 s and completed in the background after the outline was readable. The browser reported no business request failures; the intentionally blocked usage-event write from the read-only harness is excluded.
- Evidence: `D:/lingzhi/.codex_tmp/course-open-20260913/course-outline-batch-a-final-browser.json`. This is one production read-only sample, so task 1.1 remains open until the controlled multi-sample P50/P95 run is completed.

## Batch B projection-cache checkpoint

- The blueprint response now declares `teacher_blueprint_view_v2`, source and draft revisions, quality rule version, and one projection revision bound to all response-affecting inputs.
- Repeated reads of the same projection reuse deterministic quality review. Changes to review requirements such as total course hours produce a different projection and rerun review.
- Concurrent reads for the same projection share one per-identity computation; different identities do not share the review result. The cache is LRU-bounded to 16 projections.
- Focused verification: 36 blueprint, generation-workspace and version tests passed; Ruff passed. Save/candidate/restore invalidation and conditional HTTP remain open in tasks 3.3 and 3.4.

## Batch C course-library checkpoint

- Production baseline on 2026-09-13 showed the course table first row at 6.5–7.6 seconds. `GET /api/teacher/courses` took 5.3–6.3 seconds while tasks and calendar reads completed within 57 milliseconds.
- A five-second progress timer issued a second course-list request before the initial request completed. The course Store now shares one in-flight request per identity surface, and the course tab defers calendar loading until the calendar tab is selected.
- Course-list production projections are reused by course source version, blueprint-draft version, task lifecycle state, and course metadata. Cache entries are bounded by count, per-entry bytes, and total bytes; source or task transitions invalidate the entry.
- Focused frontend tests passed: 26 tests across course-list continuity, teacher course-library lifecycle, and teacher-home calendar behavior. Focused backend projection and source-version tests passed on Windows with the Linux file-lock primitive shimmed for read-only test execution.
- An isolated 28.85 MB teacher-authoring sample measured 90.2 milliseconds for an uncached projection and 1.5 milliseconds for a projection-cache hit. Production commit `7109b245` measured a 5.55-second process-cold fill, 53–84 millisecond repeat reads, and a 1.08-second visible first course row after manual warming. The application now performs that fill during startup before accepting traffic.
- Production commit `75706fb9` passed the full deployment workflow. The first browser visit after activation, without manual warming, issued one course-list request in 116 milliseconds and displayed the first course row in 865 milliseconds; health reported the same commit and `ready=true`.

## Outline contention follow-up checkpoint

- The workspace now reads `course-information?view=summary`; the summary loads raw metadata, performs the same owner check, and omits document revision and history so it cannot be used as a write precondition. Opening the edit dialog still performs the existing full versioned read.
- The foundation stage no longer starts full lesson-authoring. Direct lesson/script/PPT routes remain owned by the parent loader; later user stage changes explicitly request lesson data through the existing Store.
- The lesson Store keeps `lessons` and `jobs` as arrays when a future summary response omits those collections, preserving the distinction between unloaded and corrupt state.
- Focused verification: 3 summary/baseline tests passed; 151 workbench, lesson Store and loading-boundary tests passed; production build and strict OpenSpec validation passed. Full Linux coverage remains assigned to CI.
- First CI run `34751185616` stopped before deployment because the new `view` query parameter displaced the repository dependency's established third positional argument in a direct compatibility test. A dedicated positional-call test now locks that interface, and `view` follows the repository parameter without changing the HTTP query contract.

## Stable outline multi-browser result

- Final version for this checkpoint: `13a71e500cc2e3a2a2b29cf0c3579bf87f1f67e7`; protected run `34751558838` passed all checks, task protection, activation and production model verification.
- Ten sequential fresh-browser direct-link samples recorded formal outline text readiness: P50 1.630 s, P95 2.067 s, minimum 1.520 s, maximum 2.067 s, failures 0/10.
- Every sample made zero lesson-authoring requests and zero full course-information requests on the foundation path. The earlier five-browser run before this follow-up had P50 7.640 s and P95 8.261 s because each outline open started a full lesson-authoring read that contended with the next browser.
- Ten low-frequency blueprint endpoint samples on the revision cache recorded P50 0.188 s and P95 0.612 s, with a constant 28,155-byte compressed response.
- Evidence files: `D:/lingzhi/.codex_tmp/course-open-20260913/course-outline-summary-browser-{1..10}-browser.json`. Task 1.1 remains open because lesson-plan and handout target-text timings are not yet recorded.

## Lesson-plan AI candidate acceptance hot-path checkpoint

- A production screenshot showed a long wait after applying one lesson-plan AI suggestion. Code tracing confirmed that the resolve endpoint did not call the model or reload the frontend Store. It wrote the monolithic teacher-authoring file twice, then projected every lesson before selecting the changed lesson.
- The representative course's existing local read-only snapshot contains a 1.62 MiB course record and a 15.96 MiB teacher-authoring record. In compact JSON, completed jobs account for about 7.25 MiB and one PPT manuscript for about 3.05 MiB, although neither is changed by accepting a lesson-plan suggestion.
- A before benchmark on a temporary copy of that snapshot measured 3,994.6 ms for candidate acceptance and 557.4 ms for all-lesson projection, about 4,552 ms combined. The two acceptance saves took 812 ms and 937 ms. This is a local Windows comparison on one historical snapshot, not a production P50/P95 claim.
- The candidate revision and accepted status now commit in one atomic authoring-file replacement. Candidate validation, base-revision conflict checks, dependent PPT staleness, quality reports and result revision IDs remain in the same transaction.
- The resolve endpoint reuses the returned changed lesson and projects only that lesson. Cached lesson and outline-revision reads copy only their requested slice instead of deep-copying unrelated jobs, manuscripts and lessons.
- The same temporary-copy benchmark after the change measured 1,238.9 ms for acceptance and 1.8 ms for target-lesson projection, about 1,241 ms combined: roughly 73% lower than the before path. One durable save took 703 ms.
- Regression coverage proves one durable save, target-only projection, no full cached-tree copy for lesson reads, candidate provenance, and unchanged acceptance results. The broader summary and `lesson_unit_id + content` GET contracts in tasks 4.1–4.5 remain open; this checkpoint only removes the confirmed candidate-acceptance bottleneck.

## Direct PPT loading checkpoint

- Direct `stage=ppt&lesson=...` entry previously awaited the full teacher course preview, then started the full lesson-authoring response, and only mounted the target lesson PPT after both. The PPT component then re-read an existing manuscript after polling its already completed task and eagerly generated the first hidden render preview.
- Direct PPT entry now awaits the course-information summary and one `lesson-authoring?lesson_unit_id=...` projection in parallel. The targeted projection omits all persisted job scans and the full production-state projection; switching to other lesson-backed stages can still request the compatible full view.
- Existing manuscript reads validate the current plan and script revisions without constructing the complete PPT source document. Material freshness uses relationship identities without parsing selected material bodies. The response contract and source revision checks remain unchanged.
- The client no longer polls completed manuscript tasks, preloads a hidden render preview, reloads for an unchanged script revision, or requests a page preview already cached under the current manuscript revision. Concurrent reads for the same course and lesson share one request.
- On the existing 67-page local read-only snapshot, the cold target-lesson projection measured 219.3 ms and returned about 105 KiB. Revision validation measured 244.1 ms and manuscript state construction 32.9 ms. The manuscript response remains about 1.57 MiB because the current product contract continuously displays the whole lesson's page content; these are local single-sample measurements, not production P50/P95 results.
- Regression coverage includes direct-link request ordering, single-lesson Store merging, duplicate request coalescing, one manuscript read, completed-task suppression, revision-aware preview reuse, lightweight manuscript reads, and the existing generation/recovery workflows. Tasks 4.4–4.5 remain open for bounded adjacent prefetch and active-task handoff coverage.

## Lesson-plan and handout first-load checkpoint

- Production version `618b87b2` showed the selected lesson plan at 12.715 seconds and the selected handout at 16.341 seconds in one fresh browser sample. Both entries first waited for a 2.35–2.72 second full generation preview, then requested the six-lesson authoring view; that response took about 8.0–8.2 seconds and returned about 1.08 MB uncompressed with 55 jobs. The existing target-lesson response took 181 milliseconds and returned about 116 KB.
- The new `view=summary` response lists every lesson, readiness state, task summary and production state while marking plan and handout bodies as `content_loaded=false`. It omits plan revisions, handout sections, candidates and presentation revision bodies. The compatible full response and `lesson_unit_id` response remain available.
- Repository summary projection reads the parsed authoring owner under its lock without cloning the complete course body. The production-state compiler continues to prove that it does not mutate supplied snapshots and no longer deep-copies the authoring root.
- On the existing 11.92 MB local authoring snapshot, the summary projection took 322.7 milliseconds cold and 270.0 milliseconds warm, returning about 118 KB. The warm target-lesson projection took 3.2 milliseconds and returned about 115 KB. These are isolated local measurements rather than production percentiles.
- Lesson, handout and PPT entries now load the summary and selected lesson before mounting the workspace. The Store merges them without replacing an already loaded body, coalesces matching reads, ignores responses for a course that is no longer active, and loads a summary-only lesson before changing the visible selection.
- Focused verification passed: 83 production-state tests, 6 lesson-view tests, 41 loading-boundary and Store tests, 116 workbench tests, and the production frontend build.
- Production `11d56597` confirmed the new summary and target-lesson path but still showed 5.019 seconds for the lesson plan and 7.934 seconds for the handout. The summary and target lesson were serial, and WebSocket reconnect also requested the full course document.
- Production `df1ae227` starts summary and target-lesson reads together and marks the course shell as a lesson-summary projection so reconnect cannot request the full document. Five fresh-browser samples per stage recorded lesson-plan text P50 3.272 s and P95 3.486 s, and handout text P50 3.297 s and P95 4.187 s. All 10 samples loaded six lesson entries, failures were 0/10, and full-document requests were 0/10.
