## ADDED Requirements

### Requirement: 学习行为必须写入统一事件账本

系统 MUST 提供轻量学习事件账本，把关键学习行为记录为结构化 `LearningEvent`。事件账本 MUST 使用现有文件存储能力，MUST 支持后续学习者状态模型和教学决策层查询，不得只保存不可分析的散文日志。

#### Scenario: 保存学习事件

- **WHEN** 后端记录一次学习行为
- **THEN** 系统 MUST 写入包含事件 ID、事件类型、用户、课程、节点、来源、证据、结果、元数据和时间戳的事件
- **AND** 事件 MUST 可按用户、课程、节点和事件类型过滤读取

#### Scenario: AI 问答产生事件

- **WHEN** 用户通过 `/api/ask` 或 `/api/ask_events` 提问
- **THEN** 系统 SHOULD 记录用户提问事件
- **AND** 当 AI 流式回答结束时 SHOULD 记录 AI 回答完成事件
- **AND** 不得改变现有问答响应协议

#### Scenario: 标注保存产生事件

- **WHEN** 用户或 AI 保存标注、笔记、错题或格式问题
- **THEN** 系统 SHOULD 记录对应的标注保存事件
- **AND** 事件 SHOULD 关联 `anno_id`、`source_type`、`course_id` 和 `node_id`

#### Scenario: 学习结果产生事件

- **WHEN** 导师学习记录接口收到答题正确性、耗时或题目信息
- **THEN** 系统 SHOULD 记录学习结果事件
- **AND** 事件 SHOULD 保留正确性、耗时、题目摘要和导师记忆更新后的掌握度结果
