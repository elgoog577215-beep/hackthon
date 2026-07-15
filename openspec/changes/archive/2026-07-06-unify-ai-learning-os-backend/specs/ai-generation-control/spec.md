## ADDED Requirements

### Requirement: 后端 AI 链路必须通过教学决策层表达教学意图

系统 MUST 提供轻量 `TeachingDecision` 能力，把 `LearnerState` 中的事实证据和系统推断转换成结构化教学意图。教学决策层 MUST 不直接调用大模型，MUST 不替代学习者状态，MUST 输出可解释依据和保守置信度。

#### Scenario: 从薄弱状态生成教学决策

- **GIVEN** 某节点存在错题、低正确率或重复提问
- **WHEN** 系统为该课程或节点构建教学决策
- **THEN** 决策 SHOULD 包含复习、简化解释、补充例子或针对薄弱点练习等动作
- **AND** 决策 MUST 保留事实依据、系统推断依据和证据强度

#### Scenario: 证据不足时保持保守

- **GIVEN** 当前用户、课程或节点缺少学习事件
- **WHEN** 系统构建教学决策
- **THEN** 决策 MUST 标记为证据不足或探索阶段
- **AND** 不得伪造掌握度、薄弱点或风险结论

### Requirement: 后端必须提供统一 AI Learning Context 编排层

系统 MUST 提供统一 AI Learning Context 编排能力，组合课程/节点上下文、旧 `LearnerContext`、`LearnerState` 和 `TeachingDecision`。该编排层 MUST 同时提供结构化对象和 prompt 摘要，供 AI 助手、课程内容生成、导师建议等链路复用。

#### Scenario: AI 助手读取统一上下文

- **WHEN** AI 助手构造问答 prompt
- **THEN** prompt MUST 包含统一学习者上下文
- **AND** prompt SHOULD 包含学习者状态摘要
- **AND** prompt SHOULD 包含教学决策摘要
- **AND** 问答响应协议 MUST 保持兼容

#### Scenario: 课程内容生成读取统一上下文

- **WHEN** `CourseService` 生成、重写、扩展或总结课程节点内容
- **THEN** prompt SHOULD 通过 AI Learning Context 读取学习者状态和教学决策摘要
- **AND** 学习者状态和教学决策不得覆盖课程蓝图、课程账本和节点契约

### Requirement: 旧记忆、状态和决策必须有清晰边界

系统 MUST 明确并保持以下职责边界：`LearningEvent` 记录发生过什么，`LearnerState` 归纳当前状态，`TeachingDecision` 表达下一步教学意图，`LearnerContext`/Memory 保留长期背景、画像、笔记和错题兼容信号，`AI Learning Context` 负责把这些内容组织给 AI 使用。

#### Scenario: 旧学习者上下文继续兼容

- **WHEN** 旧问答、课程内容或导师链路需要学习者背景
- **THEN** 系统 MAY 继续调用 `LearnerContext`
- **AND** 新链路 SHOULD 把 `LearnerContext` 作为 AI Learning Context 的一部分
- **AND** 不得复制一套新的旧式记忆拼装逻辑

#### Scenario: 导师建议读取新状态与决策

- **WHEN** 客户端请求导师学习建议
- **THEN** 后端 SHOULD 优先基于 `LearnerState` 和 `TeachingDecision` 生成建议
- **AND** 旧导师记忆中的目标、连续学习、错题本和知识状态 MAY 作为兼容补充
- **AND** 响应结构 MUST 保持现有 `suggestions` 字段兼容
