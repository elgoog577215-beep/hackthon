## ADDED Requirements

### Requirement: 课程生成运行态必须端到端对账

课程生成 MUST 将本地运行环境、唯一 GenerationJob、检查点恢复、正式课程发布和前端课程摘要视为同一运行闭环。普通 active job MUST NOT 被解释为恢复任务；正式文档发布后，前端 MUST 对账课程正文、任务终态和课程库摘要。

#### Scenario: 新课程正常开始生成

- **WHEN** 新建 GenerationJob 处于 `pending` 或 `running` 且没有恢复原因
- **THEN** 后端恢复描述 MUST 返回普通非恢复状态
- **AND** 前端 MUST 显示“等待生成”或“正在生成”
- **AND** MUST NOT 显示“正在恢复”

#### Scenario: 服务重启或人工继续后任务活跃

- **WHEN** active job 具有 `service_restart` 或 `manual_resume` 恢复原因
- **THEN** 后端恢复描述 MUST 标记该任务正在从检查点继续
- **AND** MUST 保留原 `job_id`、已完成节点和草稿

#### Scenario: 正式课程发布完成

- **WHEN** 前端从 WebSocket 或任务轮询观察到 GenerationJob 首次迁移为 `completed`
- **THEN** 前端 MUST 重新读取正式 CourseDocument
- **AND** MUST 重新读取课程库摘要
- **AND** 课程卡片的节点数 MUST 与已发布文档一致，无需用户手动刷新

#### Scenario: 本地启动课程生成环境

- **WHEN** 开发者执行项目本地启动脚本
- **THEN** 脚本 MUST 使用项目既定 Python 与前端依赖启动前后端
- **AND** MUST 校验课程生成所需 AI 配置
- **AND** MUST 在前后端健康检查通过后才报告服务可用
- **AND** 任一子进程异常退出 MUST 使编排进程失败并清理另一子进程

### Requirement: 模型思考内容不得进入普通运行输出

模型 provider 返回的思考内容 MUST NOT 被写入标准输出、课程正文或用户可见日志。系统 MAY 记录思考内容长度等非内容元数据用于调试。

#### Scenario: 模型同时返回思考与答案增量

- **WHEN** AIBase 聚合含 `reasoning_content` 和 `content` 的流式响应
- **THEN** 最终结果 MUST 只由 `content` 聚合
- **AND** 标准输出 MUST NOT 包含 `reasoning_content`
- **AND** 普通 info 日志 MUST NOT 记录思考正文
