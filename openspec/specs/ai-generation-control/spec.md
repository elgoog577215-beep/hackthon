# ai-generation-control Specification

## Purpose
TBD - created by archiving change improve-ai-generation-control. Update Purpose after archive.
## Requirements
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

### Requirement: 课程生成入口必须使用统一课程服务

课程生成主入口 MUST 调用 `CourseService` 生成课程蓝图，不能再使用旧 `AIService/AICourseService` 生成课程大纲。

#### Scenario: 用户创建新课程

- **WHEN** 客户端调用 `/api/generate_course`
- **THEN** 服务端 MUST 使用 `CourseService.generate_course` 生成课程
- **AND** 响应 MUST 包含 `course_id`、`course_name` 和 `nodes`
- **AND** 课程 MUST 保存到存储层，供后续 `/auto_generate` 使用

### Requirement: 课程节点必须携带蓝图契约字段

课程生成返回的 L2 节点 MUST 携带后续正文生成所需的蓝图契约字段。

#### Scenario: 课程蓝图包含小节契约

- **WHEN** `/api/generate_course` 返回 L2 节点
- **THEN** 每个 L2 节点 SHOULD 包含 `learning_objective`
- **AND** SHOULD 包含 `prerequisite_node_ids`
- **AND** SHOULD 包含 `misconceptions`
- **AND** SHOULD 包含 `assessment`
- **AND** SHOULD 包含 `scope_boundary`

### Requirement: 子节点生成接口必须与后台生成使用同一课程服务

手动子节点生成接口 MUST 使用 `CourseService.generate_sub_nodes`，与后台自动生成链路保持一致。

#### Scenario: 用户手动补充子节点

- **WHEN** 客户端调用 `/api/courses/{course_id}/nodes/{node_id}/subnodes`
- **THEN** 服务端 MUST 使用 `CourseService.generate_sub_nodes`
- **AND** 已有子节点时 MUST 直接返回已有子节点，不重复生成

### Requirement: 课程正文必须支持结构化内容块

课程小节正文 SHOULD 保存为 `content_blocks`，每个 block MUST 有稳定 `block_id`、`type`、`title`、`content` 和顺序字段。系统 MUST 继续维护 `node_content` 作为 Markdown 兼容结果。

#### Scenario: 新正文生成完成

- **WHEN** 小节正文生成完成
- **THEN** 系统 SHOULD 从最终正文创建 `content_blocks`
- **AND** 系统 MUST 用 `content_blocks` 重建 `node_content`

#### Scenario: 旧节点没有 content_blocks

- **WHEN** 前端或接口读取旧节点
- **THEN** 系统 MUST 继续使用 `node_content`
- **AND** 后端 MAY 在更新或局部重写时将旧 Markdown 转成 fallback blocks

### Requirement: 系统必须支持 block 级重新生成

系统 MUST 提供节点内部 block 级重新生成能力，重新生成时只能替换目标 block，不能丢失同节点其他 block。

#### Scenario: 用户要求重写应用部分

- **WHEN** 客户端请求重新生成某个 `block_id`
- **THEN** 后端 MUST 基于课程账本、当前节点契约、目标 block 原文、相邻 block 摘要和用户要求构造上下文
- **AND** 后端 MUST 只更新该 block 的 `content`
- **AND** 后端 MUST 重新生成该节点的 `node_content`

### Requirement: 课程内容操作必须使用统一课程服务

节点重写、节点扩展、节点摘要和课程内定位 MUST 通过 `CourseService` 执行。旧 `AICourseService` 和 `AICourseServiceV5` MUST NOT 作为后端可调用服务保留；课程 AI 能力的生产入口只允许落在 `CourseService`。

#### Scenario: 用户重写整个节点

- **WHEN** 客户端调用 `/api/courses/{course_id}/nodes/{node_id}/redefine`
- **THEN** 服务端 MUST 使用 `CourseService` 构造课程上下文、节点契约和用户要求
- **AND** 返回值 MUST 保持兼容，包含 `node_content`
- **AND** 节点的 `content_blocks` MUST 与最终 `node_content` 同步

#### Scenario: 用户扩展节点内容

- **WHEN** 客户端调用 `/api/courses/{course_id}/nodes/{node_id}/extend`
- **THEN** 服务端 MUST 使用 `CourseService` 生成与课程上下文一致的补充内容
- **AND** 响应 MUST 保持现有 `content` 字段

#### Scenario: 后端初始化 AI 门面

- **WHEN** `ai_service` 模块被导入
- **THEN** `AIService` MUST NOT 继承或导入旧课程生成服务
- **AND** quiz、QA、graph、learning、diagram、profile 能力 MUST 保持可用

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
