## MODIFIED Requirements

### Requirement: 后端 AI 链路必须通过教学决策层表达教学意图

系统 MUST 提供轻量 `TeachingDecision` 能力，把 `LearnerState` 中的事实证据和系统推断转换成结构化教学意图。教学决策层 MUST 不直接调用大模型，MUST 不替代学习者状态，MUST 输出可解释依据和保守置信度。旧导师建议、学习路径和前端主动建议 SHOULD 优先消费教学决策或由其派生的统一快照，不得各自生成互相竞争的主建议。

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

#### Scenario: 旧建议接口消费统一决策

- **WHEN** 客户端请求导师建议或学习状态
- **THEN** 后端 SHOULD 优先基于 `LearnerState` 和 `TeachingDecision` 返回主行动
- **AND** 旧导师记忆、目标、复习项和错题本 MAY 作为兼容补充
- **AND** 旧响应字段 MUST 保持可用

### Requirement: 前端学习建议必须统一来源

前端 MUST 把主动下一步学习建议统一到后端 `TeachingDecision` 或由其派生的统一学习洞察对象。旧统计、画像和 AI 助手组件 MUST NOT 各自用本地规则生成互相竞争的主建议。当前主行动 SHOULD 由导师行动卡承载，其他入口只展示摘要、依据或轨迹。

#### Scenario: 用户查看当前学习页

- **WHEN** 当前课程和节点存在学习状态或教学决策
- **THEN** 前端 SHOULD 只通过导师行动卡展示当前主建议
- **AND** 统计面板、画像面板和 AI 助手 MAY 展示同一建议的摘要或依据
- **AND** 这些组件 MUST NOT 生成另一套相互冲突的下一步行动

#### Scenario: 前端收到统一学习快照

- **WHEN** 后端响应包含 Learning OS 快照
- **THEN** 前端 SHOULD 优先使用快照中的洞察、证据亮点、薄弱点和风险
- **AND** 当前旧 `state`、`decision` 和 `suggestions` 字段 MUST 继续作为兼容输入

## ADDED Requirements

### Requirement: 后端必须提供统一 Learning OS 快照

系统 MUST 提供轻量 `LearningOSSnapshot` 读取模型，把学习者状态、教学决策、课程轨迹和旧导师记忆兼容信号组织成一个结构化响应。快照 MUST 使用现有文件存储和内存服务，不得引入重型数据库。快照 MUST 不替代事件账本、状态模型或决策层，而是作为服务层和前端的统一读契约。

#### Scenario: 构建课程节点快照

- **WHEN** 系统为指定 `course_id` 和 `node_id` 构建学习快照
- **THEN** 响应 MUST 包含 `state`、`decision`、`state_summary`、`decision_summary`
- **AND** 响应 SHOULD 包含可供前端直接使用的 `insights`
- **AND** 响应 SHOULD 包含课程级 `trajectory` 和旧导师 `legacy_signals`

#### Scenario: 旧学习状态接口保持兼容

- **WHEN** 客户端调用 `/api/tutor/learning-state`
- **THEN** 后端 MUST 继续返回 `state`、`decision`、`state_summary` 和 `decision_summary`
- **AND** 后端 SHOULD 附加 `snapshot`
- **AND** 旧客户端不得因为新增字段而失效

#### Scenario: 新统一快照接口

- **WHEN** 客户端调用 `/api/learning-os/snapshot`
- **THEN** 后端 MUST 返回统一快照结构
- **AND** 支持按课程和节点过滤

### Requirement: 测验结果必须能进入统一学习事件链路

前端本地测验结果 SHOULD 通过现有后端学习记录接口写入统一学习事件账本，使 `LearnerState` 和 `TeachingDecision` 能感知真实答题反馈。该写入 MUST 不阻断用户提交测验的本地体验；后端失败时前端 MAY 保留本地结果并提示或静默降级。

#### Scenario: 用户提交节点测验

- **WHEN** 用户在前端完成并提交某节点测验
- **THEN** 前端 SHOULD 保留本地测验历史和错题记录
- **AND** 前端 SHOULD 调用后端学习记录接口提交正确性、题目摘要、用户答案和课程节点信息
- **AND** 后端 SHOULD 写入 `learning_result_recorded` 事件并保留旧导师记忆更新

#### Scenario: 后端学习记录包含课程 ID

- **WHEN** 后端收到学习记录请求且包含 `course_id`
- **THEN** 写入的学习事件 SHOULD 关联该课程
- **AND** 旧未携带 `course_id` 的请求 MUST 继续可用
