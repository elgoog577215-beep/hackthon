# course-blueprint-versioning Specification

## Purpose
TBD - created by archiving change unify-course-blueprint-and-learning-assets. Update Purpose after archive.
## Requirements
### Requirement: 蓝图必须拥有可审阅草稿和不可变修订

系统 MUST 将可编辑 `BlueprintDraft` 与不可变 `BlueprintRevision` 分开。草稿修改 MUST 经过 schema、依赖和锁定校验；确认或开始生成时 MUST 冻结为新修订，后续任务不得静默吸收草稿新变化。

#### Scenario: 用户修改并确认蓝图

- **WHEN** 用户保存课程目标、章节、难度、资料或资产计划修改
- **THEN** 系统 MUST 保存工作草稿并返回影响预览
- **AND** 确认时 MUST 创建不可变 BlueprintRevision
- **AND** 生成任务 MUST 绑定该修订 ID

### Requirement: 蓝图审阅必须在同一 GenerationJob 内等待

课程生成 MUST 支持快速模式和蓝图审阅模式。审阅模式 MUST 在轻量课程目录已经
通过形状、顺序、唯一责任和学习目标检查，但尚未生成逐节知识包之前，于同一任务
的 `outline_ready` 阶段进入 `waiting_for_review`。确认后继续原任务；服务重启不得
自动越过等待状态。快速模式 MUST 在相同检查通过后自动冻结目录修订，再进入逐节
知识包生成。

#### Scenario: 审阅模式生成课程

- **WHEN** 请求使用 `review_blueprint`
- **THEN** 系统 MUST 完成资料、教学画像、难度、轻量目录和目录质量检查
- **AND** MUST 暂停在 waiting_for_review
- **AND** MUST 通过确认接口继续同一个 job_id
- **AND** 确认前 MUST NOT 生成原子知识、知识关系、正文或正式学习资产

### Requirement: 修改必须产生确定性影响报告

系统 MUST 根据字段语义、显式依赖、证据绑定和资产绑定计算影响，不得仅比较时间戳或让 AI 决定失效范围。

#### Scenario: 修改一个节点难度

- **WHEN** 用户只修改一个节点的难度契约
- **THEN** 影响报告 MUST 包含该节点的题目、掌握标准、提示和反馈
- **AND** MUST NOT 自动使无关节点正文或知识事实失效

#### Scenario: 修改资料证据

- **WHEN** 某个 EvidenceUnit 失效或绑定策略变化
- **THEN** 系统 MUST 只标记引用该证据的正文和资产
- **AND** MUST 沿类型化下游依赖传播到清单与质量报告

### Requirement: 锁定必须阻止改写但保留冲突可见性

规划、正文和资产锁定 MUST 阻止自动改写。锁定对象与新契约不一致时 MUST 标记 `locked_conflict`，不得静默解锁，也不得继续充当有效掌握证据。

#### Scenario: 锁定题目失去证据

- **WHEN** 锁定题目引用的证据被删除
- **THEN** 题目 MUST 保留旧修订并标记锁定冲突
- **AND** 对应掌握标准 MUST 显示暂时无法验证

### Requirement: 课程版本必须与故障快照分离

系统 MUST 维护不可变 CourseVersion，引用蓝图、节点正文和资产修订。现有文件快照 MAY 继续用于损坏恢复，但 MUST NOT 作为用户版本历史或比较 API。

#### Scenario: 局部生成成功

- **WHEN** 受影响节点和资产全部通过质量闸门
- **THEN** 系统 MUST 创建新 CourseVersion
- **AND** 未变化对象 MUST 复用旧修订 ID
- **AND** 新版本 MUST 原子成为当前版本

#### Scenario: 候选生成失败

- **WHEN** 必选节点或资产仍未通过质量闸门
- **THEN** 候选 MUST NOT 覆盖当前版本
- **AND** 当前课程 MUST 继续可读

### Requirement: 恢复历史版本必须创建新版本

恢复操作 MUST 从历史快照创建新的 CourseVersion，不得删除后来版本或回退版本号。

#### Scenario: 从 v6 恢复到当前 v9

- **WHEN** 用户恢复 v6
- **THEN** 系统 MUST 创建内容等同 v6 的新版本 v10
- **AND** v6 到 v9 MUST 继续可查看和比较

### Requirement: 同课程并发候选必须保护基础版本

每个候选 MUST 保存 `base_version_id`。基础版本已经变化的候选完成时 MUST 进入冲突状态，不得静默覆盖新的当前版本。

#### Scenario: 两个候选基于同一版本

- **GIVEN** A 和 B 都基于 v8
- **WHEN** A 先提升为 v9，B 后完成
- **THEN** B MUST 保持候选并报告基础版本冲突
- **AND** 用户 MUST 能比较、重新基于 v9 生成或放弃 B
