## 1. Baseline and contracts

- [x] 1.1 Finish the current template-pack implementation on a clean commit and verify backend, frontend contract tests and production build.
- [x] 1.2 Create the V6 branch from the template baseline and merge the latest deployed progress work without overwriting other changes.
- [x] 1.3 Add failing contract tests for source freeze, course graph coverage/order, template layout closure, story validation, visual degradation and final V6 states.
- [x] 1.4 Add a non-math/non-programming synthetic course fixture and hardcoding guard.

## 2. Course presentation graph and template registry

- [x] 2.1 Implement `ppt_source_contract_v2` and immutable digest checks.
- [x] 2.2 Implement `course_presentation_graph_v1` from canonical ordered course blocks and formal teaching roles without character-based story splitting.
- [x] 2.3 Implement `template_layout_contract_v1` with slots, capacities, intentions, artifact kinds, safe continuations and renderer adapters.
- [x] 2.4 Reject unknown, legacy or unmapped layouts and validate personal-template V6 publication coverage.

## 3. AI story and visual planning

- [x] 3.1 Implement `slide_story_plan_v3` schemas, chapter batching, AIBase invocation and persisted diagnostics.
- [x] 3.2 Enforce 100% primary-block coverage, order/dependency preservation, known IDs and grounded factual tokens; fail the whole candidate on any story-batch failure.
- [x] 3.3 Implement `slide_visual_plan_v2` schemas, bounded concurrency, source-backed decisions and page-level degradations.
- [x] 3.4 Mark allowed degradations `v6_needs_manual_edit`; hard-fail subject, source, capacity and template loss.
- [x] 3.5 Make source-grounded, Markdown-free page summaries an explicit LLM output contract bounded by the selected template slot.
- [x] 3.6 Add selective visual replanning that targets only degraded pages and preserves healthy decisions inside partially resumed chapter batches.

## 4. Final compiler and orchestration

- [x] 4.1 Implement `slide_deck_v6`, dynamic template-safe unit page allocation, typed slot materialization and full-source speaker notes.
- [x] 4.2 Make Web and PPTX adapters consume only the resolved V6 template contract.
- [x] 4.3 Implement final fidelity, subject, grammar, capacity, render and export gates with structured failures.
- [x] 4.4 Route all build entries through one durable V6 orchestrator and atomically retain the last published version on failure.
- [x] 4.5 Compile Markdown, code and tables into template-safe visible projections while retaining complete source text in speaker notes.
- [x] 4.6 Preserve complete table-cell semantics with full-width/wide selection, row pagination with repeated headers, oversized-row detail pages and a no-generated-ellipsis gate.
- [x] 4.7 Compile source-bound full-course agenda pages from ordered top-level sections without distorting formal block coverage.
- [x] 4.8 Preserve semantic paragraph boundaries in body projection and add a vertical numbered practice-sequence composition for Web/PPTX.
- [x] 4.9 Select the full-width table family for dense three-column evidence and size exported rows from measured wrapped text.
- [x] 4.10 Add atomic published-V6 visual repair with frozen story/template/source checks, race protection and last-good-version retention.
- [x] 4.11 Remove the teaching page-count cap, paginate code/steps/tables/prose without semantic loss, preserve sole-body and artifact-support source text, and gate visible artifact/prose fidelity plus generated ellipses.
- [x] 4.12 Compile source-derived two-level agenda entries, cap each agenda page at the sample-backed readable density and keep Web/PPTX agenda hierarchy identical.
- [x] 4.13 Persist code language/line-range metadata, keep adjacent declarations together when capacity permits, and render language, continuation and line-number reading aids without changing source code.
- [x] 4.14 Add a post-export region visibility gate so missing title, prose, steps, table cells or code fails before atomic publication.

## 5. Adaptive progress

- [x] 5.1 Add failing tests for weighted progress, monotonic discovery, 99% publication cap, heartbeat and restart recovery.
- [x] 5.2 Implement persisted `slide_build_progress_v2` manifests and five-second events.
- [x] 5.3 Replace frontend stage inference with server-owned work counts, provider wait/retry and failure details.
- [x] 5.4 Add the degraded-page repair API, durable task monitoring and workbench action without triggering a full rebuild.

## 6. Validation and rollout

- [x] 6.1 Run focused and full backend/frontend regressions, build, OpenSpec validation and hardcoding scan.
- [x] 6.2 Render/export cross-subject fixtures and verify notes, overflow, Web/PPTX parity and PPTX openability.
- [ ] 6.3 Run one shadow chapter through the official website chain for Unity, linear algebra and machine learning.
- [ ] 6.4 Enable V6 as the default for new builds only after all three shadow gates pass; keep V5 readable/exportable and document rollback/metrics.
- [x] 6.5 Compare the full-course V6 output against the published Qizhi sample for agenda hierarchy, source-region visibility and code readability, then render every page and run overflow/export audits.

## 7. Teacher PPT Agent convergence

- [x] 7.1 Audit PPTAgent/DeepPresenter, Presenton and PptxGenJS for planning, editing, rendering and license boundaries.
- [x] 7.2 Remove the deterministic teacher story/visual adapter and route the teacher workbench through the shared V6 AI planners.
- [x] 7.3 Reject the retired deterministic planner identities if they are ever reported as completed AI planning.
- [x] 7.4 Persist and display a compact source-bound storyboard summary for teacher inspection.
- [ ] 7.5 Regenerate the accepted teacher test lesson with the live provider and compare page rhythm, title uniqueness, layout diversity and visual decisions against the 41-page baseline. The 2026-08-24 live attempt reached the shared story planner, then returned the retryable `story_ai_batch_rate_limited` boundary; the published 41-page baseline remained intact.
