# learning-asset-pipeline Specification

## Purpose
TBD - created by archiving change unify-course-blueprint-and-learning-assets. Update Purpose after archive.
## Requirements
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

正式知识结构 MUST 使用课程、章节、小节、主题和知识点组成的单一知识树；父子字段 MUST 表达包含结构。跨知识点关系 MUST 标记资料支持、课程结构确定、AI 候选、存在争议或证据不足，并保存理由和不可变修订。AI 候选 MUST 经过维护流程接受或验证才能成为正式关系；难度只能改变展示深度，不能改变知识事实。

#### Scenario: AI 提出新关系

- **WHEN** AI 生成一条资料未明确支持的跨知识点关系
- **THEN** 关系 MUST 保存为候选并记录理由
- **AND** MUST NOT 直接覆盖已有正式关系或父子结构

#### Scenario: 课程结构建立包含关系

- **WHEN** 系统编译课程、章节、小节、主题和知识点
- **THEN** 包含关系 MUST 只由节点父级和路径表达
- **AND** MUST NOT 重复生成为普通关系边

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

前端 MUST 继续以课程正文为唯一学习主舞台，在正文原位置和底部工具坞提供正式资产入口。练习 MUST 打开同一正式任务覆盖层；知识树 MUST 以弹层提供结构导航、知识点详情和正文回跳。学生界面 MUST NOT 增加资产页面模式栏、知识树编辑模式或候选关系审批。

#### Scenario: 用户完成一章学习

- **WHEN** 用户到达章节末尾或从工具坞打开学习资产
- **THEN** 页面 MUST 使用已版本化且通过闸门的掌握标准、误区、练习和知识树
- **AND** 关闭覆盖层后 MUST 返回原正文位置

### Requirement: 旧学习资产链路必须退出生产

新消费者迁移后，系统 MUST 删除临时 quiz/similar_quiz、通用回退题、图谱直接覆盖和旧大纲整体替换入口。旧课程与旧图谱 MAY 通过只读或幂等迁移适配，但 MUST NOT 重新成为生产真源。

#### Scenario: 新前端请求练习

- **WHEN** 新前端打开章节练习
- **THEN** MUST 读取正式 QuestionRevision
- **AND** MUST NOT 提交 node_content 到旧生成测验接口

### Requirement: 最终正文必须持久化稳定内容块

生成节点完成时，系统 MUST 将最终正文转换为稳定 `content_blocks` 并与正文一起保存。节点完成和 finalized 实时事件 MUST 携带保存后的同一组内容块；MUST NOT 继续写入或发送空数组。

#### Scenario: 节点正文生成完成

- **WHEN** 模型流式生成结束且正文通过节点质量处理
- **THEN** 节点 MUST 保存带 block_id、content_fingerprint 和 block_revision_id 的内容块
- **AND** WebSocket 完成事件 MUST 携带这些持久内容块

### Requirement: 学习资产必须包含章节推进契约

学习资产编译器 MUST 为每个有效章节生成版本化章节推进契约，包含真实 `chapter_id`、当前必需目标、掌握要求、前置策略和完成策略。契约引用 MUST 与 LearningContinuation 使用的章节和目标身份一致。

#### Scenario: 系统化课程包含两个章节

- **WHEN** 学习资产编译器处理带 L1 章节和 L2 目标的系统化课程
- **THEN** 每个章节 MUST 获得一个 chapter_progression_contract
- **AND** 必需目标 MUST 只引用该章当前目标 ID

### Requirement: 阅读型降级必须由最终资产计划显式表达

当课程用途或资产偏好不启用正式题目时，资产计划 MUST 设置 `reading_only_degraded=true`；启用正式题目时 MUST 为 false。系统 MUST 根据最终 enabled assets 计算该值。

#### Scenario: 资料整理课程未请求题目

- **WHEN** `material_organization` 使用默认资产偏好
- **THEN** 计划 MUST 明确标记 reading_only_degraded
- **AND** 后续预检 MUST 能自动选择 reading_only 口径

### Requirement: 质量门必须覆盖内容与章节推进契约

资产质量门 MUST 阻止缺少持久内容块、内容块修订、章节推进契约或有效目标引用的课程通过。读取层兼容投影 MUST NOT 满足生成质量门。

#### Scenario: 正文存在但内容块未持久化

- **WHEN** 生成课程只有 node_content 而 content_blocks 为空
- **THEN** 资产质量报告 MUST 包含 critical content issue
- **AND** 课程 MUST NOT 发布为当前版本

### Requirement: 学习资产只能在版本发布成功后激活

编译后的资产包 MAY 先保存为不可变修订，但 current 指针 MUST 只在最终质量通过且初始版本创建或候选版本提升成功后更新。失败生成 MUST NOT 替换当前资产包。

#### Scenario: 初始课程资产质量失败

- **WHEN** 资产包已经保存但质量门未通过
- **THEN** 系统 MUST 保留诊断修订
- **AND** MUST NOT 激活该修订或创建当前课程版本
