## ADDED Requirements

### Requirement: 前端问答必须默认使用结构化事件协议

前端主问答流程 MUST 默认调用 `/api/ask_events`，并按 SSE 事件类型处理回答正文、最终答案和 metadata。旧 `/api/ask` MAY 保留为兼容接口，但前端主路径 MUST NOT 依赖正文中的 `---METADATA---` 分隔符。

#### Scenario: 用户在课程页向 AI 老师提问

- **WHEN** 前端执行 `askQuestion`
- **THEN** 客户端 MUST 请求 `/api/ask_events`
- **AND** MUST 用 `answer` 事件增量追加当前 AI 消息正文
- **AND** MUST 用 `final_answer` 事件覆盖最终答案
- **AND** MUST 用 `metadata` 事件创建 AI 笔记、引用和节点定位

#### Scenario: SSE metadata 缺失或解析失败

- **WHEN** `/api/ask_events` 没有返回有效 metadata
- **THEN** 前端 MUST 继续展示已收到的回答正文
- **AND** MUST NOT 创建 AI 笔记
- **AND** MUST NOT 因 metadata 错误中断答案展示

### Requirement: AI 能力必须消费统一学习上下文

答疑、节点重写、内容补救、复习建议和课程迭代相关 AI 能力 MUST 通过 `build_ai_learning_context` 获取学习者上下文。模块自己的业务输入 MAY 作为显式参数或 `request_context` 进入该统一上下文，但 MUST NOT 新增平行画像、平行记忆或平行 Agent。

#### Scenario: 节点重写构造 prompt

- **WHEN** 用户请求重写节点、改写选区、扩展内容或摘要节点
- **THEN** 后端 MUST 通过 `CourseService._ai_learning_context_prompt` 调用 `build_ai_learning_context`
- **AND** prompt MUST 使用同一份学习状态解释
- **AND** 节点内容、选中文本、重写要求或补救要求 MUST 作为业务输入进入统一上下文

### Requirement: 原型阶段用户身份必须通过 X-User-Id 贯通

后端 MUST 提供轻量用户身份解析函数，优先读取请求头 `X-User-Id`，为空时回退 `DEFAULT_USER_ID`。该值 MUST 仅用于本地或原型阶段区分学习数据，MUST NOT 作为安全身份或鉴权依据。

#### Scenario: 请求携带 X-User-Id

- **WHEN** 客户端请求问答、学习状态、学习事件或节点 AI 能力时携带 `X-User-Id`
- **THEN** 后端 MUST 将该用户 ID 用于学习事件记录
- **AND** MUST 将该用户 ID 传入学习状态和 AI Learning Context 构建

#### Scenario: 请求未携带 X-User-Id

- **WHEN** 客户端请求未携带 `X-User-Id`
- **THEN** 后端 MUST 使用 `DEFAULT_USER_ID`
- **AND** 现有无登录原型流程 MUST 保持可用

### Requirement: AI 输出质量事件必须回流课程质量报告

课程质量报告 MUST 聚合已有 `ai_output_quality_assessed` 学习事件，并输出低质量节点、课程级质量概览和最小修复建议。系统 MUST NOT 在该阶段引入 LLM 评审，也 MUST NOT 自动重写课程。

#### Scenario: 课程存在低质量 AI 输出事件

- **WHEN** 某课程存在 `score < 0.65` 的 `ai_output_quality_assessed` 事件
- **THEN** `GenerationQualityReport` MUST 将对应节点写入 `weak_node_outputs`
- **AND** MUST 更新 `quality_event_summary`
- **AND** MUST 在 `recommended_repairs` 中给出重写、补结构、补例题、重新生成或人工检查来源等最小建议

#### Scenario: 输出通过但包含外部来源核验风险

- **WHEN** 质量事件 issues 包含需要核验外部来源表述
- **THEN** 课程质量报告 SHOULD 建议人工检查来源
- **AND** MUST NOT 自动改写课程事实

### Requirement: TaskManager 瘦身不得改变任务协议

`TaskManager._process_node` MAY 抽出节点正文落盘和节点完成推送 helper，但 MUST 保持任务调度、暂停、重试、停止、跳过、WebSocket payload 和节点生成落盘行为兼容。

#### Scenario: 节点正文生成完成

- **WHEN** `_process_node` 收集到最终正文
- **THEN** 后端 MUST 保存 `node_content`、`content_blocks`、`generation_status`、`generated_chars` 和 `error_summary`
- **AND** MUST 推送与原来兼容的 `node_finalized` 和 `node_completed` 消息
- **AND** MUST NOT 改变前端接收的任务进度协议

### Requirement: 模型路由必须保持低成本默认

普通节点正文流式生成 MUST 继续使用当前默认模型路由。课程大纲、弱点补救、质量修复和课程迭代建议 MAY 使用更强模型或 `enable_thinking`，但 MUST NOT 全局打开 thinking，也 MUST NOT 引入新的 provider 抽象。

#### Scenario: 普通节点正文生成

- **WHEN** 系统执行普通节点正文流式生成
- **THEN** MUST 沿用当前默认模型配置
- **AND** MUST NOT 因本次改造全局启用 thinking

#### Scenario: 高价值规划或修复环节

- **WHEN** 系统执行课程大纲、节点重写、弱点补救或质量修复
- **THEN** 后端 MAY 通过现有 `AIBase` 参数启用更强模型路径或 thinking
- **AND** API key 缺失时 MUST 继续保持现有降级行为
