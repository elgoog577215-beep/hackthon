## ADDED Requirements

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
