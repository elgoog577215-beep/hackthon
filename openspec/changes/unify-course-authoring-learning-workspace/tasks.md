## 1. Contract and navigation

- [x] 1.1 Freeze the three-mode information architecture, terminology and source-of-truth boundaries.
- [x] 1.2 Add the unified course route and shared mode navigation in zh/en.
- [x] 1.3 Make course cards enter the unified workspace while resume actions still enter the saved learning location.
- [x] 1.4 Redirect legacy teacher routes to the matching unified mode and remove the production overview from the active product flow.

## 2. Course setup

- [x] 2.1 Build basic information, files, course design and teaching calendar submodes in the original course visual system.
- [x] 2.2 Add stable `course_id` ownership to course-space packages and cover backward-compatible repository/API behavior.
- [x] 2.3 Embed file and calendar workspaces without their old teacher shell or duplicate course reload.

## 3. Course preparation and formal use

- [x] 3.1 Reuse `CourseOutlineReview` for outline editing without creating a second outline tree.
- [x] 3.2 Present `CourseTeachingPlan.overall` as course design and `.sections` as lesson preparation using one workbench revision chain.
- [x] 3.3 Keep formal practice and PPT truth, and provide direct preparation actions into the existing formal workspaces.
- [x] 3.4 Keep the original learning surface as the formal-course mode and preserve its course/practice/PPT tools.

## 4. Performance and convergence

- [x] 4.1 Load only the current submode and keep visited submodes alive within the same course.
- [x] 4.2 Stop the unified flow from reading or writing the parallel teacher lesson-authoring repository.
- [x] 4.3 Record the compatibility and production-data audit required before deleting old teacher APIs and files.

## 5. Verification and release

- [x] 5.1 Add/update backend and frontend tests for course binding, routes, navigation and module behavior.
- [x] 5.2 Run relevant backend tests, frontend tests/build, `openspec validate --all` and diff checks.
- [x] 5.3 Verify zh/en and desktop/mobile real pages, including loading, empty, error and focus states.
- [x] 5.4 Update canonical product/status/architecture docs, commit only task files and push the branch.
