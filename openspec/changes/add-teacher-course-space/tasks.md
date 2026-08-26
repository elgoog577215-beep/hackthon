## 1. Course-space domain and safety

- [ ] 1.1 Add typed work-package, asset, import-batch and category models plus deterministic classifier tests.
- [ ] 1.2 Implement an atomic course-space repository with owner isolation, normalized relative paths and stable asset IDs.
- [ ] 1.3 Add API routes for package CRUD, batch import, tree read, category correction, original download and ZIP export.
- [ ] 1.4 Register routes and cover success, ownership, traversal, invalid-format, duplicate and partial-batch API cases.

## 2. Teacher file-space UI

- [ ] 2.1 Add a Pinia store and API client for teacher work packages and assets.
- [ ] 2.2 Build a responsive teacher course-space view with course/term creation, package summary and categorized asset tree.
- [ ] 2.3 Add directory selection, multi-file fallback, drag/drop, import progress/outcomes and category correction.
- [ ] 2.4 Add original-file and ZIP export actions with accessible errors, empty states and responsive behavior.

## 3. Integration and verification

- [ ] 3.1 Surface the teacher file-space entry from the course library without changing current learning-course generation.
- [ ] 3.2 Run backend tests, frontend component/store tests, production build and browser import/export smoke.
- [ ] 3.3 Review diff scope and record runtime, security and future B-integration limits.

## 4. Existing-material preparation flow

- [x] 4.1 Route newly created courses to the course file system and persist pending, review, completed and skipped preparation states.
- [x] 4.2 Add folder selection, multi-file selection and recursive directory drag/drop while preserving relative paths and empty folders.
- [x] 4.3 Replace formal-to-formal inspector links with primary-original, reference-original and original-usage views.
- [x] 4.4 Cover preparation-state compatibility, relationship-source boundaries, course-create routing and file-space UI behavior with tests.
- [x] 4.5 Verify new-course entry, batch import, review state and completion in the real browser UI.
- [x] 4.6 Replace the full-page preparation state with a workbench starting-point dialog and recognized-structure confirmation.
- [x] 4.7 Register imported originals for generation, auto-match stage sources, and preserve later teacher overrides.
- [x] 4.8 Verify the new entry, import review, source auto-match, focused tests, build and desktop browser states.
- [x] 4.9 Parse imported originals and run one bounded batch AI analysis over document purpose, course placement, version role and file relationships.
- [x] 4.10 Persist confidence, reasons, missing-material gaps and explicit rule fallback while preserving teacher-confirmed types.
- [x] 4.11 Surface the four-dimensional result in both the preparation review and course-file inspector without changing formal-file relationship boundaries.
- [x] 4.12 Verify focused backend/frontend tests, a real provider request with an ambiguously named document, and the real desktop page.
