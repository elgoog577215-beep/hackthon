## Context Scout

- 已读取：本 change 全部 artifacts；灵知 `LearningView`、`SideAIPanel`、router、`AIBase`、SSE router、课程版本/原子仓库、课程质量门和依赖清单。
- 教育 agent 参考：`agents/ppt/{agent,slides,pptx_render,runner}.py`、`ResourceView.vue`、`PptGenerateMethodModal.vue`。
- 已批准视觉真源：`.codex/harness/visual-companion/2026-07-15-ppt-workbench/visual-companion-screen.html` 最初版本。
- 不需要外部研究：本次框架选择已有两个真实项目源代码和可运行依赖证据；`python-pptx==1.0.2` 已在教育 agent 生产依赖中使用。
- 已知运行边界：前端 5173、后端 8000；本 change 不改端口。

## Intent

目标是做一个可持续编辑的“课件工作台”，不是一次性 PPT 导出。页面骨架主要参考教育 agent，内容、版本、质量、AI 和视觉全部按灵知真实架构适配。

成功形态：用户从当前课程进入工作台，选择章节/整课与模板，先看到页序、再看到页面逐张出现；用户可对当前页提出修改，先查看 diff 再应用或撤销；点击完成后，质量通过才下载 HTML/PPTX。

非目标：自由拖拽画布、任意 PPT 模板上传、图片模型逐页出图、多人协作、自动回写课程、移动端完整双栏编辑。

## Education Agent Adaptation Matrix

| 教育 agent 证据 | 灵知采用 | 灵知适配 |
| --- | --- | --- |
| `slides.py:_make_outline/_fill_slides` | 先 outline、后受控并发填页 | 输入改为结构化 source snapshot；每页保存来源并立即发事件 |
| Pydantic schema + JSON 重试 | typed JSON、结构校验、有限重试 | 复用异步 `AIBase` 和当前 LLM profile；不复制同步 vLLM runner |
| 同一 deck 渲染 HTML/PPTX | 单一 slide schema 双渲染 | 使用三 style/十 layout registry；未知 layout 直接阻断 |
| `python-pptx` 16:9、notes | PPTX 输出和演讲者备注 | 显式声明依赖；artifact 绑定 revision/checksum |
| `ResourceView` 顶栏、stepper、`1fr 400px` | 顶栏 + 层级 + 左大预览 + 右 AI | 使用已批准的灵知视觉基线；不复制蓝灰渐变和巨型单文件 |
| SSE loading/end | 生成进度流 | 改为带序号的 deck 领域事件，并支持断线恢复 |

明确不采用：SQL Resource 产物 URL 模型、同步 `OpenAI + ThreadPoolExecutor + sleep`、整份 Markdown 截断后给每一页、空页失败仍导出、生成完成后才整体 iframe 预览、“本地/超星”生成方式选择。

## Domain Contract

### SourceRef / SourceSnapshot

灵知同时存在 canonical course document revision 与产品课程版本 `cvN`。deck 不保存一个含糊的 `source_course_version_id`，而是保存：

```text
SourceRef {
  course_id,
  source_format: canonical | legacy_snapshot,
  version_id,
  document_revision,
  blueprint_revision_id,
  asset_bundle_revision_id,
  source_snapshot_id,
  source_snapshot_sha256
}
```

创建 deck 时将 scope 内 sections、blocks、objectives、practices、misconceptions 和 asset refs 投影为不可变 `source_snapshot.json`。以后课程更新只提示“基于旧版本”，不重写旧 deck。

### PresentationDeck manifest

```text
schema_version, deck_id, course_id, title, source_ref,
scope { type: chapter | course, section_ids },
purpose: teaching | self_study,
template_id,
status: draft | generating | editing | quality_blocked | ready | exporting | exported | failed,
active_revision_id, active_generation_id,
latest_quality_report_id, latest_artifact_id,
created_at, updated_at
```

### GenerationWorkingSnapshot

生成期间允许原子覆盖一个工作快照，保存 `generation_id/event_seq/outline_revision/slide_order/slides/cancelled_slot_ids/quality`。它支持刷新恢复和逐页更新，但不是正式 revision。生成完成后冻结为第一份不可变 revision；失败/取消时保留工作快照用于诊断或重试。

生成中删除页面记录 tombstone；晚到的 worker 结果若命中 tombstone 必须丢弃，不能复活页面。调序只更新 outline revision，不重生成已完成页面。

### DeckRevision / Slide

每个 revision 是完整 deck 快照并追加写入：

```text
DeckRevision {
  revision_id, parent_revision_id, deck_id,
  reason: initial_generation | chat_patch | reorder | restore | quality_repair,
  created_at, created_by, source_snapshot_id, slide_order, slides[]
}

Slide {
  slide_id, position, layout_id,
  status: planned | generating | ready | failed,
  title, subtitle, key_message, blocks[], speaker_notes,
  source_refs { section_ids, block_ids, block_revision_ids, objective_ids, asset_ids },
  quality { issues[], capacity }
}
```

restore 不把 manifest 指回旧文件，而是复制旧 revision 生成新的 restore revision，保证审计链单向增长。

### DeckProposal

proposal 绑定 `base_revision_id`、`request_id` 和显式 scope。当前页 proposal 只允许 patch 指定 slide 的 `title/subtitle/key_message/blocks/speaker_notes/layout_id`；不得改其他页、模板、source refs 或 course。apply 时若 active revision 已变化，返回 `409 stale_proposal`。`command_id` 保证重复 apply 返回同一 receipt。

### ArtifactReceipt

artifact 必须绑定 `deck_id/revision_id/source_snapshot_id/template_id/template_version/layout_registry_version`，保存 HTML/PPTX 路径、SHA-256、页数、标题 digest、质量报告和生成时间。active revision 变化后旧 artifact 保留但标记 stale，下载按钮关闭，直到重新 finalize。

## Repository Layout and Transaction Rule

```text
backend/data/presentation_decks/{course_id}/{deck_id}/
  manifest.json
  source_snapshot.json
  working/{generation_id}.json
  streams/{generation_id}.json
  revisions/{revision_id}.json
  proposals/{proposal_id}.json
  quality/{report_id}.json
  artifacts/{artifact_id}/receipt.json
  artifacts/{artifact_id}/deck.html
  artifacts/{artifact_id}/deck.pptx
```

沿用现有 safe-id、per-deck `RLock`、临时文件 + `os.replace`。多文件提交顺序是“实体先写并校验 → 最后原子切 manifest 指针”；读取时必须验证 manifest 指向的实体存在。禁止通过用户输入拼接任意下载路径。

## Generation Pipeline

1. Source projector：从不可变 source snapshot 生成 scope packet 和 slide-level retrieval index。
2. Teaching curator：确定目标覆盖、讲授叙事、必须出现的误区/练习。
3. Outline planner：只输出 page brief、layout id、source query 和页序；必须使用 registry。
4. Page filler：`asyncio.Semaphore(2~3)` 受控并发，按页面相关 blocks/objectives 填充，不把同一段截断全文喂给所有页面。
5. Working snapshot + SSE：每页完成即原子保存，并发送 `slide_upsert`。
6. Draft quality：执行 deterministic gate，生成 `quality_report`，然后发送 `generation_complete`。
7. 用户编辑：proposal → diff → apply → 新 revision → undo/restore。
8. Finalize：重新检查 bound course gate + deck gate，渲染 HTML/PPTX，校验后保存 receipt，最后发送 `export_ready`。

模型失败不得写空白 ready slide。单页失败标 `failed` 并产生可操作 issue；outline 兜底只允许形成草稿，不得绕过正式导出门。

## Event Contract

generate 使用 fetch-SSE，事件 envelope 固定为：

```text
schema_version, event_type, deck_id, generation_id,
event_seq, outline_revision, revision_id?, emitted_at, payload
```

事件：`deck_outline`, `slide_upsert`, `slide_patch`, `progress`, `quality_report`, `generation_complete`, `error`。finalize 单独产生 `quality_report`, `export_ready` 或 `error`。`export_ready` 不属于普通 generate 的结束事件。

SSE `id` 为 `{generation_id}:{event_seq}`；服务端保存小型有序事件日志，支持 `Last-Event-ID/after_seq` replay。相同 `request_id` 返回同一 generation；已有活动 generation 时返回 409。SSE 建立后的错误通过 `error` 事件结束，不能伪造成 HTTP 成功结果。

## API Contract

- `POST /api/courses/{course_id}/presentations`：创建草稿，`request_id` 幂等。
- `GET /api/courses/{course_id}/presentations`：列出该课程 deck。
- `GET /api/presentations/{deck_id}`：manifest + active/working snapshot + quality/artifact 摘要。
- `POST /api/presentations/{deck_id}/generate`：`request_id + expected_revision_id`，返回 SSE。
- `GET /api/presentations/{deck_id}/events?generation_id=&after_seq=`：断线 replay/续接。
- `POST /api/presentations/{deck_id}/chat`：只创建 proposal，不写 revision。
- `POST /api/presentations/{deck_id}/patches/{proposal_id}/apply`：`expected_revision_id + command_id`。
- `POST /api/presentations/{deck_id}/revisions/{revision_id}/restore`：创建新 restore revision。
- `POST /api/presentations/{deck_id}/finalize`：`expected_revision_id + command_id + render_measurement`。
- `GET /api/presentation-artifacts/{artifact_id}/html|pptx`：根据 receipt 安全返回文件。

## Template and Layout Registry

首期注册三种 style：`lingzhi-classroom`、`lingzhi-engineering`、`lingzhi-academic`。注册 L01 cover、L02 agenda、L03 section、L04 concept、L05 comparison、L06 process、L07 code_annotation、L08 misconception、L09 practice、L10 summary。

每个 layout 声明 slots、最大 blocks/字符/行数、字体比例、允许的 block 类型、HTML renderer 和 PPTX renderer。模型只能选 id，不能产 CSS/坐标。未知 id 是 blocking schema error，不自动降级。

视觉基线以用户批准的最初静态原型为准：顶部返回/课程名/保存/下载，步骤条，左预览、右 400px AI；不增加大缩略图栏，不擅自加入后续品牌头或深色代码块变体。

## Preview and AI Contract

HTML preview 通过版本化 postMessage channel 通信：`preview:ready`、`slide:selected`、`render:measured`。预览运行在不授予 same-origin 的 opaque sandbox 中；父页面验证 `event.source`、预期 opaque origin、channel version、deck/revision id 与 revision checksum。渲染测量必须显式包含页数、overflow 和 collision；右栏显示“正在修改：第 N 页”。无选中页时才允许 deck scope。

右栏复用 `SideAIPanel` 的交互语义和 token，不直接复用课程 AI store：课件需要独立对话、proposal 和 revision 状态。快捷操作为补例子、加入易错点、变课堂练习、精简本页、调整语气、查看来源。

路由使用 `meta: { shell: 'workbench' }`。`App.vue` 在该模式隐藏全局 60px Header，由 `PresentationStudioView` 独占已批准原型中的顶栏，避免出现双层导航。学习页发布态必须显示稳定的顶部工具条，并把“AI 老师 / 课件”并排；不得只把入口放进桌面默认隐藏的 `context-actions`。创建入口携带 `nodeId` query，deck 创建后把 scope 固化到 manifest，刷新不能依赖内存恢复章节上下文。

## Quality and Publication Gate

MVP blocking gate 采用 deterministic 规则：

- schema、layout 和 required slots 合法；所有正式页 ready。
- 每页 source refs 可在 source snapshot 解析；scope 内目标有覆盖。
- 有 misconception 资产时必须包含 L08；按 purpose/练习资产规则要求 L09。
- layout 容量合法；浏览器 preview 在 `document.fonts.ready` 后报告 overflow/collision，报告必须绑定 revision checksum。
- bound source 满足正式发布门；草稿预览不受此限制。
- HTML/PPTX 均真实生成；PPTX reload 成功；页数和逐页标题一致。

LLM 语义审阅在 MVP 只做 advisory，不作为 blocking gate。这样保留教学提示，同时避免正式导出被不稳定模型判断卡死。

## Frontend State Machine

主阶段使用 `booting → configuring → generating → editing → finalizing → quality_blocked|export_ready`；另设正交子状态 `syncState`、`proposalState` 和 `exportState`，避免“生成中查看已完成页”等合法组合被巨型枚举排除。

- 未生成：左引导，右配置 scope/template/purpose/page budget/要求。
- 生成中：outline 先出现；页面逐张 ready；允许删未生成页和调页序。
- 编辑中：当前页 scope，proposal/diff/apply/undo，artifact stale 时关闭下载。
- 完成：显示质量结果、版本和下载。
- 窄屏：仅“预览 / AI”切换；不承诺双栏完整编辑。

前端 reducer 保存 `activeGenerationId/lastSequence`：忽略重复和旧 generation 事件；发现 sequence 缺口时重新 GET deck；`slide_upsert` 以 `slide_id` 合并而不是按 position 覆盖。失败保留已有 deck。只有 ready slide 能发当前页修改；下载状态只认服务端 quality/artifact receipt。

## Implementation Boundaries

后端新增：`presentation_models.py`、`presentation_repository.py`、`presentation_source.py`、`presentation_templates.py`、`presentation_generation.py`、`presentation_render.py`、`presentation_quality.py`、`routers/presentations.py`。仅在 `main.py`、`routers/__init__.py`、`requirements.txt` 做注册/依赖修改。

前端新增：`views/PresentationStudioView.vue`、`components/presentation/*`、`stores/presentation.ts`、`services/presentations.ts`、`types/presentation.ts`、`composables/usePresentationEvents.ts`。仅更新 `App.vue` 的 workbench shell 分支、router、LearningView、LearningDock 和 CourseLibraryView。

不修改课程 JSON 结构，不把 presentation 混入 CourseTaskCenter，不改变现有 AI 老师 action protocol，不改端口。

## Phasing

### Delivery A — 可用主链

共享 schema/repository/source snapshot；三 styles/十 layouts；outline + 逐页生成；工作台；当前页 proposal/apply/undo；HTML/PPTX finalize；正式导出 gate。

生成期间只支持删除未生成页与调整 outline 顺序；新增页、多页 scope 后置。

### Delivery B — 编辑与追溯增强

新增/删除已生成页、多页选择、版本列表、来源回跳、完整质量面板、讲稿编辑、学术引用细节。

### Delivery C — 内容增强

图表/插图/代码高亮增强、受控同步课程、自定义品牌模板、移动端更完整编辑。

## Risks and Rollback

- PPTX/HTML 漂移：同 schema + registry；HTML 为视觉真相；artifact receipt 做页数/标题对账。
- LLM provider 不可用：保留 working snapshot 和明确 error，不写空页，不消耗已有 revision。
- 并发写冲突：expected revision、command id、deck lock、tombstone 和 outline revision。
- 字体漂移：固定中文/代码字体 fallback，下载前提示字体条件。
- 实施回滚：新领域独立；移除路由入口即可停止暴露，不需要迁移/回滚 CourseDocument。
