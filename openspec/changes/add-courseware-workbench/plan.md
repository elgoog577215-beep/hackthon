# Implementation Plan — add-courseware-workbench

本文件是唯一执行进度真源。`tasks.md` 保持稳定 work package/AC 合同；所有源码修改绑定当前 change、当前 run 和 Authority receipt。执行策略为 `direct + sync-then-parallel`，Light 只缩小验证矩阵。

## Shared Boundary Contract

- Change: `add-courseware-workbench`
- Run: `courseware-mvp-20260715`
- Allowed root: `D:\xsh\cursor\灵知\hackthon`
- Allowed operations: `patch`, `state-write`, `test`
- Source-of-truth order: OpenSpec artifacts → current source → approved initial visual companion → education agent reference.
- Data boundary: only `backend/data/presentation_decks/`; no CourseDocument mutation.
- Runtime boundary: keep frontend 5173/backend 8000 and existing API base/auth headers.
- Visual boundary: reproduce the approved first prototype; education agent contributes structure, never its brand styling.
- Concurrency boundary: freeze domain/event/render contracts first. Thereafter each worker owns disjoint files and returns a handoff; lead alone integrates shared registration files.
- Validation boundary: presentation-targeted tests, one build, representative render fixture, desktop main path, narrow smoke, strict OpenSpec. No full-suite or 3×10 screenshot matrix.

## Execution

- [x] P0 — Freeze contracts and prove renderer feasibility
  - Create backend domain DTOs, style/layout registry, frontend types, event/postMessage envelopes and representative six-page fixture.
  - Add `python-pptx` explicitly and prove one fixture renders self-contained HTML plus reloadable PPTX with matching page count, titles and notes.
  - Reject unknown `template_id/layout_id`; record exact API errors, idempotency keys and revision preconditions.
  - Files: `backend/presentation_models.py`, `backend/presentation_templates.py`, `frontend/src/types/presentation.ts`, `backend/requirements.txt`, targeted contract/render tests.
  - Exit: G1 and the feasibility portion of G6 pass; parallel interfaces are frozen.

- [x] P1 — Build persistence and immutable course projection
  - Implement safe IDs, per-deck locks, atomic entity-first/pointer-last writes, manifests, working snapshots, event logs, revisions, proposals, quality reports and artifact receipts.
  - Project current chapter/course into immutable `source_snapshot.json`; persist canonical and legacy identities plus digest.
  - Cover reload, restore-as-new-revision, duplicate command receipt, stale conflict, path rejection and failed pointer switch.
  - Owner after P0: backend-domain worker.
  - Files: `backend/presentation_repository.py`, `backend/presentation_source.py`, targeted repository/source tests.
  - Exit: G2 and source half of G8 pass.

- [x] P2 — Build generation, quality, rendering and API
  - Implement curator → outline → bounded async page filler using `AIBase`; deterministic fallback may create a visible draft but never bypass export gates.
  - Persist each working update before ordered SSE emit; support replay, idempotent generation, tombstones and stale/concurrent 409 responses.
  - Implement current-page proposal/apply/restore, deterministic quality reports, atomic finalize, receipt-bound safe HTML/PPTX downloads.
  - Owner after P1 interface handoff: backend-service worker. Lead owns final edits to `main.py` and router registration.
  - Files: `backend/presentation_generation.py`, `backend/presentation_quality.py`, `backend/presentation_render.py`, `backend/routers/presentations.py`, targeted API/service tests.
  - Exit: G3–G6 and backend half of G8 pass.

- [x] P3 — Build the approved workbench shell and resilient client state
  - Add `shell: workbench` route mode so the page has exactly one internal top bar; add stable LearningView toolbar entry with `nodeId`, course-library secondary entry and context-preserving return.
  - Implement independent presentation service/store/reducer with ordered SSE handling, refresh hydration, selected-slide scope, stale artifact state and narrow Preview/AI switch.
  - Implement approved left preview + fixed 400px AI layout, versioned opaque-sandbox postMessage validation bound to revision checksum, proposal/diff/apply/undo and structured quality fixes.
  - Owner after P0: frontend worker. It must not change backend files or reuse course AI stores.
  - Files: `frontend/src/{types,services,stores,composables}/presentation*`, `views/PresentationStudioView.vue`, `components/presentation/*`, router/App/LearningView/LearningDock/CourseLibraryView, targeted tests.
  - Exit: AC-01, AC-05, AC-08 and client portions of G7 pass.

- [x] P4 — Integrate shared boundaries
  - Lead reviews worker handoffs and diffs, aligns generated JSON with TypeScript, binds real endpoints, resolves App/router/main registration and ensures no unrelated dirty changes were overwritten.
  - Verify CourseDocument digest before and after create/generate/edit/finalize; verify old artifact becomes stale after a new revision.
  - Add `scripts/presentation-goal-eval.mjs` that emits the native GOAL evaluator JSON for G1–G8 without modifying source.
  - Exit: all ten ACs have an executable evidence path; no BLOCK remains in multi-lens review.

- [x] P5 — Light verification and proof
  - Backend: run presentation-only contract/repository/service/API/render tests.
  - Frontend: run presentation-only Vitest and one production build.
  - Browser: 1440×900 main path with console/network inspection; 390×844 Preview/AI switch and export-block smoke; save current screenshots.
  - Spec/goal: run `openspec validate add-courseware-workbench --strict`, native evaluator, and focused diff review.
  - Store receipts/proof under `openspec/changes/add-courseware-workbench/runs/courseware-mvp-20260715/`; do not claim unrun full-suite coverage.
  - Exit: G1–G8 pass, plan checkboxes reflect reality, proof maps AC-01…AC-10.

## Parallel Handoff Contract

Every worker handoff must contain: owned files, contract version used, behavior delivered, commands/results, unresolved risks, and confirmation that shared files were not edited outside ownership. Handoffs live in the current run as `HANDOFF-backend-domain.md`, `HANDOFF-backend-service.md`, and `HANDOFF-frontend.md`. Worker self-reports are integration inputs, not final proof.

## Stop / Replan Rules

- Stop immediately for CourseDocument mutation, arbitrary path access, stale-write acceptance, partial artifacts or formal-download bypass.
- Replan if three consecutive implementation/evaluation iterations do not reduce failing hard gates.
- Provider unavailability is recoverable: preserve working state and test the deterministic fallback; do not forge a live-model PASS.
- Completion requires the Light evaluator plus real browser evidence; target score alone is not completion.
