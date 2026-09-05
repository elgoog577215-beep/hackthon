## Context

现有数据分层已经规定：`LearningEvent` 保存会影响学习进度、诊断、个性化和课程生长
的学习事实；模型调用遥测只回答生成性能与成本；任务状态只回答长任务是否可恢复。
页面访问和通用功能使用不属于其中任何一个真源，因此需要独立但更弱的分析账本。

本变更首先支持“产品是否真的被使用、主要入口和失败点在哪里”的周度判断，不尝试
一次建立增长归因、实验平台或用户画像系统。

## Goals / Non-Goals

**Goals:**

- 用稳定、可版本化的事件合同记录产品使用信号。
- 自动覆盖页面访问和所有 Axios 写操作，减少漏埋和事件命名漂移。
- 支持按用户治理原始记录，并安全获得全局聚合指标。
- 保证埋点离线、超时或存储失败不影响课程、学习和 AI 主链。
- 从源头禁止正文、答案、Prompt、错误消息、URL 查询、IP 和 User-Agent 进入账本。

**Non-Goals:**

- 不替代 `LearningEvent` 或从 UsageEvent 推导掌握状态。
- 不引入第三方分析 SDK、跨站 Cookie、设备指纹或广告归因。
- 不记录每次滚动、鼠标移动、按键或高频轮询。
- 不在本变更中建设可视化运营后台或实验分流平台。
- 不把客户端事件当成计费、权限或正式业务审计依据。

## Decisions

### Decision: UsageEvent 是独立的非权威分析账本

事件保存 `event_id / client_event_id / event_name / user_id / session_id /
surface / route_name / course_id / properties / client_occurred_at / received_at /
schema_version`。它可以用于聚合分析，但不得被 LearnerModel、LearningRuntime、
课程修订或权限判断消费。

### Decision: 事件类型和属性都使用白名单

V1 只接受：

| 事件 | 用途 | 允许的额外属性 |
| --- | --- | --- |
| `session_started` | 统计一次浏览器标签页会话 | `entry_kind` |
| `page_viewed` | 统计稳定 route name 的访问 | `navigation_kind` |
| `api_action_completed` | 统计写操作成功 | `method`、`route_template`、`status_code`、`duration_ms` |
| `api_action_failed` | 定位写操作失败 | 同上 |
| `client_error` | 发现脱敏前端运行错误 | `error_kind` |

所有字符串有长度上限；未知事件、未知属性、容器值和自由文本直接拒绝。route 只保存
Vue route name 或去掉查询参数并替换动态 ID 的 API 模板。

### Decision: 前端统一自动采集，业务结果仍由正式领域对象判断

router `afterEach` 记录最终页面；HTTP 拦截器只记录 `POST/PUT/PATCH/DELETE` 的终态。
采集器以 `sessionStorage` 保存会话 ID，以有界 `localStorage` 队列抵御刷新和短暂离线，
按身份分批上报。采集器使用独立 `fetch`，避免进入 Axios 拦截器造成递归。

一次 `api_action_completed` 只说明接口返回成功，课程是否发布、练习是否掌握等业务
结论仍由正式任务、课程和学习事实判断。

### Decision: 以服务端接收时间做聚合时间轴

客户端时间只用于排查体验顺序，聚合一律使用 `received_at`，避免客户端时钟漂移改变
DAU 和趋势。相同用户与 `client_event_id` 重试时返回原事件，不重复计数。

### Decision: 默认自托管并设置数据寿命

数据写入 `LINGZHI_DATA_DIR/usage_events.json`。默认保留 180 天、最多 200,000 条，
写入时清理过期记录并保留最近记录；两个阈值都可由环境变量在安全范围内调整。
服务端可通过 `LINGZHI_USAGE_TRACKING_ENABLED=false` 停止接收新记录，前端也可通过
`VITE_USAGE_TRACKING_ENABLED=false` 完全关闭浏览器采集。

### Decision: 原始记录按用户治理，全局只暴露聚合

普通身份只能查询汇总、导出或删除自己的 UsageEvent。全局摘要要求
`LINGZHI_ANALYTICS_ADMIN_TOKEN` 与 `X-Analytics-Admin-Token` 匹配；未配置时端点不可用。
管理端点不返回全局原始事件。

V1 身份边界复用项目现有 `X-User-Id` 稳定身份合同，不把它误述为正式账号鉴权。
多租户生产部署必须先接入真实账号/会话 authority，再把个人治理接口视为租户隔离证明。

## KPI Framework

### Primary KPIs

1. **有意义活跃用户**：窗口内至少产生一次页面访问或写操作的去重用户数。
2. **有意义活跃会话**：窗口内至少产生一次页面访问或写操作的去重会话数。
3. **写操作成功率**：成功写操作数 ÷（成功写操作数 + 失败写操作数）。

### Drivers

- 页面访问量与热点 route，判断入口采用情况。
- 成功写操作量与热点 route template，判断功能实际使用情况。

### Guardrails

- 写操作失败率不得被页面访问增长掩盖。
- 采集请求失败必须静默，不得改变正式请求结果或重复正式业务写入。
- 事件白名单测试必须证明敏感自由文本不能落盘。

当前没有可信历史基线，因此本变更不设置增长目标；先稳定采集一个完整观察周期，再基于
真实分布设定目标。

## Risks / Trade-offs

- 自动记录 HTTP 写操作能广覆盖，但 route template 只能说明“调用了什么”，不能替代
  领域终态；摘要必须与任务和领域对象交叉解释。
- 文件账本适合当前单实例阶段；多实例部署前需要迁移到具备唯一约束和保留策略的数据库。
- 本地队列会短暂保存脱敏事件；队列严格有界且不含正文，但仍需在用户删除后清空本机队列。

## Verification

- 后端测试覆盖白名单、幂等、身份隔离、保留期、容量、汇总、导出、删除和管理密钥。
- 前端测试覆盖路由模板脱敏、队列分身份、失败保留和关闭开关。
- 路由接线、OpenSpec 和受影响前后端测试全部通过。
