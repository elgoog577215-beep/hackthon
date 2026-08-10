## Context

正式课程正文真源是 `CourseDocument + ordered CourseBlock[]`。PPT 是 `TeachingRepresentation`，不能成为第二课程正文。V5 的主要缺口不是渲染组件数量，而是故事规划入口已收到按字符容量拆过的片段、布局名称跨层漂移、生成入口不统一、AI 规划结果可被确定性结果冒充，以及进度由前端固定阶段推断。

V6 采用“课程语义先行、模板合同后置、故事严格、视觉弹性”的编译模型。容量只用于最终页面分配；故事 AI 只能选择已有教学单元与模板合同；视觉 AI 只能选择来源支持的表现形式；Web 与 PPTX 消费同一最终页面合同。

## Goals / Non-Goals

**Goals**

- 每个正式课程块都有一个主要可见表达位置，完整原文进入讲者备注并保持来源绑定。
- 页面顺序忠于课程顺序和正式教学依赖，禁止为填满页面跨主题拼接。
- 代码、公式、表格、数据、实验、原文等学科特征素材与条件、解释、结果形成原子教学组合。
- 每个教学单元使用 1～3 张模板安全页，每页只有一个主要教学任务。
- 最新已发布模板版本成为唯一布局合同，浏览器与 PPTX 不再各自推断。
- 故事 AI 失败硬失败；视觉 AI 只允许来源完整的页面级降级。
- 进度可解释、可恢复、每 5 秒心跳且在发布前不超过 99%。
- 修复规则跨学科通用，不按课程标题、课程 ID、固定公式、素材 ID 或章节层级写分支。

**Non-Goals**

- V6 不修改正式课程正文和教案。
- V6 不从视觉模板反推或创造课程事实。
- V6 不自动覆盖已有 V5 课件。
- V6 不支持任意 PPTX 宏、脚本或未声明布局。
- 本变更不以降低字号、裁切或空占位换取“生成成功”。

## Pipeline

```text
freeze source/template
  -> compile course presentation graph
  -> run chapter-scoped story AI
  -> validate source/order/coverage/facts
  -> allocate published template layouts
  -> run bounded visual AI batches
  -> compile slide_deck_v6 + speaker notes
  -> render Web/PPTX from the same contract
  -> fidelity + subject + layout + export gates
  -> atomically publish or retain last published version
```

## Contracts

### `ppt_source_contract_v2`

Stores immutable identifiers and digests for course/document revision, ordered active block IDs, formal teaching-plan revision, knowledge snapshot, template pack/version/digest, story/visual policy versions, locale and build request. The orchestrator rechecks course and template digests before publication and fails with `source_revision_changed` or `template_revision_changed` when they drift.

### `course_presentation_graph_v1`

Contains ordered `TeachingUnit` nodes. Each node records source section, ordered primary block IDs, supporting block IDs, teaching intent, artifact kinds, prerequisites, dependants and source-native boundaries. Deterministic grouping uses section membership, explicit teaching roles, source order and dependency evidence. It never uses visible character capacity and never joins unrelated topics.

Every active formal block appears exactly once in `primary_block_ids`. The same block may be referenced by other units as support. Code/formula/table/data/experiment/source artifacts are atomic with their conditions, explanation and result. Missing required neighbors remain explicit graph diagnostics rather than being fabricated.

### `template_layout_contract_v1`

Each published template layout declares:

- `template_layout_id`, template ID/version/digest;
- compatible teaching intents and artifact kinds;
- required/optional typed slots;
- title/body/item/code/formula/table/visual capacities;
- safe continuations and base-layout inheritance;
- Web and PPTX renderer adapter IDs.

The template registry is closed. V6 planning receives only published contract IDs. Compatibility aliases such as `two-column`, `answer` and `data-highlight` exist only in V5 read adapters. Missing mappings fail with `template_layout_unavailable`; no heuristic layout fallback is allowed.

Personal templates may publish for V6 only after representative-page mapping, capacity declarations and required-layout coverage pass. A missing specialized layout may inherit an explicitly declared base template layout; inheritance is stored, finite and cycle-checked.

### `slide_story_plan_v3`

Story planning runs in ordered chapter batches through the existing `AIBase` provider pool. A batch may only:

- select supplied teaching unit IDs and compatible template layout IDs;
- write bounded source-faithful titles, summaries and transitions;
- split one teaching unit into 1～3 safe pages without changing dependencies;
- preserve unit order and 100% primary block coverage.

The validator rejects unknown IDs, omitted primary blocks, duplicate primary ownership, order inversions, ungrounded protected tokens and unsupported factual assertions. Any rejected or unavailable story batch fails the entire V6 candidate; accepted batches are never silently replaced by a deterministic story.

Each batch stores provider/model, start/end/duration, attempts, normalized failure category and validation result. It never stores credentials or unrelated raw conversation.

### `slide_visual_plan_v2`

Visual planning runs chapter-scoped batches with the shared 2～4 concurrency budget. It chooses only source-backed code, formula, table, chart, image, diagram or text-native representations. A page may degrade only to a declared text/code/formula/table layout that preserves all required source meaning and fits capacity. Such a page records `degradation_reason`, `original_decision`, `resolved_decision` and triggers `v6_needs_manual_edit`.

Missing required subject artifacts, invalid data, unsupported identifiers, capacity loss or unavailable layout are hard failures. Decorative imagery failure alone is degradable.

### `slide_deck_v6`

The final contract stores pages, resolved template layout IDs, typed slots, source block/teaching unit bindings, subject artifacts, speaker notes, visual decisions, renderer adapters and per-page quality. Web/PPTX adapters receive this contract without consulting story intent or legacy layout aliases.

Full block text, full code and supplemental detail are stored in speaker notes with exact block/revision bindings. Canvas copy remains a source-faithful presentation expression, not a verbatim prose wall.

### `slide_build_progress_v2`

The backend creates and persists work items before or as work becomes known. Item kinds and default weights are local validation/unit `1`, render page `3`, asset `5`, AI batch `10`. Progress equals completed cost divided by a monotonic total-cost high-water mark. Newly discovered items increase the high-water mark without decreasing the displayed percentage; completion cannot reach 100% before atomic publication.

Each event/heartbeat contains stage, step index/count, chapter/batch/page, completed/total units and weights, elapsed time, provider wait/retry details, discovered work and remaining estimate. The task emits at least one event every five seconds, resumes from its persisted manifest after reconnect/restart, and the frontend does not maintain a second stage-percentage table.

## State and Failure Model

Only these V6 terminal states exist:

- `v6_ready`: all hard gates pass and no visual degradation requires review.
- `v6_needs_manual_edit`: all fidelity/subject/export gates pass, but one or more allowed visual degradations require review.
- `v6_failed`: story, source, template, subject, capacity, render or export hard gate failed.

Every failure contains `stage`, `code`, `message`, `retryable`, and optional `chapter_id`, `page_id`, `batch_id`. A failed candidate never replaces the latest published representation. Atomic publication writes the candidate contracts and registry pointer only after all gates pass.

## Quality Gates

- formal block visible coverage 100%; full-text note binding 100%;
- course order and dependency order preserved; no cross-topic merge;
- all visible facts, numbers, formulas and code identifiers traceable;
- subject contract satisfied for characteristic artifacts;
- exactly one primary teaching job per page;
- template layout and teaching intent compatible;
- no empty required slot, fake visual, duplicate heading/body, prose wall, clipping, overlap or Web/PPTX drift;
- source and template revisions unchanged;
- exported PPTX opens and contains the expected page/note contracts.

## Compatibility and Migration

- V5 records remain readable/exportable through existing adapters.
- A V5 deck is never rewritten as V6 without a new build.
- All new generation endpoints enqueue the same durable V6 orchestrator when the V6 feature flag is enabled.
- The synchronous compatibility route may return the durable task ID or `v6_orchestrator_unavailable`; it may not compile an alternate plan.
- Rollback disables new V6 builds and restores V5 as default; published V6 remains readable.

## Release

1. Implement contracts and offline regression fixtures.
2. Run a representative synthetic batch covering programming, mathematics/data and a non-math/non-programming subject.
3. Enable shadow builds for one online chapter from Unity, linear algebra and machine learning.
4. Require source coverage, sequence, subject artifacts, template selection, AI diagnostics, Web/PPTX parity and export-open checks for all three.
5. Only after all samples pass, switch the new-build default to V6. Monitor build success, story failure, visual degradation, manual edits, stage latency and template conflicts.

Shadow verification uses the same public build stream with
`engine_version=v6`, `shadow_only=true` and one `chapter_id`. The task freezes
that section subtree, runs the durable V6 compiler, and records a terminal
candidate with `published=false`; it never updates the teaching-representation
registry. Authenticated diagnostics and PPTX export are read from the
course-scoped shadow endpoints.

Rollout has two independent switches. `SLIDE_DECK_V6_ENABLED=false` disables
explicit shadow/V6 requests, while `SLIDE_DECK_V6_DEFAULT_ENABLED=false` keeps
ordinary new builds on V5. Rollback first disables the default switch, then the
explicit V6 switch if required; existing V5/V6 specs and exports remain
readable because rollback does not delete registry history or candidates.

The reference visual baseline is `frontend/public/presentation-templates/qizhi-classroom-v2.pptx` plus the currently published template pack manifests. V6 never hardcodes a course to that template or to any subject-specific layout ID.
