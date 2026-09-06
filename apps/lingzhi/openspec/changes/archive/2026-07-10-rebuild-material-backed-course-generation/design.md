## Context

课程生成当前具备若干正确底盘：唯一 `/api/course-generation/generate` 入口、`CourseService` 课程 AI 门面、TaskManager 的 asyncio 队列和节点并发、WebSocket 推送与 HTTP 轮询降级、课程原子写入与版本快照、完整 Markdown `node_content`。这些能力继续保留。

需要替换的是生成内核：旧 `DisciplineType` 把数学、自然科学、生命科学和语言学习混在一起；正文 prompt 强制每节写固定板块；`generation_task`、TaskManager task 和前端 local task 表达同一任务；`CourseService` 依赖进程内 plan/settings/context；质量报告在节点生成前创建；质量评分主要奖励标题、字数、加粗、代码和公式。

## Goals / Non-Goals

**Goals:**

- 建立唯一、可持久化、可恢复的 `GenerationJob`。
- 完整实现学科教学画像和模块化课程结构。
- 让课程蓝图成为正文生成的真实执行契约。
- 让 prompt、质量检查和修复全部读取同一教学画像与模块计划。
- 支持多课程并行、真实暂停、重启续跑和分阶段进度。
- 删除旧运行时分类、固定正文板块和课程生成旁路。

**Non-Goals:**

- 本变更不提前确定后续难度设计的完整教学规则，只保留现有三档输入并解除公式密度等跨学科硬编码。
- 本变更不新增默认联网搜索或外部 provider 抽象。
- 本变更不在没有真实解析器时假装支持 PDF/PPT 正文解析；二进制资料保持 `metadata_only`。
- 本变更不完成蓝图编辑器、配套题库和知识图谱展示的最终产品形态，但为它们保存稳定契约。

## Target Workflow

```text
POST /api/course-generation/generate
-> 创建课程草稿与唯一 GenerationJob
-> requirement_analysis
-> material_processing
-> pedagogy_resolution
-> blueprint_generation
-> blueprint_validation
-> content_generation
-> content_validation
-> finalizing
-> completed
```

创建接口立即返回 `202` 语义的数据。所有阶段、节点状态、错误、草稿和报告都挂在同一个 `job_id` 上。默认自动继续；未来蓝图预览可把任务停在 `blueprint_ready`，再通过统一任务继续接口推进，不再创建第二个正文任务。

## Canonical Contracts

### GenerationJob

- `id`、`course_id`、`type=course_generation`
- `status`：`pending/running/paused/completed/failed/cancelled`
- `phase`、`progress`、`phase_progress`
- `request_snapshot`
- `node_states`、`node_drafts`
- `completed_nodes`、`total_nodes`
- `created_at`、`updated_at`、`error`

### SubjectPedagogyProfile

- `profile_version`
- `primary_mode`
- `secondary_mode`
- `secondary_intensity`：`light/collaborative/dual_core`
- `confidence`、`evidence`、`rationale`
- `enabled_module_ids`
- `user_locked`

实际主模式只允许：`general`、`math_formal`、`programming_engineering`、`natural_science`、`life_medical`、`humanities_social`、`language_learning`、`business_career`。`auto` 只允许出现在请求中。

### CourseBlueprint

- 课程定位、学习成果、前置依赖和章节节点。
- `pedagogy_profile`。
- 课程级 `course_module_plan`。
- 每个节点的目标、范围、资料引用、知识点、误区、验收标准和 `module_plan`。
- 蓝图质量报告、资料覆盖计划和 schema 版本。

### GenerationQualityReport

- 只能在节点正文生成和节点检查完成后生成。
- 聚合教学画像有效性、蓝图有效性、节点模块履约、失败/警告节点、资料覆盖、brief 满足情况和最终状态。
- 预生成阶段只能产生 `BlueprintValidationReport`，不得冒充最终报告。

## Pedagogy Composition

最终结构由以下部分组成：

```text
通用骨架 + 主模式模块包 + 辅模式注入 + 后续难度规则 + 资料规则
```

主模式拥有课程顺序和最终考核。辅模式只在依赖点注入；相同模块去重；普通节点至多承载一个辅模式核心模块，双核课程可拥有独立辅模式单元。模块是语义契约，不要求成为固定 Markdown 标题。

## Backend Boundaries

- `CourseService` 保留为唯一课程 AI 门面，但不再保存生成真源；课程记录和 GenerationJob 是真源。
- `course_generation_workflow` 负责确定性中间对象和上下文格式化，不创建第二套任务。
- TaskManager 负责生命周期、阶段、并发、取消、恢复、检查点和事件推送，不编写 prompt。
- 单一课程 prompt 编排器负责教学画像、蓝图、正文和定向修复四类 prompt。
- 初始蓝图和基础正文只读取冻结的生成请求、资料、教学画像和课程蓝图；动态 `LearnerState/TeachingDecision` 只进入导师补救和用户主动重写。
- 知识图谱是蓝图概念依赖的派生产物，不作为进程内生成真源。

## Scheduling And Recovery

- 消费循环只负责派发任务，不得等待一门课程全部完成后才读取下一门。
- 使用课程级并发限制和全局节点并发限制。
- 暂停任务必须停止新节点并取消正在运行的调用；已收到草稿必须保存为检查点。
- 服务启动时将中断的 `running` 任务恢复为 `pending` 并重新入队；已完成节点不重复生成。
- 任务文件使用固定路径和原子替换写入。
- 前端 localStorage 只缓存 job 引用，恢复时以后端状态覆盖本地状态。

## Quality Gates

1. 教学画像闸门：模式合法、证据存在、主辅不重复。
2. 蓝图闸门：节点 schema、依赖无环、必备模块覆盖、资料引用有效。
3. 节点闸门：检查当前节点目标、主模块产出、学习者行动、反馈和格式。
4. 全课闸门：检查全部节点状态、模块覆盖、资料覆盖和最终成果。

确定性问题优先确定性修复。语义内容问题至多触发一次定向 AI 修复；修复后重新检查。仍不通过时保存内容并标记警告或失败，不无限重写。

## Migration And Deletion

- 旧课程学科值只通过 `legacy_mode_alias` 读取，并根据课程主题补充判断；新请求和新课程不得写旧值。
- `content_blocks` 只为旧数据和旧局部接口兼容；新正文写入空数组或不写入。
- 前端与后端在同一变更中切换到唯一任务，随后删除 `/auto_generate`。
- 所有消费者迁移后删除旧学科配置、V5 prompt 引擎、QualityPredictor、ContentFixer、旧关键词一致性校验和死生成分支。

## Risks / Trade-offs

- 变更面大：按契约、教学内核、质量、调度、前端、删除六个阶段推进，每阶段运行针对性测试。
- 模型结构化输出不稳定：所有结果都经过 schema 归一化，并保留确定性 fallback。
- 暂停草稿续写可能重复：续写 prompt 只允许输出追加内容，最终质量闸门检查重复和结构。
- 旧课程字段不完整：读取适配器从主题、节点和现有元数据恢复最小画像，不修改原文件。
