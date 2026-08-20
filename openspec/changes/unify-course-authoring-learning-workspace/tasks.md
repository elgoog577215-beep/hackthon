## 1. Contract and navigation

- [x] 1.1 Freeze the calendar-file-space-formal-course information architecture, terminology and source-of-truth boundaries.
- [x] 1.2 Make the teaching calendar the teacher home with a wider course rail and non-title-derived course icons.
- [x] 1.3 Make course entries open the file space and add an explicit formal-course preview route.
- [x] 1.4 Redirect legacy teacher routes without preserving the duplicate four-stage tab bar.

## 2. Course file space

- [x] 2.1 Separate left folder navigation, current-folder files, and right-side file details.
- [x] 2.2 Group assets as outline, lesson plan, material, PPT and practice without splitting material into duplicate categories.
- [x] 2.3 Provide type-specific create dialogs and keep stable `course_id` ownership for file packages.
- [x] 2.4 Project folder navigation to a horizontal mobile control instead of stacking the desktop tree.
- [x] 2.5 Split PPT creation into AI-generated and teacher-uploaded flows, preserving uploaded originals and optionally deriving a reviewable lesson-plan draft from PPTX evidence.
- [x] 2.6 Create an empty course space before generation; keep contextual New actionable in every folder while enforcing one outline per course, one lesson plan/PPT/practice per lesson, and multiple materials.

## 3. Formal course and teacher agent

- [x] 3.1 Reuse the formal learning surface as a read-only teacher preview assembled from course blocks and formal practice.
- [x] 3.2 Add a teacher-agent entry in the course file space with teacher-specific prompts and actions.
- [x] 3.3 Prevent teacher mode from exposing learner evidence, learner-note actions or web retrieval.
- [x] 3.4 Keep semantic changes behind impact preview, teacher confirmation and affected-unit rebuild.

## 4. Same-source authoring

- [x] 4.1 Reuse `CourseOutlineReview` and the structured lesson-plan revision chain rather than creating parallel truth.
- [x] 4.2 Keep PPT truth in `TeachingRepresentation / SlideDeckSpec` and expose stale source status in the file space.
- [ ] 4.3 Complete durable dependency indexes and asynchronous precise rebuild for every lesson-plan, content, practice and PPT unit.
- [ ] 4.4 Verify failure recovery keeps the last usable representation for all supported asset types.

## 5. Verification and release

- [x] 5.1 Add/update backend and frontend tests for teacher perspective, folder navigation, formal preview and same-source wording.
- [x] 5.2 Run relevant backend tests, frontend tests/build, `openspec validate --all` and the frontend design detector.
- [x] 5.3 Verify zh/en and desktop/mobile real pages for calendar, file navigation, teacher agent and formal preview.
- [x] 5.4 Update canonical product/status docs, commit only task files and push the branch.
