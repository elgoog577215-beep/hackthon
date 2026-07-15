## ADDED Requirements

### Requirement: 每门新课程必须拥有可生长的课程知识库

系统 MUST 在首次课程生成工作区中同时生成 `CourseKnowledgeBase`，并在正式课程发布时将其与同一 `course_id` 的 `CourseDocument`、学习目标、题目和 `CourseKnowledgeMap` 一起激活。课程知识库 MUST 只服务当前课程，且 MUST 区分课程局部节点与跨课程正式知识引用。

#### Scenario: 首次课程质量通过并发布

- **WHEN** 课程正文、学习资产和课程知识库均通过质量门
- **THEN** 系统 MUST 使用同一 `course_id` 发布课程文档与课程知识库
- **AND** 每个可教学知识节点 MUST 能定位相关课程块或学习目标
- **AND** 系统 MUST NOT 把模型生成的课程局部节点伪装成跨课程正式知识

#### Scenario: 首次课程知识库质量失败

- **WHEN** 课程知识库存在无环、引用、颗粒度或来源硬错误
- **THEN** 首次生成 MUST 保留工作区供修订
- **AND** 系统 MUST NOT 发布正文与知识关系不一致的正式课程

### Requirement: 课程知识库必须支持候选式细化

AI MUST 能针对当前课程知识节点生成新增、补写、拆分、合并、移动、重命名和关系调整候选。所有候选 MUST 固定基础知识库修订、原因、证据、影响范围和质量报告；用户确认前 MUST NOT 修改活动知识库。

#### Scenario: AI 发现知识颗粒度不足

- **WHEN** 多个独立教学对象被压在一个无法分别解释、练习和诊断的粗节点中
- **THEN** AI MUST 能生成节点拆分候选
- **AND** 候选 MUST 列出新节点、旧新 ID 映射、正文引用和学习资产影响
- **AND** 当前活动知识库 MUST 保持不变直到用户确认

#### Scenario: 用户拒绝知识细化

- **WHEN** 用户拒绝当前节点细化候选
- **THEN** 活动知识库 MUST 保持原修订
- **AND** 系统 MUST 保存拒绝记录与证据修订冷却

### Requirement: 正式学科知识库与课程知识库必须保持治理隔离

`SubjectKnowledgeLibrary` MUST 继续作为跨课程正式语义真源，学生课程 AI MUST NOT 自动创建、修改或删除正式知识 ID。`CourseKnowledgeBase` MAY 保存未映射或部分映射的课程局部节点，并 MUST 通过 `CourseKnowledgeMap` 记录映射状态与置信度。

#### Scenario: 课程新增正式库未覆盖的知识

- **WHEN** 当前课程需要一个无法精确映射正式知识库的独立知识点
- **THEN** 系统 MUST 将其保存为当前课程局部节点或待治理候选
- **AND** 系统 MUST NOT 自造正式知识 ID
- **AND** 其他课程 MUST NOT 自动读取该个人课程节点

#### Scenario: 课程节点精确命中正式知识

- **WHEN** 课程节点名称或正式别名精确命中现有正式知识
- **THEN** `CourseKnowledgeMap` MUST 保存正式引用和课程局部表达
- **AND** 课程局部顺序或描述变化 MUST NOT 改写正式学科层级

### Requirement: 课程与知识库必须进行双向影响分析

任何已提出的知识结构变化 MUST 计算对正文块、学习目标、正式题目、掌握标准和映射的影响；任何改变课程语义覆盖的正文变化 MUST 检查课程知识库是否需要补写、细化或重新映射。影响分析 MUST 生成候选，不得未经确认级联写入正式对象。

#### Scenario: 知识节点拆分影响正文与题目

- **WHEN** 用户确认查看一个知识节点拆分候选
- **THEN** 系统 MUST 列出已有覆盖、缺失覆盖和需要重映射的课程对象
- **AND** 系统 MUST 只为真实缺口生成关联课程操作
- **AND** 已经覆盖的新细节点 MUST NOT 被重复生成内容

#### Scenario: 正文新增独立知识内容

- **WHEN** 一个课程内容候选新增可独立解释、练习和诊断的知识对象
- **THEN** 系统 MUST 生成补写或新增课程知识节点的关联候选
- **AND** 用户 MUST 能分别预览课程变化和知识变化

### Requirement: 双向联动必须具有单一因果链和循环抑制

同一跨域变化 MUST 使用一个 `change_set_id`、因果来源和依赖图。系统 MUST 对重复请求幂等处理，MUST NOT 将知识变化引发的课程变化再次识别为一条全新的相同知识变化。

#### Scenario: 知识拆分引发课程补写

- **WHEN** 课程补写由同一变更集中的知识拆分操作产生
- **THEN** 影响分析 MUST 标记其因果来源
- **AND** 再次分析该课程补写时 MUST NOT 生成重复知识拆分

#### Scenario: 联动期间基础修订变化

- **WHEN** 课程文档、课程知识库或映射修订在确认前发生变化
- **THEN** 关联变更集 MUST 标记为过期或冲突
- **AND** 系统 MUST 基于当前修订重新计算完整影响

### Requirement: 知识引用迁移必须保护历史事实

知识节点拆分、合并、移动和墓碑 MUST 保存稳定旧新 ID 映射。历史 `PracticeAttempt`、学习事件、诊断和记录 MUST 保留发生时的知识引用，当前投影 MAY 使用映射解释，但 MUST NOT 重写历史证据。

#### Scenario: 有历史作答的知识节点被拆分

- **WHEN** 一个被历史作答引用的课程知识节点被接受拆分
- **THEN** 历史 Attempt MUST 保留原知识引用和修订
- **AND** 系统 MUST 保存旧节点到新节点的映射
- **AND** 当前课程和后续任务 MUST 使用新修订引用
