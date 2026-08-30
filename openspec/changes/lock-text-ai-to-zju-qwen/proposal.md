## Why

灵知本地与生产发布仍会把文本请求发往 ModelScope 或 DeepSeek，与已确认的基础设施边界冲突。系统需要把所有文本 AI 角色固定到浙大自建 `qwen3.8-27b` 节点，并防止以后的配置或发布再把请求切回 ModelScope。

## What Changes

- **BREAKING**：删除灵知文本 AI 的 ModelScope 主路由、最后回退和本地 Codex 旁路；这些文本端点不再是可支持配置。
- 课程生成、AI 老师、内容修改、评估与 PPT 文本规划统一使用浙大自建 `qwen3.8-27b`。
- 生产发布从 GitHub Secrets 读取自建端点和凭据，不在仓库、Actions 日志或回复中暴露私有地址。
- 运行时拒绝 ModelScope 文本端点和非 `qwen3.8-27b` 文本模型，错误配置必须显式失败，不得静默切换提供方。
- 增加脱敏的生产模型探针，即使检索或其他诊断项失败，仍能单独证明真实文本请求使用了指定模型。
- 更新本地示例、正式技术文档、项目长期规则和服务器私有映射。赛事作品的魔搭展示链接与独立图像生成不在本次范围。

## Capabilities

### New Capabilities

- `text-ai-provider-policy`: 定义灵知文本 AI 只能使用浙大自建 `qwen3.8-27b`，禁止 ModelScope 文本路由和隐式提供方回退。

### Modified Capabilities

无。

## Impact

- 后端：`backend/ai_base.py`、模型路由遥测与相关测试。
- 发布：`.github/workflows/deploy-lingzhi.yml`、`.github/workflows/production-diagnostics.yml`、生产 `/opt/lingzhi/state/.env`。
- 配置：`.env.example`、本地私有 `.env`、GitHub Secrets；端点和凭据不进入 Git。
- 文档与规则：`README.md`、`docs/系统架构.md`、`docs/产品状态.md`、`docs/事实.md`、`AGENTS.md`及仓库外私有服务器登记。
- API 和数据模型不变；未配置或配错时会从“尝试其他提供方”改为“显式不可用”。
