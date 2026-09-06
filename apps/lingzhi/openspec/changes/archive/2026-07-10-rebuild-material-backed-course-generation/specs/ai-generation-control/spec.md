## ADDED Requirements

### Requirement: 课程生成必须使用唯一可恢复任务

系统 MUST 为一次课程生成创建唯一 `GenerationJob`。brief、资料、教学画像、蓝图、正文、质量检查和最终保存 MUST 使用同一个 `job_id`；前端 MUST NOT 再创建独立任务身份或调用第二个正文启动接口。

#### Scenario: 用户创建课程

- **WHEN** 客户端调用 `/api/course-generation/generate`
- **THEN** 服务端 MUST 创建课程草稿和唯一 GenerationJob
- **AND** MUST 立即返回 `course_id`、`course_name`、`job_id` 和任务状态
- **AND** 后续阶段 MUST 通过任务查询和实时事件暴露

#### Scenario: 服务在生成过程中重启

- **WHEN** 持久化任务处于 `running` 且服务重新启动
- **THEN** 系统 MUST 将任务恢复为可执行状态并重新入队
- **AND** MUST 跳过已经完成的节点
- **AND** MUST 恢复请求、资料、教学画像、蓝图和节点检查点

### Requirement: 课程生成必须形成教学画像

系统 MUST 在生成课程蓝图前形成 `SubjectPedagogyProfile`。实际主模式 MUST 是八种已注册教学模式之一，辅模式最多一个；`auto` MUST NOT 作为最终主模式保存。

#### Scenario: 自动识别教学模式

- **WHEN** 用户选择自动模式
- **THEN** 系统 MUST 综合最终成果、主要学习行为、资料结构和课程主题
- **AND** MUST 输出主模式、可选辅模式、辅助强度、置信度、证据和判断理由
- **AND** 低置信度 MUST 回退通用课程而不是自然科学

#### Scenario: 用户手动指定模式

- **WHEN** 用户提交明确的教学模式
- **THEN** 系统 MUST 锁定该主模式
- **AND** 后续蓝图、正文或重新生成 MUST NOT 自动覆盖它

### Requirement: 学科结构必须由教学模块组合

系统 MUST 使用通用骨架、主模式模块包和可选辅模式注入生成课程结构。模块 MUST 表达教学产出和检查标准，不得要求所有模块成为固定 Markdown 标题。

#### Scenario: 生成课程蓝图

- **WHEN** brief、资料 digest 和教学画像准备完成
- **THEN** CourseBlueprint MUST 保存教学画像和课程级模块计划
- **AND** 每个正文节点 MUST 保存自己的 `module_plan`
- **AND** 主模式 MUST 决定课程顺序和最终考核
- **AND** 辅模式模块 MUST 去重并在依赖它的主任务之前出现

### Requirement: 正文必须读取持久化蓝图契约

节点正文 MUST 读取持久化请求、brief、资料 digest、教学画像、节点范围和模块计划。系统 MUST NOT 在节点级根据标题重新猜学科，也 MUST NOT 依赖进程内缓存作为唯一上下文。

#### Scenario: 生成或恢复某个节点

- **WHEN** TaskManager 调用节点正文生成
- **THEN** prompt MUST 包含节点目标、范围、资料引用、知识点、误区、验收标准和模块产出
- **AND** 输出 MUST 保存为完整 Markdown `node_content`
- **AND** 动态学习者状态 MUST NOT 改写基础课程的蓝图或正文主线

### Requirement: 任务必须支持多课程并发和真实暂停

任务消费者 MUST 能同时推进多门课程，并使用全局并发限制保护模型调用。暂停 MUST 停止新节点并取消当前调用，已接收草稿 MUST 保存为检查点。

#### Scenario: 两门课程同时排队

- **WHEN** 两个 GenerationJob 均处于 pending
- **THEN** 调度器 SHOULD 在课程并发上限内同时推进它们
- **AND** 节点调用总数 MUST 不超过全局并发上限

#### Scenario: 用户暂停并继续任务

- **WHEN** 用户暂停运行中的任务
- **THEN** 系统 MUST 停止任务继续消耗模型调用
- **AND** MUST 保存当前节点草稿和已完成节点
- **WHEN** 用户继续任务
- **THEN** 系统 MUST 从检查点和未完成节点继续

### Requirement: 质量报告必须由分层质量闸门产生

系统 MUST 分别检查教学画像、蓝图、节点和全课。最终 `GenerationQualityReport` MUST 在正文检查完成后生成，MUST NOT 使用预生成报告冒充最终报告。

#### Scenario: 节点未履行模块契约

- **WHEN** 节点缺少当前模块要求的核心产出、学习者行动或验收反馈
- **THEN** 系统 MUST 返回具体问题
- **AND** MAY 执行至多一次定向 AI 修复
- **AND** 修复后 MUST 重新检查
- **AND** 仍未通过时 MUST 保存警告或失败状态，不得无限重写

#### Scenario: 课程生成完成

- **WHEN** 所有节点完成、跳过或失败处理
- **THEN** 系统 MUST 聚合资料覆盖、brief 满足、模块覆盖、节点质量和失败节点
- **AND** MUST 保存最终 GenerationQualityReport
- **AND** MUST 将任务进度更新为 100

### Requirement: 旧课程只能通过读取适配器兼容

旧学科值和 `content_blocks` MAY 在读取旧课程时被适配，但新请求、新教学画像、新蓝图和新正文生成 MUST NOT 写入旧学科值或依赖旧固定板块。

#### Scenario: 打开旧课程并继续生成

- **WHEN** 课程只保存旧学科值或缺少教学画像
- **THEN** 系统 MUST 根据旧值、课程主题和节点恢复最小教学画像
- **AND** MUST 使用新模块和新 prompt 继续生成
- **AND** MUST NOT 重新启用旧 prompt 或旧分类器

### Requirement: 无资料和无法解析资料必须诚实降级

系统 MUST 支持无资料生成。没有真实解析器的二进制资料 MUST 标记为 `metadata_only`，不得标记为已解析或伪装成正文依据。

#### Scenario: 用户没有上传资料

- **WHEN** 用户只提交主题和要求
- **THEN** 系统 MAY 使用模型通用知识生成
- **AND** 最终报告 MUST 说明没有上传资料依据

#### Scenario: 用户上传当前无法解析的 PDF 或 PPT

- **WHEN** 系统只能读取文件名和用户说明
- **THEN** MaterialCard MUST 标记 `metadata_only`
- **AND** MaterialDigest MUST NOT 伪造正文知识点或证据片段
