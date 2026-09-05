## ADDED Requirements

### Requirement: 课程生成必须使用上下文账本

课程正文生成 MUST 注入课程上下文账本，账本至少包含课程目标、前置知识、本节学习目标、范围边界、误区、验收标准、已完成前置内容摘要和已出现概念。

#### Scenario: 从课程蓝图创建账本
- **WHEN** 课程大纲生成完成
- **THEN** 系统 MUST 从大纲中的章节和小节字段创建课程上下文账本
- **AND** 每个小节的 `learning_objective`、`prerequisite_node_ids`、`misconceptions`、`assessment`、`scope_boundary` MUST 可供正文生成读取

#### Scenario: 正文生成更新账本
- **WHEN** 一个小节正文生成完成并经过修复
- **THEN** 系统 MUST 用最终正文更新该节点摘要和概念索引

### Requirement: 节点调度必须尊重前置依赖

正文生成调度 MUST 优先生成无依赖或依赖已满足的节点，仍允许同一波次的无依赖节点并发。

#### Scenario: 节点声明前置依赖
- **GIVEN** 节点 B 声明依赖节点 A
- **WHEN** A 和 B 都待生成
- **THEN** 系统 MUST 先生成 A，再生成 B

#### Scenario: 依赖无效或形成循环
- **GIVEN** 模型输出了不存在或循环的依赖
- **WHEN** 调度器无法找到可推进节点
- **THEN** 系统 MUST 按原始顺序退化生成，避免任务卡死

### Requirement: 流式生成必须区分草稿和最终稿

系统 MUST 保留实时草稿 chunk 推送，并在最终内容确定后推送独立 final 事件。

#### Scenario: 流式生成结束后内容被修复
- **WHEN** 草稿流结束后质量检查或 LaTeX 修复改变了正文
- **THEN** 系统 MUST 推送 `node_finalized` 事件
- **AND** 事件 payload MUST 包含最终 `node_content`

### Requirement: 问答 metadata 必须支持结构化事件流

系统 MUST 提供结构化问答事件流接口，将回答正文和 metadata 拆成不同事件。

#### Scenario: 客户端请求结构化问答流
- **WHEN** 客户端调用 `/api/ask_events`
- **THEN** 服务端 MUST 返回 `text/event-stream`
- **AND** 回答正文 MUST 通过 `answer` 或 `final_answer` 事件返回
- **AND** metadata MUST 通过 `metadata` 事件返回
