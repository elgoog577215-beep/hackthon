## ADDED Requirements

### Requirement: AI Learning OS 升级必须遵守统一主链路方法

系统新增或保留任何学习智能功能时，MUST 将其归入统一主链路：`LearningEvent -> LearnerState -> TeachingDecision -> LearningOSSnapshot / AI Learning Context -> AI/前端体验 -> 结果回写 LearningEvent`。功能不得绕开该链路另起一套状态、建议、画像或主行动判断。旧链路 MAY 保留为兼容包装或 legacy signals，但 SHOULD 逐步消费新主链路。

#### Scenario: 评审新增学习功能

- **WHEN** 新增或改造学习功能
- **THEN** 方案 MUST 说明该功能收集什么学习证据
- **AND** MUST 说明如何影响学习者状态或为什么不影响状态
- **AND** MUST 说明是否触发教学决策
- **AND** MUST 说明用户在哪里感知到智能增强
- **AND** MUST 说明结果如何回写闭环

#### Scenario: 发现旧功能与新链路重复

- **WHEN** 旧功能独立生成薄弱点、掌握度、学习建议或画像判断
- **THEN** 系统 SHOULD 优先让旧功能消费 `LearnerState`、`TeachingDecision` 或 `LearningOSSnapshot`
- **AND** 若旧接口仍被前端或测试使用，MUST 保持响应兼容
- **AND** 不得新增另一套平行的主建议来源

### Requirement: 九阶段升级必须以连续归一化方式推进

系统演进 MUST 将九个阶段视为同一条 AI Learning OS 主链路的连续落点，而不是九个孤立功能。前半段 SHOULD 优先完成主链路归一化，后半段 SHOULD 优先做旧链路收敛、质量评估、体验打磨和长期智能结构预留。

#### Scenario: 执行阶段性改造

- **WHEN** 执行任一阶段
- **THEN** 改造 SHOULD 尽量复用旧系统已有价值
- **AND** SHOULD 合并重复入口
- **AND** MUST 避免无验证的大范围重构
- **AND** MUST 保持旧接口兼容或明确迁移边界

#### Scenario: 前端出现多个相似智能入口

- **WHEN** 学习画像、学习统计、AI 助手、导师卡或课程 block 同时展示学习智能信息
- **THEN** 前端 MUST 按行动、解释、轨迹、对话和内容操作分层
- **AND** 主动下一步行动 SHOULD 由导师行动卡承载
- **AND** 其他入口 MUST 展示同一套状态/决策的不同侧面，不得互相竞争

### Requirement: 复习和课程 block 操作必须进入学习证据闭环

复习提交、内容 block 简化、扩展、补例子、练习、问 AI 和重写请求 MUST 写入统一学习事件账本。事件 SHOULD 包含课程、节点、block、动作类型、用户要求、结果摘要和来源，以便后续 `LearnerState`、`TeachingDecision` 和质量评估使用。

#### Scenario: 用户提交复习结果

- **WHEN** 客户端调用 `/courses/{course_id}/review/submit`
- **THEN** 后端 SHOULD 为每个复习结果写入结构化学习事件
- **AND** 事件 SHOULD 记录质量评分、是否通过、下一次复习计划和 SM-2 结果摘要
- **AND** 原有复习响应 MUST 保持兼容

#### Scenario: 用户操作内容 block

- **WHEN** 用户对课程内容 block 执行简化、扩展、补例子、练习、问 AI 或重写
- **THEN** 系统 SHOULD 记录 block 操作事件
- **AND** 后续状态和决策 MAY 使用这些事件判断学习偏好、困惑点和内容质量问题
