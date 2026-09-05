## MODIFIED Requirements

### Requirement: 前端问答必须默认使用结构化事件协议

前端主问答流程 MUST 使用结构化 SSE 事件处理回答正文、最终答案、来源、提案、回执和错误。旧 `/api/ask` MAY 保留只读兼容；前端 MUST NOT 从正文分隔符猜测 metadata，也不得根据 metadata 自动创建 AI 笔记。

#### Scenario: 用户在课程页向 AI 老师提问

- **WHEN** 前端提交带稳定上下文引用的 AI 请求
- **THEN** 客户端 MUST 用 answer 事件增量展示当前回答
- **AND** MUST 用 final_answer 和 sources 事件固定最终正文与引用
- **AND** 只有 proposal 事件通过结构校验后才能展示正式动作

#### Scenario: metadata 或来源事件缺失

- **WHEN** 问答流没有返回有效 metadata 或来源
- **THEN** 前端 MUST 继续展示已收到的回答正文
- **AND** MUST 标记引用不可用
- **AND** MUST NOT 自动创建笔记、问题或其他学习记录

### Requirement: 后端 AI 链路必须通过教学决策层表达教学意图

系统 MUST 将当前回答的教学策略与当前学习下一步分开。教学策略 MAY 根据用户本轮请求和可靠证据选择直接解释、简化、举例、追问或分步推导；唯一下一步 MUST 来自 `LearningRuntime`。教学策略 MUST NOT 根据旧导师记忆、提问次数、停留时间或低置信弱点生成正式主行动。

#### Scenario: 用户本轮明确表示困惑

- **WHEN** 当前请求明确要求更慢、更具体或增加例子
- **THEN** 教学策略 SHOULD 调整本次回答方式
- **AND** MUST NOT 因该表达直接写入稳定薄弱点或创建复习任务

#### Scenario: 证据不足

- **GIVEN** 当前没有正式阻塞或可靠主动触发证据
- **WHEN** 系统构建教学策略
- **THEN** 系统 MUST 允许直接回答且不生成主动建议
- **AND** MUST NOT 强制补充“直接解释并给出下一步”等导师动作

#### Scenario: 用户询问下一步

- **WHEN** AI 需要解释当前学习行动
- **THEN** MUST 使用 LearningRuntime primary action
- **AND** 旧 tutor suggestion、TeachingDecision action 和 Learning OS legacy signal MUST NOT 参与竞争

### Requirement: 后端必须提供统一 AI Learning Context 编排层

系统 MUST 通过 `AIContextPackage` 编排当前请求、版本化学习现场、`LearningRuntime`、正式任务、定向课程片段、必要学习证据、会话摘要和权限策略。该层 MUST 同时提供结构化对象和受预算约束的 prompt 表达；MUST NOT 默认组合旧 TutorMemory、全部 LearnerContext、整门课程和全部笔记。

#### Scenario: AI 助手读取统一上下文

- **WHEN** AI 老师构造问答 prompt
- **THEN** 上下文 MUST 包含当前课程版本、节点、目标修订和 runtime_revision_id
- **AND** SHOULD 按用户意图选择少量课程来源与学习证据
- **AND** MUST 包含当前动作权限和答案披露策略

#### Scenario: 课程内容生成读取上下文

- **WHEN** `CourseService` 创建基础课程蓝图或初始正文
- **THEN** prompt MUST 只读取生成请求、资料证据、教学画像和持久化蓝图契约
- **AND** MUST NOT 读取动态 AI 会话、动作提案或个人学习运行时

### Requirement: 旧记忆、状态和决策必须有清晰边界

系统 MUST 明确以下职责：`LearningEvent` 保存发生过的学习事实，正式领域仓库保存当前对象，学习者模型生成可追溯投影，`LearningRuntime` 聚合当前现场和唯一下一步，AI 会话保存对话，`AIContextPackage` 只做单次装配。`TutorMemory`、AI 专属画像和本地 session memory MUST NOT 作为实时真源。

#### Scenario: 读取长期学习信息

- **WHEN** AI 回答需要长期偏好或稳定学习结论
- **THEN** 教学偏好 MUST 来自用户设置
- **AND** 掌握与错因 MUST 来自正式学习者模型和已确认诊断
- **AND** MUST NOT 从旧 tutor_memory 或会话摘要生成稳定结论

#### Scenario: 删除 AI 会话

- **WHEN** 用户删除 AI 会话
- **THEN** 会话消息和仅由其生成的摘要 MUST 删除
- **AND** 正式 LearningEvent、LearningRecord、PracticeAttempt 和已执行动作回执 MUST 保留

### Requirement: 前端必须提供低打扰 AI 导师行动卡片

前端 MUST 将旧页面级导师行动卡退出生产路径。低打扰主动帮助只能进入统一 AI 入口或相关上下文中的单一提案；`LearningContinuityBar` 继续拥有唯一全局主要动作，AI 不得重复展示同一动作。

#### Scenario: 系统没有强触发证据

- **WHEN** 当前只有少量一般学习证据且没有正式阻塞
- **THEN** 页面 MUST 不展示导师行动卡或建议横幅
- **AND** 用户 MUST 能通过统一 AI 入口主动提问

#### Scenario: 系统存在可靠主动候选

- **WHEN** TriggerCandidate 通过证据、去重和冷却校验
- **THEN** 前端 MAY 在 AI 入口显示状态点或在相关上下文展示一个提案
- **AND** MUST 不增加第二个全局主要动作

### Requirement: 前端学习建议必须统一来源

前端 MUST 以 `LearningRuntime` 作为当前主要学习动作来源，以 TriggerCandidate 作为可选主动帮助来源，以当前回答教学策略作为讲法来源。统计、画像、AI 会话和本地 Store MUST NOT 各自生成下一步建议。

#### Scenario: 用户查看当前课程页

- **WHEN** LearningRuntime 返回 primary action
- **THEN** LearningContinuityBar MUST 展示该唯一主要动作
- **AND** AI MAY 解释该动作但 MUST NOT 复制为另一张导师卡

#### Scenario: 旧学习洞察仍包含导师动作

- **WHEN** 兼容响应包含 TeachingDecision actions、旧 suggestions 或 legacy_signals
- **THEN** 新前端 MUST 忽略这些字段的主行动语义
- **AND** 迁移完成后后端 MUST 停止返回这些实时兼容信号
