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
  -> 章节骨架 -> 各章有界批次并行 -> 本地汇编轻量目录
  -> 用户确认目录
  -> 有界连续骨架分片 -> 有界并行详细批次 -> 本地汇编 CourseTeachingPlanV3
  -> 本地编译 CourseKnowledgeBase、稳定 ID、关系图与逐节绑定
  -> TaskManager 只读取 AI 语义完整的冻结教案，将独立正文单元送入共享自适应容量队列
  -> 确定性编译学习资产；只把失败的“小节 × 练习位”送入通用练习编排器并逐节保存
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
- 首次生成只有一条 AI 主链：轻量目录、正式全课教案、逐节正文，以及正文完成后按质量缺口触发的定向练习生成。自动教学画像、
  难度、模板、稳定 ID、知识库、关系图、校验、恢复和发布均为本地确定性步骤，不得
  新增辅助模型判断、AI 评分或独立知识/关系生成。
- 目录阶段没有单门课程总小节数上限，也没有课程级紧凑快捷路径。每门课程都先用一份
  轻量章节骨架冻结课程定位、目标、章节顺序和各章小节数，再按章
  并行展开。单章超过 6 节时继续拆为顺序批次；每批只读取当前章、相邻章衔接、当前
  章已完成的小节和最多 4 条相关证据，最后由本地按稳定 ID 汇编唯一目录。章节批次
  完成即保存，恢复时只重做缺失批次。全局章节骨架没有有效语义时不得伪造整门占位
  课程；骨架有效后，单个章节批次失败才允许局部保底并标记人工复核。
- 目录确认后的正式教案统一使用“全局骨架串行 → 详细批次有界并行 → 本地汇编
  串行”的 `1 → N → 1`，包括只有 1 节的显式课程。所有课程都写入唯一正式
  `CourseTeachingPlanV3`，不允许按规模分叉执行协议。
- 教案骨架是一份连续增长的全课身份产物，但默认每次调用最多处理 2 节，只读取这些
  小节直接需要的前序知识边界；本地合并器负责重排分片临时键并维持唯一负责、复用、
  前置和模块边界。每片通过后持久化连续前缀；服务重启时先校验前缀和目录修订，再从
  第一个未完成分片续跑。详细教案默认每次只生成 1 节；业务层可同时准备多个独立单元，
  但所有真实请求在 `AIBase` 共享按提供方与模型计算的容量队列。队列从保守并发开始，连续成功后渐进扩容，
  `429` 或额度错误会立即收缩并让已排队请求改走候选模型。每批只携带当前知识与直接依赖闭包，不再重复发送全课知识注册表。
  完成一批立即持久化。无法适配预算、定点纠正失败或提供方失败时，可以本地编译该最小单元作为可见预览，但教案阶段必须标记
  `retry_required`并停在正文之前；恢复时保留其他 AI 成功批次，只重跑非模型单元。乱序完成不能改变目录顺序、知识身份或最终修订。
- `prerequisite_node_ids` 只表达学生学习顺序，不是正文生产依赖。正文只消费已经冻结的
  全课教案、当前节点合同和有界证据，因此所有待生成小节可直接进入同一并发队列；某节
  失败只影响该节，不得阻断后续小节。
- 每次必要模型请求发出前先持久化准确阶段。提供方立即失败时必须显示目录、骨架、
  教案批次或正文的真实故障位置，不能继续沿用教学画像等上一阶段名称。
- 正文完成后先本地编译题库与学习资产。输入、答案、领域或可判定性校验失败的正式练习才进入 `AssessmentGenerationOrchestrator`；通过的练习保持不变，同一小节最多三个练习位有界并行，每节完成立即保存题库修订。恢复从未完成小节继续，不得重做目录、教案或正文。未批准的诊断、补救验证和综合测评候选稿保持隔离，运行时只选择 `quality_status=passed` 的增强资产；候选稿失败不阻断首次发布，教师批准后则重新进入正式硬门。
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
- 学科教学画像 V2 保留八个一级模式，但不再把一个模式的全部学科块机械复制到每节。
  系统先确定必要学科分型，再依据小节目标、关键词和全课位置，从每个模式的五种课型中
  选择当前课型。每个课型同时声明教学目的、必需课程块、成果证据和质量底线；编程中的
  最小运行、调试、测试重构，人文中的材料解释、因果变化、观点论证等因此成为不同课型，
  而不是每节重复的固定栏目。分型和课型均由本地确定性规则完成，不增加模型调用。
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

### 2.1 自适应生成链与最终安全预算

`course_generation_v16 / course_prompt_v25` 先把目录、教案和正文拆成有边界、可恢复
的小工作单元，再把硬门作为最后安全熔断。目录与教案统一使用
`1 → N → 1` 分片路径；每次只发送当前单元的最小必要上下文，不发送整课正文、完整
证据库或随着小节数平方增长的前后列表。多小节单元仍不适配时继续拆分，最小单元才
使用本地确定性预览。目录局部保底依然需要用户确认；教案本地预览不得冒充完整 AI 语义质量，
必须停止下游生成并续跑失败单元。

v24 不增加生成阶段或模型调用。它把教师看到的总体教案确定性压缩为同源教学引领，
让详细教案批次和当前小节正文同时读取课程定位、总体成果、教学对象、学习起点、教学
主线、章节责任和评价证据。宏观教案只控制内容选择、讲法与评价对齐，不能修改已经
冻结的目录、知识身份、课程块集合、资料边界和难度合同。

v25 在同一稳定链内把学科画像升级为 V2：一级学科、必要分型、当前课型、成果证据和
质量底线进入章节骨架、详细教案与正文 Prompt；每节模块集合由当前课型确定，不再等于
整个学科模块清单。该变化仍不改变调用顺序、模型调用数、检查点或恢复协议。

用户未明确章数或总小节数时，需求 brief 写入“至少 6 章、至少 18 节”的完整课程
基线；用户明确给出数量时严格遵守该数量，但仍经过同一完整生成链。批次上限只限制
单次模型请求，不得反向压缩课程规模或变成默认课程长度。
默认值如下：

| 边界 | 默认值 | 作用 |
|---|---:|---|
| 单门课程小节数 | 不设产品硬上限 | 课程越大只增加目录、教案与正文的小工作单元，不构造整课大请求 |
| 最终单次模型输入 | 20,000 字符且 7,000 mixed-language estimated tokens | `system + user` 合并后同时通过两道硬门；约 4 万字符的请求不会触达提供方 |
| 候选模型总尝试 | 2 | 所有候选共享总次数，不再形成“候选数 × 每模型重试数” |
| 目录章节批次 | 每批 6 节 | 所有课程先生成轻量章节骨架；不同章并行，同章多批顺序衔接 |
| 教案骨架分片 / 详细单元 | 2 节 / 1 节 | 真实复跑显示两节完整教案已可逼近 8k 输出上限；详细语义按节并行，全课身份仍连续汇编 |
| 目录 / 教案连续无进展窗口 | 90 秒 | 模型推理、内容或容量队列活动都刷新窗口；不使用整单元或整课墙钟倒计时 |
| 全课阶段时限 | 无 | 以全部最小单元完成、失败或明确取消为结算条件 |
| 正文连续无进展窗口 | 90 秒 | 小节只要持续收到新内容就继续；连续无输出才取消当前小节并保留草稿，不设置单节或整课固定总时限 |
| 业务工作单元上限 | 目录 4 / 教案 4 / 正文 4 | 只限制本地同时准备的工作单元，不等于真实提供方并发 |
| 定向练习并发 | 同一小节最多 3 个练习位 | 只生成确定性质量门拒绝的练习位；不同小节逐节结算并保存，避免失败回滚整门题库 |
| 真实提供方并发 | 每模型初始 2，上限 4 | 跨目录、教案、正文和其他 AI 服务共享；连续成功扩容，限流/额度失败收缩与切换模型 |
| 正文应用层重试 | 1 | 复用已保存草稿续写；每次尝试重新按无进展窗口判断，不共享一个不断耗尽的总时限 |

环境变量只能在代码允许的上下界内调节，不能关闭单次输入、尝试次数和工作窗口保护，
也不能重新引入课程总小节数门禁。每个正式阶段和节点只保存非敏感运行指标，包括调用
数、累计与最大输入估算、实际 Prompt 细节等级、自适应拆分与降级单元、耗时、并发、
非流式时限、流式无进展窗口和输出字符数；不保存 Prompt 正文、密钥或模型推理。正文
草稿按节点写入独立原子 sidecar，读取工作区时叠加恢复；定稿、上游失效、发布和删除
时清理，流式热路径不再每 8 秒重写整门课程。恢复时只重做失败或未完成
单元，不重复已经通过的目录骨架、目录批次、教案骨架和教案批次。直接绕过自适应链的
超大请求仍会由最终硬门在本地拒绝。

2026-07-22 同输入真实验收使用 6 章 12 节概率论课程。基线在 510 秒后仍不可发布；
v15 首轮保留 11/12 节模型教案，最小单元续跑补齐剩余 1 节后完成 12/12 模型正文，
累计真实执行约 899 秒，最终实际发布成功。最大单次输入为 13,667 字符和 6,554
estimated tokens，发布时正文与资产阻断均为 0。未阻断告警主要是单知识点概念组、
待教师确认的综合测评和部分检查反馈排版，不得与“无警告”混为一谈。

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
