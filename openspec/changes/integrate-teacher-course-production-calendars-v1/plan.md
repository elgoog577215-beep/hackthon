# Implementation Plan

## 1. Contract

- Change: `integrate-teacher-course-production-calendars-v1`
- Product truth: `docs/product/启智教师课程工作台_完整规划与开发图.md`
- Stable work packages: `tasks.md`
- Evaluation: `eval-contract.md`
- Strategy: existing isolated worktree, serial integration on top of existing course/generation/PPT contracts
- Authority: current user request authorizes planning and worktree implementation; no push, force operation, `.env` write, lockfile change or destructive cleanup

This plan is the mutable execution truth. The simulated page is not a product or state-machine contract. It may only inform visual tone, density, control size and spacing rhythm.

## 2. Outcome and release definition

### 2.1 Product V1 outcome

A teacher can enter a course workspace, create or open a course, stop and resume the real `outline → teaching plans → PPT → release` workflow, maintain a course teaching calendar, and see all owned course sessions in a teacher total calendar. The system must use real stores/APIs, preserve existing generation/PPT semantics, expose understandable failures, and keep teacher confirmation separate from student publication.

### 2.2 V1 is not a one-shot milestone

`V1.0-alpha` is a functional integration slice, not the complete product V1:

- real course identity and real generation state are visible;
- manual course calendar persistence and total-calendar aggregation work;
- major route and layout gaps may still remain and must be labelled.

`V1.0 release` additionally requires:

- correct teacher workspace entry, teacher overview and six single-course destinations;
- the final production interaction model: lesson table → large preview → immersive lesson workspace;
- complete responsive/UI hard gates;
- outline/calendar import candidates and the confirmed Zhejiang University editable DOCX + reading PDF export path;
- success/failure, permission and model-backed validation evidence.

The CourseAsset file-space bridge, student private notes/AI feedback and knowledge-node cascade are explicitly later phases unless a separate change authorizes them.

## 3. Locked product logic

### 3.1 Navigation hierarchy

```text
Platform home
└─ Course workspace
   ├─ My courses (default)
   │  ├─ group by academic year / term
   │  ├─ new course
   │  └─ open course → teacher course overview
   └─ Teacher total calendar

Single-course workspace
├─ Course overview
├─ Teaching outline
├─ Teaching calendar
├─ Course production
├─ Course files
└─ Release management
```

Rules:

1. A course card always opens the teacher course overview. It never jumps by current task status.
2. The overview shows next class, asset progress, actionable exceptions and one recommended next action. It is not the student `LearningView` and does not render course正文.
3. Outline, calendar, production, files and release are separate professional pages that share one `courseId` and one asset/state truth.
4. Course production only contains lesson overview, teaching-plan production and PPT production. Student-oriented content remains at its existing route in V1.
5. Teacher total calendar lives beside My Courses, not inside a single course.

### 3.2 Creation and production state flow

```text
Create recoverable course shell
  ├─ AI plan from brief + selected materials + optional web search
  ├─ import existing outline and recognize into a managed draft
  └─ start blank
          ↓
Outline draft
  ├─ save / AI candidate / compare / discard
  └─ explicit teacher confirmation
          ↓
Confirmed outline version
  ├───────────────┐
  ↓               ↓
Calendar draft    lesson teaching-plan drafts (parallel, per lesson)
  ↓               ↓
confirm/export    explicit teaching-plan confirmation
                  ↓
                  PPT becomes eligible, generated only on demand
                  ↓
                  PPT draft / compare / confirm
                  ↓
select lesson + asset + exact version
                  ↓
immutable student release snapshot
```

Rules:

- saving never confirms; confirmation never publishes;
- the teacher may stop after the outline or any set of teaching plans and continue later;
- calendar completion is not a hard gate for teaching-plan or PPT generation;
- an upstream revision never silently overwrites downstream work; downstream assets become `stale/needs_regeneration` while last-good remains usable;
- failures are per task/per lesson and do not erase successful siblings;
- each lesson may have multiple PPT assets; each PPT asset has working, confirmed and published version pointers; history is folded in details, not encoded in filenames.

### 3.3 Course production interaction

Default production view:

1. one course navigation surface only;
2. one top status line with course, teaching-plan count, PPT count, failures and next action;
3. compact secondary switch: lesson overview / teaching plans / PPT;
4. immediate lesson table with lesson, date, topic, teaching-plan state, PPT state, student release version and next action;
5. no fixed production-stage sidebar and no fixed right status/version sidebar.

Progressive opening:

1. click an asset state → large quick preview;
2. preview supports previous/next lesson, source/version context and close with scroll/filter/focus restoration;
3. click Continue → immersive workspace;
4. only immersive mode collapses course navigation and adds a lesson rail;
5. center switches only between teaching plan and PPT;
6. versions, sources, AI evidence and impact open in drawers; long tasks use a bottom-right task popover backed by `CourseTaskCenter`.

### 3.4 Calendar model and linkage

- `LessonUnit` means what is taught; `ClassSession` means when/where/by whom/to which group.
- one LessonUnit may map to multiple sessions such as A/B/C groups.
- outline confirmation may derive session candidates; it never overwrites dates, locations, teachers or manual edits.
- course calendar supports table as default plus month/week views; short fields edit inline, long content/requirements/notes edit in a side editor.
- teacher total calendar is a read-only aggregation in V1; editing occurs in the course calendar and both views read the same ClassSession.
- calendar import preserves original evidence and creates recognition/diff candidates before teacher acceptance.
- Zhejiang University is the first formal template: editable DOCX is the main handoff; PDF is the fixed reading output. Column order, 63-record reference behavior, groups, pagination and final notes region are acceptance evidence.

### 3.5 Managed assets and file-space boundary

- Outline, calendar, teaching plans and PPT are managed CourseAssets with stable IDs and versions.
- Production and file space are two projections of the same assets, never two copies.
- V1 navigation keeps the Course Files destination, but the CourseAsset file bridge starts only after production and calendars are stable.
- Later folder template: `0 outline / 1 calendar / 2 lesson teaching plans / 3 PPT / 4 references`; versions do not appear in filenames.

### 3.6 Teacher/student boundary

- teacher drafts are private by default;
- student view reads only a frozen published snapshot;
- student private notes and private AI conversations do not flow back to the teacher;
- later feedback may include student-submitted questions and aggregated node-level signals only;
- V1 does not redesign the student surface.

## 4. UI inheritance and layout contract

### 4.1 Inherit, do not recreate

Directly inherit existing:

- color/type/radius/shadow tokens (`--lz-*`, `--space-*`);
- buttons, icon buttons, Badge, inputs, selects, tables, Tooltip;
- Drawer, Dialog, Toast/Message, Confirm and focus/error behavior;
- `CourseOutlineReview`, `GenerationLessonPlan`, `CourseGenerationGate`, `CourseTaskCenter`, PPT workspace and existing AI panels.

### 4.2 Recompose by function

Do not inherit page geometry blindly. Page grid, sidebar behavior and spacing are chosen after the page task is known:

- course collection prioritizes scanning courses and one next action;
- overview prioritizes next class and asset exceptions;
- outline prioritizes chapter navigation and long-form editing;
- calendar prioritizes a wide editable schedule;
- production prioritizes lesson scanning, preview and immersive creation;
- release prioritizes exact asset/version comparison and impact.

Spacing uses existing 4/8/12/16/24/32 rhythm, but grouping density changes by relationship. No decorative cards are added to fill empty space. Sidebar width is derived from complete labels, icons/badges and the minimum usable body width; when space is insufficient, secondary context collapses before the body is squeezed.

### 4.3 Responsive hard behavior

- `≥1200`: one course sidebar + top status + main body; lesson rail only in immersive mode.
- `900–1199`: course sidebar becomes labelled-tooltip icon rail; details move to drawers; tables may scroll.
- `680–899`: 64px icon rail is allowed only if no active label becomes vertical; status reduces to current page, exception count and next action.
- `<680`: course functions become a horizontally scrollable top short navigation; body becomes full width; toolbars may wrap; wide tables keep lesson/action columns reachable.
- deep editing may recommend desktop, but view/save/back/error recovery must remain reachable.

Prohibited: vertical Chinese labels, hidden primary action, three permanent sidebars, card grids for status, thick colored side accents, fake metrics, explanation walls and new component styling that conflicts with the project.

## 5. Work packages and dependencies

### WP0 — Plan and design contract [complete]

Deliverables:

- reconcile all confirmed product decisions with proposal/design/tasks/eval/plan;
- keep simulation visual-only;
- record current code-to-plan gaps;
- validate OpenSpec.

Exit:

- all 20 confirmed decisions have a plan owner;
- no product V1 item is mislabelled completed by the alpha slice;
- OpenSpec strict validation passes.

### WP1 — Course workspace entry and creation [functional alpha; backend shell gap remains, P0]

1. Make My Courses and Teacher Total Calendar sibling destinations in one teacher workspace shell.
2. Group course list by academic year/term; keep course cards dense and limited to identity, audience/hours, outline/calendar/teaching-plan/PPT status and one next action.
3. Replace the create modal as the main teacher flow with a recoverable three-step page:
   - basic course identity → create shell exactly once;
   - scheduling basics (may defer, required before calendar derivation);
   - outline starting point: AI plan / import / blank.
4. Reuse the existing generation request contract and material upload; no second generation API.

Exit:

- refresh after step 1 returns to the same course shell;
- repeated click does not create duplicate course/generation requests;
- no unauthorized course is visible.

### WP2 — Single-course route truth and teacher overview [functional alpha; file route gap remains, P0]

1. Add a teacher-specific overview route and page.
2. Ensure all six navigation items keep `courseId` and restore course context.
3. Outline, production and release may reuse a shared shell, but their bodies and states remain separate.
4. Course Files must not drop into an unscoped generic space; until the asset bridge exists, expose a truthful pending/limited state rather than a false context.

Exit:

- course card → teacher overview;
- each nav destination is correct and back returns to the same course;
- student editor/content is not exposed as teacher overview.

### WP3 — Real production orchestration [functional alpha; active-task and PPT-source gaps remain, P0]

1. Preserve `courseStore.loadCourse(courseId)` and `generationStore.observeCourse(courseId)` lifecycle, including unobserve on leave.
2. Derive outline/teaching/PPT/release availability from real task workflow, projection and existing workbench data.
3. Rebuild production overview to the interaction in 3.3.
4. Reuse real teaching-plan workbench and route to existing PPT workspace with canonical-source and legacy migration gates intact.
5. Add understandable blocked/failed/stale states, per-lesson retry and last-good presentation.
6. Add task popover and full task center; preserve web-search sources, excluded sources and failure evidence.

Exit:

- no local fake lesson array, setTimeout success or parallel store;
- refresh preserves task/phase/failure;
- the teacher can finish only selected teaching plans and leave before PPT;
- PPT interface semantics remain unchanged.

### WP4 — Course teaching calendar core [functional alpha complete; release gaps pending]

Completed alpha surface:

- `TeachingCalendarV1/ClassSessionV1` file repository;
- stable session ID, owner/course isolation, atomic save and revision conflict;
- manual add/edit/delete/save;
- outline-derived initial candidates;
- table/month surface and course navigation entry.

Remaining for V1 release:

1. finish week view and side editor for long fields;
2. expose candidate diff rather than treating derivation as direct replacement;
3. add scheduling-base completeness checks and actionable conflicts;
4. guarantee delete confirmation/undo and revision conflict recovery;
5. pass all responsive/UI gates.

### WP5 — Teacher total calendar [functional alpha complete; shell integration pending]

Completed alpha surface:

- owner-scoped aggregation API;
- month/week/list representation;
- course color key and route-back context.

Remaining:

1. place My Courses / Teacher Total Calendar in the same workspace shell;
2. verify dense multi-course days, empty/error/loading states and exact session focus;
3. ensure V1 remains read-only and never creates a duplicate session.

### WP6 — Calendar import, school calendar and formal export [follow-up change required; product V1 release]

1. Import existing teaching outline/calendar from PDF and Excel first; Word follows after contract stability.
2. Store original file, recognition evidence, field confidence and unresolved rows.
3. Import school calendar holidays/make-up days and generate conflict proposals with original value, suggestion, reason and impact.
4. Apply proposals only after explicit teacher selection; never silently shift all dates.
5. Implement editable Zhejiang University DOCX export and fixed PDF output from the same managed data.
6. Compare course metadata, 10 columns, record count, A/B/C grouping, cross-page layout and final notes area with the reference.

Exit:

- import failure names the unsupported structure/field and preserves the original file;
- export content is searchable/editable where required and contains no browser print noise;
- data-to-DOCX-to-PDF fields reconcile.

### WP7 — CourseAsset file-space bridge [separate follow-up change after V1 course/calendar stabilization]

1. Open Course Files with `courseId` and stable CourseAsset IDs.
2. Auto-place generated assets without copying content.
3. Preserve lesson relations after move/rename.
4. Support folder import/classification as review candidates, empty folders, download/export and confirmed deletion.

This package must not block WP1–WP6 and must not be started by changing generation/PPT interfaces.

### WP8 — Teacher/student feedback, collaboration and knowledge cascade [separate later change]

- collaboration role split for edit/confirm/publish;
- student private-note/PPT-derived-note product;
- submitted questions and aggregated learning feedback;
- knowledge-node graph and explicit downstream regeneration proposals.

No WP8 behavior is claimed in V1.

### WP9 — Teacher/student surface isolation and merge compatibility [planned; current round]

1. Freeze route ownership: student stays on `/courses` and `/course/:courseId/learn`; teacher uses `/teacher/courses` and `/teacher/course/:courseId/...`.
2. Preserve the original student course library and learner flow; retain the current teacher course-library experience in a teacher-owned view.
3. Introduce one teacher runtime adapter as the only teacher-page entry to shared course and generation stores. It may translate state and forward commands, but it may not copy course/task/PPT state.
4. Move teacher-only authoring/orchestration endpoints out of the shared courses router into a teacher router. Existing student and shared engine endpoints keep their paths and semantics.
5. Reconcile with `origin/main` using file ownership:
   - upstream wins for student pages, shared generation policy, model/retry/search/PPT internals;
   - this change wins for teacher pages, calendars, teacher routes and teacher orchestration;
   - shared components keep only backward-compatible props/events covered by contract tests.
6. Restore or split teacher-branch edits that alter global budgets, validation policy, polling or student navigation unless they are independently required and proven for both surfaces.
7. Verify both surfaces before creating the merge-ready local commit.

Exit:

- original student routes, default navigation and API behavior have regression evidence;
- teacher routes and teacher-only endpoints are namespaced and directly testable;
- teacher preview is read-only;
- the adapter has no duplicated content/task source;
- the final diff report classifies every changed shared file and contains no runtime data, secret, generated artifact or unrelated worktree file;
- no push or main merge occurs without a later explicit user request.

## 6. Current implementation checkpoint

| Area | Current evidence | Honest status |
| --- | --- | --- |
| six nav labels/order | shared course sidebar + six named routes | overview/outline/calendar/production/files/release share the course-scoped shell |
| production real store/API wiring | `loadCourse` + `observeCourse/unobserveCourse` | published maintenance path, real AI candidate and real PPT streaming build pass; active generation review fixture still required |
| production overview | compact tabs + immediate lesson table | Markdown/KaTeX preview, persistent next action and PPT registry state pass at 1440/680 |
| quick preview | large lesson preview from real nodes | opens and continues into teaching/PPT; previous/next and focus restoration remain |
| immersive lesson workspace | real `GenerationLessonPlan` + lesson rail | AI creates a real draft and field-level candidate; accepted-candidate confirmation path still requires a disposable fixture |
| course calendar persistence | backend/frontend tests + browser save/reload | functional alpha plus truthful CSV exchange; formal recognized import and DOCX/PDF remain release work |
| total calendar aggregation | browser/API pass with three courses/five sessions | month/week/list and session-focused route-back pass; dense same-day overflow still required |
| 680 responsive | horizontal course-function navigation | overview/production browser pass; no vertical Chinese observed |
| recoverable new course | three-step page + local draft + real AI/import entry | browser/build pass; blank shell disabled because backend API is absent |
| formal import/export | CSV exchange only | Zhejiang editable DOCX/read-only PDF and evidence-preserving recognition remain V1 release pending |
| course file bridge | course-scoped embedded file view | context bridge passes; stable CourseAsset identity/auto-placement remains later |
| DeepSeek model-backed generation | real teaching-plan AI candidate + real 11-slide PPT build | both model-backed paths passed in the current configured runtime; secret provenance was not read or written |

## 7. Verification map

### Code/API

- backend calendar tests: success, invalid time, unknown course, owner isolation, revision 409, non-overwrite derivation, aggregation;
- frontend store/router/entry tests;
- build/type validation and locale JSON parse;
- strict OpenSpec validation;
- generation/PPT API semantic diff review.

### Real browser

Use at least:

- one generating course;
- one partially failed/stale course;
- one published course;
- two courses with overlapping calendar sessions;
- one A/B/C repeated lesson group.

Flows:

1. My Courses → course overview → each of six destinations → back with same context.
2. Outline draft → confirm → calendar and teaching plans both become available.
3. Lesson table → preview → previous/next → immersive teaching plan → PPT → back to original lesson/scroll.
4. Pause after teaching plan; reload and later continue PPT.
5. Per-lesson failure → reason → retry without losing successful siblings.
6. Calendar edit/add/delete/save → reload/backend restart → same data.
7. Course calendar edit → total calendar reflects same session → click back focuses it.
8. Import recognition failure and revision conflict preserve work and name the recovery action.

Viewports: 1440, 1180, 880 and 680. Every viewport checks navigation readability, main action reachability, horizontal scroll, focus, console and page errors. Visual acceptance is required in addition to functional assertions.

### Model/runtime

- configure secrets only through a user-controlled/system environment mechanism;
- never write the supplied key to source, `.env`, logs, docs or commits;
- verify one real outline/teaching-plan generation with official DeepSeek flash configuration, local materials and optional web search;
- if web search fails but local evidence is sufficient, label the reduced-evidence result; otherwise block with the missing-evidence reason.

## 8. Rollback and stop rules

- If production integration requires changing generation/PPT semantics, stop and revise the plan; do not create a parallel API.
- If calendar ownership cannot be proven, keep writes isolated and do not claim full teacher authorization.
- If any hard gate fails, the milestone remains incomplete even if build/tests pass.
- Route rollback may hide the new pages without deleting calendar JSON.
- No destructive cleanup, force push, secret persistence or user-data migration is authorized.

## 9. Progress

- [x] P0a Capture complete product decisions and correct simulation-reference boundary.
- [x] P0b Define LessonUnit/ClassSession and CourseAsset/version invariants.
- [x] P0c Add current code-to-plan gap audit and update OpenSpec contract.
- [x] P0d Obtain user acceptance of this detailed plan and UI layout contract.
- [ ] WP1 Course workspace entry and recoverable new-course flow. (Alpha page complete; idempotent blank shell API and term grouping remain.)
- [x] WP2 Teacher overview and six route destinations. (All six routes retain the course context; stable CourseAsset identity remains WP7.)
- [x] WP3 First-round production overview/preview/immersive workflow. (Ten-lesson projection, real teaching-plan workbench, AI candidate flow, PPT pre-release source and read-only teacher preview are closed; multi-PPT asset/version history remains a later CourseAsset change.)
- [x] WP4a Course calendar persistence functional alpha.
- [x] WP4b Course calendar first-round UX/conflict/responsive completion.
- [x] WP5a Total calendar aggregation functional alpha.
- [x] WP5b Total calendar workspace-shell and dense-state completion.
- [x] WP6a Zhejiang template export: editable DOCX, fixed PDF, XLSX and CSV from one saved revision.
- [ ] Handoff WP6b to a follow-up change: school calendar and Word/PDF/Excel recognition with evidence/confidence review.
- [ ] Handoff WP7 to a separate file-space bridge change after production/calendar stabilization.
- [ ] Keep WP8 outside the current change; later student/collaboration/knowledge change only.
- [x] Alpha verification, direct evidence and issue record: frontend 813 tests, backend calendar 5 tests, build and real browser at 1440/680.
- [ ] V1 release verification with active/failed model-backed courses, overlapping calendars, import/export and permissions.

## 9.1 Current closure round (2026-08-14)

- [x] R1 Freeze and implement one compatibility projection. `frontend/src/utils/lesson-units.ts` and the backend calendar derivation treat each top-level outline chapter as one `LessonUnit`; all descendants are in-lesson content; each calendar row is a `ClassSession`.
- [x] R2 Replace teacher-facing leaf-node projections with the shared `LessonUnit` projection. Overview, production, immersive navigation, release rows and calendar derivation now agree on ten lectures for the acceptance course.
- [x] R3 Separate teacher PPT authoring from student publication through a compatibility adapter. A teacher-confirmed source opens the unchanged PPT workspace before release without fabricating a student publication.
- [x] R4 Project lifecycle from one precedence rule and apply task polling cache/backoff. Stale completed jobs no longer override newer confirmed teacher assets.
- [x] R5 Add `teacher-preview` as a read-only learner rendering mode. Browser network assertions observed zero learning-record, progress, practice or AI-conversation mutations.
- [x] R6 Close single-course calendar gaps. Dense table is default; month/week remain alternate views; complete scheduling semantics, candidate diff, dirty guards, normalized time controls and responsive lecture navigation are verified.
- [x] R7 Close total-calendar gaps. Entry/focus refresh, stable colors, filters, incomplete layer, overlap conflicts, asset readiness popover and exact schedule/preparation navigation are verified.
- [x] R8 Produce the first Zhejiang University export from the same saved revision: editable DOCX, fixed PDF, XLSX and CSV. The final verification used revision 14 with ten sessions; DOCX contained an editable 10-column table and PDF rendered with searchable text and no clipping.
- [x] R9 Run focused backend/frontend tests, production build and real-browser acceptance. Final evidence: backend 29 passed; frontend 51 passed; production build passed; nine Playwright flows passed at desktop and 1024/880 responsive widths, supplementing the earlier 1440/1180/880/680 sweep.

### 9.2 Acceptance gates for this closure round

| Gate | PASS condition | Failure/rollback condition |
| --- | --- | --- |
| G1 Domain consistency | The same test course is 10 lectures in overview, production and calendar; one lecture may contain N knowledge nodes and N schedule records. | Any page derives lecture count directly from leaf/content node count. |
| G2 Authoring continuity | Outline confirmation opens per-lecture lesson-plan work; a confirmed lesson plan can open the unchanged PPT workspace before student release. | PPT requires `is_published`, or the adapter writes a fake release. |
| G3 Version isolation | Working draft, teacher-confirmed version and student-published snapshot are separately named and projected. | Saving/previewing a teacher draft changes learner-visible state. |
| G4 Calendar integrity | Outline derivation is a visible candidate diff; manual schedule fields survive; only complete sessions appear as scheduled. | Candidate silently overwrites saved data or incomplete sessions enter the official total calendar. |
| G5 Read-only preview | Teacher preview performs GET-only learner rendering and returns to the originating teacher page. | Any learning record, AI conversation, progress or practice mutation is observed. |
| G6 UI contract | Existing components/tokens are reused; status is concentrated at the top; categories stay in the left rail; body content appears in the first viewport; four target widths remain usable. | New visual system, explanatory-card sprawl, hidden core navigation or clipped controls. |
| G7 Export fidelity | DOCX is editable and PDF/row sequence/metadata reconcile with the first Zhejiang template. | Screenshot-only/raster document, mismatched record count or independent export data source. |

## 10. Confirmed-decision traceability

| # | Confirmed decision | Plan owner | Release proof |
| --- | --- | --- | --- |
| 1 | simulation is visual-only; product logic comes from confirmed scheme | WP0 | document/OpenSpec diff + original simulation unchanged |
| 2 | My Courses and Teacher Total Calendar are siblings | WP1/WP5 | shared workspace-shell browser proof |
| 3 | recoverable new-course page; AI/import/blank converge | WP1 | duplicate-safe create + reload recovery |
| 4 | course card always opens teacher overview with one next action | WP2 | route and overview assertions |
| 5 | six single-course destinations | WP2 | all route/context assertions |
| 6 | outline, teaching plan and PPT are explicitly separated | WP3 | real-state flow browser proof |
| 7 | teaching plan can finish without PPT; tasks fail/retry independently | WP3 | pause/reload/partial-failure proof |
| 8 | lesson table → large preview → immersive creation | WP3 | interaction and return-context proof |
| 9 | one intelligent primary action; secondary actions grouped | WP1–WP6 UI | per-page action inventory |
| 10 | task popover + real task center; web evidence retained | WP3 | task/source/failure browser proof |
| 11 | calendar table default, calendar views optional, long fields in side editor | WP4 | CRUD/view/side-editor proof |
| 12 | Zhejiang template; DOCX editable and PDF fixed | WP6 | field/row/page reconciliation |
| 13 | total calendar read-only aggregation in V1 | WP5 | same-session identity and route-back proof |
| 14 | folder template 0–4; versions not in names | WP7 | later file bridge acceptance |
| 15 | real backend/store state only | all | no fake timer/store scan + reload proof |
| 16 | LessonUnit and ClassSession are distinct | WP4 | model/API tests including A/B/C groups |
| 17 | production and files share CourseAsset truth | WP7 | stable asset ID after move/rename |
| 18 | high density, strong classification, low distraction, body first, original components | all UI | component/token audit + four-view browser proof |
| 19 | teacher confirmation and student release are separate exact-version operations | WP3/release | version pointers and frozen snapshot proof |
| 20 | student-oriented content remains at the existing entry in V1 | WP2/WP3 | route/source review |

Unresolved items are not hidden requirements: second school template, calendar-format priority beyond PDF/Excel, final student-content placement, collaborative-teacher role split and personal reminders remain separate decisions. They may not silently expand WP1–WP6.

## 11. Merge-ready isolation round

### 11.1 Frozen contract

| Boundary | Student owner | Teacher owner | Shared engine |
| --- | --- | --- | --- |
| Product route | `/courses`, `/course/:id/learn` | `/teacher/courses`, `/teacher/course/:id/...` | none |
| Course entry | existing learner library and resume behavior | teacher course library and teacher overview | course identity/list query |
| Generation UX | existing learner generation/projection | outline → lesson plan → PPT → release orchestration | jobs, task events, model/search providers |
| Authoring | no teacher actions embedded in learner pages | teacher adapter and authoring endpoints | course document, teaching-plan and representation engines |
| Preview | normal learner behavior | explicit read-only teacher preview with return context | common renderer |
| Data | learning/progress/practice/AI conversations | teacher drafts, calendars, release intent | immutable published course versions |

### 11.2 Ordered implementation

- [ ] M1 Snapshot current dirty state and classify user/runtime files; exclude all runtime JSON, screenshots, generated exports and local harness receipts from source scope.
- [ ] M2 Add route-contract tests first, then complete the `/teacher` namespace while restoring `/course/:courseId` to the learner route.
- [ ] M3 Preserve the teacher library in `TeacherCourseLibraryView` and restore `CourseLibraryView` to upstream student behavior; split tests by surface.
- [ ] M4 Replace direct teacher-page store imports with `useTeacherCourseRuntime`; add an architectural test that teacher views do not import student stores directly.
- [ ] M5 Move confirm-generation-preview and future teacher commands to a teacher authoring router; update the teacher workbench client and cover 400/404/409/422/success.
- [ ] M6 Compare every shared-file modification with `origin/main`; restore upstream-owned strategy changes, retain only minimal compatibility extensions, and document any unavoidable overlap.
- [ ] M7 Rebase or merge the current upstream snapshot only after M2–M6 produce a narrow diff; resolve shared engines in favor of upstream and reconnect through adapters.
- [ ] M8 Run focused and full-enough regression: router contracts, student course library/lifecycle, teacher library/workflow, teacher preview write guard, backend teacher authoring, calendars, frontend build and real browser flows.
- [ ] M9 Run `git diff --check`, secret/runtime-artifact scan, changed-file ownership report and conflict forecast; create one local merge-ready commit only after all hard gates pass.

### 11.3 Hard gates

| Gate | PASS | BLOCK |
| --- | --- | --- |
| Student preservation | `/courses` and learner routes render and keep existing resume/learning semantics | any default route lands in teacher UI or student API changes |
| Teacher autonomy | teacher can create/open a course and run its staged authoring flow through teacher routes | teacher UI depends on learner-page navigation or mutations |
| Shared capability | current upstream generation/search/PPT implementation is reused | duplicated engine/state or pinned older provider behavior |
| Merge safety | all overlap is classified and shared strategy follows upstream | unexplained edits remain in shared generation/student files |
| Data safety | teacher preview is read-only and no runtime data/secrets enter the diff | preview writes learning state or source diff contains local data/secrets |
| UI regression | existing components/tokens remain and both products are browser-usable | new visual system or teacher isolation breaks student layout |

### 11.4 Failure and rollback

- If the adapter needs a second copy of course/task/PPT state, stop and redesign the contract.
- If a teacher requirement needs a breaking student/shared API change, add a teacher endpoint or backward-compatible engine extension; do not silently change the old contract.
- If upstream integration creates unresolved engine conflicts, keep the teacher commit local and report the exact files instead of choosing by intuition.
- Route isolation can be rolled back by removing teacher route registration without deleting teacher calendar or course data.
