## MODIFIED Requirements

### Requirement: 学习现场必须保持左目录中正文右 AI 的稳定骨架

桌面学习现场 MUST 以课程导航、连续正文和按需 AI 协作表达不同职责，正文 MUST 是唯一长期主舞台。结构化课程块 MUST 提供原位 AI 协作入口；全局 AI 工作区 MAY 作为历史与跨块问题入口按需打开，但 MUST NOT 永久挤压正文或成为块级理解的强制中转站。系统 MUST NOT 使用顶部平级模式替换正文。

#### Scenario: 用户并行理解多个课程块

- **WHEN** 用户在阅读中分别需要解释、例子、简化或提问
- **THEN** 每个动作 MUST 从对应课程块原位发起
- **AND** 系统 MUST NOT 把这些并行理解动作包装成唯一下一步

#### Scenario: 移动端打开块级 AI

- **WHEN** 用户在 390 像素视口打开课程块 AI 菜单或结果
- **THEN** 菜单、回答、操作和输入区 MUST 保持在正文宽度内
- **AND** MUST NOT 被底部导航遮挡或产生横向溢出
