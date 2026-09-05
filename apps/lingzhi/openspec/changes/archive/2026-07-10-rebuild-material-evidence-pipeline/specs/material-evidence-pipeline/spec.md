## ADDED Requirements

### Requirement: 用户资料必须作为真实资产上传和持久化

系统 MUST 通过受控 multipart 接口接收课程资料，流式写入非静态资料目录，并保存资产 ID、原始文件名、安全文件名、MIME、大小、SHA-256、状态和时间。课程生成请求 MUST 引用资产 ID，不得把二进制文件或完整文件文本内嵌到任务快照。

#### Scenario: 上传支持的课程资料

- **WHEN** 用户上传受支持且未超过限制的 PDF、DOCX、PPTX、Markdown 或文本文件
- **THEN** 系统 MUST 返回持久化 `MaterialAsset`
- **AND** 原始文件 MUST 可以在服务重启后继续读取
- **AND** 文件 MUST NOT 进入前端静态目录或 Git 自动同步

#### Scenario: 上传不安全或超限文件

- **WHEN** 文件路径、类型、MIME、大小或压缩展开风险不符合限制
- **THEN** 系统 MUST 拒绝上传并返回可读错误
- **AND** MUST 清理未完成的临时文件

### Requirement: 文档解析必须产出统一 ParsedDocument

系统 MUST 通过项目自有 `DocumentParser` 适配器把资料转换为解析器无关的 `ParsedDocument`。输出 MUST 尽可能保留文档层级、区块类型、阅读顺序、页码或幻灯片、坐标、表格和公式，并记录解析器、版本、选项与质量状态。

#### Scenario: 结构化解析成功

- **WHEN** 解析器成功处理一份文档
- **THEN** 系统 MUST 保存 ParsedDocument 和解析缓存键
- **AND** 后续课程生成 MUST 从 ParsedDocument 读取内容而不是重新读取请求内联文本

#### Scenario: 解析器只能降级提取文本

- **WHEN** 主解析器失败但降级解析器取得部分文本
- **THEN** 系统 MUST 标记结果为 `degraded`
- **AND** MUST 明确缺失的页级、布局级或 OCR 能力
- **AND** MUST NOT 把降级结果标记为完整解析

### Requirement: 证据单元必须保留不可伪造来源

系统 MUST 从 ParsedDocument 的真实区块构建 `EvidenceUnit`。`source_text`、来源区块、locator 和内容哈希 MUST 由确定性代码产生；AI MAY 分类或摘要，但 MUST NOT 创造证据原文或不存在的来源位置。

#### Scenario: 从区块生成证据

- **WHEN** 系统把定义、观点、步骤、例题、题目、公式或表格编译为 EvidenceUnit
- **THEN** 每个 EvidenceUnit MUST 指向一个或多个真实文档区块
- **AND** MUST 能追溯到资产版本和可用的页码、幻灯片或章节路径

#### Scenario: 模型返回无效来源

- **WHEN** AI 分类结果引用不存在的区块或修改了证据原文
- **THEN** 系统 MUST 拒绝该来源映射
- **AND** MUST 保留确定性证据或把该单元标记为不可用

### Requirement: 资料用途、权威与使用策略必须独立表达

每个课程资料绑定 MUST 分别保存用途、权威等级、优先级和使用策略。事实证据选择 MUST 遵守这些边界，讲法参考和弱背景 MUST NOT 越权成为事实依据。

#### Scenario: 讲法参考参与课程生成

- **WHEN** 资料绑定为 `style_reference` 或 `style_only`
- **THEN** 系统 MUST 只提取抽象讲法特征
- **AND** MUST NOT 把该资料的陈述作为课程事实来源

#### Scenario: 核心资料必须使用

- **WHEN** 资料绑定为 `must_use` 且解析成功
- **THEN** EvidenceCoveragePlan MUST 为其分配目标或节点
- **AND** 无法合理分配时 MUST 形成可见覆盖缺口

### Requirement: 资料冲突与覆盖缺口必须显式处理

系统 MUST 检测同一主题上的候选证据冲突和学习目标证据缺口。系统 MUST 根据权威、优先级和版本执行确定性选择；无法解决时 MUST 保存冲突或缺口，不得静默伪装为一致。

#### Scenario: 两份资料给出冲突陈述

- **WHEN** 同一目标的主证据互相冲突且无法根据权威或版本解决
- **THEN** 系统 MUST 创建 `EvidenceConflict`
- **AND** 蓝图或正文 MUST 明确保留多种观点、跳过该结论或标记警告

#### Scenario: 必讲目标没有资料依据

- **WHEN** 课程目标没有可用资料证据
- **THEN** 系统 MUST 创建 `CoverageGap`
- **AND** MUST 根据 grounding strategy 决定允许通用知识生成、降低为背景说明或阻止该目标进入正文

### Requirement: 解析与证据结果必须可缓存和恢复

系统 MUST 以文件哈希、解析器版本和解析选项作为解析缓存依据。GenerationJob 重启后 MUST 复用已完成解析和证据结果，并将中断的解析恢复为可重试状态。

#### Scenario: 相同资产再次用于课程生成

- **WHEN** 资产哈希、解析器版本和选项未变化
- **THEN** 系统 MUST 复用 ParsedDocument 和 EvidenceUnit
- **AND** MUST NOT 因新课程或修改资料用途而重复解析原文件

#### Scenario: 服务在解析中重启

- **WHEN** 持久化资产处于 `parsing` 且服务重启
- **THEN** 系统 MUST 将其恢复为可重试状态
- **AND** 同一 GenerationJob MUST 从资料检查点继续
