# FINAL CHECKER — add-courseware-workbench

## Verdict

**PASS（冻结的 Light 合同）**。

G1–G8 全部通过，AC-01…AC-10 均有当前证据；未发现 CourseDocument 变更、越权路径、陈旧写入接受、部分产物挂接或正式下载绕过。此次 Checker 为独立只读复核，未修改应用代码；唯一写入是本报告。

## Freshness / authority binding

| 项目 | 当前绑定 |
| --- | --- |
| Change | `add-courseware-workbench` |
| Run | `courseware-mvp-20260715` |
| Authority receipt | `sha256:084034b702e343b7337d4c8834b4d45da17bcf10613e1ff7f3177ef17ad5707b` |
| Contract digest | `sha256:3251dfa51f6357a0781871f2e4793d638ebd82b580ed6955b70df24cbac09b16` |
| Fresh iteration | `002` |
| Fresh workspace digest | `sha256:97dcbb6fb158e9583adf58392ffe3ffbec03ef40284ca18c90a081397fb25585` |
| Fresh evaluator receipt | `sha256:088938d526c96b2eb12b854bf10626ddc9ffb2c54771488de2071fd58438fe1e` |
| Evaluator result | `G1–G8 PASS`, score `100`, exit `0` |

`best.json` 仍指向同分的 iteration 001，但其 workspace digest 已早于最后的真实入口上下文、编辑态只读配置和课程库次入口修复；本报告明确以更新的 iteration 002 与 receipt `088938…` 为 freshness 真源。

## Hard-gate review

| Gate | Verdict | Independent evidence |
| --- | --- | --- |
| G1 Contract | PASS | `openspec validate add-courseware-workbench --strict` 通过；后端 DTO、前端 TS、`PreviewMessage.revision_checksum`、3 styles/10 layouts 注册表均由 presentation contract tests 覆盖。 |
| G2 Persistence | PASS | Repository 使用 safe id、deck lock、原子 entity-first/pointer-last 写入、不可变 source/revision、意图指纹回执与 receipt-bound artifact；定向 repository/service tests 覆盖重载、冲突、幂等、路径拒绝和指针失败。 |
| G3 Generation | PASS | `deck_outline` 先于逐页事件；working 在 emit 前持久化；事件 seq 单调可 replay。注入 `append_event` 失败时保留页面内容并回滚到旧 seq，重试仍为连续回放；刷新续接测试从 seq 3 恢复到 terminal。真实浏览器生成 8 页。 |
| G4 Patch isolation | PASS | Apply 仅允许 `title/subtitle/key_message/blocks/speaker_notes/layout_id`，强制恢复原 `slide_id/position/source_refs`；expected revision、proposal base 和 command receipt 均 fail-closed。测试证明只改变目标页且重复 apply 不新增 revision；浏览器证明第 4 页 proposal → apply → undo。 |
| G5 Quality/export | PASS | Finalize 的阻断权来自 deterministic quality：publication、ready、schema/layout/required slot、source refs、目标覆盖、L08/L09、容量、整套页面 overflow/collision 与当前 revision checksum。质量问题包含 code、slide/source/artifact target 和 fix action；blocked source、fallback、缺测量、render parity failure 均无 artifact。 |
| G6 Render parity | PASS | 同一 revision 渲染 HTML/PPTX；PPTX 真实 reload 后核对页数、命名标题 shape 和 speaker notes digest，再保存 SHA-256 receipt。代表性 L01/L04/L07/L08/L09/L10 × 3 styles 通过；浏览器下载的 fresh PPTX 为 8 页、8 页 notes 均非空，SHA-256 `25ecc5a40edf35ade44f959cfbff51bf74c450e70519159643c2176132be6450`。 |
| G7 Workbench | PASS | LearningView 主入口与独立 workbench routes 已接线，真实 course/chapter 标题随入口传递；无 nodeId 的 CourseLibrary 次入口默认整门课程并实测 create 201/generate 200。桌面为单顶栏 + crumb + 左大预览 + 固定 400px AI；窄屏为 Preview/AI 单面切换。Opaque iframe 校验 exact source、`origin === "null"`、channel/deck/revision/checksum，并按整套页面上报具体 overflow/collision slide ids。浏览器证据为 0 console error、0 warning、0 network failure。 |
| G8 Source integrity | PASS | Source projector 从 deep copy 生成冻结 snapshot 并验证 SHA-256；完整 create → generate → proposal/apply → finalize 测试同时断言课程序列化 digest、snapshot 内容、snapshot digest 和 manifest source ref 全程不变。Deck 数据只落 `backend/data/presentation_decks/`。 |

## AC mapping

| AC | Status | Evidence path |
| --- | --- | --- |
| AC-01 | PASS | LearningView entry test、router workbench meta、App 单 shell、CourseLibrary 次入口 course-scope test。 |
| AC-02 | PASS | Immutable source + manifest/working/revision reload tests；refresh reconnect test。 |
| AC-03 | PASS | Ordered SSE、persist-before-event、failure rollback、replay and terminal tests；generate 不产生 `export_ready`。 |
| AC-04 | PASS | Frozen 3-template/10-layout registry；unknown ids validation failure。 |
| AC-05 | PASS | Current-slide whitelist patch、source-ref preservation、append-only apply/restore、idempotency tests and browser flow。 |
| AC-06 | PASS | Structured deterministic quality issues and blocked finalize tests。 |
| AC-07 | PASS | Render/reload/parity tests、receipt-bound HTML/PPTX、fresh browser PPTX reload。 |
| AC-08 | PASS | Repository dynamic stale detection + client `canDownload` current-revision binding tests。 |
| AC-09 | PASS | Approved-first-prototype visual comparison and desktop/narrow browser captures。 |
| AC-10 | PASS | Full lifecycle CourseDocument/source digest immutability test。 |

## Visual verdict

**PASS。** 视觉真源仍是用户确认的首版原型：顶部返回/课程名/下载、层级条、左侧自适应大预览、右侧固定约 400px 课件 AI、原尺寸快捷按钮。实现借用了教育 agent 的工作台结构，没有复制其品牌色或改成三栏；色彩、表面、边框、圆角和语义状态均保持灵知的浅色/靛蓝语言。

引用的清晰证据：

- `output/playwright/courseware-desktop-proposal-fresh.png` — proposal/diff，SHA-256 `240fbd59…c9aa9`
- `output/playwright/courseware-desktop-export-ready-fresh.png` — finalize/download ready，SHA-256 `50606575…394d`
- `output/playwright/courseware-narrow-ai-fresh.png` — 390×844 AI surface，SHA-256 `0666d4ec…408`

旧的黑块捕获和 `applied-fresh` 黑块捕获未作为视觉 PASS 证据；apply/undo 由 locator、API、目标页内容和 revision 证据证明。

## Commands and artifacts checked

- `python -m pytest -q backend/tests/test_presentation_contracts.py backend/tests/test_presentation_repository.py backend/tests/test_presentation_services.py backend/tests/test_presentations_api.py` → **34 passed**。
- Presentation frontend tests、LearningView entry test、store tests、`npm run build`、OpenSpec strict → 均由 fresh evaluator receipt `088938…` 以 exit 0 记录。
- 额外独立 focused checks：LearningView 上下文 + AIAside 编辑态只读 **3 passed**；CourseLibrary launch scope **1 passed**。
- 最新冻结 evaluator 独立重跑 → **G1–G8 PASS / score 100 / exit 0**。
- `git diff --check` → exit 0；仅现有 LF/CRLF 转换 warning，无 whitespace error。
- `browser-proof.json` digest：`sha256:17aed442b0d37d927e65e78e82488225d51127671a62098923eac1cdf3da53ab`。

## Explicit Light limitations

- 按冻结合同未运行全仓测试、跨浏览器矩阵、3×10 全截图矩阵、性能基准或多 provider live generation。
- 浏览器主路径使用 production router/service + 临时 repository + 固定 deterministic test AI，证明的是工作台/协议/持久化/渲染链路，不伪称真实外部模型联通性。
- 运行中浏览器断线可 replay；进程崩溃后 working/events 仍在，但未实现自动重启未完成的 page workers。
- 当前首版 UI 验证的是当前页提议/应用/撤销；后端已有 deck-scope patch 合同，但显式“整套课件修改”切换仍可作为后续交互增强。

以上均不违反本次 frozen Light AC 或 G1–G8，故最终裁决保持 **PASS**。
