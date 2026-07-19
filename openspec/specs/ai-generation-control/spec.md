# ai-generation-control Specification

## Purpose
定义课程生成、课程内容操作、学习上下文、导师决策与前端智能体验的统一生产协议，确保 AI 能力可恢复、可解释、可验证，并且不会形成彼此竞争的旧新链路。
## Requirements
### Requirement: 课程生成必须使用上下文账本

课程正文生成 MUST 注入课程上下文账本，账本至少包含课程目标、前置知识、本节学习目标、范围边界、误区、验收标准、已完成前置内容摘要和已出现概念。

#### Scenario: 从课程蓝图创建账本
- **WHEN** 课程大纲生成完成
- **THEN** 系统 MUST 从大纲中的章节和小节字段创建课程上下文账本
- **AND** 每个小节的 `learning_objective`、`prerequisite_node_ids`、`misconceptions`、`assessment`、`scope_boundary` MUST 可供正文生成读取

#### Scenario: 正文生成更新账本
- **WHEN** 一个小节正文生成完成并经过修复
- **THEN** 系统 MUST 用最终正文更新该节点摘要和概念索引

### Requirement: 节点调度必须尊重前置依赖

正文生成调度 MUST 优先生成无依赖或依赖已满足的节点，仍允许同一波次的无依赖节点并发。

#### Scenario: 节点声明前置依赖
- **GIVEN** 节点 B 声明依赖节点 A
- **WHEN** A 和 B 都待生成
- **THEN** 系统 MUST 先生成 A，再生成 B

#### Scenario: 依赖无效或形成循环
- **GIVEN** 模型输出了不存在或循环的依赖
- **WHEN** 调度器无法找到可推进节点
- **THEN** 系统 MUST 按原始顺序退化生成，避免任务卡死

### Requirement: 流式生成必须区分草稿和最终稿

系统 MUST 保留实时草稿 chunk 推送，并在最终内容确定后推送独立 final 事件。

#### Scenario: 流式生成结束后内容被修复
- **WHEN** 草稿流结束后质量检查或 LaTeX 修复改变了正文
- **THEN** 系统 MUST 推送 `node_finalized` 事件
- **AND** 事件 payload MUST 包含最终 `node_content`

### Requirement: 问答 metadata 必须支持结构化事件流

系统 MUST 提供结构化问答事件流接口，将回答正文和 metadata 拆成不同事件。

#### Scenario: 客户端请求结构化问答流
- **WHEN** 客户端调用 `/api/ask_events`
- **THEN** 服务端 MUST 返回 `text/event-stream`
- **AND** 回答正文 MUST 通过 `answer` 或 `final_answer` 事件返回
- **AND** metadata MUST 通过 `metadata` 事件返回

### Requirement: 课程生成入口必须使用统一课程服务和唯一任务

课程生成主入口 MUST 通过唯一 `GenerationJob` 调用 `CourseService` 的资料增强生成链路，不能再使用旧 `AIService/AICourseService`、旧 prompt 或第二阶段正文启动接口。

#### Scenario: 用户创建新课程

- **WHEN** 客户端调用 `/api/course-generation/generate`
- **THEN** 服务端 MUST 创建课程草稿和唯一 `GenerationJob`
- **AND** 响应 MUST 以 `202` 返回 `course_id`、`course_name`、`job_id` 和任务状态
- **AND** brief、资料、教学画像、蓝图、正文、质量检查和保存 MUST 在同一任务内继续
- **AND** 系统 MUST NOT 提供第二阶段 `/auto_generate` 启动接口
- **AND** 旧 `/api/generate_course` MUST NOT 作为课程生成入口继续提供

### Requirement: 课程节点必须携带蓝图契约字段

课程生成返回的 L2 节点 MUST 携带后续正文生成所需的蓝图契约字段。

#### Scenario: 课程蓝图包含小节契约

- **WHEN** `/api/course-generation/generate` 返回 L2 节点
- **THEN** 每个 L2 节点 SHOULD 包含 `learning_objective`
- **AND** SHOULD 包含 `prerequisite_node_ids`
- **AND** SHOULD 包含 `misconceptions`
- **AND** SHOULD 包含 `assessment`
- **AND** SHOULD 包含 `scope_boundary`

### Requirement: 子节点生成接口必须与后台生成使用同一课程服务

手动子节点生成接口 MUST 使用 `CourseService.generate_sub_nodes`，与后台自动生成链路保持一致。

#### Scenario: 用户手动补充子节点

- **WHEN** 客户端调用 `/api/courses/{course_id}/nodes/{node_id}/subnodes`
- **THEN** 服务端 MUST 使用 `CourseService.generate_sub_nodes`
- **AND** 已有子节点时 MUST 直接返回已有子节点，不重复生成

### Requirement: 课程正文必须支持结构化内容块

课程小节正文 MUST 以完整 `node_content` Markdown 作为主内容本体。系统 MUST NOT 要求后台生成、保存或展示固定教学块来表达正文结构。`content_blocks` MAY 作为旧数据和旧接口兼容字段保留，但 MUST NOT 覆盖 Markdown 的学科章法、标题结构和阅读形态。

#### Scenario: 新正文生成完成

- **WHEN** 小节正文生成完成
- **THEN** 系统 MUST 保存最终 Markdown 到 `node_content`
- **AND** 系统 MUST NOT 为了生成主链路把正文强制拆成固定 `content_blocks`
- **AND** 前端 MUST 优先按 Markdown 文档渲染正文

#### Scenario: 旧节点包含 content_blocks

- **WHEN** 前端或接口读取旧节点
- **THEN** 系统 MUST 继续兼容 `content_blocks`
- **AND** 前端 SHOULD 不再将 `content_blocks` 作为默认正文阅读形态
- **AND** 后端 MAY 在旧 block 级接口中使用 `content_blocks` 完成兼容操作

### Requirement: 课程内容操作必须使用统一课程服务

节点重写、节点扩展、节点摘要和课程内定位 MUST 通过 `CourseService` 执行。旧 `AICourseService` 和 `AICourseServiceV5` MUST NOT 作为后端可调用服务保留；课程 AI 能力的生产入口只允许落在 `CourseService`。

#### Scenario: 用户重写整个节点

- **WHEN** 客户端调用 `/api/courses/{course_id}/nodes/{node_id}/redefine`
- **THEN** 服务端 MUST 使用 `CourseService` 构造课程上下文、节点契约和用户要求
- **AND** 返回值 MUST 保持兼容，包含 `node_content`
- **AND** 节点的 `content_blocks` MUST 与最终 `node_content` 同步

#### Scenario: 用户扩展节点内容

- **WHEN** 客户端调用 `/api/courses/{course_id}/nodes/{node_id}/extend`
- **THEN** 服务端 MUST 使用 `CourseService` 生成与课程上下文一致的补充内容
- **AND** 响应 MUST 保持现有 `content` 字段

#### Scenario: 后端初始化 AI 门面

- **WHEN** `ai_service` 模块被导入
- **THEN** `AIService` MUST NOT 继承或导入旧课程生成服务
- **AND** quiz、QA、graph、learning、diagram、profile 能力 MUST 保持可用

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

### Requirement: 学习行为必须写入统一事件账本

系统 MUST 提供轻量学习事件账本，把关键学习行为记录为结构化 `LearningEvent`。事件账本 MUST 使用现有文件存储能力，MUST 支持后续学习者状态模型和教学决策层查询，不得只保存不可分析的散文日志。

#### Scenario: 保存学习事件

- **WHEN** 后端记录一次学习行为
- **THEN** 系统 MUST 写入包含事件 ID、事件类型、用户、课程、节点、来源、证据、结果、元数据和时间戳的事件
- **AND** 事件 MUST 可按用户、课程、节点和事件类型过滤读取

#### Scenario: AI 问答产生事件

- **WHEN** 用户通过 `/api/ask` 或 `/api/ask_events` 提问
- **THEN** 系统 SHOULD 记录用户提问事件
- **AND** 当 AI 流式回答结束时 SHOULD 记录 AI 回答完成事件
- **AND** 不得改变现有问答响应协议

#### Scenario: 标注保存产生事件

- **WHEN** 用户或 AI 保存标注、笔记、错题或格式问题
- **THEN** 系统 SHOULD 记录对应的标注保存事件
- **AND** 事件 SHOULD 关联 `anno_id`、`source_type`、`course_id` 和 `node_id`

#### Scenario: 学习结果产生事件

- **WHEN** 导师学习记录接口收到答题正确性、耗时或题目信息
- **THEN** 系统 SHOULD 记录学习结果事件
- **AND** 事件 SHOULD 保留正确性、耗时、题目摘要和导师记忆更新后的掌握度结果

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

### Requirement: 前端必须提供可折叠的 Markdown 课程文档体验

前端 MUST 将完整 `node_content` Markdown 作为课程正文真源，并按标题层级提供折叠阅读。课程内容操作 MUST 进入统一 AI 助手或课程内容接口，不得在文档组件内维护第二套选区 AI 面板。

#### Scenario: 用户阅读或操作课程正文

- **WHEN** 用户在课程内容区查看 Markdown 文档
- **THEN** 前端 SHOULD 按标题层级提供折叠状态
- **AND** 用户 SHOULD 能通过统一入口执行简化、扩展、补例子、生成练习、重写或问 AI
- **AND** 旧 `content_blocks` MAY 读取兼容，但 MUST NOT 成为默认正文真源

### Requirement: 前端必须展示可解释学习状态

前端 MUST 在现有学习工作区的“学习概况”覆盖层中展示正式阅读、掌握、模型充分度、当前目标、统一动作和证据计数，不得新增独立画像页。界面 MUST 区分正式事实、系统推断和证据不足，不得展示伪造总分、学习风格、最佳时段或由 localStorage 推断的稳定结论。

#### Scenario: 用户打开学习概况

- **WHEN** LearnerModel 只有有限证据
- **THEN** 界面 MUST 显示有限证据或低置信状态
- **AND** MUST 展示模型修订或可追溯依据
- **AND** MUST NOT 把阅读完成显示为已经掌握

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

### Requirement: 系统必须支持 Markdown 选区级 AI 修改

系统 MUST 支持用户选中 Markdown 正文中的任意文字后请求 AI 局部修改。选区修改 MUST 基于选中文本、标题路径、前后文、课程/节点上下文和用户要求生成候选替换文本，并 MUST 保持当前学科章法。

#### Scenario: 用户选中文字发起改写

- **WHEN** 客户端提交选中文本、标题路径、前后文、节点正文和用户要求
- **THEN** 后端 MUST 使用 `CourseService` 构造选区修改上下文
- **AND** prompt SHOULD 包含课程账本、节点契约、AI Learning Context 和选区上下文
- **AND** 后端 MUST 返回候选替换文本
- **AND** 后端 MUST NOT 直接保存节点正文

#### Scenario: 用户确认候选修改

- **WHEN** 用户接受 AI 候选替换文本
- **THEN** 前端 MUST 只替换原 Markdown 中对应选区
- **AND** 前端 MUST 保存更新后的完整 `node_content`
- **AND** 若选区无法唯一定位，前端 MUST 避免静默替换错误位置

### Requirement: 前端必须提供文档式标题树和折叠体验

前端 MUST 从 Markdown 标题临时解析父子标题树，并在阅读界面展示类似文档编辑器的层级、缩进和折叠控制。该结构 MUST 只作为 UI 索引，不得改变后端正文存储格式。

#### Scenario: Markdown 包含多级标题

- **WHEN** 节点正文包含 `#`、`##`、`###` 等标题
- **THEN** 前端 SHOULD 构造父子标题树
- **AND** 前端 SHOULD 在正文中提供标题折叠控制
- **AND** 折叠状态 MUST NOT 修改 `node_content`

#### Scenario: 用户选中正文

- **WHEN** 用户在正文中选中一段文字
- **THEN** 前端 SHOULD 显示轻量浮动工具条
- **AND** 工具条 SHOULD 提供改写、简化、补例子、出题、问 AI 等操作
- **AND** 工具条 MUST 不把整篇正文改造成卡片列表

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

### Requirement: AI 能力必须消费统一学习上下文

答疑、节点重写、内容补救、复习建议和课程迭代相关 AI 能力 MUST 通过 `build_ai_learning_context` 获取学习者上下文。模块自己的业务输入 MAY 作为显式参数或 `request_context` 进入该统一上下文，但 MUST NOT 新增平行画像、平行记忆或平行 Agent。

#### Scenario: 节点重写构造 prompt

- **WHEN** 用户请求重写节点、改写选区、扩展内容或摘要节点
- **THEN** 后端 MUST 通过 `CourseService._ai_learning_context_prompt` 调用 `build_ai_learning_context`
- **AND** prompt MUST 使用同一份学习状态解释
- **AND** 节点内容、选中文本、重写要求或补救要求 MUST 作为业务输入进入统一上下文

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

### Requirement: TaskManager 必须只负责任务生命周期与调度

`TaskManager` MUST 负责 GenerationJob 生命周期、阶段、并发、暂停、恢复、重试、取消、检查点和事件推送；prompt、教学画像和质量规则 MUST 由对应课程服务组件负责。

#### Scenario: 节点正文生成完成

- **WHEN** `_process_node` 收集到最终正文
- **THEN** 后端 MUST 保存 `node_content`、`generation_status`、`generated_chars`、质量结果和错误摘要
- **AND** MUST 推送 `node_finalized`、`node_completed` 和任务阶段进度
- **AND** 任务查询、WebSocket 和前端本地引用 MUST 使用同一个 `job_id`

### Requirement: 模型路由必须保持低成本默认

普通节点正文流式生成 MUST 继续使用当前默认模型路由。课程大纲、弱点补救、质量修复和课程迭代建议 MAY 使用更强模型或 `enable_thinking`，但 MUST NOT 全局打开 thinking，也 MUST NOT 引入新的 provider 抽象。

#### Scenario: 普通节点正文生成

- **WHEN** 系统执行普通节点正文流式生成
- **THEN** MUST 沿用当前默认模型配置
- **AND** MUST NOT 因本次改造全局启用 thinking

#### Scenario: 高价值规划或修复环节

- **WHEN** 系统执行课程大纲、节点重写、弱点补救或质量修复
- **THEN** 后端 MAY 通过现有 `AIBase` 参数启用更强模型路径或 thinking
- **AND** API key 缺失时 MUST 继续保持现有降级行为

### Requirement: 课程生成必须使用唯一可恢复任务

系统 MUST 为一次课程生成或局部再生成创建唯一 `GenerationJob`。brief、资料解析、证据编译、教学画像、难度契约、覆盖计划、蓝图、可选蓝图等待、正文、学习资产、质量检查、候选版本和最终保存 MUST 使用同一任务模型与 TaskManager；前端 MUST NOT 创建独立任务身份或调用第二阶段生成入口。

#### Scenario: 历史快速模式请求

- **WHEN** 客户端提交 `generation_mode=fast`
- **THEN** 服务端 MUST 创建唯一 GenerationJob 并立即返回 job_id/course_id
- **AND** 服务端 MUST 将历史值归一为唯一的 `review_blueprint` 产品路径
- **AND** 任务 MUST 在目录与发布处等待确认，MUST NOT 绕过目录审阅

#### Scenario: 唯一课程生产路径

- **WHEN** 客户端提交 `generation_mode=review_blueprint`
- **THEN** 同一任务 MUST 在目录完成后进入 `waiting_for_review`
- **AND** 用户确认目录后 MUST 在同一 job_id 自动完成教案、正文和学习资产
- **AND** 最终只在发布处再次等待确认

#### Scenario: 局部再生成

- **WHEN** 用户确认影响报告并更新受影响内容
- **THEN** 系统 MUST 使用同一 GenerationJob 模型创建候选工作区
- **AND** MUST 只调度受影响节点和资产
- **AND** 失败候选 MUST NOT 覆盖当前课程版本

### Requirement: 课程生成必须形成教学画像

系统 MUST 在生成课程蓝图前形成 `SubjectPedagogyProfile`。实际主模式 MUST 是八种已注册教学模式之一，辅模式最多一个；`auto` MUST NOT 作为最终主模式保存。
教学画像 MUST 由用户显式选择或确定性规则直接编译，MUST NOT 为自动模式增加独立
模型分类调用或目录前的额外网络故障点。

#### Scenario: 自动识别教学模式

- **WHEN** 用户选择自动模式
- **THEN** 系统 MUST 综合最终成果、主要学习行为、资料结构和课程主题
- **AND** MUST 输出主模式、可选辅模式、辅助强度、置信度、证据和判断理由
- **AND** 低置信度 MUST 回退通用课程而不是自然科学
- **AND** MUST NOT 调用模型重新判断确定性结果

#### Scenario: 用户手动指定模式

- **WHEN** 用户提交明确的教学模式
- **THEN** 系统 MUST 锁定该主模式
- **AND** 后续蓝图、正文或重新生成 MUST NOT 自动覆盖它

### Requirement: 学科结构必须由教学模块组合

系统 MUST 使用通用骨架、主模式模块包和可选辅模式注入生成课程结构。模块 MUST 表达教学产出和检查标准，不得要求所有模块成为固定 Markdown 标题。存在资料时，结构生成 MUST 先消费 EvidenceCoveragePlan，不能直接从资料摘要猜测覆盖关系。

#### Scenario: 生成课程蓝图

- **WHEN** brief、证据目录、EvidenceCoveragePlan 和教学画像准备完成
- **THEN** CourseBlueprint MUST 保存教学画像和课程级模块计划
- **AND** 每个正文节点 MUST 保存自己的 `module_plan` 和 `grounding_contract`
- **AND** 主模式 MUST 决定课程顺序和最终考核
- **AND** 辅模式模块 MUST 去重并在依赖它的主任务之前出现
- **AND** 资料引用 MUST 通过有效 EvidenceUnit ID 表达

### Requirement: 正文必须读取持久化蓝图契约

节点正文 MUST 读取持久化请求、brief、教学画像、难度契约、节点范围、模块计划和 `NodeGroundingContract`。系统 MUST NOT 在节点级根据标题重新猜学科，也 MUST NOT 依赖进程内缓存、全量资料摘要或默认资料广播作为唯一上下文。

#### Scenario: 生成或恢复某个节点

- **WHEN** TaskManager 调用节点正文生成
- **THEN** prompt MUST 包含节点目标、范围、证据包、知识点、误区、验收标准、模块产出和难度要求
- **AND** 资料事实 MUST 使用当前 grounding contract 允许的来源标记
- **AND** 输出 MUST 保存为完整 Markdown `node_content`
- **AND** 来源映射 MUST 独立保存为 `grounding_annotations`
- **AND** 动态学习者状态 MUST NOT 改写基础课程的蓝图或正文主线

### Requirement: 任务必须支持多课程并发和真实暂停

任务消费者 MUST 能同时推进多门课程，并使用全局并发限制保护模型调用。暂停 MUST 停止新节点并取消当前调用，已接收草稿 MUST 保存为检查点。

#### Scenario: 两门课程同时排队

- **WHEN** 两个 GenerationJob 均处于 pending
- **THEN** 调度器 SHOULD 在课程并发上限内同时推进它们
- **AND** 节点调用总数 MUST 不超过全局并发上限

#### Scenario: 用户暂停并继续任务

- **WHEN** 用户暂停运行中的任务
- **THEN** 系统 MUST 停止任务继续消耗模型调用
- **AND** MUST 保存当前节点草稿和已完成节点
- **WHEN** 用户继续任务
- **THEN** 系统 MUST 从检查点和未完成节点继续

### Requirement: 质量报告必须由分层质量闸门产生

系统 MUST 分别检查教学画像、难度画像、资料解析、证据覆盖、蓝图、难度曲线、节点正文和学习资产。最终 GenerationQualityReport MUST 聚合节点与 AssetQualityReport，并在候选版本全部完成后产生。

#### Scenario: 课程候选完成

- **WHEN** 正文与资产生成结束
- **THEN** 最终报告 MUST 包含节点质量、资料接地、难度对齐、资产覆盖、资产失败和锁定冲突
- **AND** 必选资产硬失败 MUST 阻止候选成为当前版本
- **AND** 任务进度 MUST 准确反映资产生成与验证阶段

### Requirement: 旧课程只能通过读取适配器兼容

旧学科值、缺失的难度契约和 `content_blocks` MAY 在读取旧课程时被适配，但新请求、新教学画像、新难度画像、新蓝图和新正文生成 MUST NOT 写入旧学科值、自由 `complexity` 或依赖旧固定板块。

#### Scenario: 打开旧课程并继续生成

- **WHEN** 课程只保存旧难度标签或节点 `complexity`
- **THEN** 系统 MUST 根据课程难度、教学画像和节点位置恢复最小难度契约
- **AND** MUST 使用新难度编译器继续生成
- **AND** MUST NOT 重新启用旧 prompt 或旧难度映射

### Requirement: 无资料和无法解析资料必须诚实降级

系统 MUST 支持无资料生成。无法解析或只能降级提取的资料 MUST 保存真实状态，不得标记为完整解析、不得伪造 EvidenceUnit，也不得把文件名或用户说明当成正文事实依据。

#### Scenario: 用户没有上传资料

- **WHEN** 用户只提交主题和要求
- **THEN** 系统 MAY 使用模型通用知识生成
- **AND** 最终报告 MUST 说明没有上传资料依据

#### Scenario: 用户上传无法解析的 PDF 或 PPT

- **WHEN** 主解析器和允许的降级解析器都无法取得可信内容
- **THEN** MaterialAsset MUST 标记为 `failed` 或 `metadata_only`
- **AND** 系统 MUST NOT 为该资产生成伪造证据或资料覆盖
- **AND** 前端和最终报告 MUST 展示失败原因

#### Scenario: 用户上传只能降级提取的资料

- **WHEN** 系统只能取得无完整来源坐标的文本
- **THEN** ParsedDocument MUST 标记为 `degraded`
- **AND** EvidenceUnit MUST 标记定位和置信度限制
- **AND** 质量报告 MUST NOT 把它等同于完整解析资料

### Requirement: 课程难度必须编译为能力契约

系统 MUST 将 `beginner/intermediate/advanced` 编译为结构化 `DifficultyProfile`，至少包含入口要求、挑战维度、支持维度和掌握契约。难度 MUST NOT 由文本长度、公式密度、代码量或小节数量单独表示。

#### Scenario: 编译三个难度等级

- **WHEN** 请求使用任一合法难度值
- **THEN** 系统 MUST 生成版本化的 `DifficultyProfile`
- **AND** 挑战强度与独立性 MUST 按入门、进阶、高阶递增
- **AND** 教学支架 MUST 总体按该顺序递减

### Requirement: 难度必须经过学科教学模式适配

系统 MUST 使用持久化 `SubjectPedagogyProfile` 将共享难度维度翻译为主教学模式的可观察任务和掌握证据。系统 MUST NOT 为每个学科维护三套独立难度 prompt。

#### Scenario: 同一难度用于不同教学模式

- **WHEN** 数学课与编程课都选择高阶
- **THEN** 两者 MUST 共享同级挑战、支持与独立性维度
- **AND** 数学课 MUST 将其翻译为形式推理、证明或建模证据
- **AND** 编程课 MUST 将其翻译为设计、调试、验证和权衡证据

### Requirement: 课程必须保存锯齿型难度曲线

`CourseBlueprint` MUST 保存 `CourseDifficultyCurve`，每个正文节点 MUST 保存 `NodeDifficultyContract`。曲线 MUST 允许新能力波次重新提高支架，并防止无前置的挑战跳变。

#### Scenario: 编译课程节点

- **WHEN** 蓝图结构和教学画像已确定
- **THEN** 系统 MUST 为每个 L2 节点分配能力角色、挑战、支架、掌握证据与学科任务
- **AND** 相邻节点挑战跳变 SHOULD 不超过 2 级
- **AND** 新概念负荷和任务复杂度 MUST NOT 同时无支架跃升

### Requirement: 目标难度与当前就绪度必须分开

系统 MUST 分开保存当前就绪度、课程入口要求和用户选择的目标难度。系统 MUST NOT 根据未授权动态学习痕迹静默更改目标难度。

#### Scenario: 就绪度未知

- **WHEN** 请求没有明确基础说明或诊断结果
- **THEN** `DifficultyGapAssessment` MUST 标记就绪度未知
- **AND** 系统 SHOULD 提供前置检查或桥接节点
- **AND** 目标难度 MUST 保持不变

#### Scenario: 就绪度低于入口要求

- **WHEN** 明确信息显示差距为 1 级
- **THEN** 系统 SHOULD 在目标课内增加桥接支架
- **WHEN** 差距为 2 级
- **THEN** 系统 SHOULD 规划前置单元
- **WHEN** 差距为 3 级或以上
- **THEN** 系统 SHOULD 建议拆分基础课与目标课，而不是静默降级

### Requirement: 蓝图、正文与重写必须消费同一难度契约

蓝图 prompt、节点正文 prompt、定向修复与局部重写 MUST 使用持久化难度契约。局部重写在没有明确新难度时 MUST 继承当前节点契约。

#### Scenario: 生成节点正文

- **WHEN** `CourseService` 生成某个 L2 节点
- **THEN** prompt MUST 包含该节点的挑战、支架、掌握证据、学科任务和伪难度禁止项
- **AND** prompt MUST NOT 只提供 `beginner/intermediate/advanced` 标签

#### Scenario: 用户未传难度地重写节点

- **WHEN** 节点重写请求未提供新难度
- **THEN** 系统 MUST 继承 `NodeDifficultyContract`
- **AND** MUST NOT 默认使用 `advanced`

### Requirement: 难度对齐必须有独立质量报告

质量链路 MUST 生成 `DifficultyAlignmentReport`，分开报告挑战、支持、独立性、掌握证据、曲线和学科任务对齐。关键契约缺失或曲线硬失败 MUST 使报告失败，不得被其他分数平均掉。

#### Scenario: 检测伪难度

- **WHEN** 正文只通过增加术语、长度、公式、代码或题量来表现高阶
- **THEN** 报告 SHOULD 标记伪难度风险
- **AND** 系统 SHOULD 要求补充推理、整合、独立决策、迁移或权衡证据

#### Scenario: 跨等级基准

- **WHEN** 同一教学模式编译三个难度等级
- **THEN** 系统 MUST 验证挑战和独立性严格递增
- **AND** MUST 验证支架强度总体递减

### Requirement: 首次课程生成必须提供可对账的恢复契约

系统 MUST 根据 `GenerationJob`、隔离工作区和正式课程发布回执生成恢复描述。恢复描述 MUST 说明是否可继续、恢复原因和最近检查点；前端 MUST NOT 只根据笼统失败状态猜测恢复动作。

#### Scenario: 服务在正文生成中重启

- **WHEN** 服务加载一个重启前处于运行或排队状态的首次生成任务
- **THEN** 系统 MUST 保留原 `job_id`、`course_id`、已完成节点和节点草稿
- **AND** MUST 将中断中的未完成节点恢复为待生成后重新入队
- **AND** 正式课程 MUST 继续保持未发布外壳

#### Scenario: 发布成功后任务终态尚未写入

- **WHEN** 正式课程已经存在该任务的幂等发布回执，但任务仍记录为运行或排队
- **THEN** 系统 MUST 将任务对账为完成
- **AND** MUST NOT 再次调用模型、重复发布或增加第二条发布操作记录

#### Scenario: 恢复所需工作区缺失

- **WHEN** 首次生成任务引用的隔离工作区不存在
- **THEN** 恢复描述 MUST 标记为不可恢复并说明原因
- **AND** 继续接口 MUST 拒绝入队
- **AND** 前端 MUST NOT 显示可执行的普通重试按钮

### Requirement: 运行失败与质量阻塞必须使用不同恢复动作

运行异常、用户暂停和节点失败 MAY 从原检查点继续；只有确定性质量门未通过且没有运行失败节点时，系统 MUST 标记为质量阻塞，MUST NOT 通过相同输入的普通重放冒充修复。

#### Scenario: 部分节点运行失败

- **WHEN** 工作区仍存在失败节点或中断草稿
- **THEN** 恢复描述 MUST 允许从原任务继续
- **AND** 继续操作 MUST 保留已完成节点，只重置可恢复的未完成节点

#### Scenario: 内容全部完成但质量门未通过

- **WHEN** 工作区没有失败节点且最终质量报告未通过
- **THEN** 恢复描述 MUST 标记为质量阻塞
- **AND** 普通继续接口 MUST NOT 重复执行同一生成流程
- **AND** 前端 MUST 引导用户查看或后续优化课程，而不是显示“重新尝试”

#### Scenario: 重复点击继续

- **WHEN** 同一任务已经排队或运行时客户端再次调用继续接口
- **THEN** 系统 MUST 返回当前恢复状态
- **AND** MUST NOT 重复入队或并行执行第二个同任务作业

### Requirement: 课程生成运行态必须端到端对账

课程生成 MUST 将本地运行环境、唯一 GenerationJob、检查点恢复、正式课程发布和前端课程摘要视为同一运行闭环。普通 active job MUST NOT 被解释为恢复任务；正式文档发布后，前端 MUST 对账课程正文、任务终态和课程库摘要。

#### Scenario: 新课程正常开始生成

- **WHEN** 新建 GenerationJob 处于 `pending` 或 `running` 且没有恢复原因
- **THEN** 后端恢复描述 MUST 返回普通非恢复状态
- **AND** 前端 MUST 显示“等待生成”或“正在生成”
- **AND** MUST NOT 显示“正在恢复”

#### Scenario: 服务重启或人工继续后任务活跃

- **WHEN** active job 具有 `service_restart` 或 `manual_resume` 恢复原因
- **THEN** 后端恢复描述 MUST 标记该任务正在从检查点继续
- **AND** MUST 保留原 `job_id`、已完成节点和草稿

#### Scenario: 正式课程发布完成

- **WHEN** 前端从 WebSocket 或任务轮询观察到 GenerationJob 首次迁移为 `completed`
- **THEN** 前端 MUST 重新读取正式 CourseDocument
- **AND** MUST 重新读取课程库摘要
- **AND** 课程卡片的节点数 MUST 与已发布文档一致，无需用户手动刷新

#### Scenario: 本地启动课程生成环境

- **WHEN** 开发者执行项目本地启动脚本
- **THEN** 脚本 MUST 使用项目既定 Python 与前端依赖启动前后端
- **AND** MUST 校验课程生成所需 AI 配置
- **AND** MUST 在前后端健康检查通过后才报告服务可用
- **AND** 任一子进程异常退出 MUST 使编排进程失败并清理另一子进程

### Requirement: 模型思考内容不得进入普通运行输出

模型 provider 返回的思考内容 MUST NOT 被写入标准输出、课程正文或用户可见日志。系统 MAY 记录思考内容长度等非内容元数据用于调试。

#### Scenario: 模型同时返回思考与答案增量

- **WHEN** AIBase 聚合含 `reasoning_content` 和 `content` 的流式响应
- **THEN** 最终结果 MUST 只由 `content` 聚合
- **AND** 标准输出 MUST NOT 包含 `reasoning_content`
- **AND** 普通 info 日志 MUST NOT 记录思考正文

### Requirement: 浏览器任务缓存不得冒充服务端活动任务

浏览器 MAY 缓存最后一次成功读取的课程生成状态用于刷新和离线连续性，但 MUST NOT 在服务端明确不存在对应任务时继续显示为活动任务。

#### Scenario: 任务列表缺少本地活动任务

- **WHEN** 服务端任务列表成功返回，但没有包含浏览器缓存中的活动任务
- **THEN** 前端 MUST 使用原任务 ID 查询服务端单任务接口
- **AND** MUST NOT 仅根据本地百分比断定任务仍在运行

#### Scenario: 服务端明确不存在原任务

- **WHEN** 单任务接口对本地活动任务返回 404
- **THEN** 前端 MUST 清理对应本地任务和进度投影
- **AND** 任务中心与课程卡 MUST 停止显示旧生成百分比
- **AND** 前端 MUST 向用户说明本地任务状态已经失效

#### Scenario: 单任务核对遇到临时错误

- **WHEN** 单任务接口因断网、超时或服务端临时错误无法完成核对
- **THEN** 前端 MUST 保留最后一次成功的本地任务状态
- **AND** MUST NOT 把临时不可达解释为任务已不存在

### Requirement: 课程生成任务必须拥有可补偿的完整生命周期

课程生成 MUST 将任务、运行协程、生成工作区、候选版本和未发布课程外壳作为同一生命周期管理。创建中途失败或用户取消时，系统 MUST 清理本次任务拥有的临时对象；已正式发布的课程文档 MUST NOT 因任务清理而删除。

#### Scenario: 创建任务中途失败

- **WHEN** 工作区创建后，课程外壳创建、任务持久化或任务入队任一步失败
- **THEN** 系统 MUST 按相反顺序补偿本次已经创建的对象
- **AND** MUST NOT 留下没有对应任务的工作区或 0 节点课程外壳

#### Scenario: 取消尚未发布的新课程

- **WHEN** 用户取消仍在生成且尚未正式发布的初始课程任务
- **THEN** 系统 MUST 先阻止新的后台写入并等待关联协程结束
- **AND** MUST 删除任务工作区、候选版本、蓝图草稿和任务记录
- **AND** MUST 删除由该任务创建的未发布课程外壳

#### Scenario: 清理已发布课程的任务记录

- **WHEN** 用户清理一个已经正式发布课程的终态任务
- **THEN** 系统 MUST 删除任务及其临时生成状态
- **AND** MUST 保留正式 CourseDocument 及其可学习内容

### Requirement: 删除课程必须先终止关联生成任务

课程删除 MUST 通过统一后端生命周期先终止并清理关联生成任务，再删除正式课程对象。后台生成协程 MUST NOT 在课程删除成功后继续写入或重新创建该课程。

#### Scenario: 删除正在生成的课程

- **WHEN** 用户删除具有关联活动 GenerationJob 的课程
- **THEN** 系统 MUST 将任务标记为取消并等待后台协程结束
- **AND** MUST 清理任务工作区、候选版本和任务记录
- **AND** MUST 最后删除正式课程对象

#### Scenario: 删除没有活动任务的课程

- **WHEN** 用户删除只包含历史终态任务或不包含任务的课程
- **THEN** 系统 MUST 幂等清理关联生成状态
- **AND** MUST 删除课程并返回真实结果

### Requirement: 任务控制接口必须返回真实状态机结果

暂停、恢复、节点控制、删除任务和失败任务清理 MUST 校验任务是否存在以及当前状态是否允许操作。成功响应 MUST 表示操作已经发生；不存在对象 MUST 返回 404，状态冲突 MUST 返回 409。

#### Scenario: 暂停不存在或已结束的任务

- **WHEN** 客户端暂停不存在的任务
- **THEN** 服务端 MUST 返回 404
- **WHEN** 客户端暂停已完成、已取消或不可暂停的任务
- **THEN** 服务端 MUST 返回 409 并说明当前状态

#### Scenario: 对终态任务执行节点控制

- **WHEN** 客户端对没有活动任务的课程执行节点跳过、重试、停止或附加指令
- **THEN** 服务端 MUST 返回 404 或 409
- **AND** MUST NOT 修改历史终态任务

#### Scenario: 清理失败任务

- **WHEN** 客户端批量清理失败任务
- **THEN** 系统 MUST 复用单任务生命周期清理逻辑
- **AND** MUST NOT 只删除任务索引而留下工作区或未发布课程外壳

### Requirement: 课程生成输入必须在持久化前规范化

课程主题 MUST 在创建工作区、课程外壳或任务前去除首尾空白并完成非空校验。

#### Scenario: 提交空白课程主题

- **WHEN** 客户端提交只包含空白字符的课程主题
- **THEN** 服务端 MUST 返回 422
- **AND** MUST NOT 创建任务、工作区或课程外壳

### Requirement: 首次课程创建必须按请求号幂等

首次课程创建 MUST 接受稳定的客户端请求号，并 MUST 保证同一请求号只对应一个 `GenerationJob`、一个生成工作区和一门课程。该关系 MUST 随任务持久化，因此服务重启后重复请求仍能返回原任务。

#### Scenario: 同一创建请求并发到达

- **WHEN** 客户端因重复点击、网络重试或响应丢失，使用同一请求号重复提交课程创建
- **THEN** 服务端 MUST 返回第一次创建的 `job_id` 和 `course_id`
- **AND** MUST NOT 创建第二个工作区、课程外壳或任务

#### Scenario: 用户重新发起独立创建

- **WHEN** 用户关闭上一次创建会话后重新提交相同课程参数
- **AND** 客户端使用新的请求号
- **THEN** 服务端 MAY 创建新的独立课程任务

### Requirement: 前端课程列表与生成任务必须持续对账

前端 MUST 以服务端 GenerationJob 和正式 CourseDocument 为真源。取消、删除或发现其他标签页创建的新任务后，前端 MUST 对账任务投影、生成进度和课程列表。

#### Scenario: 取消未发布课程任务

- **WHEN** 服务端确认取消成功
- **THEN** 前端 MUST 移除对应任务和生成进度
- **AND** MUST 重新读取课程列表以移除未发布课程外壳

#### Scenario: 发现本地未知的服务端任务

- **WHEN** 任务轮询发现本地没有记录的新 GenerationJob
- **THEN** 前端 MUST 接纳该任务作为真实状态
- **AND** SHOULD 重新读取课程列表以显示其课程外壳

#### Scenario: 进度样本不足

- **WHEN** 前端没有足够的连续有效样本计算剩余时间
- **THEN** 前端 MUST 显示计算中或不展示估算
- **AND** MUST NOT 根据单次并发跳变展示虚假精确时间

#### Scenario: 历史未发布外壳失去任务

- **WHEN** 课程存储中存在带生成任务号、尚未发布，但任务索引中已无对应任务的历史外壳
- **THEN** 课程列表 MUST NOT 将其展示为可学习课程
- **AND** 系统 MUST 保留原文件用于审计，除非用户执行显式清理

#### Scenario: 已发布课程带有质量建议

- **WHEN** 任务状态为 `completed_with_warnings` 且 `publication_allowed=true`
- **THEN** 前端 MUST 将课程显示为可学习并保留优化建议
- **AND** MUST NOT 把它计入活动或阻断任务数量

### Requirement: 模型调用必须有唯一且有限的重试边界

模型 SDK MUST 使用明确的连接与读取超时，并 MUST NOT 在业务层之外暗中执行额外重试。业务层 MUST 只在有限预算内重试可恢复错误；普通网络错误 MUST NOT 触发对全部模型候选的长时间遍历。

#### Scenario: provider 长时间没有返回数据

- **WHEN** 单次模型请求超过配置的读取等待上限
- **THEN** 请求 MUST 以可恢复错误结束
- **AND** 节点生成 MUST 进入既有有限重试或失败恢复
- **AND** MUST 保留已经保存的节点草稿

#### Scenario: 流式模型请求失败

- **WHEN** provider 返回超时、连接错误、空流或无可用模型
- **THEN** AI 调用层 MUST 抛出结构化错误
- **AND** MUST NOT 把 `[Error: ...]` 或类似错误文本作为课程正文 chunk

#### Scenario: 当前候选模型明确不可用

- **WHEN** provider 明确返回当前模型不受支持、配额不足或模型级限流
- **THEN** AI 调用层 MAY 切换到下一个候选模型
- **AND** 整个请求仍 MUST 受统一尝试预算和超时约束

### Requirement: 质量闸门必须区分发布阻断与优化建议

最终课程质量报告 MUST 分别表达严格质量状态和发布许可。少量非关键质量建议 MUST NOT 阻止完整课程进入正式 CourseDocument；关键内容、资料和资产缺陷 MUST 继续阻断发布并保留生成工作区。

#### Scenario: 完整课程只有少量难度建议

- **WHEN** 所有学习节点生成完成且节点质量通过
- **AND** 只有少量 major 难度或迁移建议，没有 critical 问题、必用资料缺失或资产阻断项
- **THEN** 质量报告 MUST 返回 `final_status=completed_with_warnings`
- **AND** MUST 返回 `publication_allowed=true`
- **AND** 系统 MUST 发布正式课程文档并保留质量警告

#### Scenario: 课程存在关键缺陷

- **WHEN** 任一学习节点为空、生成失败、含 critical 内容问题、使用无效证据、遗漏必用资料或学习资产包含 blocking issue
- **THEN** 质量报告 MUST 返回 `publication_allowed=false`
- **AND** 系统 MUST NOT 发布当前工作区
- **AND** MUST 保留工作区、失败节点和定点修复依据

#### Scenario: 服务发现旧的质量阻塞任务现在允许发布

- **WHEN** 服务启动时读取一个 `quality_failed` 工作区
- **AND** 按当前质量分级重新计算得到 `publication_allowed=true`
- **THEN** 系统 MUST 直接完成质量对账和正式发布
- **AND** MUST NOT 重新调用模型生成已经完成的正文

### Requirement: 首次课程生成必须执行不可绕过的运行预算

首次课程生成 MUST 为最终模型请求执行输入字符、混合语言估算 token、输出 token、提供方总尝试次数和
单调用截止时间硬门，并为教案规划、单节点正文和整课正文执行独立阶段总截止时间。
详细教案批次 MUST 只读取当前批次知识闭包；正文调度 MUST 将学习前置与生成依赖
分离。预算超限和截止时间到达都 MUST 保存最近检查点并停止当前最小单元，不得把
候选模型与业务重试相乘为小时级等待。

#### Scenario: 最终 Prompt 超过输入预算

- **WHEN** system prompt 与 user prompt 组成后的估算输入 token 超过硬上限
- **THEN** 系统 MUST 在提供方调用前返回预算错误
- **AND** 任务 MUST 保存阶段、估算规模和最近检查点
- **AND** MUST NOT 发送请求后依赖提供方截断

#### Scenario: 线性学习路径进入正文生成

- **WHEN** 多个小节通过 `prerequisite_node_ids` 形成线性学习顺序
- **THEN** 正文 MUST 在全局有界并发内独立生成
- **AND** 后序小节 MUST 使用冻结的教学责任和知识契约建立承接
- **AND** 前序正文失败 MUST NOT 自动阻断其他小节

### Requirement: 课程生成必须将编排偏好编译为可验证的块配方

课程生成 MUST 将课程编排偏好建模为独立于正文语气、视觉排版、学科教学结构和 AI 老师人格的正式输入。系统 MUST 使用已登记的编排画像确定课程块角色的增量、比例与节奏，并 MUST 保留学科教学结构要求的全部必要模块。编排偏好 MUST NOT 仅作为自然语言形容词进入 prompt。

#### Scenario: 用户选择案例实战型编排

- **WHEN** 用户以相同主题、难度和教学结构选择 `example_driven`
- **THEN** 教学方案 MUST 比智能均衡方案稳定增加案例或真实应用模块
- **AND** 每个新增模块 MUST 有已登记模块 ID、块角色、实例 ID 和编排来源
- **AND** 学科必要模块 MUST 继续存在

#### Scenario: 旧任务只包含教学风格

- **WHEN** 系统恢复只包含旧 `style` 字段的生成任务
- **THEN** 系统 MUST 使用固定兼容表映射到课程编排偏好
- **AND** 后续产物 MUST 使用规范化后的编排值
- **AND** MUST NOT 再把旧值解释为不受约束的文案风格

### Requirement: 难度契约必须投影到每个课程块模块

课程生成 MUST 在学科教学结构和课程编排偏好之后，将目标难度编译为确定性的课程块配方，再根据节级目标难度、节点角色和模块块角色生成块级难度契约。入门、进阶和高阶 MUST 能在相同主题与编排偏好下形成可解释的模块分布差异，而不只是改变正文长度、术语密度或同一批块的描述。块级契约 MUST 至少表达目标层级、重点维度、支架强度、学习者自主程度、迁移距离和反馈时机，并 MUST 在教学确认、正文生成和最终课程块之间保持可追溯。

#### Scenario: 用户生成入门课程

- **WHEN** 小节目标难度为 `beginner`
- **THEN** 模块计划 MUST 增加分步示范
- **AND** 从引导练习阶段起 MUST 增加带支架练习
- **AND** 学科必要模块 MUST 继续存在

#### Scenario: 用户生成高阶数学课程

- **WHEN** 主教学模式为数学与形式科学且目标难度为 `advanced`
- **THEN** 后续节点 MUST 增加证明与推导模块
- **AND** 整合或末端节点 MUST 增加数学建模或迁移挑战
- **AND** 这些模块 MUST 作为必需模块进入正文 prompt 与质量检查

#### Scenario: 编排偏好与难度选择同一模块

- **WHEN** 课程编排偏好和目标难度同时选择同一个已登记模块
- **THEN** 模块计划 MUST 只保留一个模块实例
- **AND** 该实例 MUST 同时保留编排偏好与难度的选择原因

#### Scenario: 项目驱动课程进入后半程独立节点

- **WHEN** 项目驱动课程的节点角色从基础或引导练习进入独立、迁移或综合节点
- **THEN** 项目或活动块的自主程度与迁移距离 MUST 相应提高
- **AND** 概念或先修块仍 MUST 保留与目标难度相称的必要支架
- **AND** 块配方与块内难度变化 MUST 在教学方案中可见

### Requirement: 教学方案确认必须展示真实课程块编排

六步课程生成的教学方案产物 MUST 展示规范化编排画像、全课角色分布和每节按顺序排列的模块实例。用户确认的教学方案修订 MUST 包含这些字段；编排偏好或块配方改变后，旧确认 MUST 失效。

#### Scenario: 用户进入教学方案确认

- **WHEN** 知识蓝图已确认并完成教学方案编译
- **THEN** 用户 MUST 能看到所选编排偏好实际增加或调整了哪些块
- **AND** MUST 能看到每节块角色、编排来源和块级难度摘要
- **AND** 课程内容生成 MUST 消费该次已确认的模块实例计划
