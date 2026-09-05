## ADDED Requirements

### Requirement: 课程内容操作必须使用统一课程服务

节点重写、节点扩展、节点摘要和课程内定位 SHOULD 通过 `CourseService` 执行，避免继续把课程内容能力散落在旧 `AICourseService` 中。旧服务 MAY 保留为 legacy 备份，但生产路由 MUST 优先调用 `CourseService`。

#### Scenario: 用户重写整个节点

- **WHEN** 客户端调用 `/api/courses/{course_id}/nodes/{node_id}/redefine`
- **THEN** 服务端 MUST 使用 `CourseService` 构造课程上下文、节点契约和用户要求
- **AND** 返回值 MUST 保持兼容，包含 `node_content`
- **AND** 节点的 `content_blocks` MUST 与最终 `node_content` 同步

#### Scenario: 用户扩展节点内容

- **WHEN** 客户端调用 `/api/courses/{course_id}/nodes/{node_id}/extend`
- **THEN** 服务端 SHOULD 使用 `CourseService` 生成与课程上下文一致的补充内容
- **AND** 响应 MUST 保持现有 `content` 字段

### Requirement: 学习者上下文必须有统一后端聚合层

系统 MUST 提供轻量学习者上下文聚合层，把用户笔记、错题、导师知识状态、最近学习足迹和画像摘要整理成稳定结构，供课程内容生成、局部重写、导师问答和画像接口复用。

#### Scenario: 导师问答构造用户记忆

- **WHEN** 问答服务为某个 `node_id` 构造导师 prompt
- **THEN** 系统 MUST 读取统一学习者上下文
- **AND** 不得返回硬编码的用户偏好占位文案

#### Scenario: 画像接口生成新画像

- **WHEN** 客户端调用 `/api/profile/generate`
- **THEN** 服务端 SHOULD 保存最新画像摘要到后端学习者上下文
- **AND** 后续 AI 链路 MAY 读取该画像摘要作为个性化约束

#### Scenario: 局部内容块重新生成

- **WHEN** 用户重新生成某个内容块
- **THEN** prompt SHOULD 同时包含课程上下文和学习者上下文
- **AND** 学习者上下文不得替代课程蓝图约束
