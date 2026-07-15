## ADDED Requirements

### Requirement: 课程难度必须编译为能力契约

系统 MUST 将 `beginner/intermediate/advanced` 编译为结构化 `DifficultyProfile`，至少包含入口要求、挑战维度、支持维度和掌握契约。难度 MUST NOT 由文本长度、公式密度、代码量或小节数量单独表示。

#### Scenario: 编译三个难度等级

- **WHEN** 请求使用任一合法难度值
- **THEN** 系统 MUST 生成版本化的 `DifficultyProfile`
- **AND** 挑战强度与独立性 MUST 按入门、进阶、高阶递增
- **AND** 教学支架 MUST 总体按该顺序递减

### Requirement: 难度必须经过学科教学模式适配

系统 MUST 使用持久化 `SubjectPedagogyProfile` 将共享难度维度翻译为主教学模式的可观察任务和掌握证据。系统 MUST NOT 为每个学科维护三套独立难度 prompt。

#### Scenario: 同一难度用于不同教学模式

- **WHEN** 数学课与编程课都选择高阶
- **THEN** 两者 MUST 共享同级挑战、支持与独立性维度
- **AND** 数学课 MUST 将其翻译为形式推理、证明或建模证据
- **AND** 编程课 MUST 将其翻译为设计、调试、验证和权衡证据

### Requirement: 课程必须保存锯齿型难度曲线

`CourseBlueprint` MUST 保存 `CourseDifficultyCurve`，每个正文节点 MUST 保存 `NodeDifficultyContract`。曲线 MUST 允许新能力波次重新提高支架，并防止无前置的挑战跳变。

#### Scenario: 编译课程节点

- **WHEN** 蓝图结构和教学画像已确定
- **THEN** 系统 MUST 为每个 L2 节点分配能力角色、挑战、支架、掌握证据与学科任务
- **AND** 相邻节点挑战跳变 SHOULD 不超过 2 级
- **AND** 新概念负荷和任务复杂度 MUST NOT 同时无支架跃升

### Requirement: 目标难度与当前就绪度必须分开

系统 MUST 分开保存当前就绪度、课程入口要求和用户选择的目标难度。系统 MUST NOT 根据未授权动态学习痕迹静默更改目标难度。

#### Scenario: 就绪度未知

- **WHEN** 请求没有明确基础说明或诊断结果
- **THEN** `DifficultyGapAssessment` MUST 标记就绪度未知
- **AND** 系统 SHOULD 提供前置检查或桥接节点
- **AND** 目标难度 MUST 保持不变

#### Scenario: 就绪度低于入口要求

- **WHEN** 明确信息显示差距为 1 级
- **THEN** 系统 SHOULD 在目标课内增加桥接支架
- **WHEN** 差距为 2 级
- **THEN** 系统 SHOULD 规划前置单元
- **WHEN** 差距为 3 级或以上
- **THEN** 系统 SHOULD 建议拆分基础课与目标课，而不是静默降级

### Requirement: 蓝图、正文与重写必须消费同一难度契约

蓝图 prompt、节点正文 prompt、定向修复与局部重写 MUST 使用持久化难度契约。局部重写在没有明确新难度时 MUST 继承当前节点契约。

#### Scenario: 生成节点正文

- **WHEN** `CourseService` 生成某个 L2 节点
- **THEN** prompt MUST 包含该节点的挑战、支架、掌握证据、学科任务和伪难度禁止项
- **AND** prompt MUST NOT 只提供 `beginner/intermediate/advanced` 标签

#### Scenario: 用户未传难度地重写节点

- **WHEN** 节点重写请求未提供新难度
- **THEN** 系统 MUST 继承 `NodeDifficultyContract`
- **AND** MUST NOT 默认使用 `advanced`

### Requirement: 难度对齐必须有独立质量报告

质量链路 MUST 生成 `DifficultyAlignmentReport`，分开报告挑战、支持、独立性、掌握证据、曲线和学科任务对齐。关键契约缺失或曲线硬失败 MUST 使报告失败，不得被其他分数平均掉。

#### Scenario: 检测伪难度

- **WHEN** 正文只通过增加术语、长度、公式、代码或题量来表现高阶
- **THEN** 报告 SHOULD 标记伪难度风险
- **AND** 系统 SHOULD 要求补充推理、整合、独立决策、迁移或权衡证据

#### Scenario: 跨等级基准

- **WHEN** 同一教学模式编译三个难度等级
- **THEN** 系统 MUST 验证挑战和独立性严格递增
- **AND** MUST 验证支架强度总体递减

## MODIFIED Requirements

### Requirement: 质量报告必须由分层质量闸门产生

系统 MUST 分别检查教学画像、难度画像、蓝图、难度曲线、节点和全课。最终 `GenerationQualityReport` MUST 在正文检查完成后生成，MUST 包含 `DifficultyAlignmentReport`，且 MUST NOT 使用预生成报告冒充最终报告。

#### Scenario: 课程生成完成

- **WHEN** 所有节点完成、跳过或失败处理
- **THEN** 系统 MUST 聚合资料覆盖、brief 满足、模块覆盖、难度对齐、节点质量和失败节点
- **AND** MUST 保存最终 `GenerationQualityReport`
- **AND** MUST 将任务进度更新为 100

### Requirement: 旧课程只能通过读取适配器兼容

旧学科值、缺失的难度契约和 `content_blocks` MAY 在读取旧课程时被适配，但新请求、新教学画像、新难度画像、新蓝图和新正文生成 MUST NOT 写入旧学科值、自由 `complexity` 或依赖旧固定板块。

#### Scenario: 打开旧课程并继续生成

- **WHEN** 课程只保存旧难度标签或节点 `complexity`
- **THEN** 系统 MUST 根据课程难度、教学画像和节点位置恢复最小难度契约
- **AND** MUST 使用新难度编译器继续生成
- **AND** MUST NOT 重新启用旧 prompt 或旧难度映射
