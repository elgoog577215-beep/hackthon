## ADDED Requirements

### Requirement: 个人学习适配必须使用结构化方案

AI 对当前学习现场的持久个人适配 MUST 形成 `PersonalAdaptationPlan`，其中每个 `PersonalAdaptationOperation` MUST 包含操作类型、基础目标引用、个人前后差异、理由、证据、范围、依赖、预期基础修订和质量状态。自由文本回答 MUST NOT 被直接解释为已应用个人适配。

#### Scenario: AI 只补写原块的一行

- **WHEN** 适应判断只要求在现有段落增加一个边界说明
- **THEN** 系统 MUST 生成 `PATCH_PERSONAL_SPAN` 或等价个人行级覆盖操作
- **AND** MUST 保留未修改内容和原 `block_id`
- **AND** MUST 提供精确行内差异

#### Scenario: AI 需要组合多种修改

- **WHEN** 一个前置缺口需要补写定义、插入例子并调整后续检查
- **THEN** 系统 MUST 生成一个含多个依赖操作的个人适配方案
- **AND** 每个操作 MUST 可独立预览

### Requirement: 个人覆盖层必须支持完整适配操作

个人覆盖层服务 MUST 支持行级个人补充、插入或替换个人块、隐藏个人视图中的块、个人路径预调、检查点、补救路径和个人难度差异。所有操作 MUST 保留基础课程目标引用，不得修改、移除或重排基础 `CourseBlock`。

#### Scenario: 拆分过密课程块

- **WHEN** 用户确认将一个过密块在个人视图中展开为定义、推导和例子三个个人块
- **THEN** 系统 MUST 保存三个个人块到同一基础块的来源映射
- **AND** 仍可唯一定位的笔记和记录 MUST 迁移到对应新块
- **AND** 不确定锚点 MUST 进入待确认而非静默附着

#### Scenario: 重排存在活动任务的块

- **WHEN** 方案要在个人路径中调整一个被当前 Attempt 引用的正式任务周边内容
- **THEN** 影响分析 MUST 显示活动任务风险
- **AND** 当前 Attempt MUST 继续使用开始时冻结的任务与课程修订

### Requirement: AI 必须支持当前、向后和向前的个人适配

适应规划 MUST 能覆盖当前学习位置、为已经学习的上游位置增加个人补充，并根据知识与目标依赖提前调整未学习的后续个人视图。所有方向的持久变化 MUST 进入个人方案层。

#### Scenario: 第二节暴露后续前置缺口

- **WHEN** 当前第二节的强证据表明第三至第五节依赖的前置知识不足
- **THEN** 系统 MUST 能在第三至第五节生成桥接、例子或检查点候选
- **AND** 左侧目录 MUST 能显示未来范围的待处理提示
- **AND** 基础后续章节 MUST 在确认前后保持原修订

#### Scenario: 后续错误证明前面定义不充分

- **WHEN** 独立诊断表明错误源于前面定义遗漏的边界
- **THEN** 系统 MUST 能为原定义块生成向后修补候选
- **AND** 历史作答 MUST 保留发生时的旧内容语境

### Requirement: 难度变化必须编译为真实课程组成

任何个体难度调整 MUST 明确描述知识颗粒度、抽象程度、推导完整度、例子、支架、任务复杂度、知识跨度、节奏、反馈或掌握要求中的变化，并 MUST 通过个人覆盖内容、个人任务建议或个人难度差异体现。系统 MUST NOT 修改基础知识节点、正式任务或基础难度契约，也不得将单纯增加篇幅、术语或题量视为有效调整。

#### Scenario: 学生需要更低门槛的推导

- **WHEN** 强证据支持降低当前推导门槛
- **THEN** 候选 MUST 指明增加的中间步骤、桥接或检查点
- **AND** `difficulty_delta` MUST 说明支架和推导完整度变化

#### Scenario: 学生已经稳定掌握基础内容

- **WHEN** 多个独立正式证据证明学生可无支架完成基础任务
- **THEN** 系统 MAY 推荐压缩已知解释并增加迁移任务
- **AND** MUST 保留必要检查点和用户确认

### Requirement: AI 可以生成高权限候选但不得代替确认

AI MAY 在方案层生成任何合法个人覆盖操作，但 MUST NOT 生成基础课程或知识库写操作，也不得将方案标记为用户接受或调用接受接口。只有当前学习者的明确操作才能确认个人适配。

#### Scenario: AI 主动发现全课程模式

- **WHEN** 证据达到广域调整门槛
- **THEN** AI MAY 生成多章节候选并推荐范围
- **AND** MUST 等待用户接受
- **AND** 未确认变化 MUST 清楚标记为 AI 候选

### Requirement: 个人方案与覆盖层不得成为基础课程真源

学习页面 MAY 将 `CourseDocument`、待确认 `PersonalAdaptationPlan` 与已确认 `PersonalCourseOverlay` 叠加渲染，但基础课程 API、目录结构修订和课程领域对象 MUST 继续以 `CourseDocument` 为唯一基础真源。用户与个人内容的交互 MUST 引用方案或覆盖操作 ID。

#### Scenario: 用户阅读未确认新增块

- **WHEN** 用户展开并学习一个待确认候选块
- **THEN** 页面 MUST 持续显示其候选身份
- **AND** 基础 `CourseDocument` 修订 MUST 在确认前后保持不变
- **AND** 相关交互 MUST 关联候选和操作 ID

#### Scenario: 用户完成候选中的非正式检查

- **WHEN** 用户回答待确认候选中的非正式理解检查
- **THEN** 系统 MAY 记录候选效果证据
- **AND** MUST NOT 自动将结果投影为正式掌握

### Requirement: 确认个人方案必须通过可恢复个人操作组应用

系统 MUST 在确认时校验身份、课程归属、用户选择范围、基础课程与知识修订、个人操作依赖和质量报告。所有已接受操作 MUST 作为一个逻辑个人操作组写入 `PersonalCourseOverlay`，并 MUST 返回持久、幂等 `ActionReceipt`；操作组 MUST NOT 调用基础课程或课程知识库写命令。

#### Scenario: 用户接受多位置个人适配方案

- **WHEN** 所有前置修订一致且质量通过
- **THEN** 系统 MUST 一次逻辑应用被接受的个人覆盖操作
- **AND** MUST 只更新个人覆盖层修订和操作日志
- **AND** 重复确认 MUST 返回原回执

#### Scenario: 命令组中途失败

- **WHEN** 任一领域操作无法提交
- **THEN** 系统 MUST 保持原个人覆盖层修订或进入可自动完成、可补偿的明确恢复状态
- **AND** MUST NOT 将半应用结果报告为成功

### Requirement: 个人适配必须只作用于当前学习者覆盖层

已确认个人适配 MUST 只更新当前学习者、当前 `course_id` 的 `PersonalCourseOverlay`。系统 MUST NOT 修改基础 `CourseDocument`、当前 `CourseKnowledgeBase`、启智教师课程、共享模板、其他学习者覆盖层或跨课程正式学科库。

#### Scenario: 学生接受全课程详细化

- **WHEN** 学生确认把调整范围应用到全课程
- **THEN** “全课程” MUST 只指当前 `course_id`
- **AND** 其他课程和共享来源 MUST 保持不变
