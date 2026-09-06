## ADDED Requirements

### Requirement: AI 老师必须按意图读取最小学习者模型证据

AIContextPackage MUST 只在请求需要学习状态判断时读取 LearnerModel，并只包含相关目标的模型结论、证据类型、置信度和模型修订。普通解释请求 MUST NOT 默认注入完整画像或全部学习历史。

#### Scenario: 用户询问自己的薄弱点

- **WHEN** 当前问题明确要求学习复盘
- **THEN** 上下文 MUST 包含相关目标的正式模型结论及其证据摘要
- **AND** AI MUST 区分已验证事实、系统推断与证据不足

#### Scenario: 用户只要求解释选中文本

- **WHEN** 当前意图是解释一个课程块
- **THEN** 上下文 MUST 以课程片段和当前目标为主
- **AND** MUST NOT 加载无关目标的学习者模型详情

### Requirement: AI 老师不得把模型解释成新的正式事实

AI 回答 MUST 使用模型修订固定当次依据，并用有边界的语言表达推断。聊天、总结、主动建议和用户接受某种说法 MUST NOT 自动改变 LearnerModel；只有正式领域动作产生的新事实才能在下一次重算中改变模型。

#### Scenario: AI 建议重点复习一个目标

- **WHEN** 建议依据低置信或近期正式失败证据
- **THEN** AI MUST 说明依据与不确定性
- **AND** MUST NOT 自动把目标标记为薄弱或需要复习

### Requirement: 旧画像与 Learning OS 不得进入 AI 生产上下文

AI 老师构建回答、主动触发或提案时 MUST NOT 读取旧 AI profile、Learning OS 推断、localStorage 学习统计或默认用户数据。历史显式自我报告只有迁移到正式分区后才 MAY 作为有来源的上下文。

#### Scenario: 旧 profile 保存了 AI 生成的学习风格

- **WHEN** 系统装配当前 AI 上下文
- **THEN** MUST 忽略该 AI 生成画像
- **AND** MUST NOT 根据其调整回答或下一步
