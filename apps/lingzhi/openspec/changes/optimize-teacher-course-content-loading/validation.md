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

## Outline contention follow-up checkpoint

- The workspace now reads `course-information?view=summary`; the summary loads raw metadata, performs the same owner check, and omits document revision and history so it cannot be used as a write precondition. Opening the edit dialog still performs the existing full versioned read.
- The foundation stage no longer starts full lesson-authoring. Direct lesson/script/PPT routes remain owned by the parent loader; later user stage changes explicitly request lesson data through the existing Store.
- The lesson Store keeps `lessons` and `jobs` as arrays when a future summary response omits those collections, preserving the distinction between unloaded and corrupt state.
- Focused verification: 3 summary/baseline tests passed; 151 workbench, lesson Store and loading-boundary tests passed; production build and strict OpenSpec validation passed. Full Linux coverage remains assigned to CI.
