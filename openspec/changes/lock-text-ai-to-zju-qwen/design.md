## Context

当前 `AIBase` 允许 DeepSeek/ModelScope 作为主提供方，也会在主模型池耗尽后调用 `MODELSCOPE_*` 回退。生产工作流每次部署都会将 DeepSeek PPT 模型和 ModelScope 回退写入 `/opt/lingzhi/state/.env`；本地 `.env` 也仍以 ModelScope 为主路由。用户已确认灵知生产入口 `https://tuotuzju.com/lingzhi/` 的文本 AI 只能调用私有登记中的 `a800-qwen` 节点与 `qwen3.8-27b`。

节点已经通过实时 `/v1/models` 和 `/v1/chat/completions` 探针。私有地址和凭据不能写入 Git，生产依然通过 GitHub Secrets 向服务器的独立环境文件下发。

## Goals / Non-Goals

**Goals:**

- 所有文本 AI 角色只调用 `a800-qwen` 上的 `qwen3.8-27b`。
- 错误的 ModelScope 地址或其他文本模型在发起网络请求前被拒绝。
- 主模型失败时只按有限边界重试同一节点，不再切换外部提供方。
- 本地、CI 发布与生产运行时使用同一组配置字段和校验。
- 真实生产探针与检索诊断解除先后依赖，能单独证明模型路由。

**Non-Goals:**

- 不删除赛事作品的 ModelScope 部署链接字段。
- 不把文本模型当成图像生成模型，不改造独立图像提供方。
- 不改变课程、AI 老师或 PPT 的业务 API 协议。
- 不将私有服务器地址、账号或凭据写入仓库。

## Decisions

1. 使用 `ZJU_QWEN_BASE_URL` 作为私有端点锚点，`ZJU_QWEN_API_KEY` 作为凭据，模型 ID 固定为 `qwen3.8-27b`。`AI_API_*` 和 `AI_PPT_*` 作为现有运行时兼容投影，由配置脚本原子性写成同一端点和模型，不由工作流分别拼接。相比只改 `AI_API_BASE`，这能防止 PPT 专用配置继续去 DeepSeek。

2. 在 `AIBase` 初始化时集中校验所有文本角色：实际 base URL 必须与 `ZJU_QWEN_BASE_URL` 规范化后一致，所有候选模型必须等于 `qwen3.8-27b`，且不得配置 `MODELSCOPE_*` 文本回退或本地 Codex 旁路。相比只检查 host 不是 ModelScope，精确锚点能阻止误配到第三方兼容端点。

3. 保留现有单节点内的有限模型重试、超时、熔断与结构化错误，但移除 `ModelScope fallback` 客户端、切换分支和发布配置。错误时让业务层进入现有失败恢复，不能为了“看起来成功”把请求发给未授权外部模型。

4. 新建 `scripts/configure_zju_qwen_provider.py` 承担本地和生产环境文件的同源更新：校验私有 base URL 和模型，写入临时文件后替换，设置文本主路由与 PPT 角色，并删除 `MODELSCOPE_*` 和旧 DeepSeek 文本配置。脚本只输出脱敏结果。

5. 生产诊断先执行模型配置摘要和真实探针，再执行 SearXNG 等其他诊断。输出只包含模型 ID、路由名、状态和耗时，不打印 base URL 或凭据。

## Risks / Trade-offs

- [自建节点不可用时不再有外部提供方回退] → 保留结构化失败、有限重试、任务恢复和明确运维告警，但不违反提供方边界。
- [单个 27B 模型承担快速、深度和 PPT 角色可能改变延迟] → 先跑最小并发与真实业务探针，保留已有超时和并发限制，不通过引入另一提供方解决延迟。
- [生产服务器到 A800 的网络与本地不同] → 部署前探测端点，部署后从生产进程发起真实请求，不用本地成功代替线上验收。
- [私有 HTTP 端点未强制 TLS] → 只在已授权网络中使用，不在日志中暴露地址；HTTPS 和强鉴权作为后续基础设施加固。

## Migration Plan

1. 备份本地 `.env`、生产 `/opt/lingzhi/state/.env`、当前发布版本与持久数据。
2. 在 GitHub Secrets 中配置 `ZJU_QWEN_BASE_URL` 与 `ZJU_QWEN_API_KEY`，并在本地私有 `.env` 中写入同一映射。
3. 部署前验证 `/v1/models` 包含 `qwen3.8-27b`且最小结构化对话完整返回。
4. 部署代码和生产环境配置，重启 `lingzhi.service`，检查 Caddy、健康接口和静态资源。
5. 从生产进程发起通用文本角色和 PPT 文本角色探针，确认所有 attempt 的 model ID 都是 `qwen3.8-27b`、路由为 primary，且无 ModelScope 切换。
6. 如业务路径回归失败，回滚到备份发布版本和环境文件；回滚只用于恢复服务，不把 ModelScope 恢复为长期提供方。

## Open Questions

无。
