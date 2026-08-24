## 1. Contract and navigation

- [x] 1.1 Freeze the calendar-file-space-formal-course information architecture, terminology and source-of-truth boundaries.
- [x] 1.2 Keep the teacher home as a two-tab surface for the full teaching calendar and the full course library; retain a calendar-side course shortcut rail for search and direct entry.
- [x] 1.3 Make course entries open the file space and add an explicit formal-course preview route.
- [x] 1.4 Redirect legacy teacher routes without preserving the duplicate four-stage tab bar.

## 2. Course file space

- [x] 2.1 Separate left folder navigation, current-folder files, and right-side file details.
- [x] 2.2 Group assets as outline, lesson plan, material, PPT and practice without splitting material into duplicate categories.
- [x] 2.3 Provide type-specific create dialogs and keep stable `course_id` ownership for file packages.
- [x] 2.4 Project folder navigation to a horizontal mobile control instead of stacking the desktop tree.
- [x] 2.5 Split PPT creation into AI-generated and teacher-uploaded flows, preserving uploaded originals and optionally deriving a reviewable lesson-plan draft from PPTX evidence.
- [x] 2.6 Create an empty course space before generation; keep outline, lesson plan, content, practice and companion PPT visible as direct asset entries with `Not generated` states, while materials use explicit add-file and add-folder actions.
- [x] 2.7 Restore the course-level teaching calendar as a fixed managed file type, reuse the existing outline-derived editor and exports, and route legacy calendar links into the unified workspace.

## 3. Formal course and teacher agent

- [x] 3.1 Reuse the formal learning surface as a read-only teacher preview assembled from course blocks and formal practice.
- [x] 3.2 Add a teacher-agent entry in the course file space with teacher-specific prompts and actions.
- [x] 3.3 Prevent teacher mode from exposing learner evidence, learner-note actions or web retrieval.
- [x] 3.4 Keep semantic changes behind impact preview, teacher confirmation and affected-unit rebuild.
- [x] 3.5 Reuse the existing centered top bar for file/category and question-book view switches instead of adding dedicated rows.
- [x] 3.6 Upgrade the existing assistant context and prompts with teacher file-scope discipline and intent-adaptive learner/teacher response strategies, without adding an endpoint.
- [x] 3.7 Replace the category production table with a master-detail browser that expands lesson-scoped assets in the left navigation and renders the selected content on the right.
- [x] 3.8 Rename the category surface to the default course workbench, add outline-to-PPT production guidance and progress, and reuse the persisted course-generation request as shared workbench settings.

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
- [x] 5.5 Remove repeated helper copy and decorative hierarchy from the teacher home, course header, course-creation dialog, outline-generation dialog and task workbench; keep supporting text at 12px or above.
- [x] 5.6 Remove redundant empty-state, option and dialog helper copy across the active teacher path while retaining error recovery, data-boundary and irreversible-action warnings.
- [x] 5.7 Add direct task-row deletion, status filters, invalid-task cleanup and completed-record cleanup to the task center.
- [x] 5.8 Restore the teacher course library inside the home, including card/list switching and a single-row global header.
- [x] 5.9 Route new-course entry to the detailed creation flow, persist its production baseline on an empty course shell, and enter the default four-stage workbench without starting generation.
- [x] 5.10 Verify the two home tabs, empty-shell creation, zh/en copy and desktop/mobile layouts; then update product docs and release evidence.

## 6. Staged course-development workbench

- [x] 6.1 Move stable course framing to course-space creation, fix the audience to university students, and remove outline-stage re-entry to the legacy course-settings panel.
- [x] 6.2 Keep the stage navigator and formal course content visible while embedding the existing teacher AI assistant as a right-side workbench pane.
- [x] 6.3 Preserve file scoping, reviewable proposals, impact preview and explicit confirmation in the embedded assistant; keep fullscreen behavior for other surfaces.
- [x] 6.4 Add zh/en copy and focused tests for the three-column workbench and fixed-audience creation boundary.
- [x] 6.5 Run focused tests, build, strict OpenSpec validation, the design detector and desktop/mobile real-page verification; update canonical docs and release evidence.
- [x] 6.6 Make every course-framing item open a prefilled baseline editor and persist explicit teacher-confirmed changes without starting generation.
- [x] 6.7 Let the existing teacher conversation produce a bounded, reviewable course-framing draft that opens in the same editor without silently saving.
- [x] 6.8 Verify baseline persistence, AI draft boundaries, zh/en copy and desktop/mobile editing flows.
- [x] 6.9 Move full course adjustment out of the teacher chat rail into one dedicated responsive workspace while preserving AI and inline launch paths to the same `CourseEvolutionPlan`.

## 7. Minimal teacher-agent course production

- [x] 7.1 Replace the legacy generation dialog with one compact new-course modal, keep optional basic information expanded, and keep all file upload in the course workspace.
- [x] 7.2 Add course-scoped material registration and a durable bidirectional relationship index between uploaded assets and formal course files.
- [x] 7.3 Replace the workbench chat rail with a primary-source/reference tray and four guided stages: course foundation, lesson plan, script plus PPT, and question bank.
- [x] 7.4 Switch the center pane from the stage form to real streaming generation output in place, preserving partial output and recovery controls.
- [x] 7.5 Show upstream sources for formal files and downstream formal usages for uploaded files without duplicating the underlying asset.
- [x] 7.6 Add focused backend/frontend tests, zh/en copy, canonical documentation and desktop/mobile verification.

## 8. Five-entry asset workbench and exam papers

- [x] 8.1 Split the workbench into course foundation, lesson plan, question bank, script and PPT entries; keep the order non-blocking and the question bank optional.
- [x] 8.2 Embed the existing teacher question-bank studio in the workbench and bind the right-side selected materials to its rebuild request.
- [x] 8.3 Add course-owned formal exam papers composed from approved immutable question revisions inside the question-bank studio.
- [x] 8.4 Show question banks and exam papers as managed formal assets in the file view without duplicating question truth.
- [x] 8.5 Add zh/en copy, focused backend/frontend tests, canonical documentation and Chinese desktop real-page verification.

## 9. Explicit identity and ownership boundary

- [x] 9.1 Replace URL-derived identity inference with explicit router/domain `teacher` and `learner` request scopes.
- [x] 9.2 Keep course creation, generation, file space, calendar, task control and teacher preview on the same stable teacher actor.
- [x] 9.3 Filter the teacher library by owner and guard every unpublished teacher-course subresource plus owned generation tasks.
- [x] 9.4 Return one structured draft-owner error and leave the workbench in an explicit interrupted state without a duplicate generic toast.
- [x] 9.5 Add a dry-run-first, externally backed-up reconciliation tool and repair only proven empty local drafts created under transient learner identities.
- [x] 9.6 Run focused frontend/backend tests, production build, strict OpenSpec validation and update canonical architecture documentation.

## 10. Template-backed companion documents

- [x] 10.1 Keep the five numbered teaching-production entries unchanged and add one separate, non-numbered companion-document entry.
- [x] 10.2 Provision only the Zhejiang University grading-rubric and exam-course material-checklist templates supported by teacher-provided samples.
- [x] 10.3 Save generated companion documents as course-owned immutable revisions, keep source relationships in the existing file-space index and treat DOCX/Markdown as exports.
- [x] 10.4 Add the second-level template gallery, structured forms, formal preview, re-editing and DOCX export to the course workbench.
- [x] 10.5 Project generated companion documents into a dedicated file-space folder and route editing back to the same template studio.
- [x] 10.6 Add zh/en copy, focused backend/frontend tests, canonical documentation and desktop verification.

## 11. Stage-scoped web research sources

- [x] 11.1 Add web sources beside uploaded references in the course-workbench right rail and open a responsive research dialog from that section.
- [x] 11.2 Show the teacher-visible research brief, actual outbound queries, filtered source summaries, trust/license metadata and explicit source selection.
- [x] 11.3 Persist bounded stage/lesson research sessions and convert selected sources into ordinary course material assets through the existing parse, evidence and file-space relationship chain.
- [x] 11.4 Pass selected material assets into outline, lesson-plan and question-bank generation while preserving web-source authority and reuse restrictions.
- [x] 11.5 Add zh/en copy plus focused backend/frontend tests and production-build verification.
- [x] 11.6 Enhance the existing search/select interfaces with query/domain diversity, bounded HTML/PDF deep reading, structured `web_document_v1` evidence and per-source excerpt fallback; do not add a parallel research API or source of truth.

## 12. Teacher outline skeleton checkpoint and inline review

- [x] 12.1 Remove pre-generation section-count inference from total hours and do not ask for per-chapter counts before chapter names exist.
- [x] 12.2 Stop `teacher_outline_generation` after the named chapter skeleton, persist the checkpoint, and expose one teacher-only shape-confirmation command.
- [x] 12.3 Save teacher-adjusted per-chapter section counts in the outline stage, resume the same job, and stream structured chapter/section growth from backend checkpoints.
- [x] 12.4 Distinguish active, shape-review, full-outline-review and failure states; keep fast failures and teacher identity/course title synchronized.
- [x] 12.5 Render full outline review/editing in the workbench center and remove the duplicate outline drawer.
- [x] 12.6 Run focused backend/frontend tests, production build, strict OpenSpec validation and Chinese desktop real-page verification; then update canonical docs and release evidence.

## 13. Current-session preparation inspector

- [x] 13.1 Reorganize the selected session into class logistics and one outline/lesson-plan/PPT readiness list without the former flexible blank region.
- [x] 13.2 Read lesson-plan and PPT state from the existing lesson-authoring view, explain missing/stale/working/review/failure states, and keep the selected lesson when opening its workbench.
- [x] 13.3 Verify focused frontend tests, production build, strict OpenSpec validation, detector output and the Chinese desktop page.

## 14. Stable outline handoff and visible lesson-plan jobs

- [x] 14.1 Keep the final streamed outline visible while the teacher projection hydrates, and prevent the workbench from falling back to the initial form.
- [x] 14.2 Reconcile teacher-outline completion through the teacher projection and move from confirmed outline to the first lesson automatically.
- [x] 14.3 Normalize outline-only lesson scopes through the existing pedagogy compiler before reusing the V3 teaching-plan engine.
- [x] 14.4 Show lesson-plan job progress and failures, prevent duplicate submission, add an explicit lesson-plan confirmation, and bind PPT generation to the confirmed revision.
- [x] 14.5 Run focused backend/frontend tests, production build, strict OpenSpec validation and Chinese desktop real-page verification; then update canonical docs and release evidence.

## 15. Unified lesson review and V6 production handoff

- [x] 15.1 Keep lesson-plan viewing, editing and AI candidates in one document surface; move confirmation to the stable bottom-right workflow position.
- [x] 15.2 Add one shared previous/current/next lesson navigator for lesson plans, question bank, scripts and PPT handoff.
- [x] 15.3 Store one formal script asset per lesson, generate it from the confirmed lesson plan and teacher requirements, support inline editing and AI candidates, and require an explicit script confirmation bound to the confirmed lesson-plan revision.
- [x] 15.4 Remove active legacy PPT generation/edit candidate APIs and route every teacher PPT creation to the existing `SlideDeckV6` workbench.
- [x] 15.5 Bind each V6 PPT revision to both the confirmed lesson-plan revision and confirmed script revision; mark it stale when either source changes.
- [x] 15.6 Run focused backend/frontend tests, production build, strict OpenSpec validation and Chinese desktop real-page verification; then update canonical docs and release evidence.

## 16. Lesson-scoped reference materials

- [x] 16.1 Bind the lesson-plan reference tray to the visible `lesson_unit_id` and label the current lesson explicitly.
- [x] 16.2 Persist upload, selection and removal immediately through the existing formal-file relationship index without duplicating source assets.
- [x] 16.3 Restore each lesson's independent primary and supporting references when switching or reloading lessons.
- [x] 16.4 Add focused frontend tests, strict OpenSpec validation, production-build verification and Chinese desktop real-page verification.
- [x] 16.5 Add a one-click previous-session reference merge that preserves current selections and the single-primary-source constraint.

## 17. Durable lesson-plan content streaming

- [x] 17.1 Forward provider-visible content deltas through the existing `CourseTeachingPlanV3` batch callbacks without exposing reasoning content.
- [x] 17.2 Persist per-batch stream checkpoints atomically on the existing lesson job and expose reconnectable SSE snapshots without creating a second lesson-plan source of truth.
- [x] 17.3 Render readable partial lesson-plan content in the original workbench surface and replace it with the quality-gated formal revision on completion.
- [x] 17.4 Preserve streamed working content on failure, retain polling as transport fallback and cover model, repository, API and workbench behavior with focused tests.
