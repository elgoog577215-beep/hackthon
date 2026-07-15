# tighten-ai-learning-loop Specification

## Requirements

### Requirement: 前端问答必须默认使用结构化事件流

前端 AI 问答 MUST 默认调用 `/api/ask_events`，并按事件类型处理回答正文、最终答案和 metadata。前端 MUST NOT 在主路径中从正文流解析 `---METADATA---`。

#### Scenario: 结构化问答流返回正文和 metadata

- **WHEN** 用户在前端提问
- **THEN** 前端 MUST 调用 `/api/ask_events`
- **AND** `answer` 事件 MUST 增量更新当前 AI 回答正文
- **AND** `final_answer` 事件 MUST 覆盖最终正文
- **AND** `metadata` 事件 MUST 更新引用、摘要和节点定位信息

#### Scenario: metadata 缺失或解析失败

- **WHEN** 回答流没有可用 metadata
- **THEN** 前端 MUST 保留正文回答
- **AND** MUST NOT 创建 AI 笔记
- **AND** MUST NOT 让问答界面崩溃

### Requirement: 学习事件和 AI 上下文必须使用同一用户标识

后端问答相关路径 SHOULD 从 `X-User-Id` 读取用户标识；未提供时 MUST 回退默认用户。该用户标识 MUST 同时用于学习事件记录和 AI Learning Context 构建。

#### Scenario: 请求携带 X-User-Id

- **WHEN** 客户端调用 `/api/ask` 或 `/api/ask_events` 并携带 `X-User-Id`
- **THEN** 用户提问事件和回答完成事件 SHOULD 记录该用户标识
- **AND** AI Learning Context SHOULD 使用同一用户标识读取学习状态

#### Scenario: 请求未携带 X-User-Id

- **WHEN** 客户端未携带 `X-User-Id`
- **THEN** 系统 MUST 使用默认用户标识
- **AND** 旧接口行为 MUST 保持兼容

### Requirement: AI 输出质量事件必须回流课程质量报告

课程质量报告 SHOULD 聚合当前课程的 `ai_output_quality_assessed` 学习事件，标记低质量节点、课程级质量概览和推荐修复动作。

#### Scenario: 节点存在低质量输出事件

- **GIVEN** 某节点最近一次 AI 输出质量分低于 `0.65`
- **WHEN** 系统构建 `GenerationQualityReport`
- **THEN** 报告 SHOULD 在 `weak_node_outputs` 中列出该节点
- **AND** SHOULD 给出最小修复建议

#### Scenario: 输出包含需核验外部来源

- **GIVEN** 质量事件 issues 包含需要核验外部来源的表述
- **WHEN** 系统构建推荐修复动作
- **THEN** SHOULD 建议人工检查来源
- **AND** MUST NOT 自动伪造或补充来源

### Requirement: 任务管理瘦身不得改变任务协议

`TaskManager._process_node` MAY 抽出落盘和完成推送 helper，但 MUST 保持现有调度、重试、WebSocket payload 和节点保存行为。

#### Scenario: 节点生成完成

- **WHEN** 节点正文生成并修复完成
- **THEN** 系统 MUST 保存最终 `node_content`
- **AND** MUST 推送现有节点完成事件
- **AND** 任务进度行为 MUST 保持兼容

### Requirement: 高价值生成场景可以选择强模型

课程大纲、弱点补救和质量修复 MAY 使用更强模型或更深推理配置；普通节点正文流式生成 SHOULD 保持当前低延迟路径。

#### Scenario: 普通节点正文生成

- **WHEN** 后台生成普通节点正文
- **THEN** 系统 SHOULD 使用当前流式低延迟路径

#### Scenario: 课程大纲或补救内容生成

- **WHEN** 系统生成课程大纲、弱点补救或质量修复内容
- **THEN** 系统 MAY 选择强模型路径
- **AND** API key 缺失时 MUST 保持现有降级行为
