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

## 4. Final compiler and orchestration

- [x] 4.1 Implement `slide_deck_v6`, 1～3 page unit allocation, typed slot materialization and full-source speaker notes.
- [x] 4.2 Make Web and PPTX adapters consume only the resolved V6 template contract.
- [x] 4.3 Implement final fidelity, subject, grammar, capacity, render and export gates with structured failures.
- [x] 4.4 Route all build entries through one durable V6 orchestrator and atomically retain the last published version on failure.

## 5. Adaptive progress

- [x] 5.1 Add failing tests for weighted progress, monotonic discovery, 99% publication cap, heartbeat and restart recovery.
- [x] 5.2 Implement persisted `slide_build_progress_v2` manifests and five-second events.
- [x] 5.3 Replace frontend stage inference with server-owned work counts, provider wait/retry and failure details.

## 6. Validation and rollout

- [x] 6.1 Run focused and full backend/frontend regressions, build, OpenSpec validation and hardcoding scan.
- [x] 6.2 Render/export cross-subject fixtures and verify notes, overflow, Web/PPTX parity and PPTX openability.
- [ ] 6.3 Run one shadow chapter through the official website chain for Unity, linear algebra and machine learning.
- [ ] 6.4 Enable V6 as the default for new builds only after all three shadow gates pass; keep V5 readable/exportable and document rollback/metrics.
