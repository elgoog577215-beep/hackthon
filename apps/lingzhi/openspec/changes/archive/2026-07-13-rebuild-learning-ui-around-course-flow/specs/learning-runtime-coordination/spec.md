## MODIFIED Requirements

### Requirement: 前端任务型主动作必须按任务引用路由

前端 MUST 使用 `NextLearningAction.task_ref.kind` 区分普通练习、诊断、补救和独立复验；MUST 从正文中的对应任务入口打开统一 `TaskOverlay` 并精确定位任务修订，MUST NOT 维护基于动作 scope 的第二套任务路由真相或切换独立练习模式。

#### Scenario: 连续性动作进入指定任务

- **WHEN** primary action 携带可用的 practice、diagnostic、remediation 或 validation 任务引用
- **THEN** 学习现场 MUST 聚焦对应正文任务入口并打开该任务修订
- **AND** 任务不存在或已失效时 MUST 在原入口显示失效状态，不得退回第一题

### Requirement: 移动端课程模式必须可理解

前端在移动端 MUST 为目录、正文、学习记录和 AI 老师保留可见文字或等效的持续可见名称；练习、掌握、蓝图和版本 MUST NOT 作为顶层移动导航。

#### Scenario: 390px 视口切换学习空间

- **WHEN** 用户查看移动端学习导航
- **THEN** 目录、正文、记录和 AI MUST 有可见名称
- **AND** 导航 MUST NOT 遮挡正文、输入区或安全区

## ADDED Requirements

### Requirement: 运行时必须提供可追溯的临时适配块

`LearningRuntime` MAY 根据强学习证据返回低风险 `adaptive_blocks`，每个块 MUST 绑定语义锚点、原因码、证据引用、状态和有效期。适配块 MUST NOT 写入正式课程、正式题目或掌握事实。

#### Scenario: 当前概念出现已确认理解缺口

- **WHEN** 运行时存在足以支持最小解释或反例的强证据
- **THEN** 系统 MAY 在相关课程块后返回一个活动适配块
- **AND** 同一锚点 MUST NOT 同时返回多个竞争块

### Requirement: 临时适配块必须可跳过且不阻断确定性学习

用户 MUST 能跳过、收起或反馈适配块；模型失败或块过期 MUST 不改变基础课程顺序、正式 Attempt、学习记录或确定性下一步。

#### Scenario: 适配内容生成失败

- **WHEN** AI provider 无法生成临时解释
- **THEN** 正文、正式任务和连续性动作 MUST 继续可用
- **AND** 系统 MUST NOT 保存半段输出或伪造完成状态
