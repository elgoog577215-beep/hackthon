# Implementation Plan

## Contract

- Change: `split-teacher-lesson-authoring-v1`
- Product scope: pure Lingzhi teacher lesson authoring; no education-agent integration
- Stable work packages: `tasks.md`
- Evaluation: `eval-contract.md`
- Strategy: direct, contract-first serial implementation in the existing isolated worktree
- Authority: current user request authorizes planning and implementation for this change; no push, `.env` write, lockfile change, destructive cleanup or student redesign

## Goal / Context / Constraints

### Goal

Deliver one real teacher vertical slice: teacher-defined lesson count → confirmed outline → select any lesson → generate all in-lesson sections as an independent editable/AI-optimizable lesson plan → generate and optimize that lesson's PPT. Teacher flow creates no course正文 and does not change student behavior.

### Constraints

- Preserve existing dirty/runtime/user files; stage nothing automatically.
- Extend shared generation/PPT internals only through backward-compatible contracts.
- Teacher tasks and repositories are namespaced and may not be consumed by the student store.
- Reuse current AI provider and ports 5182/8002; no new dependency or service.
- UI reuses existing tokens, components and teacher shell.

### Non-goals

Education-agent integration, student publication, calendars/files migration, old-course migration, outline import, bulk generation, full teacher knowledge page and complex supplemental-deck UI.

## Execution Checklist

- [x] P0 Create proposal/design/spec/eval/review/task contract for the corrected pure-Lingzhi scope.
- [x] P1 Add regression tests for hard lesson count, teacher outline stop, lesson-scoped task isolation and fallback warning completion.
- [x] P2 Add teacher outline/task contract and map teacher expected sessions to top-level lesson count.
- [x] P3 Add atomic teacher lesson asset repository and lesson-scoped plan generation/read/retry endpoints.
- [x] P4 Add draft patch/confirm/AI candidate/knowledge-evidence endpoints for one lesson.
- [x] P5 Split frontend lesson/section state and implement nested section navigation plus section/lesson view.
- [x] P6 Connect lesson generation/edit/AI state to teacher production UI.
- [x] P7 Add lesson-plan authoring source adapter and connect it to the existing V6 PPT engine/workbench with lesson-scoped version state.
- [x] P8 Run focused tests/build/OpenSpec validation and repair failures.
- [x] P9 Run real browser teacher/student regression and record completion or exact remaining block.

## Expected Files

### Backend new/extended

- `backend/teacher_lesson_authoring.py`
- `backend/routers/teacher_lesson_authoring.py`
- `backend/dependencies.py`, `backend/main.py`
- `backend/task_manager.py`, `backend/course_service.py`
- `backend/teaching_representations.py` / teacher PPT source adapter
- focused backend tests under `backend/tests/`

### Frontend new/extended

- `frontend/src/features/teacher-course/useTeacherCourseRuntime.ts`
- `frontend/src/stores/teacherLessonAuthoring.ts`
- `frontend/src/views/TeacherCourseCreateView.vue`
- `frontend/src/components/CourseGenerationDialog.vue`
- `frontend/src/components/TeacherCourseWorkbench.vue`
- `frontend/src/components/TeacherLessonPlanDocument.vue`
- teacher-focused Vitest files and locale keys

## Verification Commands

- `openspec validate split-teacher-lesson-authoring-v1 --strict`
- focused `python -m pytest` for new teacher lesson contracts plus teacher authoring/generation recovery
- focused `npm.cmd test -- ...` for teacher navigation/store and existing student boundary suites
- `npm.cmd run build`
- Playwright teacher create/outline/lesson/AI/PPT/reload and student route/content smoke
- `git diff --check` and scoped secret/runtime-artifact scan

## Failure / Rollback

- If teacher PPT requires writing student content, stop at P6 and report P7 blocked.
- If per-lesson generation cannot reuse current planner without cross-lesson state, isolate the planner in a new teacher service; do not mutate student jobs.
- If any student regression appears, revert the smallest shared extension and keep teacher route hidden.
- The isolated cleanup branch may be pushed after scoped and full regression pass; merging and production deployment remain separate actions.

## Progress Truth

Only this file records execution progress. `tasks.md` remains the stable work-package contract; run evidence belongs under `runs/lesson-authoring-20260817/`.
