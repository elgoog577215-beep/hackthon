# text-ai-provider-policy Specification

## Purpose
把灵知生产环境中的课程生成、内容修改、评估和 PPT 文本规划统一约束到浙大自建 Qwen，确保配置选择、最终请求、健康检查、失败回滚与运行证据使用同一模型政策，不再静默落入公网或本地文本旁路。

## Requirements

### Requirement: 文本 AI 只能使用浙大自建 Qwen

灵知的课程生成、AI 老师、内容修改、评估和 PPT 文本规划 MUST 只把文本请求发往 `ZJU_QWEN_BASE_URL` 指定的私有端点，且模型 ID MUST 为 `qwen3.8-27b`。

#### Scenario: 通用文本请求使用指定模型

- **WHEN** 任一生产文本 AI 能力初始化提供方
- **THEN** 实际 base URL MUST 与 `ZJU_QWEN_BASE_URL` 规范化后一致
- **AND** 所有主模型、快速模型和候选模型 MUST 为 `qwen3.8-27b`

#### Scenario: PPT 文本角色不得使用独立外部提供方

- **WHEN** 系统初始化 PPT 故事或视觉文本规划角色
- **THEN** `AI_PPT_API_BASE` MUST 与 `ZJU_QWEN_BASE_URL` 一致
- **AND** `AI_PPT_STORY_MODELS` 与 `AI_PPT_VISUAL_MODELS` MUST 只包含 `qwen3.8-27b`

### Requirement: ModelScope 不得承载灵知文本请求

系统 MUST 在发起网络请求前拒绝 ModelScope 文本端点、`MODELSCOPE_*` 文本回退和任何隐式外部提供方切换。

#### Scenario: 误配为 ModelScope 主端点

- **WHEN** `AI_API_BASE` 或 `AI_PPT_API_BASE` 指向 ModelScope 或与 `ZJU_QWEN_BASE_URL` 不一致
- **THEN** 提供方初始化 MUST 返回可识别的配置错误
- **AND** 系统 MUST NOT 发起该文本请求

#### Scenario: 主模型请求失败

- **WHEN** `qwen3.8-27b` 返回超时、限流、配额或结构化失败
- **THEN** 调用层 MAY 在现有有限预算内重试同一端点和模型
- **AND** 调用层 MUST NOT 切换到 ModelScope、DeepSeek 或其他文本提供方
- **AND** 预算耗尽后 MUST 返回现有结构化失败以便任务恢复

#### Scenario: 本地网站配置其他文本旁路

- **WHEN** 本地网站运行环境把 `AI_LOCAL_PROVIDER` 配置为 `codex` 或其他非 HTTP 旁路
- **THEN** 提供方初始化 MUST 返回可识别的配置错误
- **AND** 系统 MUST NOT 调用该旁路

### Requirement: 生产发布必须使用私有配置同源更新所有文本角色

生产发布 MUST 从 GitHub Secrets 读取浙大 Qwen 端点与凭据，原子性更新 `/opt/lingzhi/state/.env` 的通用文本和 PPT 文本配置，并清除 ModelScope 文本配置。

#### Scenario: 部署一个新版本

- **WHEN** `main` 发布工作流配置生产模型
- **THEN** 工作流 MUST 在不输出私有地址和凭据的情况下验证 `qwen3.8-27b` 可用
- **AND** 环境文件 MUST 把通用、快速、PPT 故事和 PPT 视觉文本角色指向同一端点与模型
- **AND** 环境文件 MUST NOT 保留 `MODELSCOPE_API_KEY`、`MODELSCOPE_BASE_URL` 或 `MODELSCOPE_MODEL`

#### Scenario: 私有配置缺失或端点不可用

- **WHEN** GitHub Secret 缺失、模型列表不含 `qwen3.8-27b` 或结构化探针失败
- **THEN** 发布 MUST 在更新生产环境和切换发布版本之前失败

### Requirement: 生产模型探针必须与其他诊断解除依赖

生产诊断 MUST 能单独输出脱敏文本模型路由证据，检索、图像或课程数据的失败 MUST NOT 阻止模型探针执行。

#### Scenario: SearXNG 不可用但用户要求模型探针

- **WHEN** `probe_ai_model=true` 且 SearXNG 或其他诊断项失败
- **THEN** 工作流 MUST 仍从生产进程发起最小文本请求
- **AND** 输出 MUST 包含模型 ID、路由、状态和耗时
- **AND** 输出 MUST NOT 包含 base URL、API key 或请求正文
