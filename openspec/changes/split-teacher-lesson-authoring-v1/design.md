## Context

灵知学生端以一次耐久 `course_generation` 任务生成目录、全课教案、课程正文、练习和发布课程，学习页在任务运行时主动读取 generation preview。这套编排对学生自建课程成立，但教师端需要按学期讲次逐次备课：教师先确定讲数并确认大纲，再任选一讲生成包含全部讲内小节的教案，编辑或 AI 优化后制作本讲 PPT。当前教师页只是投影整课任务，造成四个直接问题：

1. 教师确认大纲后仍自动进入全课教案、正文和发布链；
2. 教案批次按 token 容量跨讲切分，批次计划在恢复时会变化，单批失败反复重跑；
3. 顶层讲次 ID 与讲内小节 ID 被折叠成一个选择状态，URL 已切换但正文仍回到本讲首节；
4. PPT 工作台读取课程级 CourseDocument/全课教案，无法表达“本讲教案修订 → 本讲 PPT”。

当前 worktree 已经隔离 `/teacher` 路由，但教师与学生仍共享课程任务和文档数据。此次变更只完善灵知教师端能力，不接教育智能体，不改变学生端课程生成、正文、学习、练习、笔记、AI 老师或现有 PPT 路由语义。

## Goals / Non-Goals

**Goals:**

- 教师输入的讲次数成为大纲一级讲次的硬约束，默认讲次时长可单讲覆盖。
- 大纲确认后停止教师大纲任务；不自动生成教案、课程正文或学生发布。
- 每讲拥有独立、可恢复的教案任务和资产修订；一次生成该讲全部小节。
- 结构有效的本地降级教案以 `completed_with_warnings` 完成，AI/模型失败只影响当前讲。
- 左侧当前讲展开全部小节，讲次与小节分别寻址；支持单节、整讲和真实上一节/下一节。
- 每讲教案草稿可手动编辑、自动保存和 AI 差异优化；接受候选产生新草稿修订。
- 每讲教案草稿可按需生成本讲主 PPT；PPT 绑定精确教案修订并支持独立 AI 优化。
- 学生端任务、路由、CourseDocument、学习记录和测试保持不变。

**Non-Goals:**

- 不生成教师课程正文，不把教师草稿写入学生 CourseDocument。
- 不实现教师发布给学生、班级授权或学生反馈回流。
- 不迁移教学日历、文件空间、已有课程或大纲导入。
- 不接教育智能体、PostgreSQL 或新的 AI 提供方。
- 不在首条纵向链实现批量生成全部未完成讲次、完整教师知识库页面或复杂补充课件管理。

## Decisions

### 1. 教师编排使用独立任务类型，不复用学生整课状态机

新增：

```text
teacher_outline_generation
teacher_lesson_plan_generation
teacher_lesson_ppt_generation
```

教师新建入口可复用现有需求、材料、检索、目录规划和 AI 调用，但必须通过 teacher orchestration 路由创建教师任务。学生的 `course_generation`、guided workflow、generation preview 和 `LearningView` 不改变。

**替代方案：**给现有 `course_generation` 增加更多分支。拒绝，因为学生页面会继续观察教师任务，正文/发布状态也会重新耦合。

### 2. 教师大纲任务只生成到确认大纲

教师新建课程将 `expectedSessions` 映射为明确讲次数，而不是总小节数。生成请求冻结：

```text
lesson_unit_count
default_lesson_duration_minutes
per_lesson_duration_overrides
```

AI 必须返回恰好该数量的一级讲次，每讲含一个或多个二级小节。教师确认后冻结 `outline_revision_id` 和知识依据快照，任务结束为 `completed`；不会进入全课教案或正文阶段。

### 3. 教师讲次资产独立持久化，不写学生 CourseDocument

新增教师专属仓库 `TeacherLessonAuthoringRepository`，按 `course_id` 保存：

```text
outline_revision_id
lesson_units[]
lesson_plan_assets[lesson_unit_id]
  working_revision_id
  confirmed_revision_id
  revisions[]
ppt_assets[lesson_unit_id]
  primary_asset_id
  assets[]
```

每个修订记录来源大纲/知识版本、生成来源、警告、时间和内容摘要。仓库使用现有文件仓库的临时文件 + `os.replace` 原子写模式；不会复制学生课程正文。

### 4. 一讲是任务边界，小节是讲内编辑/展示边界

`teacher_lesson_plan_generation` 请求必须包含稳定 `lesson_unit_id`。服务从冻结大纲选择该讲及其所有二级小节，构建稳定作用域；技术批次不得跨讲。任务 ID、检查点和幂等键绑定：

```text
course_id + lesson_unit_id + outline_revision_id + request_id
```

生成结果形成一个 `LessonPlanAsset`，内部包含全部小节。单节 AI 优化只改变该资产的新草稿修订，不创建另一份讲次资产。

### 5. 批次计划冻结，结构有效降级视为可用完成

讲次任务首次运行时保存稳定 batch spec；恢复直接读取原 spec，批次 ID 由 section IDs 摘要确定，不按每次计算顺序重新编号。模型结果若不通过结构校验，只重试当前讲的当前批次一次；仍失败则使用确定性编译结果。确定性结果通过校验时任务状态为 `completed_with_warnings`，资产标记 `needs_ai_review`，允许编辑、AI 优化和生成 PPT。

### 6. 讲次与小节拥有两个路由状态

教师生产页使用：

```text
?stage=teaching&lesson=<L1>&section=<L2>&view=section|lesson
```

左侧只展开当前讲并列出全部小节。单节模式的上一节/下一节在课程有序小节中移动，并在边界明确跨讲；整讲模式切换上一讲/下一讲。组件不得把小节 ID 再解析回讲次 ID 后传给教案正文。

### 7. 教案编辑与 AI 优化以候选修订工作

手动编辑自动保存当前 working revision；显式确认创建/推进 confirmed pointer。AI 优化接收整讲或单节 scope，返回可审阅字段差异；接受项写入新 working revision，拒绝不改变当前草稿。涉及知识语义变化只返回知识建议，不直接修改共享知识依据。

### 8. 本讲 PPT 使用教案作者态来源，不需要学生正文

教师讲次 PPT 服务把本讲教案的课堂路径、知识与评价、活动和作业编译成 PPT 作者态 source contract，再复用现有 V6 规划、模板、渲染和导出能力。PPT 修订记录 `source_lesson_plan_revision_id`；教案来源变化只把对应 PPT 标记为 `stale`，不删除最后可用版本。

首条纵向链只交付每讲一套主课件和版本历史；数据合同预留补充课件角色。学生现有 course-level PPT 接口不改变。

### 9. 教师知识依据先用讲次抽屉，数据合同支持后续全课页面

教师不增加知识库一级导航。每讲教案提供“本讲知识依据”抽屉，读取冻结知识快照中当前讲的知识点、来源和冲突。接口允许省略 `lesson_unit_id`，为后续完整教师知识库页面保留扩展，但本轮 UI 只实现讲次筛选。

## Risks / Trade-offs

- **教师资产与学生 CourseDocument 暂时并存** → 通过 teacher 命名空间、独立仓库和零学生写入测试防止双向污染；发布映射留给后续 change。
- **现有 V6 强依赖 CourseDocument** → 新增作者态 source adapter，禁止把讲次教案伪装并保存为学生正文。
- **当前 AI 输出经常知识 ID 不匹配** → 冻结讲次知识作用域、缩小 prompt、单批一次纠正和结构有效降级完成。
- **UI 同时支持讲/节可能再次混淆** → 路由、store 和组件 prop 明确拆为 `lessonUnitId` / `sectionNodeId`，加入刷新与导航回归。
- **任务类型增加造成全局轮询噪声** → 教师 adapter 只观察当前教师任务；学生 generation store 不消费教师任务。
- **范围较大** → 按“导航修复 → 教师大纲停靠 → 按讲教案任务 → 教案编辑/AI → 按讲 PPT”逐步验证；任何阶段不通过时保留原学生路径。

## Migration Plan

1. 先增加新类型、仓库和后端契约测试，不接 UI。
2. 修复教师讲/节双选择，先让现有数据可正确浏览。
3. 教师创建请求传递硬讲数并在大纲确认后停止教师任务。
4. 接入按讲教案任务、降级和恢复；一门测试课只生成任意一讲。
5. 接入手动编辑、AI 候选与讲次知识抽屉。
6. 接入本讲 PPT 作者态适配和主课件工作台。
7. 运行学生端、教师端、构建和真实浏览器回归。

回滚只需隐藏新 teacher lesson endpoints/页面状态并恢复教师页读取旧投影；学生任务和数据不需要迁移或回滚。

## Open Questions

第一条纵向链没有未决产品问题。补充课件高级 UI、旧课程升级、大纲导入、批量生成、教学日历、文件空间和师生发布均进入后续 change。
