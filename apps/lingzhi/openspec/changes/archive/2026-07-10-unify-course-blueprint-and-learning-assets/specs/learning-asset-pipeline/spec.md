## ADDED Requirements

### Requirement: 课程蓝图必须包含可执行学习资产计划

系统 MUST 根据课程目的、主辅教学模式、难度、学习目标和资料证据编译 `LearningAssetPlan`，为每项资产声明范围、必选性、生成方式、证据、难度、依赖和质量闸门。

#### Scenario: 系统学习课程

- **WHEN** 课程目的为系统学习
- **THEN** 资产计划 MUST 包含课程总览、知识子图、掌握标准、章节练习、通用误区、检查清单和综合检测
- **AND** 用户关闭练习与检测时 MUST 明确降级为阅读型资料

#### Scenario: 主辅模式课程

- **WHEN** 课程存在辅教学模式
- **THEN** 主模式 MUST 决定资产主体结构
- **AND** 辅模式 MUST 按 light/collaborative/dual_core 注入第二类学习成果

### Requirement: 正式学习资产必须使用不可变修订和稳定绑定

题目、课程知识子图、掌握标准和通用误区 MUST 拥有稳定 ID 和不可变修订。课程 MUST 通过类型化绑定引用资产，不得使用名称匹配或互不关联的 Markdown 附件。

#### Scenario: 课程版本引用题目

- **WHEN** 课程版本包含章节练习
- **THEN** MUST 保存 QuestionRevision ID、课程节点、学习目标、概念、误区和证据绑定
- **AND** 后续题目修改 MUST NOT 改变历史课程版本

### Requirement: 题目必须同时履行资料与掌握契约

题目事实、答案和解析 MUST 使用允许的资料证据；题型、支架、推理步数、迁移距离、反馈和评分 MUST 履行节点难度与掌握契约。争议资料不得被强行生成唯一答案题。

#### Scenario: 生成节点题目

- **WHEN** 系统为节点生成题目
- **THEN** 题目 MUST 绑定目标、概念、难度、证据和答案/量规
- **AND** 风格资料 MUST NOT 作为答案事实来源
- **AND** 难度 MUST NOT 仅由生僻措辞、篇幅或超纲事实制造

#### Scenario: 资料存在未解决冲突

- **WHEN** 题目涉及未解决 EvidenceConflict
- **THEN** 系统 MUST 使用比较、材料分析、论证或多模型题型
- **AND** MUST NOT 生成伪唯一答案

### Requirement: 知识图谱关系必须保存来源和候选状态

每个概念和关系 MUST 标记资料支持、课程结构确定、AI 候选、存在争议或证据不足。AI 候选 MUST 经过接受或验证才能进入正式课程修订；难度只能改变展示深度，不能改变知识事实。

#### Scenario: AI 提出新关系

- **WHEN** AI 生成一条资料未明确支持的关系
- **THEN** 关系 MUST 保存为候选并记录理由
- **AND** MUST NOT 直接覆盖已有正式关系

### Requirement: 掌握标准必须绑定可观察检测

每条 MasteryCriterion MUST 绑定学习目标、学科任务、可观察表现、通过阈值、支架条件和至少一种 AssessmentBinding。手动勾选 MUST 记录为自我确认，不得直接成为系统验证。

#### Scenario: 检查课程掌握清单

- **WHEN** 用户查看章节检查清单
- **THEN** 系统 MUST 区分尚未学习、自我确认、系统验证、需要复习和资产过期
- **AND** 没有有效检测资产的标准 MUST 标记为尚未验证

### Requirement: 通用误区与个人错误必须分离

通用误区 MUST 保存错误表现、触发、原因、样例、辨析、概念、检测题和依据。个人错误 MUST 只进入 LearningEvent，不得自动写入通用误区真源。

#### Scenario: 用户答错题目

- **WHEN** 用户答案与题目量规不符
- **THEN** 系统 MUST 记录关联题目修订和误区的学习事件
- **AND** MUST NOT 自动修改课程误区或知识图谱

### Requirement: 资产必须通过五层质量闸门

系统 MUST 对资产执行结构、证据/难度、学科验证器、语义复核和整课覆盖检查。语义问题最多定向修复一次；必选资产仍失败时 MUST 阻止候选版本提升。

#### Scenario: 题目生成失败

- **WHEN** 题目答案不一致、证据无效或学科验证失败
- **THEN** 系统 MUST 生成具体 AssetQualityIssue
- **AND** MAY 定向修复一次并重复相同闸门
- **AND** MUST NOT 使用通用回退题补足数量

### Requirement: 学习结果必须写入事件账本

新作答、错题、自我确认和复习结果 MUST 写入 LearningEvent，并保存当时的 CourseVersion、QuestionRevision、Criterion 和 Concept 引用。学习者模型 MUST 从事件派生掌握状态，新数据不得继续写入 node.quiz_score 或 course.review_history。

#### Scenario: 提交正式练习

- **WHEN** 用户提交一道正式题目
- **THEN** 系统 MUST 写入结构化作答事件
- **AND** 事件 MUST 保存题目修订、答案、评分、耗时和关联目标
- **AND** 掌握清单 MUST 从事件与学习者模型更新

### Requirement: 前端必须围绕课程总览和章节闭环组织资产

前端 MUST 在课程树提供课程总览和综合检测，在章节末尾提供目标、掌握、误区和正式练习。练习 MUST 使用主内容区工作区，知识图谱 MUST 区分学习与编辑模式，不得新增一排互相割裂的资产页面。

#### Scenario: 用户完成一章学习

- **WHEN** 用户到达章节末尾
- **THEN** 页面 MUST 显示本章掌握标准、验证状态、通用误区和练习入口
- **AND** “练习” MUST 打开已经版本化并通过闸门的题目
- **AND** 右侧笔记和错题 MUST 继续表示个人学习痕迹

### Requirement: 旧学习资产链路必须退出生产

新消费者迁移后，系统 MUST 删除临时 quiz/similar_quiz、通用回退题、图谱直接覆盖和旧大纲整体替换入口。旧课程与旧图谱 MAY 通过只读或幂等迁移适配，但 MUST NOT 重新成为生产真源。

#### Scenario: 新前端请求练习

- **WHEN** 新前端打开章节练习
- **THEN** MUST 读取正式 QuestionRevision
- **AND** MUST NOT 提交 node_content 到旧生成测验接口
