## Why

课程正文的主体验应该是一篇有学科章法的 Markdown 讲义，而不是后端预切出来的一组固定教学块。上一轮 `content_blocks` 主导正文展示后，前端变成块状卡片，后端也倾向把数学、人文、辩论、工程等课程压成统一章法，破坏了课程生成质量和阅读美感。

新的目标是保留完整 Markdown 作为内容本体，同时让前端提供文档编辑器式的父子标题树、标题折叠和选中文字后的 AI 局部修改能力。AI 修改只作用于用户选区或标题范围，不改变课程正文的学科结构模板。

## What Changes

- 将课程正文主链路明确为完整 `node_content` Markdown，不再要求后台生成或保存固定 `content_blocks`。
- 前端从 Markdown 临时解析标题树，展示父子关系、缩进层级和折叠状态。
- 前端支持用户选中任意文字后弹出轻量 AI 工具条，可发起改写、简化、补例子、出题、问 AI 等操作。
- 后端新增选区级 AI 修改接口，接收选中文本、标题路径、前后文、用户要求和完整节点上下文，返回候选替换文本。
- 前端展示 AI 修改预览，用户确认后只替换原 Markdown 选区并保存完整 `node_content`。
- 选区修改行为写入学习事件账本，供后续学习者状态和教学决策使用。
- 旧 block 级接口保留兼容，但不作为前端阅读和课程生成主链路。

## Impact

- Affected backend:
  - `course_service.py` 增加选区修改 prompt 编排。
  - `routers/nodes.py` 增加选区修改 API，并记录事件。
  - `models.py` 增加请求/响应模型。
- Affected frontend:
  - 新增 Markdown 标题解析和选区上下文工具。
  - `CourseNode.vue` 或周边阅读组件增加标题折叠、选区工具条和 AI 修改面板。
  - `stores/course.ts` 增加选区修改和保存调用。
- Affected tests:
  - 后端选区修改上下文、事件记录、旧接口兼容测试。
  - 前端 Markdown 标题树解析、选区替换定位和工具逻辑测试。

## Non-Goals

- 不重写课程生成学科模板。
- 不把正文重新卡片化。
- 不批量迁移或重写已有课程 JSON 内容。
- 不删除旧 `content_blocks` 字段和旧 block 级接口，只把它们降级为兼容层。
