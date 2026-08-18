## 1. Contract and regression baseline

1.1 Freeze teacher task types, lesson/section identifiers, asset revision fields and zero student-write boundary.

1.2 Add failing backend and frontend tests for teacher hard lesson count, lesson-scoped tasks, usable fallback completion, section navigation and student lifecycle preservation.

## 2. Teacher outline stop point

2.1 Map teacher `expectedSessions` to explicit lesson-unit count and preserve default lesson duration separately from total section count.

2.2 Add teacher outline task/orchestration that reuses current outline planning but completes after teacher outline confirmation without teaching-plan/content continuation.

2.3 Project the confirmed outline and frozen lesson knowledge scope into the teacher workspace without exposing it as a student generation preview.

## 3. Lesson-scoped teaching-plan assets

3.1 Implement atomic `TeacherLessonAuthoringRepository` with per-course/per-lesson working and confirmed revision pointers.

3.2 Implement `teacher_lesson_plan_generation` creation, idempotency, stable scoped checkpoints and task projection.

3.3 Reuse current teaching-plan planning for one lesson and all its child sections; accept schema-valid deterministic fallback as `completed_with_warnings`.

3.4 Implement lesson-plan read, manual draft patch, confirm, whole-lesson/section AI candidate, accept and reject contracts.

3.5 Implement lesson-filtered knowledge evidence projection.

## 4. Teacher lesson production UI

4.1 Add a teacher lesson-authoring Store/adapter that observes only teacher outline/lesson/PPT tasks.

4.2 Separate `lessonUnitId` and `sectionNodeId` in production routing and component props.

4.3 Expand the selected lesson's child sections in the left rail; implement section/lesson views and truthful previous/next navigation.

4.4 Show per-lesson state, generate/retry/edit/AI/confirm actions, warning details and knowledge-evidence drawer.

## 5. Lesson-scoped PPT

5.1 Define a teacher lesson-plan authoring source adapter for V6 without writing student CourseDocument content.

5.2 Implement `teacher_lesson_ppt_generation` and per-lesson primary deck revision/source pointers.

5.3 Connect the teacher PPT route/workbench to exact lesson and lesson-plan revision; preserve old deck when source becomes stale.

5.4 Add independent whole-deck/page-range AI candidate actions through existing PPT editing contracts.

## 6. Verification and handoff

6.1 Run focused backend and frontend tests, student regression tests, type/build and OpenSpec validation.

6.2 Run real browser flows for exact lesson count, selective lesson generation, section navigation, edit/AI, PPT, reload and current-lesson-only failure.

6.3 Review console/network, confirm zero teacher content-generation and zero student task/data mutation, and record remaining deferred scope.
