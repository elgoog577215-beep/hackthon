## ADDED Requirements

### Requirement: 正式学习写入必须具有稳定身份和幂等关联

所有新学习领域写操作 MUST 使用非共享的稳定学习者身份，并以幂等请求关联领域对象修订与 LearningEvent。缺失身份或 `default_user` MUST NOT 接受生产写入；重复语义请求 MUST NOT 创建第二个对象、第二次状态变化或重复事件。

#### Scenario: 匿名浏览器首次保存学习记录

- **WHEN** 浏览器已经生成安装级匿名学习者 ID 并提交记录
- **THEN** 领域对象与事件 MUST 归属于同一身份、课程和操作 ID
- **AND** 使用相同幂等键重试 MUST 返回原结果

#### Scenario: 客户端未发送学习者身份

- **WHEN** 客户端调用正式学习写接口但没有有效 `X-User-Id`
- **THEN** 服务端 MUST 拒绝写入并返回稳定错误
- **AND** MUST NOT 把事实写入 `default_user`

### Requirement: 运行时必须包含同批学习者模型修订

LearningRuntime MUST 使用构建进度、记录、Attempt、诊断和连续性的同一批来源构建 LearnerModel 摘要，并返回 `model_revision_id`。运行时不得读取旧 AI profile 或独立 Learning OS 聚合结果。

#### Scenario: 正式作答改变当前掌握

- **WHEN** 新 Attempt 使目标的正式掌握投影变化
- **THEN** 同一运行时响应的 progress、continuation 与 learner_model_summary MUST 基于同一证据批次
- **AND** revision_vector MUST 反映新的模型来源修订

### Requirement: 旧学习入口只能迁移或投影正式真源

旧 annotation、Learning OS 和 localStorage 学习统计 MAY 提供一次性幂等迁移或只读兼容展示，但 MUST NOT 继续创建平行正式事实、学习者判断或下一步。迁移完成后新界面 MUST 只读取正式领域接口。

#### Scenario: 历史 annotation 已经迁移

- **WHEN** 同一旧 annotation 再次进入迁移流程
- **THEN** 系统 MUST 返回已有 LearningRecord 关联
- **AND** MUST NOT 重复创建记录或事件
