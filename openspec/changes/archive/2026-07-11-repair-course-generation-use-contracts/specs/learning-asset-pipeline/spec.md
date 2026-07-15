# learning-asset-pipeline Specification

## ADDED Requirements

### Requirement: 最终正文必须持久化稳定内容块

生成节点完成时，系统 MUST 将最终正文转换为稳定 `content_blocks` 并与正文一起保存。节点完成和 finalized 实时事件 MUST 携带保存后的同一组内容块；MUST NOT 继续写入或发送空数组。

#### Scenario: 节点正文生成完成

- **WHEN** 模型流式生成结束且正文通过节点质量处理
- **THEN** 节点 MUST 保存带 block_id、content_fingerprint 和 block_revision_id 的内容块
- **AND** WebSocket 完成事件 MUST 携带这些持久内容块

### Requirement: 学习资产必须包含章节推进契约

学习资产编译器 MUST 为每个有效章节生成版本化章节推进契约，包含真实 `chapter_id`、当前必需目标、掌握要求、前置策略和完成策略。契约引用 MUST 与 LearningContinuation 使用的章节和目标身份一致。

#### Scenario: 系统化课程包含两个章节

- **WHEN** 学习资产编译器处理带 L1 章节和 L2 目标的系统化课程
- **THEN** 每个章节 MUST 获得一个 chapter_progression_contract
- **AND** 必需目标 MUST 只引用该章当前目标 ID

### Requirement: 阅读型降级必须由最终资产计划显式表达

当课程用途或资产偏好不启用正式题目时，资产计划 MUST 设置 `reading_only_degraded=true`；启用正式题目时 MUST 为 false。系统 MUST 根据最终 enabled assets 计算该值。

#### Scenario: 资料整理课程未请求题目

- **WHEN** `material_organization` 使用默认资产偏好
- **THEN** 计划 MUST 明确标记 reading_only_degraded
- **AND** 后续预检 MUST 能自动选择 reading_only 口径

### Requirement: 质量门必须覆盖内容与章节推进契约

资产质量门 MUST 阻止缺少持久内容块、内容块修订、章节推进契约或有效目标引用的课程通过。读取层兼容投影 MUST NOT 满足生成质量门。

#### Scenario: 正文存在但内容块未持久化

- **WHEN** 生成课程只有 node_content 而 content_blocks 为空
- **THEN** 资产质量报告 MUST 包含 critical content issue
- **AND** 课程 MUST NOT 发布为当前版本

### Requirement: 学习资产只能在版本发布成功后激活

编译后的资产包 MAY 先保存为不可变修订，但 current 指针 MUST 只在最终质量通过且初始版本创建或候选版本提升成功后更新。失败生成 MUST NOT 替换当前资产包。

#### Scenario: 初始课程资产质量失败

- **WHEN** 资产包已经保存但质量门未通过
- **THEN** 系统 MUST 保留诊断修订
- **AND** MUST NOT 激活该修订或创建当前课程版本
