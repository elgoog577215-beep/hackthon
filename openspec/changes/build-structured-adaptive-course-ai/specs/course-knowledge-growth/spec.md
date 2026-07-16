## ADDED Requirements

### Requirement: 每门新课程必须拥有唯一且可生长的课程知识库

系统 MUST 在首次课程生成工作区中同时生成与 `course_id` 一一对应的 `CourseKnowledgeBase`，并在正式发布时与同一课程的 `CourseDocument`、学习资产和 `CourseKnowledgeMap` 共同激活。该知识库 MUST 只服务当前课程，且 MUST NOT 依赖跨课程参考匹配才能工作。

#### Scenario: 首次课程质量通过并发布

- **WHEN** 课程正文、学习资产、课程知识库和教学绑定均通过质量门
- **THEN** 系统 MUST 使用同一 `course_id` 共同发布课程文档与课程知识库
- **AND** 正文、课件、题目、AI 和学习事实 MUST 能引用活动课程知识 ID

#### Scenario: 首次课程知识库质量失败

- **WHEN** 课程知识库存在粗知识点、无效关系、悬空引用或模板内容等硬错误
- **THEN** 首次生成 MUST 保留工作区供定点修订
- **AND** 系统 MUST NOT 发布正文与知识结构不一致的正式课程

### Requirement: 课程知识库必须分离路径树、知识关系网和叶子能力包

系统 MUST 使用 `CourseDocument` 提供章节与小节路径，在每个小节下组织 `ConceptGroup`，并将可教学内容拆为 `KnowledgePoint`。每个活动知识点 MUST 至少关联一个可观察 `SkillUnit` 和一个可验证 `MasteryCriterion`；`Misconception` 只有在存在具体错误表现、判别方法和修复策略时 MAY 生成。

#### Scenario: 生成一个课程小节的知识结构

- **WHEN** 系统处理一个具有多个独立知识对象的小节
- **THEN** 系统 MUST 先建立内容分类明确的概念组
- **AND** MUST 将每个知识对象拆成脱离章节标题仍可独立解释和考查的原子知识点
- **AND** MUST 为每个知识点生成可观察能力和掌握标准

#### Scenario: 小节标题可以概括正文但不是知识命题

- **WHEN** 小节名称只是“图像与最值”之类的学习路径标签
- **THEN** 系统 MUST NOT 自动复制该标题作为同名知识点
- **AND** MUST 从正文责任、资料和目标中抽取真实知识命题

### Requirement: 原子知识点必须具有可审查的内容而非名称占位

每个活动 `KnowledgePoint` MUST 保存 `statement`、适用条件或边界、来源、颗粒度状态和修订。知识点 MUST 只表达一个主要命题、规则或操作，MUST NOT 用整章标题、一道题、一个案例或一段正文冒充知识点。

#### Scenario: 一个候选同时打包定义、公式、图像和应用

- **WHEN** 一个知识候选包含多个可独立解释、练习和诊断的对象
- **THEN** 质量门 MUST 将其标记为 `coarse`
- **AND** 候选 MUST 在发布前拆分或被拒绝

#### Scenario: 历史课程只有章节标题投影

- **WHEN** 历史课程无法从现有数据确定真实原子知识点
- **THEN** 系统 MUST 将知识库标记为 `degraded / needs_enrichment`
- **AND** MUST NOT 将章节标题投影伪装成通过质量门的活动知识点

### Requirement: 知识关系网只能使用六类正式语义关系

系统 MUST 仅允许 `prerequisite`、`derives`、`equivalent_to`、`contrasts_with`、`applies_to` 和 `generalizes` 连接当前课程活动知识点。章节包含、课程顺序、对象绑定和无具体教学含义的 `related` MUST NOT 进入正式知识关系网。

#### Scenario: 模型只判断两个知识点“有关”

- **WHEN** 关系候选无法说明六类关系中的方向、条件和教学含义
- **THEN** 系统 MUST 拒绝该关系进入活动知识网
- **AND** MUST NOT 以 `related` 作为兜底保存

#### Scenario: 两个名称只是同一知识点的别名

- **WHEN** 两个候选只有名称不同但知识命题、条件和边界相同
- **THEN** 系统 MUST 合并知识身份并保存 `aliases`
- **AND** MUST NOT 创建两个节点后用 `equivalent_to` 连接

#### Scenario: 一个推导需要多个共同前提

- **WHEN** 目标知识必须由多个来源知识共同推出或共同满足前置
- **THEN** 相关二元边 MUST 共享 `relation_group_id`
- **AND** `group_operator=all_of` MUST 防止系统将任一单边误读为充分条件

### Requirement: 六类关系必须通过确定性与语义质量门

每条知识关系 MUST 保存方向、理由、条件、来源、置信度和修订。系统 MUST 拒绝自环、悬空端点、重复语义签名、无理由关系、`required prerequisite` 环和 `generalizes` 环；对称关系 MUST 规范化后只保存一条。

#### Scenario: 前置关系只是课程先学顺序

- **WHEN** 移除来源知识后目标知识仍可独立理解和执行
- **THEN** 系统 MUST NOT 将课程先后顺序保存为 `prerequisite`

#### Scenario: 两个知识点在给定条件下可双向替换

- **WHEN** 关系候选能够证明给定条件下双向语义或结果保持一致
- **THEN** 系统 MUST 使用一条规范化 `equivalent_to`
- **AND** MUST NOT 保存两条方向相反的 `derives`

### Requirement: 教学对象必须通过精确绑定消费课程知识

系统 MUST 使用 `CourseKnowledgeMap / KnowledgeBinding` 将知识点和能力绑定到章节、正文块、课件单元、目标、题目、掌握标准和学习记录。每个绑定 MUST 声明 `teaching_role` 与主要或辅助重要性，MUST NOT 用“属于本节”替代精确知识覆盖。

#### Scenario: 一道题只考查小节中的两个知识点

- **WHEN** 小节包含多个知识点而题目只实际考查其中两个
- **THEN** 题目 MUST 只绑定这两个知识点及真实辅助知识
- **AND** 系统 MUST NOT 默认绑定整节全部知识

#### Scenario: 同一知识点在后续章节再次出现

- **WHEN** 后续章节复习、应用或考查已有知识点
- **THEN** 系统 MUST 保留同一知识身份
- **AND** MUST 通过新的 `reinforces / applies / assesses` 绑定表达教学作用

### Requirement: 课程知识库必须支持候选式细化

AI MUST 能针对当前课程知识结构生成新增、补写、拆分、合并、移动、重命名、六类关系调整和绑定调整候选。所有候选 MUST 固定基础修订、原因、证据、影响范围和质量报告；用户确认前 MUST NOT 修改活动知识库。

#### Scenario: AI 发现知识颗粒度不足

- **WHEN** 多个独立教学对象被压在一个无法分别解释、练习和诊断的粗节点中
- **THEN** AI MUST 能生成节点拆分候选
- **AND** 候选 MUST 列出新节点、旧新 ID 映射、关系、正文引用和学习资产影响
- **AND** 当前活动知识库 MUST 保持不变直到用户确认

#### Scenario: 用户拒绝知识细化

- **WHEN** 用户拒绝当前节点细化候选
- **THEN** 活动知识库 MUST 保持原修订
- **AND** 系统 MUST 保存拒绝记录与证据修订冷却

### Requirement: ImprovementPoint 必须退出新知识库核心写入

系统 MUST NOT 在新生成或新修订的课程知识库中创建 `ImprovementPoint` 核心实体。稳定学习目标 MUST 表达为 `SkillUnit`，具体练习 MUST 表达为学习资产或 `PracticeTask`，个性化提升建议 MUST 由 AI 根据正式学习证据动态生成。

#### Scenario: 旧课程包含提升点

- **WHEN** 迁移读取遇到旧 `ImprovementPoint`
- **THEN** 系统 MAY 保留兼容引用
- **AND** MUST 将稳定能力、具体任务和个人建议分类迁移或标记待审查
- **AND** 新修订 MUST NOT 继续写入旧实体

### Requirement: 课程与知识库必须进行双向影响分析

任何已提出的知识结构变化 MUST 计算对正文块、课件、学习目标、正式题目、能力、易错、掌握标准和绑定的影响；任何改变课程语义覆盖的正文变化 MUST 检查课程知识库是否需要补写、细化或调整关系。影响分析 MUST 生成候选，不得未经确认级联写入正式对象。

#### Scenario: 知识节点拆分影响正文与题目

- **WHEN** 用户查看一个知识节点拆分候选
- **THEN** 系统 MUST 列出已有覆盖、缺失覆盖和需要重绑定的课程对象
- **AND** 系统 MUST 只为真实缺口生成关联课程操作
- **AND** 已经覆盖的新细节点 MUST NOT 被重复生成内容

#### Scenario: 正文新增独立知识内容

- **WHEN** 一个课程内容候选新增可独立解释、练习和诊断的知识对象
- **THEN** 系统 MUST 生成补写或新增课程知识点及必要关系的关联候选
- **AND** 用户 MUST 能分别预览课程变化和知识变化

### Requirement: 双向联动必须具有单一因果链和循环抑制

同一跨域变化 MUST 使用一个 `change_set_id`、因果来源和依赖图。系统 MUST 对重复请求幂等处理，MUST NOT 将知识变化引发的课程变化再次识别为一条全新的相同知识变化。

#### Scenario: 知识拆分引发课程补写

- **WHEN** 课程补写由同一变更集中的知识拆分操作产生
- **THEN** 影响分析 MUST 标记其因果来源
- **AND** 再次分析该课程补写时 MUST NOT 生成重复知识拆分

#### Scenario: 联动期间基础修订变化

- **WHEN** 课程文档、课程知识库或绑定修订在确认前发生变化
- **THEN** 关联变更集 MUST 标记为过期或冲突
- **AND** 系统 MUST 基于当前修订重新计算完整影响

### Requirement: 知识引用迁移必须保护历史事实

知识点拆分、合并、移动和墓碑 MUST 保存稳定旧新 ID 映射。历史 `PracticeAttempt`、学习事件、诊断和记录 MUST 保留发生时的知识引用，当前投影 MAY 使用映射解释，但 MUST NOT 重写历史证据。

#### Scenario: 有历史作答的知识点被拆分

- **WHEN** 一个被历史作答引用的课程知识点被接受拆分
- **THEN** 历史 Attempt MUST 保留原知识引用和修订
- **AND** 系统 MUST 保存旧节点到新节点的映射
- **AND** 当前课程和后续任务 MUST 使用新修订引用
