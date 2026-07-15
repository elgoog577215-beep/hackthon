## Context

当前课程正文生成路径是 `TaskManager._schedule_nodes -> _process_node -> CourseService.generate_node_content_stream`。正文生成时会通过 `GlobalKnowledgeGraph.get_context_for_node` 注入已定义概念和已用案例，但该对象是运行期浅上下文，不包含课程蓝图依赖、章节摘要、误区、验收标准，也不会约束并发生成顺序。

## Goals

- 在不引入数据库和新依赖的前提下，让主生成路径拥有可复用的课程上下文账本。
- 保留现有流式体验，同时让前端知道哪个内容是最终修复稿。
- 让 prompt 生成更像课程设计，而不是单纯写长文。
- 保持旧问答流可读，新增结构化事件流供前端逐步迁移。

## Non-Goals

- 不做向量数据库、复杂 RAG 或全文检索。
- 不做完整多 Agent 审稿编排。
- 不重写前端聊天渲染体系。
- 不改变现有课程文件格式的基本兼容性。

## Decisions

### Decision: 复用 `CourseContextManager` 做课程上下文账本

项目已有 `course_context.py`，只是主路径未使用。直接扩展它比新增服务更省改动：用课程 plan 初始化账本，用生成后的正文更新摘要，用账本格式化生成上下文。

### Decision: 依赖波次调度，不做复杂 DAG 引擎

每个节点读取 `prerequisite_node_ids`；满足依赖的节点一批并发生成，未满足的留到下一批。循环无法推进时退化为顺序生成，避免任务卡死。

### Decision: 流式 chunk 仍是 draft，新增 `node_finalized`

`stream_chunk` 不改含义，只补 `phase: draft`。质量检查、修复和 LaTeX 修复后的最终内容通过 `node_finalized` 推送。前端收到 final 后直接覆盖对应节点内容。

### Decision: 问答事件流采用文本 SSE 风格帧

`/api/ask` 仍保持旧纯文本兼容；新增 `/api/ask_events` 返回 `event: answer` / `event: metadata` 文本帧。这样无需引入新库，也不破坏现有调用方。

### Decision: 二段式生成先放进复杂章节提示词

复杂章节先要求模型输出“写作计划/边界确认”，再展开正文。真正拆成两次 LLM 调用只在质量模式路径中使用，避免流式主路径成本翻倍。

## Risks

- 账本摘要是启发式抽取，不等于真实语义检索；后续若课程质量仍不稳，再引入检索或更强审稿。
- 依赖由模型生成，可能出现不存在的节点 ID；调度器会忽略无效依赖并避免死锁。
- 新事件需要前端逐步消费；本次保留旧事件和旧问答接口。
