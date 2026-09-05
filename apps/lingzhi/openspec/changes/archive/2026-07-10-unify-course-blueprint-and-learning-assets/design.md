## Context

当前生产链已经固定为：

```text
CourseGenerationRequest
-> 唯一 GenerationJob
-> MaterialAsset / EvidenceCoveragePlan
-> SubjectPedagogyProfile / DifficultyProfile
-> CourseBlueprint / NodeGroundingContract
-> Markdown 节点正文
-> GenerationQualityReport
```

本变更在这条链路上增加“用户可控蓝图、不可变课程版本和正式学习资产”，不重写已稳定的资料、学科、难度和任务底盘。

## Goals / Non-Goals

### Goals

- 正文生成前可选地审阅蓝图，支持编辑、锁定、影响预览和确认。
- 课程和资产以候选版本生成，失败不污染当前有效版本。
- 题目、知识关系、掌握标准和误区共享证据、难度、版本与质量体系。
- 学习结果进入事件账本，课程资产与个人学习状态不再混写。
- 前端形成课程总览、章节闭环、正式练习、掌握清单和版本恢复体验。
- 所有旧消费者迁移后删除旧生产接口和通用回退内容。

### Non-Goals

- 不在本变更中实现扫描件 OCR、完整 PDF 排版导出或外部知识图谱数据库。
- 不建立复杂登录权限、多人协作合并或人工评审平台。
- 不让基础课程根据动态学习痕迹静默改变目标难度。
- 不把课程正文拆成固定内容块；完整 Markdown 继续是正文真源。

## Domain Model

```text
CourseGenerationBrief
-> BlueprintDraft
-> BlueprintRevision
-> LearningAssetPlan
-> CandidateCourseVersion
   ├── NodeContentRevision
   ├── QuestionRevision
   ├── CourseKnowledgeGraphRevision
   ├── MasteryCriterionRevision
   ├── MisconceptionRevision
   └── AssetQualityReport
-> Current CourseVersion
```

`BlueprintDraft` 可变并自动保存；确认或开始生成时冻结为不可变 `BlueprintRevision`。每个 `CourseVersion` 保存基础版本、变更原因、蓝图修订、节点正文修订、资产修订、证据/难度/生成器版本和质量状态。未变化对象复用修订 ID。

现有 `Storage._create_snapshot` 保持为故障恢复层。产品版本由独立 `CourseVersionRepository` 管理，恢复旧版本时创建新版本，不移动或删除历史。

## Blueprint Review And Jobs

请求增加 `generation_mode=fast|review_blueprint` 和课程目的/资产偏好。快速模式自动确认蓝图；审阅模式在完成蓝图、证据和难度检查后将同一任务置为 `waiting_for_review`，阶段为 `blueprint_ready`。

确认接口保存新的 `BlueprintRevision`，将同一任务重新入队。重启恢复只重新入队 `pending/running`，不会越过 `waiting_for_review`。局部再生成创建同类型 GenerationJob，增加 `operation=regenerate`、`base_version_id`、`affected_node_ids` 和 `candidate_workspace_id`，仍由同一个 TaskManager 执行。

候选工作区保存完整可恢复工作副本。节点和资产全部通过后才原子提升为当前版本；失败、取消和基础版本冲突时保留当前课程。

## Impact Analysis And Locks

影响分析比较字段语义而不是时间戳：

- 显示名称只确定性同步。
- 学习目标影响掌握标准、检测题和清单。
- 难度影响题目、掌握阈值、提示与反馈，不修改知识事实。
- 证据变化影响绑定该证据的正文、题目、关系和误区。
- 前置关系变化沿显式依赖传播。
- 学科或课程目的变化重新编译资产计划，再按差异确定范围。

规划锁定、正文锁定和资产锁定只阻止自动改写，不阻止过期检测。锁定对象失去契约一致性后进入 `locked_conflict`，不能继续作为有效掌握证据。

## Learning Assets

`LearningAssetPlan` 由课程目的、主辅教学模式、节点难度和证据编译。课程目的为系统学习、期末突击、资料整理或个性化补救；学习电子书/PDF 属于呈现载体，不另建教学策略。

- `QuestionRevision` 保存题型、题干、答案、解析/量规、知识点、误区、证据和难度契约。开放任务不伪装成唯一答案题。
- `CourseKnowledgeGraphRevision` 保存稳定概念、类型化关系、证据状态和课程绑定。AI 关系先为候选，不直接进入正式真源。
- `MasteryCriterionRevision` 绑定学习目标、可观察表现、阈值、支架和检测方式。
- `MisconceptionRevision` 保存错误表现、触发、原因、样例、辨析、概念、题目与依据；个人错误只进入学习事件。
- 总览和检查清单由蓝图、资产绑定、学习事件与学习者模型确定性投影。

正文与资产从同一冻结输入并行产生，不把生成正文当资料证据。最终交叉检查正文覆盖、图谱概念、题目检测、解析一致性和掌握标准绑定。

## Quality Gates

每项资产依次执行：

1. schema 与绑定完整性检查。
2. 资料证据与难度契约检查。
3. 学科验证器：数学数值/符号、代码编译/测试、自然科学单位/容差、开放任务量规。
4. 语义复核：可回答性、答案解析一致性、真实误区、关系可信度。
5. 整课覆盖：学习目标、题型、难度、证据和必选资产覆盖。

确定性问题确定性修复；语义问题至多一次定向 AI 修复。必选资产仍失败则阻止候选版本提升；可选资产可以跳过并报告。禁止通用无关题或占位资产填充数量。

## Module Ownership

- 资料与证据：原文件、解析文档、EvidenceUnit。
- 课程与生成控制：brief、蓝图、目标、掌握标准、资产计划、课程绑定、课程版本。
- 题库与评价：题目、答案、解析、量规和修订。
- 知识体系：概念、关系、别名、通用误区、证据与候选状态。
- 学习痕迹：阅读、笔记、作答、错题、复习、自我确认和导师操作事实。
- 学习者模型：掌握、薄弱、准备度和置信度推断。
- AI 老师：读取以上对象提出解释、建议和 `RegenerationRequest`，不直接修改真源。
- TaskManager：只负责任务状态、调度、检查点和事件推送。

## Migration And Deletion

- 旧课程第一次读取时生成最小蓝图和 `CourseVersion`，不修改旧字段语义。
- `quiz_score` 和 `review_history` 通过稳定迁移 ID 转为学习事件；重复迁移不重复写入。新写入只进入事件账本。
- 前端将 localStorage 错题/测验历史幂等提交到迁移接口，成功后标记迁移版本并停止作为真源。
- 旧课程知识图谱导入为课程图谱修订，AI 节点标记为未验证候选，用户节点保留来源。
- 新消费者上线后删除 `/api/generate_quiz`、`/api/similar_quiz`、通用 fallback、直接覆盖图谱的生成接口和旧大纲整体替换接口。
- `GlobalKnowledgeGraph` 只保留生成期术语去重与一致性辅助，不充当产品图谱仓库。

## Frontend Information Architecture

- `CourseTree` 增加课程总览、综合检测和章节掌握状态。
- `ContentArea` 支持阅读模式与练习模式；章节末尾显示目标、掌握、误区和练习。
- `SmartBar` 的“出题”改为“练习”，只打开正式题目资产。
- 知识图谱保留全屏画布，学习模式只读，编辑模式管理候选和课程绑定。
- 课程更多菜单提供版本、比较、恢复和完整质量报告。
- 右侧笔记与错题继续属于学习痕迹，AI 面板只消费上下文。

## Risks / Trade-offs

- 变更面大：一个 OpenSpec 内按版本底盘、任务接入、资产、事件迁移、前端和删除六个里程碑逐段验证。
- 文件仓库并发：所有 manifest 和候选工作区使用课程级锁、原子替换和基础版本检查。
- 旧数据混杂：迁移只新增事件与修订，旧字段先只读，确认消费者迁移后再停止读取。
- 自动验证能力有限：开放任务明确使用量规或人工确认状态，不制造虚假的机器精确判分。
