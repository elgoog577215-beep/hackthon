## MODIFIED Requirements

### Requirement: 课程生成必须使用唯一可恢复任务

系统 MUST 为一次课程生成创建唯一 `GenerationJob`。brief、资料解析、证据编译、教学画像、难度契约、覆盖计划、蓝图、正文、质量检查和最终保存 MUST 使用同一个 `job_id`；前端 MUST NOT 再创建独立任务身份或调用第二个正文启动接口。

#### Scenario: 用户创建课程

- **WHEN** 客户端调用 `/api/course-generation/generate`
- **THEN** 服务端 MUST 创建课程草稿和唯一 GenerationJob
- **AND** MUST 立即返回 `course_id`、`course_name`、`job_id` 和任务状态
- **AND** 后续阶段 MUST 通过任务查询和实时事件暴露
- **AND** 任务快照 MUST 保存资料资产绑定而不是完整文件内容

#### Scenario: 服务在生成过程中重启

- **WHEN** 持久化任务处于 `running` 且服务重新启动
- **THEN** 系统 MUST 将任务恢复为可执行状态并重新入队
- **AND** MUST 跳过已经完成的资料解析、证据编译和课程节点
- **AND** MUST 恢复请求、资料绑定、证据、教学画像、难度契约、覆盖计划、蓝图和节点检查点

### Requirement: 学科结构必须由教学模块组合

系统 MUST 使用通用骨架、主模式模块包和可选辅模式注入生成课程结构。模块 MUST 表达教学产出和检查标准，不得要求所有模块成为固定 Markdown 标题。存在资料时，结构生成 MUST 先消费 EvidenceCoveragePlan，不能直接从资料摘要猜测覆盖关系。

#### Scenario: 生成课程蓝图

- **WHEN** brief、证据目录、EvidenceCoveragePlan 和教学画像准备完成
- **THEN** CourseBlueprint MUST 保存教学画像和课程级模块计划
- **AND** 每个正文节点 MUST 保存自己的 `module_plan` 和 `grounding_contract`
- **AND** 主模式 MUST 决定课程顺序和最终考核
- **AND** 辅模式模块 MUST 去重并在依赖它的主任务之前出现
- **AND** 资料引用 MUST 通过有效 EvidenceUnit ID 表达

### Requirement: 正文必须读取持久化蓝图契约

节点正文 MUST 读取持久化请求、brief、教学画像、难度契约、节点范围、模块计划和 `NodeGroundingContract`。系统 MUST NOT 在节点级根据标题重新猜学科，也 MUST NOT 依赖进程内缓存、全量资料摘要或默认资料广播作为唯一上下文。

#### Scenario: 生成或恢复某个节点

- **WHEN** TaskManager 调用节点正文生成
- **THEN** prompt MUST 包含节点目标、范围、证据包、知识点、误区、验收标准、模块产出和难度要求
- **AND** 资料事实 MUST 使用当前 grounding contract 允许的来源标记
- **AND** 输出 MUST 保存为完整 Markdown `node_content`
- **AND** 来源映射 MUST 独立保存为 `grounding_annotations`
- **AND** 动态学习者状态 MUST NOT 改写基础课程的蓝图或正文主线

### Requirement: 质量报告必须由分层质量闸门产生

系统 MUST 分别检查教学画像、难度画像、资料解析、证据覆盖、蓝图、难度曲线、节点接地和全课。最终 `GenerationQualityReport` MUST 在正文检查完成后生成，MUST 包含 `DifficultyAlignmentReport` 和 `GroundingQualityReport`，且 MUST NOT 使用预生成报告冒充最终报告。

#### Scenario: 课程生成完成

- **WHEN** 所有节点完成、跳过或失败处理
- **THEN** 系统 MUST 聚合资料解析状态、证据覆盖、冲突、缺口、brief 满足、模块覆盖、难度对齐、节点质量和失败节点
- **AND** “资料已使用” MUST 有节点来源标记或有效 grounding annotation 支撑
- **AND** MUST 保存最终 GenerationQualityReport
- **AND** MUST 将任务进度更新为 100

### Requirement: 无资料和无法解析资料必须诚实降级

系统 MUST 支持无资料生成。无法解析或只能降级提取的资料 MUST 保存真实状态，不得标记为完整解析、不得伪造 EvidenceUnit，也不得把文件名或用户说明当成正文事实依据。

#### Scenario: 用户没有上传资料

- **WHEN** 用户只提交主题和要求
- **THEN** 系统 MAY 使用模型通用知识生成
- **AND** 最终报告 MUST 说明没有上传资料依据

#### Scenario: 用户上传无法解析的 PDF 或 PPT

- **WHEN** 主解析器和允许的降级解析器都无法取得可信内容
- **THEN** MaterialAsset MUST 标记为 `failed` 或 `metadata_only`
- **AND** 系统 MUST NOT 为该资产生成伪造证据或资料覆盖
- **AND** 前端和最终报告 MUST 展示失败原因

#### Scenario: 用户上传只能降级提取的资料

- **WHEN** 系统只能取得无完整来源坐标的文本
- **THEN** ParsedDocument MUST 标记为 `degraded`
- **AND** EvidenceUnit MUST 标记定位和置信度限制
- **AND** 质量报告 MUST NOT 把它等同于完整解析资料
