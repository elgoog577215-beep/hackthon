## Why

灵知已有可版本化课程、结构化内容块、学习目标、练习、误区资产和 AI 老师，但缺少面向讲授的课件表达。普通导出按钮不能承载逐页生成、来源追溯、AI 提议修改、版本恢复和正式导出质量门。

教育 agent 已验证“先规划页序、再并发填充页面、同一 deck 双渲染 HTML/PPTX、通过 SSE 报告进度”是可行骨架；灵知应借用这条生产线和“左预览、右 AI”工作台结构，并用自己的课程版本、来源锚点、异步 LLM profile、提案协议和质量门完成适配。

## What Changes

- 在课程学习页 AI 老师入口附近增加“课件”入口，进入独立全屏工作台。
- 新增独立于课程正文的 `PresentationDeck` 领域：不可变来源快照、生成工作快照、追加式 revision、提案和 artifact receipt。
- 新增先页序后逐页填充的异步生成管线，流式发送结构化 deck 事件，不流式发送 PPTX 二进制。
- 新增 HTML 实时预览、当前页选择、AI proposal/diff/apply/undo、演讲者备注和来源查看。
- 注册三种灵知模板与十种版式；模型只能选择 registry 中存在的 `template_id/layout_id`。
- 用户点击“完成课件”后才运行课程门、课件门和 HTML/PPTX 渲染；通过后才产生可下载 artifact。

## First Delivery Scope

首个可用版本包含三种模板（灵知课堂、理工推演、学术答辩）和十种注册版式，但视觉验证只覆盖代表性页面，不做 3×10 截图矩阵。生成期间支持页序先出、删除未生成页和调整 outline 顺序；生成后支持当前页 AI 修改、应用和撤销。新增页面、多页批量编辑、受控同步课程和自定义模板后置。

## Capabilities

### New Capabilities

- `courseware-workbench`: 路由、入口、草稿生命周期、预览、逐页 AI 协作和正式下载。
- `courseware-generation-pipeline`: 来源投影、页序/逐页生成、注册模板、质量门、HTML/PPTX 渲染和 artifact receipt。

### Modified Capabilities

- None. 课程正文、现有 AI 老师和 CourseTaskCenter 保持原合同；课件作为独立领域接入。

## Impact

- 后端新增 presentation models/repository/source/templates/generation/render/quality/router，并显式增加 `python-pptx` 依赖。
- 前端新增 presentation store、独立工作台视图和 presentation 组件；更新 router、LearningView 和课程库次入口。
- 新增 `backend/data/presentation_decks/`，不把 deck 写回课程 JSON。
- 不改端口；继续使用前端 5173、后端 8000 和现有 `/api` 基址。
- 已批准视觉基线：`.codex/harness/visual-companion/2026-07-15-ppt-workbench/visual-companion-screen.html` 的最初版本，实施时不得擅自换成后续视觉变体。
