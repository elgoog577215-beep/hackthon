## Context

当前系统已经具备课程 Markdown 渲染、学习事件账本、学习者状态和教学决策层，但局部重构能力曾经错误地以 `content_blocks` 为中心。这个设计会产生两个问题：

1. 后端容易把所有课程正文切成固定块，从而覆盖不同学科原本应有的写作章法。
2. 前端容易把正文展示成卡片堆，破坏文档阅读体验。

用户真正需要的是类似现代文档编辑器的体验：正文仍是连续 Markdown，标题层级可见、可折叠，选中文字后可以局部交给 AI 修改。

## Goals / Non-Goals

**Goals:**
- Markdown 仍然是课程正文的唯一主内容本体。
- 前端从 Markdown 派生标题树和折叠结构，但不改变存储格式。
- 用户可以选中任意文字后发起 AI 局部修改。
- 后端选区修改 prompt 必须带上标题路径、前后文、课程/节点契约和 AI Learning Context。
- AI 修改结果必须先作为候选文本返回，由前端确认后再替换并保存。
- 选区修改必须记录结构化 LearningEvent。

**Non-Goals:**
- 不强制后端生成 `content_blocks`。
- 不用卡片替代正文。
- 不在本轮实现完整多人协作编辑、富文本编辑器或复杂 source map。
- 不保证所有重复文本都能自动无歧义替换；第一版使用选区上下文和前端确认降低风险。

## Decisions

### Decision: Markdown is the source of truth

`node_content` 是课程正文主存储。标题树、折叠状态、选区信息都从 Markdown 临时解析或由前端 UI 状态保存，不要求后端持久化固定块结构。

这样可以避免生成端为了配合前端操作而牺牲学科章法。

### Decision: Selection rewrite is a candidate-generation API

后端选区修改接口只返回候选替换文本、说明和上下文摘要，不直接保存节点。前端确认后使用现有节点更新接口保存完整 Markdown。

这样可以避免 AI 误改后直接污染课程内容，也便于前端展示 diff 和撤销。

### Decision: Heading tree is a front-end derived index

前端解析 `#` 到 `######` 标题，构造父子标题树和每个标题范围的起止行。折叠只影响展示，不影响 Markdown 内容本身。

### Decision: Selection context is bounded but rich enough

前端传给后端：
- `selected_text`
- `heading_path`
- `before_context`
- `after_context`
- `node_content`
- `user_requirement`
- `action_type`

后端再补充课程账本、节点契约和 AI Learning Context。这样不需要后台预切正文，也能让 AI 有足够上下文。

### Decision: Keep old block APIs as compatibility layer

旧 `content_blocks` 和 block 再生成接口暂时保留，防止旧数据和旧调用断裂。但新 UI 不再把它们作为正文展示主入口，新生成和整节重写也不应依赖它们。

## Risks / Trade-offs

- 选中文本在 Markdown 中重复出现时，前端替换可能有歧义。
  - Mitigation: 第一版带上前后文定位；若无法唯一定位，要求用户重新选择或使用标题范围重写。
- 直接操作 Markdown 需要处理渲染文本和源文本之间的差异。
  - Mitigation: 第一版优先用当前 DOM 选区文本和源 Markdown 片段匹配，后续再升级 source map。
- 折叠后的阅读体验可能影响滚动定位。
  - Mitigation: 折叠状态只在当前节点内维护，滚动锚点仍使用节点/标题 ID。

## Migration Plan

- 新增前端 Markdown outline/selection 工具，先应用在课程节点正文区域。
- 新增后端选区修改接口和 CourseService 方法。
- 新 UI 默认走 Markdown 选区修改；旧 block 操作保留但不暴露为主阅读形态。
- 添加测试覆盖解析、替换、后端 prompt 和事件记录。
- 验证后再考虑是否归档旧 structured content block 规格。
