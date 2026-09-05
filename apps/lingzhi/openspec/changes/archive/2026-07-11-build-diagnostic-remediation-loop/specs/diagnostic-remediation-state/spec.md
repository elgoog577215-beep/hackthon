# diagnostic-remediation-state Specification

## ADDED Requirements

### Requirement: 单次错误不得直接确认为错因

系统 MUST 只把有效正式作答作为错答事实；首次普通失败 MUST 保持为反馈和重试，错因 MUST 经过辨别任务验证。

#### Scenario: 首次正式练习失败

- **WHEN** 用户第一次独立完成当前目标的正式题目且未通过
- **THEN** 系统 MUST 保存失败事实并提供重试
- **AND** 系统 MUST NOT 创建 confirmed 错因

### Requirement: 诊断必须区分事实、假设和决策

系统 MUST 保存候选假设的支持与反对证据，并由确定性规则输出 confirmed、rejected 或 unresolved；AI MUST NOT 直接确认错因。

#### Scenario: 辨别结果仍然含糊

- **WHEN** 多个候选假设仍被相同证据支持或评分置信度不足
- **THEN** 诊断案例 MUST 保持 unresolved 或 testing
- **AND** 系统 MUST NOT 把候选写入稳定学习者画像

### Requirement: 所有诊断补救任务必须复用正式 Attempt

系统 MUST 使用统一任务修订承载课程练习、辨别题、引导练习和复验题，并复用 PracticeAttempt 的草稿、提交、提示、评分和历史能力。

#### Scenario: 用户完成辨别题

- **WHEN** 用户提交 diagnostic_probe
- **THEN** 系统 MUST 创建或更新 PracticeAttempt
- **AND** 该结果 MUST NOT 直接成为掌握证据

### Requirement: 补救必须保持最小范围

系统 MUST 只针对一个已确认主要错因选择一个补救目标，并优先使用课程正文和正式补救资产。

#### Scenario: 正文已有对应解释

- **WHEN** 已确认错因绑定到有效内容锚点
- **THEN** 补救会话 MUST 引用该内容锚点
- **AND** 系统 MUST NOT 生成第二份正式课程正文

### Requirement: 补救成功必须经过未泄露新题复验

系统 MUST 只有在用户无帮助完成当前版本、同目标和同标准的未泄露复验任务后，才关闭诊断案例。

#### Scenario: 用户在复验中请求提示

- **WHEN** 用户使用任意提示或 AI 帮助完成 remediation_validation
- **THEN** 当前 Attempt MUST 保留为支持下练习
- **AND** 系统 MUST 安排新的独立复验任务

### Requirement: 诊断补救必须可恢复和可失效

系统 MUST 保存当前案例、补救会话和原学习位置；目标、标准或任务修订变化时 MUST 保留历史并标记 stale。

#### Scenario: 课程版本在补救期间变化

- **WHEN** 当前目标或掌握标准修订不再有效
- **THEN** 当前诊断或补救会话 MUST 标记 stale
- **AND** 旧验证结果 MUST NOT 证明新版本掌握

### Requirement: 旧错题启发式不得继续主导教学决策

系统 MUST NOT 因一次答错、旧错题数量、低分或停留时间直接确认薄弱点、阻止继续学习或抢占导师主行动。

#### Scenario: 只有旧迁移错题

- **WHEN** 用户只有低置信旧错题历史而没有当前正式诊断证据
- **THEN** 导师和画像 MUST 只把它显示为历史参考
- **AND** 系统 MUST NOT 自动开启诊断或补救
