# 课程生成与 AI 老师后端链路

本文记录当前生产后端的真实链路，用于判断新功能应接入哪里，以及旧 AI 文件是否仍可作为入口。

> 产品目标边界：本文描述的是当前实现事实，不是最终产品模型。目标产品以 `docs/product-blueprint.md` 为最高优先级真源。标准课程已经先行迁移为 `CourseDocument + ordered CourseBlock[]`；Markdown 只存在于富文本块载荷、导入导出和旧课程兼容投影中。其余历史课程与新增课程生成仍处于过渡期，不得据此新增平行课程逻辑。

## 1. 总体原则

后端 AI 能力分为正式学习运行时、课程生成上下文和 AI 老师请求上下文；三者共享领域真源，但不互相复制状态：

```text
LearningEvent + 正式领域仓库
  -> LearnerModel + LearningRuntime
  -> CourseService 使用 AI Learning Context
  -> AI 老师使用 AIContextPackage
  -> 白名单动作产生 LearningRecord 与 LearningEvent
  -> LearnerModel 与 LearningRuntime 确定性重算
```

其中：

- `LearningEvent` 记录发生过什么。
- `LearnerModel` 从正式事实生成带证据、置信度和有效期的只读投影。
- `LearningRuntime` 聚合当前现场、正式任务和唯一主要动作。
- `teaching_guidance` 只根据本轮明确请求和足够强的正式证据调整讲法，不拥有学习事实或下一步。
- `AI Learning Context` 服务课程生成；`AIContextPackage` 服务单次 AI 老师请求。

执行入口保持两条主线：

- 课程内容链路：所有课程创建、子节点生成、正文生成、节点重写、扩展、摘要和定位都通过 `CourseService`。
- AI 老师链路：服务端按意图读取当前课程来源、`LearningRuntime`、正式任务与必要证据；对话只保存消息，不成为学习状态。

`ai_service` 仍是非课程 AI 兼容门面；当前生产调用只承载问答和图表等能力。学科知识库、课程知识映射、正式练习、课程生成和学习者模型均由各自正式领域服务负责，不得重新挂回该门面。

## 2. 课程内容链路

```text
/api/course-generation/generate
  -> routers/courses.py
  -> TaskManager.create_generation_job()
  -> 一个 GenerationJob + 一个隔离生成工作区 + 空 CourseDocument 外壳
  -> 确定性编译教学画像、难度与课程块硬骨架
  -> CourseService.build_course_draft()
  -> AI 生成轻量目录
  -> 用户确认目录
  -> 小课：一次紧凑教案调用 -> 本地封装 CourseTeachingPlanV3
     大课：一次全局骨架 -> 有界并行详细批次 -> 本地汇编 CourseTeachingPlanV3
  -> 本地编译 CourseKnowledgeBase、稳定 ID、关系图与逐节绑定
  -> TaskManager 按硬前置波次并行生成正文与同源学习资产
  -> 确定性发布预检
  -> 用户确认发布
  -> CourseDocumentRepository 幂等发布唯一 CourseDocument
  -> WebSocketService 投影同一任务的阶段、检查点、草稿和终态

/api/courses/{course_id}/nodes/{node_id}/...
  -> routers/nodes.py
  -> CourseService.redefine_content()
  -> CourseService.rewrite_selection()
  -> CourseService.regenerate_content_block()
  -> CourseService.extend_content()
  -> CourseService.summarize_content()
  -> 课程生成策略 + AI Learning Context
  -> 确定性输出质量检查，不写学习事实

/api/courses/{course_id}/document
  -> CourseDocumentRepository
  -> 已迁移课程直接读取唯一持久真源
  -> 未迁移课程只生成只读兼容文档，不自动落盘
```

关键约束：

- `CourseService` 是课程 AI 能力的唯一生产入口。
- 首次生成只有一条 AI 主链：轻量目录、正式全课教案和逐节正文。自动教学画像、
  难度、模板、稳定 ID、知识库、关系图、校验、恢复和发布均为本地确定性步骤，不得
  新增辅助模型判断、AI 评分或独立知识/关系生成。
- 目录确认后的正式教案按预算选择执行策略。最多 3 节且输入输出预算安全时使用一次
  紧凑调用，并由本地编译器生成稳定知识身份修订、统一封装为
  `CourseTeachingPlanV3`；大课使用“全局骨架串行 → 详细批次有界并行 → 本地汇编
  串行”的 `1 → N → 1`。两条路径只在执行预算上不同，不允许形成两套产品 schema。
- 大课骨架决定每个知识键的唯一负责、复用、前置和模块边界；每批默认最多 3 节、
  15 个知识点，同一课程默认并发 2。完成一批立即持久化，单批失败最多定点纠正一次，
  其他成功批次不丢失；乱序完成不能改变目录顺序、知识身份或最终修订。
- 每次必要模型请求发出前先持久化准确阶段。提供方立即失败时必须显示目录、骨架、
  教案批次或正文的真实故障位置，不能继续沿用教学画像等上一阶段名称。
- 新建课程的“课程编排偏好”是课程结构控制量，不是 AI 助手人格、文字语气或页面排版主题。正式输入使用 `composition_style`；旧 `style` 只作为历史客户端和节点级能力的兼容字段。
- 课程块计划按以下顺序确定，后层不得反向删除前层的必需模块：

  ```text
  学科必需模块
    -> 编排偏好补充模块与节奏顺序
    -> 目标难度增加或提升对应课程块
    -> 章节难度契约投影到每个课程块
    -> 证据边界与质量门
    -> CourseDocument + ordered CourseBlock[]
  ```

- 当前编排预设包括智能均衡、理论推导、案例实战、项目驱动和问题探究。预设只能调整讲解、推演、案例、真实场景、项目任务、探究、边界与反例等块的占比和顺序，不能用“实战型”等偏好删掉学科必需推导或安全边界。
- 难度配方使用确定性三级规则：入门增加分步示范并逐步加入带支架练习；进阶保留学科标准配方；高阶前段增加深入推演，后段按学科增加证明、测试、实验设计、材料辨析、数据分析等模块，末端增加迁移挑战。规则按课程位置与节点角色渐进启用，不在每节机械堆满高阶模块。
- 每个生成模块必须携带稳定的 `module_instance_id`、`block_role`、`composition_source`、`selection_reasons` 和 `block_difficulty_contract`。这些信息从教学审阅、Prompt 约束一路进入最终 `CourseBlock.payload`，使用户能够在生成前审阅、生成后追溯。
- 课程难度与编排偏好是两个独立输入、按层合并：编排偏好决定跨学科的教学节奏，难度既选择与目标等级相称的课程块，也决定每个块的推理跨度、支架、迁移与自主度。同一模块被多层选中时只保留一个实例，并记录全部选择原因。
- 课程生成分三类策略：
  - 通用课程结构蓝图：不使用单个学习者状态改变目录主线。
  - 个性化节点解释：只在当前节点内部调整讲法。
  - 薄弱点补充内容：针对错题、复习失败、低正确率和风险补例子、练习、慢推理。
- 节点正文生成必须读取课程上下文账本，避免只凭当前标题自由发挥。
- 节点正文生成、重写、扩展和摘要可以读取 `AI Learning Context`，但学习者状态和教学决策不得覆盖课程蓝图、课程账本和节点契约。
- 已迁移课程以 `CourseDocument` 及有序课程块为唯一持久真源；同一课程文件不再保存旧 `nodes` 正文副本。
- 未迁移课程仍可由完整 `node_content` Markdown 生成只读兼容投影；新课程首次生成直接发布 `CourseDocument`，不得再建立第二套正式正文。
- 兼容 `content_blocks` 只允许由统一课程文档投影，或者服务尚未迁移的历史课程；前端标准课程默认读取正式课程文档接口。
- 局部改写的新主链路是 Markdown 选区级候选生成：
  - 前端从 Markdown 渲染正文中选中文字，临时解析标题路径和前后文。
  - `/api/courses/{course_id}/nodes/{node_id}/selection-rewrite` 调用 `CourseService.rewrite_selection()`。
  - 后端基于课程账本、节点契约、AI Learning Context、选区前后文和用户要求生成候选替换文本。
  - 后端不直接保存正文。未迁移课程仍可通过旧节点接口确认保存；已迁移课程的旧保存接口会拒绝覆盖，后续必须接入统一课程命令后才能开放正式确认写入。
- 课程输出质量属于课程生产过程，只进入生成日志、质量报告或课程质量对象，不得写入学习者事件账本。
- 选区改写请求会记录 `markdown_selection_rewrite_requested` 事件，用于后续分析用户更常修改哪些知识点、哪些表达需要简化、补例子或练习。
- `AIService` 不应暴露 `generate_course`、`generate_node_content`、`redefine_content`、`extend_content`、`locate_node` 等课程方法。

## 3. 学习者模型链路

```text
LearningEvent + LearningSnapshot + LearningRecord + PracticeAttempt + 诊断
  -> learner_model_service 读取同批正式来源
  -> learner_model.build_learner_model()
  -> LearnerModel(model_revision_id, evidence_refs, confidence, validity)
  -> LearningRuntime / AI Learning Context / AIContextPackage
```

`LearnerModel` 只表达可重算的学习结论：

- 阅读、正式掌握、自我报告和系统推断分区保存。
- 优势、待巩固项和支持需求必须带证据引用、置信度与有效期。
- 相同来源修订产生相同模型修订，不保存可独立漂移的画像副本。
- 一次失败、一次提问或 AI 的主观判断不能直接形成稳定薄弱点。

`learner_context.py` 只保留学习者身份解析，不再聚合画像。旧 annotation、旧 profile、`tutor_memory`、Learning OS 和 AI 会话均不参与正式模型。

## 4. 运行时与讲法链路

```text
同批正式事实与当前课程
  -> LearnerModel
  -> LearningProgress + LearningContinuation + LearningRuntime
  -> ai_learning_context.build_ai_learning_context()
  -> bounded teaching_guidance
```

职责边界：

- `LearningEvent`：事实账本，回答“发生过什么”。
- 正式领域仓库：保存当前记录、作答、快照和诊断对象。
- `LearnerModel`：解释正式事实当前支持哪些结论。
- `LearningRuntime`：组织当前学习现场、进度、连续性和统一动作。
- `teaching_guidance`：只表达本次讲法，不拥有正式状态或下一步。
- `AI Learning Context`：课程生成侧的上下文编排，不读取动态 AI 会话和动作提案。

`teaching_guidance` 是轻量规则，不调用大模型。它只能根据本轮明确请求和中高置信正式证据选择直接解释、简化、举例或补充练习；统一学习动作仍由 `LearningRuntime` 决定。

这些输出是临时策略，不能写回学习者模型。任何模型变化必须先通过正式领域命令形成可追溯事实。

## 5. AI 老师链路

```text
/api/ask_events
  -> routers/assistant.py
  -> ai_teacher_context.build_ai_teacher_context()
  -> AIContextPackage + LearningRuntime + 定向课程来源
  -> AIQAService.answer_question_events()
  -> AIBase._stream_llm()
```

协议约束：

- 生产问答只保留结构化 `/api/ask_events`，事件固定区分上下文、来源、回答、最终答案、提案、回执、错误与完成。
- 服务端根据稳定引用装配必要课程片段、运行时、正式任务和相关证据；前端不得上传课程全文、全部笔记或本地会话真源。
- 只有涉及学习状态判断的意图才读取相关目标的最小模型证据；普通解释以课程片段为主。
- 上下文固定 `model_revision_id` 并标明证据充分度，AI 不能把自己的解释改写成正式学习结论。
- 正式任务提交前不向模型提供参考答案，客户端伪造的任务状态不能放开答案披露。
- 普通对话不自动进入笔记、问题、复习或画像；所有写动作经过白名单提案、幂等执行和持久回执。

## 6. 主动帮助链路

```text
/api/ai-teacher/trigger
  -> LearningRuntime.primary_action
  -> 强证据白名单
  -> TriggerCandidate
  -> 持久拒绝与抑制
```

只有版本冲突、正式阻塞、诊断补救、需要人工支持或到期复习等强运行时动作可以产生候选。停留时间、滚动速度、一次错误、参与度和旧错题数量不能触发。AI 不生成竞争动作，只在统一入口解释运行时已有依据。

## 7. 非课程 AI 门面

`backend/ai_service.py` 当前组合：

- `AIQAService`
- `AIGraphService`
- `AILearningService`
- `AIDiagramService`

这是兼容门面，不是课程生成中心，也不是学习者模型入口。新增课程内容能力优先进入 `CourseService`；正式练习能力进入 `practice_contracts / practice_attempts / practice_grading`；AI 老师上下文进入 `ai_teacher_context`，稳定学习事实继续归正式领域仓库。

## 8. 旧链路收束状态

已收束：

- 旧课程 AI 服务文件已从生产链路移除。
- 旧 `memory.py` 双记忆控制器已从问答链路移除。
- 旧 `agent.py` 主动学习 Agent 文件无生产引用，已删除。
- 旧 `/api/ask`、`assistant_context`、本地 session memory 与 long-term memory 读取已经退出生产路径。
- 课程内容生成、重写、扩展和摘要已通过 `AI Learning Context` 读取受限的正式模型与讲法约束。
- 标准课程前端已读取正式课程文档并按有序块渲染，同时保持原有文档式阅读、课程目录、正式任务覆盖层和 AI 右栏体验；未迁移课程仍由兼容文档投影接入同一阅读组件。
- `tutor_service`、`ProactiveTutorEngine`、`TutorActionCard`、前端 tutor Store 和 `/api/tutor/*` 已删除。
- 旧单数 `learning_record.py`、旧测验服务与旧测验 Prompt 已删除；历史记录只通过迁移器读取，不再双写。
- 正式练习统一由 `QuestionRevision -> PracticeAttempt -> LearningEvent -> LearningProgress` 链路承担。
- 旧 annotation、旧 profile、Learning OS、`LearnerState`、`TeachingDecision` 与长期学习种子路由和生产文件已删除。
- 前端旧 profile、learning Store 与独立画像页已删除；学习概况只读取 `LearningRuntime` 与正式 `LearnerModel`。
- 正式学习接口要求稳定 `X-User-Id`，缺失或共享 `default_user` 时拒绝读写个体数据。
- AI 老师会话、提案、回执和抑制独立持久化，但不复制学习状态。

继续保留：

- `/api/ask_events`：唯一生产问答入口，输出结构化 SSE。
- `ai_service`：非课程 AI 兼容门面，当前只被问答、图表和旧节点文本清理调用。
- `LearningStats`、`SideAIPanel`：分别承载学习概况和统一 AI 老师，读取同一正式模型修订与运行时。
- 旧 block 级重写接口：只继续服务未迁移课程；已迁移课程拒绝旧保存，避免兼容接口反向覆盖正式课程文档。

## 9. 新功能接入规则

- 课件生成、内容改写、内容扩展、内容摘要：接 `CourseService`。
- 新建课程的块组成、块顺序、难度配方和块级难度：接 `course_composition`，并由 `CourseService` 在学科模块计划与节级难度契约之后统一编译；不得重新用自然语言 `style` 或 `difficulty` 形容词做旁路控制。
- Markdown 选区级局部改写：接 `CourseService.rewrite_selection()`，只返回候选；确认写入必须进入统一课程命令，未完成接线前不得绕回旧节点保存覆盖已迁移课程。
- 学习行为证据：写入 `LearningEvent`。
- 正式题目与评分契约：接 `learning_assets` 与 `practice_contracts`；作答事实只写 `PracticeAttempt`，再追加 `LearningEvent`。
- 可解释学习结论：接只读 `LearnerModel`。
- 当前学习现场与统一动作：接 `LearningRuntime`；本轮讲法只使用受限 `teaching_guidance`。
- 课程生成上下文：接 `AI Learning Context`；AI 老师问答上下文：接 `AIContextPackage`。
- 学习者身份：接 `learner_context.require_user_id`；不得在正式学习接口回退共享用户。
- AI 老师 prompt 与结构化事件：接 `ai_teacher_context` + `AIQAService`。
- 主动帮助：接强证据 `TriggerCandidate`，不得恢复 Tutor suggestion。
- 不新增平行的 “memory manager”、“agent controller” 或课程 AI 门面。

## 10. 后续升级方向

当前仍只是轻量规则版闭环，暂时不能可靠自动化：

- 跨课程长期掌握和复习排程仍需基于正式事件与学习者模型扩展，不得恢复导师专属状态。
- 回答教学策略还没有形成“某种讲法是否有效”的统计评估闭环。
- 课程内 `CourseKnowledgeBase` 已能生成概念组、原子知识点、六类关系与题目绑定；
  当前缺口是用多种教学模式的真实生产样本验证关系语义丰富度、提供方 P50/P95、
  429 和成本曲线，而不是再新增一套平行知识图谱。
- 复习计划和练习生成已经有正式任务底座，后续需要扩展可执行动作注册表与效果回收。

下一步应扩展正式领域动作注册表，例如打开指定 Attempt、创建复习任务和进入补救流程；每个动作继续经过提案、修订校验、幂等命令、回执和 `LearningRuntime` 刷新。
