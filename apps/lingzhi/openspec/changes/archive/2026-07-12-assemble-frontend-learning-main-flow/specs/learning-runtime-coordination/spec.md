## ADDED Requirements

### Requirement: 掌握检查动作必须指向具体正式任务

系统 MUST 为 `start_mastery_check` 返回与当前目标和节点一致的正式 `mastery_check` 任务修订；尚未创建 Attempt 时 MUST 使用空对象 ID 表示待开始任务，不得把学习目标修订伪装成练习任务修订。

#### Scenario: 阅读完成后进入掌握检查

- **WHEN** 当前目标已经完成阅读且存在正式掌握检查题
- **THEN** primary action 的 task_ref.kind MUST 为 practice
- **AND** task_revision_id MUST 等于该掌握检查题的任务修订
- **AND** 前端 MUST 选中该题但不得在用户确认前自动创建 Attempt

### Requirement: 前端任务型主动作必须按任务引用路由

前端 MUST 使用 `NextLearningAction.task_ref.kind` 区分普通练习、诊断、补救和独立复验；MUST NOT 维护基于动作 scope 的第二套任务路由真相。

#### Scenario: 连续性动作进入指定任务

- **WHEN** primary action 携带可用的 practice、diagnostic、remediation 或 validation 任务引用
- **THEN** 课程工作区 MUST 打开练习模式并定位该任务修订
- **AND** 任务不存在或已失效时 MUST 显示失效状态，不得退回第一题

### Requirement: 连续性动作展示必须共享同一翻译

连续性条、学习者画像和学习统计 MUST 使用同一套动作标签与原因码翻译；中文和英文界面 MUST NOT 向用户显示原始 action_type 或 reason_code。

#### Scenario: 多个界面展示同一下一步

- **WHEN** LearningRuntime 的 primary action 为 start_mastery_check
- **THEN** 所有可见消费者 MUST 表达相同的“掌握检查”动作和原因
- **AND** 切换英文后 MUST 使用对应英文词条

### Requirement: 浏览器主链验收必须隔离学习者身份

前端 MUST 支持在显式验收配置下发送 `X-User-Id`，浏览器验收 MUST 使用一次性隔离用户；未配置身份覆盖时 MUST 保持现有运行行为。

#### Scenario: 验收课程主链

- **WHEN** 验收服务器配置了 VITE_LEARNER_USER_ID
- **THEN** 前端所有学习领域请求 MUST 携带该用户身份
- **AND** 产生的正式学习对象 MUST NOT 写入 default_user
