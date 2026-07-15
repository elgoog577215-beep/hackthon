# Proof Pack: 灵知 PPT 课件工作台 MVP

## Scope

- Change: `add-courseware-workbench`
- Run: `courseware-mvp-20260715`
- Mode: Light / direct native GOAL
- Outcome: 从学习页或课程库进入独立课件工作台，基于冻结课程来源生成课件草稿，逐页预览，通过当前页提议/对比/应用/撤销修改，并在质量通过后导出 HTML/PPTX。
- Data boundary: 课件只写入独立 `presentation_decks` 存储；不修改 CourseDocument。

## Plan Evidence

- `plan.md` 的 P0-P5 已全部完成。
- Shared boundary contract、Authority receipt、三份并行 handoff 均位于当前 run。
- 最新原生 evaluator receipt：`receipts/eval/088938d526c96b2eb12b854bf10626ddc9ffb2c54771488de2071fd58438fe1e.json`。

## Runtime Impact

- 新增 `/api/courses/{course_id}/presentations`、`/api/presentations/*`、`/api/presentation-artifacts/*`。
- 新增 `/course/:courseId/deck` 与 `/course/:courseId/deck/:deckId` workbench routes。
- 新增依赖 `python-pptx==1.0.2`。
- 正式项目端口合同未变；浏览器证据使用临时前端 5177、后端 8011。

## Changes

- Backend: presentation models、source projection、repository、generation、quality、HTML/PPTX renderer、router。
- Frontend: presentation service/store/SSE、preview、课件 AI、proposal/quality components、studio view、学习页主入口、课程库次入口。
- Contracts: 3 个模板、10 个注册版式、不可变 source snapshot、append-only revision、ordered/replayable SSE、receipt-bound artifacts。
- UX: 精确继承用户批准首版的顶栏 + breadcrumb + 左大预览 + 右约 400px 课件 AI；窄屏切换 Preview/AI。

## Verification

- Backend targeted tests: `34 passed`。
- Frontend targeted tests: `24 passed`（presentation、store、router、LearningView entry）。
- Frontend production build: PASS；仅保留既有 browserslist 数据与大 chunk 非阻断 warning。
- OpenSpec: `openspec validate add-courseware-workbench --strict` PASS。
- Native evaluator iteration 002: G1-G8 全 PASS，score 100，workspace digest `sha256:97dcbb6fb158e9583adf58392ffe3ffbec03ef40284ca18c90a081397fb25585`。
- Real browser: create 201；generate/chat/apply/restore/finalize 全 2xx；console 0 error / 0 warning。
- Download: `courseware-browser-download-fresh.pptx` 可由 `python-pptx` 重载，8 页、8 页讲稿、标题与预览一致。
- Course-library secondary entry: 无 nodeId 时默认整门课程，create 201、generate 200，不再触发 chapter scope 422。

## AC Mapping

| AC | Result | Evidence |
| --- | --- | --- |
| AC-01 | PASS | LearningView entry test、router test、真实课程/章节 query 保留 |
| AC-02 | PASS | repository reload/source snapshot tests、SSE reconnect test |
| AC-03 | PASS | generation/API ordered event、persist-before-emit、replay tests |
| AC-04 | PASS | template/layout registry contract tests |
| AC-05 | PASS | proposal/apply/restore tests与真实第 4 页 apply/undo |
| AC-06 | PASS | deterministic blocked quality tests与结构化 fix action |
| AC-07 | PASS | finalize/API tests、HTML/PPTX receipt、PPTX reload |
| AC-08 | PASS | stale artifact tests与应用后下载禁用合同 |
| AC-09 | PASS | approved reference、desktop proposal/export-ready、390x844 AI screenshot |
| AC-10 | PASS | full lifecycle digest immutability test |

## Project Panorama Update

本 change 尚未 archive；本轮以 OpenSpec change 与当前 run 作为功能真源，没有把未归档能力提前写成项目级稳定现状。

## Learning

- 已在当前 run 捕获一项 `choice-required` 审美候选：用户批准的首版原型是本功能精确视觉真源；未获新授权不得自行重设计。
- 尚未写入项目/审美/全局正式记忆，等待用户选择。

## Known Gaps

- 按用户要求采用 Light 验证：未跑全仓测试、跨浏览器矩阵、3 模板 × 10 版式截图矩阵、性能 benchmark 或多 provider 真实 LLM 矩阵。
- 浏览器主流程使用本地确定性课程/生成 fixture；provider 不可用时的可见草稿和禁止正式导出由 targeted tests 覆盖。
- 全局 strict completion-preflight 当前固定要求 18 个 AC，本 change 冻结的是 10 个 Light AC；未篡改合同来迎合该工具，完成判断使用冻结 G1-G8 evaluator 与独立 Checker。
