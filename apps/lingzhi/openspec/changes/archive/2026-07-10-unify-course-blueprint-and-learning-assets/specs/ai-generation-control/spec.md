## MODIFIED Requirements

### Requirement: 课程生成必须使用唯一可恢复任务

系统 MUST 为一次课程生成或局部再生成创建唯一 `GenerationJob`。brief、资料解析、证据编译、教学画像、难度契约、覆盖计划、蓝图、可选蓝图等待、正文、学习资产、质量检查、候选版本和最终保存 MUST 使用同一任务模型与 TaskManager；前端 MUST NOT 创建独立任务身份或调用第二阶段生成入口。

#### Scenario: 快速模式创建课程

- **WHEN** 客户端提交 `generation_mode=fast`
- **THEN** 服务端 MUST 创建唯一 GenerationJob 并立即返回 job_id/course_id
- **AND** 任务 MUST 自动完成蓝图、正文、学习资产、质量和课程版本

#### Scenario: 蓝图审阅模式创建课程

- **WHEN** 客户端提交 `generation_mode=review_blueprint`
- **THEN** 同一任务 MUST 在 blueprint_ready 进入 waiting_for_review
- **AND** 用户确认后 MUST 继续同一 job_id

#### Scenario: 局部再生成

- **WHEN** 用户确认影响报告并更新受影响内容
- **THEN** 系统 MUST 使用同一 GenerationJob 模型创建候选工作区
- **AND** MUST 只调度受影响节点和资产
- **AND** 失败候选 MUST NOT 覆盖当前课程版本

### Requirement: 质量报告必须由分层质量闸门产生

系统 MUST 分别检查教学画像、难度画像、资料解析、证据覆盖、蓝图、难度曲线、节点正文和学习资产。最终 GenerationQualityReport MUST 聚合节点与 AssetQualityReport，并在候选版本全部完成后产生。

#### Scenario: 课程候选完成

- **WHEN** 正文与资产生成结束
- **THEN** 最终报告 MUST 包含节点质量、资料接地、难度对齐、资产覆盖、资产失败和锁定冲突
- **AND** 必选资产硬失败 MUST 阻止候选成为当前版本
- **AND** 任务进度 MUST 准确反映资产生成与验证阶段
