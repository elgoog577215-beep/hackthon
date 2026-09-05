## MODIFIED Requirements

### Requirement: 学习者上下文必须有统一后端聚合层

系统 MUST 通过只读 `LearnerModel` 聚合当前学习者的正式学习证据。模型 MUST 从 `LearningEvent`、`LearningSnapshot`、`LearningRecord`、`PracticeAttempt`、诊断和同批课程投影确定性重算；旧 AI profile、annotation、Learning OS、TutorMemory 和会话摘要 MUST NOT 成为模型输入或平行画像真源。

#### Scenario: AI 老师构造学习者上下文

- **WHEN** 当前问题确实需要判断学习状态
- **THEN** 系统 MUST 按当前目标读取最小 LearnerModel 证据、置信度、充分度和模型修订
- **AND** 普通课程解释 MUST NOT 默认加载完整学习历史

#### Scenario: 客户端请求旧画像接口

- **WHEN** 客户端调用已经退役的 `/api/profile/generate`
- **THEN** 生产服务 MUST NOT 生成或保存新的 AI 自由画像
- **AND** 当前学习概况 MUST 只读取正式 LearnerModel 与 LearningRuntime

### Requirement: 学习事件必须可聚合为学习者状态

系统 MUST 将正式学习事实确定性聚合为 `LearnerModel`。模型 MUST 区分阅读、正式掌握、用户自我报告和系统推断，并为结论返回证据引用、置信度、有效期和 `model_revision_id`；相同来源修订 MUST 产生相同模型修订。

#### Scenario: 从正式证据构建目标状态

- **WHEN** 系统读取指定学习者与课程的当前事实批次
- **THEN** 模型 MUST 返回目标级阅读、掌握、支持需求和证据充分度
- **AND** 一次失败、一次提问或页面停留 MUST NOT 自动形成稳定薄弱点

#### Scenario: AI 回答提出新判断

- **WHEN** AI 在对话中认为用户可能存在薄弱点
- **THEN** 该判断 MUST 保持为当次解释
- **AND** MUST NOT 直接写入 LearnerModel 或正式掌握状态

### Requirement: 后端 AI 链路必须通过教学决策层表达教学意图

系统 MUST 将当次回答讲法表示为受限 `teaching_guidance`，并与正式事实、LearnerModel 和 LearningRuntime 分离。讲法 MAY 根据用户本轮明确请求和中高置信正式证据选择简化、举例或补充练习；它 MUST NOT 持久化为学习者状态，也 MUST NOT 生成与运行时竞争的下一步。

#### Scenario: 用户本轮明确要求简化并举例

- **WHEN** 当前请求明确包含该要求
- **THEN** teaching guidance SHOULD 调整本次回答方式
- **AND** MUST NOT 因该表达写入稳定薄弱点或创建复习任务

#### Scenario: 只有一次正式失败

- **WHEN** LearnerModel 将支持需求标记为证据不足
- **THEN** teaching guidance MUST NOT 把目标当作稳定弱点
- **AND** AI MUST 使用有边界的语言说明不确定性

### Requirement: 前端必须展示可解释学习状态

前端 MUST 在现有学习工作区的“学习概况”覆盖层中展示正式阅读、掌握、模型充分度、当前目标、统一动作和证据计数，不得新增独立画像页。界面 MUST 区分正式事实、系统推断和证据不足，不得展示伪造总分、学习风格、最佳时段或由 localStorage 推断的稳定结论。

#### Scenario: 用户打开学习概况

- **WHEN** LearnerModel 只有有限证据
- **THEN** 界面 MUST 显示有限证据或低置信状态
- **AND** MUST 展示模型修订或可追溯依据
- **AND** MUST NOT 把阅读完成显示为已经掌握

### Requirement: 前端学习建议必须统一来源

前端 MUST 以 `LearningRuntime` 作为当前动作协调来源，以 LearnerModel 作为学习结论来源，以 teaching guidance 作为当次讲法来源。学习概况、AI 会话、本地 Store 和课程块 MUST NOT 各自生成下一步建议；普通状态不得恢复为正文顶部常驻横栏。

#### Scenario: 用户查看当前课程页

- **WHEN** LearningRuntime 返回当前动作
- **THEN** 学习概况 MAY 解释该动作
- **AND** AI MUST NOT 复制为另一张导师卡或建议横幅
- **AND** 目录、正文、练习、记录、图谱和 AI 仍保持并行入口

### Requirement: 前端智能入口必须分层展示

前端 MUST 保留两个主空间：正文学习现场与统一 AI 老师。正式学习事实通过正文记录、练习和学习概况呈现；AI 对话通过块级入口和按需全局入口呈现。旧独立画像页、导师卡、Learning OS 看板和第二 AI Store MUST 退出生产路径。

#### Scenario: 用户在学习页切换能力

- **WHEN** 用户打开学习概况或 AI 老师
- **THEN** 两者 MUST 读取同一学习者身份、模型修订和运行时事实
- **AND** 学习概况 MUST NOT 生成 AI 对话
- **AND** AI 老师 MUST NOT 保存平行画像或掌握状态

### Requirement: 测验结果必须能进入统一学习事件链路

正式测验结果 MUST 先保存为 `PracticeAttempt`，再追加关联 `LearningEvent` 并由 LearningProgress 与 LearnerModel 重算。浏览器本地测验历史 MAY 作为缓存，但 MUST NOT 替代正式 Attempt 或直接改变掌握状态。

#### Scenario: 用户提交正式练习

- **WHEN** 后端完成一次正式评分
- **THEN** 系统 MUST 保存带课程、节点、目标修订和评分结果的 PracticeAttempt
- **AND** MUST 以稳定操作 ID 追加关联 LearningEvent
- **AND** 重试 MUST NOT 产生第二次状态变化或重复事件

### Requirement: AI Learning OS 升级必须遵守统一主链路方法

系统新增或保留学习智能功能时，MUST 归入统一主链：`正式领域对象与 LearningEvent -> LearnerModel -> LearningRuntime -> AIContextPackage / 前端体验 -> 白名单领域命令 -> 新事实`。旧 LearnerState、TeachingDecision、LearningOSSnapshot、profile 和本地统计 MUST NOT 作为兼容主链继续存在。

#### Scenario: 评审新增学习功能

- **WHEN** 新增或改造学习功能
- **THEN** 方案 MUST 说明它读取哪些正式事实、是否改变 LearnerModel、用户在哪里感知，以及结果通过什么领域命令回写
- **AND** 不改变正式事实的 AI 输出 MUST 保持临时，不得为了闭环而伪造事件

### Requirement: 原型阶段用户身份必须通过 X-User-Id 贯通

前端 MUST 生成并持久化非共享的安装级匿名学习者 ID，所有正式学习领域请求 MUST 通过 `X-User-Id` 贯通。后端 MUST 拒绝缺失身份或共享 `default_user` 的个体读写；该 ID 仍不是登录鉴权，后续接入账号时必须完成可审计合并。

#### Scenario: 请求携带有效 X-User-Id

- **WHEN** 客户端请求学习事实、模型、运行时、练习、记录或 AI 个性化能力
- **THEN** 后端 MUST 使用该身份隔离所有来源与投影
- **AND** 其他学习者的数据 MUST NOT 进入当前模型或 AI 上下文

#### Scenario: 请求未携带有效身份

- **WHEN** 客户端调用正式学习接口但缺失 `X-User-Id` 或值为 `default_user`
- **THEN** 后端 MUST 返回稳定身份错误
- **AND** MUST NOT 读取或写入共享个体数据

### Requirement: AI 输出质量事件必须回流课程质量报告

课程生成输出 MUST 经过确定性质量检查，但检查结果属于课程生产与课程质量领域，MUST NOT 作为学习者 `LearningEvent` 写入。课程质量报告 MAY 读取生成日志、工作区质量结果或后续正式 `CourseQualityIssue`，不得通过污染学习事实账本获得输入。

#### Scenario: 课程输出未通过质量检查

- **WHEN** 生成正文为空、过短、结构缺失或包含待核验来源表述
- **THEN** 生成流程 MUST 记录质量问题并阻止或限制发布
- **AND** LearnerModel 的事件数量、薄弱点和模型修订 MUST NOT 因该检查变化

## REMOVED Requirements

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
