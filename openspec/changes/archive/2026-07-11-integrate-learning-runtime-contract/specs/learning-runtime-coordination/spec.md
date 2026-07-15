# learning-runtime-coordination Specification

## ADDED Requirements

### Requirement: 前六步必须共享稳定身份契约

系统 MUST 使用统一课程版本、目标修订、任务修订和内容锚点字段连接学习现场、进度、记录、练习、诊断和章节连续性；新写入 MUST 以 `task_revision_id` 为正式任务修订字段。

#### Scenario: 正式练习形成学习事件

- **WHEN** 当前 Attempt 被创建、提交或评分
- **THEN** 事件顶层 MUST 保存 task_revision_id、task_purpose 和目标修订
- **AND** question_revision_id MUST 只作为兼容别名

### Requirement: 学习运行时必须聚合同一批输入

系统 MUST 在一次运行时读取中加载事件、快照、记录、Attempt 和诊断工作流，并用同一批输入构建进度与章节连续性；MUST NOT 保存第二份运行时状态。

#### Scenario: 作答同时改变掌握与下一步

- **WHEN** 正式 Attempt 完成评分并形成新的诊断阶段
- **THEN** 同一运行时响应中的 progress、diagnostic、active_task 和 continuation MUST 相互一致
- **AND** revision_vector MUST 反映所有发生变化的来源

### Requirement: 掌握清单必须读取正式 Attempt 投影

掌握清单 MUST 从统一学习进度中的标准状态投影，不得只读取旧 `formal_question_answered` 事件。

#### Scenario: 当前标准已有独立通过 Attempt

- **WHEN** 当前题目、目标和标准修订绑定一致的 Attempt 独立通过
- **THEN** 目标进度和掌握清单 MUST 同时显示 system_verified

### Requirement: 写操作后必须确定性刷新运行时

前端 MUST 在明确阅读、学习记录、Attempt、诊断或课程版本发生语义变化后主动刷新 LearningRuntime；MUST NOT 依赖组件监听内部数组猜测变化。

#### Scenario: 用户解决阻塞问题

- **WHEN** issue 状态从 open 更新为 resolved
- **THEN** 前端 MUST 主动刷新运行时
- **AND** 旧的 resolve_blocking_issue 动作 MUST NOT 继续显示

### Requirement: 快照必须保存统一任务引用

学习快照 MUST 使用 LearningTaskRef 保存当前恢复指针，普通练习、诊断、补救和独立复验 MUST 使用同一结构；快照 MUST NOT 复制业务对象状态。

#### Scenario: 用户开始普通正式练习后刷新

- **WHEN** Attempt 已创建且仍为 in_progress
- **THEN** 快照 task_ref MUST 指向该 Attempt 和 task_revision_id
- **AND** 运行时 active_task MUST 与 Attempt 真源一致

### Requirement: 连续性动作必须精确恢复目标任务

前端 MUST 按 NextLearningAction.task_ref 精确定位 Attempt 或诊断任务；MUST NOT 只打开通用练习页并默认选择第一题。

#### Scenario: 第二道题存在未提交草稿

- **WHEN** 主要动作指向第二道题的 active Attempt
- **THEN** 练习工作区 MUST 选中该 Attempt 对应任务并恢复其草稿
- **AND** MUST NOT 自动创建或打开第一道题的新 Attempt

### Requirement: 课程版本变化必须触发六步统一重算

课程版本变化后，系统 MUST 重新解析快照位置、当前目标、正式任务有效性、诊断有效性和章节连续性，并保留旧对象作为历史。

#### Scenario: 恢复历史版本创建新课程版本

- **WHEN** 新课程版本成为 current
- **THEN** 前端 MUST 先刷新课程再加载快照与 LearningRuntime
- **AND** 旧版本活动任务 MUST 显示版本冲突或失效，不得静默继续

### Requirement: 旧字段只能作为读取兼容

历史 question_revision_id、旧快照 task_state 和旧正式作答事件 MUST 可读取；新路径 MUST NOT 再将其作为唯一字段或实时真源。

#### Scenario: 历史 Attempt 只有 question_revision_id

- **WHEN** 系统读取旧 Attempt
- **THEN** 归一化任务引用 MUST 回退到 question_revision_id
- **AND** 后续新事件 MUST 写入正式 task_revision_id
