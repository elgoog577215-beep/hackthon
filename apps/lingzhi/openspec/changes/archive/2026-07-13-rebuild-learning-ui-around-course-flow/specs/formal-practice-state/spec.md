## ADDED Requirements

### Requirement: 正式任务必须从正文引用进入统一覆盖层

每个正式练习、掌握检查、诊断、补救和独立复验 MUST 由正文中的稳定任务引用表达，点击后复用同一 `TaskOverlay` 和正式 Attempt/诊断状态。入口 MUST 显示开始、继续或查看结果，不得复制题目真源。

#### Scenario: 活动 Attempt 已有跨设备草稿

- **WHEN** 用户点击对应正文任务入口
- **THEN** 覆盖层 MUST 按 task_revision_id 恢复活动 Attempt 和服务端草稿
- **AND** MUST NOT 创建新 Attempt 或默认打开第一题

### Requirement: 任务覆盖层关闭后必须恢复来源现场

系统 MUST 在打开任务前保存来源课程块和语义滚动锚点；关闭、提交、评分或诊断阶段切换后 MUST 刷新运行时并返回来源块。恢复失败时 MUST 回退到来源节点而不是任意位置。

#### Scenario: 提交后进入诊断任务

- **WHEN** 当前 Attempt 失败并产生诊断任务
- **THEN** 同一覆盖层 MAY 继续诊断链，或关闭后让原任务入口显示下一诊断状态
- **AND** 正文位置、AI 任务上下文和正式结果 MUST 保持一致
