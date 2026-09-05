# Implementation Plan: add-teacher-course-space

## Contract

- Change: `add-teacher-course-space`
- Goal: complete A first—teacher course/term work packages, whole-folder import, explainable classification, source-file download and ZIP export.
- Non-goals: B generation, online Office editing, shared drives and production SSO.
- Strategy: direct. The storage/domain contract must be frozen before its Vue consumers are changed.

## Acceptance Criteria

- [x] A teacher can create and list only their course-term packages.
- [x] A folder batch preserves safe relative paths, succeeds partially when one file fails, and returns deterministic categories with reasons.
- [x] A teacher can change a category, download one original, and download a ZIP with original editable files and a manifest.
- [ ] The existing materials upload and learning-course creation flows remain compatible.
- [x] Backend success/failure/authorization tests, frontend tests/build and browser verification pass.

## Execution Steps

- [x] 1. Implement and unit-test backend models, repository and classifier in `backend/teacher_course_space.py`.
- [x] 2. Implement the HTTP boundary in `backend/routers/teacher_course_space.py`, register it in `backend/main.py`, and add API tests. (Runtime smoke creates template and custom physical folders.)
- [x] 3. Add frontend types/store/client and build the teacher course-space view/components. (The view inherits the course-library shell and existing dialog/message primitives.)
- [x] 4. Add the course-library entry, test UI behavior and build the frontend. (The browser renders the final 0–5 folder-only template, nested imports, adaptive previews and confirmed deletion actions.)
- [x] 5. Start an isolated local runtime and verify import, category correction, original download and ZIP export in a real browser/API runtime.

## Failure / Rollback

- Reject unsafe paths before any work-package write; keep successful files when one item fails.
- New data is isolated under a new root and new APIs; rollback removes route exposure without touching existing materials or courses.
