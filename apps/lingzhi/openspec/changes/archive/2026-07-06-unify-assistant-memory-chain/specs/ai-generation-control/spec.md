## MODIFIED Requirements

### Requirement: 学习者上下文必须有统一后端聚合层

系统 MUST 提供轻量学习者上下文聚合层，把用户笔记、错题、导师知识状态、最近学习足迹和画像摘要整理成稳定结构，供课程内容生成、局部重写、导师问答和画像接口复用。导师问答的生产 prompt MUST 直接复用该聚合层，不得再通过旧双记忆控制器分叉构造用户记忆。

#### Scenario: 导师问答构造用户记忆

- **WHEN** 问答服务为某个 `node_id` 构造导师 prompt
- **THEN** 系统 MUST 读取统一学习者上下文
- **AND** 不得返回硬编码的用户偏好占位文案
- **AND** 不得依赖旧 `memory.py` 的 `DualMemoryController` 构造生产问答 prompt

#### Scenario: 兼容问答入口保持可用

- **WHEN** 客户端调用 `/api/ask` 或 `/api/ask_events`
- **THEN** 服务端 MUST 保持现有流式响应与 metadata 协议
- **AND** prompt SHOULD 包含请求课程上下文、当前节点、学习者上下文、用户笔记和会话摘要

#### Scenario: 画像接口生成新画像

- **WHEN** 客户端调用 `/api/profile/generate`
- **THEN** 服务端 SHOULD 保存最新画像摘要到后端学习者上下文
- **AND** 后续 AI 链路 MAY 读取该画像摘要作为个性化约束

#### Scenario: 局部内容块重新生成

- **WHEN** 用户重新生成某个内容块
- **THEN** prompt SHOULD 同时包含课程上下文和学习者上下文
- **AND** 学习者上下文不得替代课程蓝图约束
