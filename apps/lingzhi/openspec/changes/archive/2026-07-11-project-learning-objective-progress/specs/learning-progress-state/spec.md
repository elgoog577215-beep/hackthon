## ADDED Requirements

### Requirement: 学习目标必须拥有稳定身份和正式资产绑定

系统 MUST 为每个可学习节点提供稳定 `objective_id` 和不可变 `objective_revision_id`，并绑定当前正文块、正式题目、掌握标准、误区和回退入口。目标陈述变化时修订 MUST 变化，历史修订 MUST NOT 被覆盖。

#### Scenario: 课程目标文字发生变化

- **WHEN** 同一节点的可观察学习目标被修改
- **THEN** objective_id MUST 保持不变
- **AND** objective_revision_id MUST 变化
- **AND** 旧目标证据 MUST 保留但不得冒充当前目标证据

### Requirement: 阅读进度与掌握状态必须分离

系统 MUST 分别投影阅读进度 `not_started/in_progress/learned` 和掌握状态 `not_checked/evidence_insufficient/partial/mastered/needs_review`。任一状态不得通过改写另一状态得到。

#### Scenario: 用户第一次打开有正文的节点

- **WHEN** 用户进入节点并产生开始学习事件
- **THEN** 阅读进度 MUST 为 in_progress
- **AND** 阅读进度 MUST NOT 自动变为 learned
- **AND** 掌握状态 MUST NOT 自动变为 mastered

#### Scenario: 用户明确完成阅读但未做正式检测

- **WHEN** 用户确认当前目标已经学完
- **THEN** 阅读进度 MUST 为 learned
- **AND** 掌握状态 MUST 为 evidence_insufficient 或 not_checked
- **AND** 系统 MUST 提供正式检测入口

### Requirement: 系统掌握必须来自当前有效检测证据

只有当前目标全部有效 MasteryCriterion 被正式检测验证时，系统 MAY 投影 mastered。自我确认、打开页面、停留时间和滚动到底 MUST NOT 单独产生系统掌握。

#### Scenario: 用户只勾选自我确认

- **WHEN** 用户确认自己理解一个掌握标准但没有正式检测通过
- **THEN** 系统 MUST 保存自我确认事实
- **AND** 掌握状态 MUST NOT 为 mastered

#### Scenario: 当前目标全部标准通过

- **WHEN** 当前目标修订绑定的全部有效标准均有通过的正式作答
- **THEN** 掌握状态 MUST 为 mastered
- **AND** 投影 MUST 返回支持该结论的事件与标准修订

### Requirement: 进度投影必须按用户和当前修订隔离

系统 MUST 按用户、课程和目标修订读取事件。其他用户或旧目标修订的事件 MUST NOT 改变当前投影。

#### Scenario: 课程目标更新

- **WHEN** 用户曾通过旧目标修订但当前目标修订已经变化
- **THEN** 当前目标 MUST NOT 继续显示 mastered
- **AND** 投影 MUST 标记存在历史证据

### Requirement: 旧完成状态只能降级迁移

旧 `completedNodes` 或 `is_read` 只代表不可靠的历史接触信号。迁移 MUST 幂等，且最多使当前阅读进度进入 in_progress，不得直接产生 learned 或 mastered。

#### Scenario: 旧版本因打开节点自动写入完成

- **WHEN** 用户升级后迁移旧完成节点
- **THEN** 系统 MUST 保存 legacy_node_completion_imported 事实
- **AND** 当前阅读进度 MUST NOT 因该事实变为 learned
- **AND** 掌握状态 MUST NOT 因该事实变为 mastered
