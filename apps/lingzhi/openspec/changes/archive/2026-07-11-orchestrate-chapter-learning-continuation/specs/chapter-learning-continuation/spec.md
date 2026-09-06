# chapter-learning-continuation Specification

## ADDED Requirements

### Requirement: 章节状态必须由现有学习事实投影

系统 MUST 从课程结构、学习进度、快照、正式作答、诊断补救和学习记录投影章节状态，MUST NOT 建立可独立修改的单一章节状态真源。

#### Scenario: 用户完成阅读但尚未验证掌握

- **WHEN** 当前章节目标均已明确完成阅读但缺少有效正式证据
- **THEN** 章节学习进度 MUST 为 covered
- **AND** 掌握证据 MUST 为 evidence_insufficient，而不是 verified

### Requirement: 系统必须只输出一个跨模块主要动作

系统 MUST 按固定优先级输出唯一 `NextLearningAction`，导师、Learning OS 和前端入口 MUST 读取同一动作。

#### Scenario: 同时存在补救会话和到期复习

- **WHEN** 用户有活动补救会话且另一个目标存在到期复习
- **THEN** 主要动作 MUST 恢复补救会话
- **AND** 到期复习最多作为次要提醒

### Requirement: 未完成任务必须优先恢复

系统 MUST 优先恢复活动诊断、补救、独立复验和未提交正式练习，并使用快照和任务修订解释恢复位置。

#### Scenario: 用户刷新未提交练习

- **WHEN** 当前课程存在有效 in_progress PracticeAttempt
- **THEN** 主要动作 MUST 指向该 Attempt
- **AND** 前端 MUST 进入同一练习工作区并恢复服务端草稿

### Requirement: 风险不得由低置信信号升级

系统 MUST 只有在显式必需前置依赖和可靠当前证据同时存在时输出 action_required；证据缺失、一次答错、旧错题、停留时间和 AI 推断 MUST NOT 阻断章节。

#### Scenario: 历史课程缺少前置掌握证据

- **WHEN** 前置目标没有正式题目或当前修订证据
- **THEN** 系统 MUST 标记尚未验证或建议检查
- **AND** 用户 MUST 仍可开始当前章节

### Requirement: 版本变化必须先确认再继续

系统 MUST 检测快照、未完成 Attempt、诊断或记录与当前课程版本的失配，并输出需要确认的版本变化动作；历史对象 MUST 保留。

#### Scenario: 补救期间课程更新

- **WHEN** 活动补救会话绑定旧课程版本
- **THEN** 主要动作 MUST 为 confirm_version_change
- **AND** 系统 MUST NOT 静默把旧会话映射到新目标修订

### Requirement: 章节结果必须按目标解释证据

系统 MUST 按目标展示阅读状态、掌握证据、活动诊断补救和遗留项，并给出唯一后续动作；MUST NOT 用总分或完成百分比替代目标证据。

#### Scenario: 章节只有部分目标验证通过

- **WHEN** 章节中一部分目标 verified，另一部分 needs_attention
- **THEN** 章节结果 MUST 为 partially_verified 或 needs_attention
- **AND** 主要动作 MUST 指向最优先的未解决目标

### Requirement: 历史课程必须可继续学习

系统 MUST 将缺少正式学习资产的历史内容投影为兼容章节，允许完成阅读和推进，但不得伪造掌握结论。

#### Scenario: 只有 L1 正文的旧课程完成阅读

- **WHEN** 用户明确完成该正文且课程没有正式题目
- **THEN** 系统 MUST 显示阅读完成、证据不足
- **AND** 默认推进策略 MUST 允许进入下一兼容章节

### Requirement: AI 只能解释统一动作

AI MUST NOT 创建或改写章节主要动作、风险等级和章节结果，只能依据统一投影解释原因或提供当前业务工作区内的帮助。

#### Scenario: AI 建议与确定性动作冲突

- **WHEN** AI 文本建议复习但统一动作要求恢复独立复验
- **THEN** 页面主要动作 MUST 保持恢复独立复验
- **AND** AI 建议 MUST NOT 生成第二个执行按钮
