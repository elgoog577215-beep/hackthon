# 用户行为与任务转化分析

本系统使用两套相互兼容的数据：

- `user_operation_logs`：保留旧驾驶舱的功能使用次数与 DAU/WAU 口径。
- `analytics_events`：页面行为、匿名访问、活跃停留、滚动深度和任务生命周期的权威事件源。

## 事件契约

客户端批量上报 `POST /api/analytics/events`，每批 1～50 条，单个访问者每分钟最多 240 条。`event_id` 唯一，重复请求不会重复落库。服务端忽略任何客户端身份声明：有合法 Bearer Token 时从 JWT 解析 `user_id`，否则仅保存 `anonymous_id`。

通用关联字段：

| 字段 | 用途 |
| --- | --- |
| `anonymous_id` | 浏览器级匿名访客标识，登录前后保持一致 |
| `session_id` | 30 分钟无活动后轮换 |
| `page_instance_id` | 单次页面实例；同一路由再次进入会生成新值 |
| `workflow_id` | 关联一次任务的开始、成功、失败或取消 |
| `occurred_at` / `received_at` | 客户端发生时间和服务端接收时间 |
| `schema_version` | 事件契约版本，当前为 1 |

事件集合如下；页面和 `feature_used` 可由客户端上报，任务生命周期只能由服务端写入，客户端伪造会被拒绝：

- `page_view`
- `page_engagement`
- `scroll_depth_reached`
- `task_started`
- `task_succeeded`
- `task_failed`
- `task_cancelled`
- `feature_used`

## 指标定义

- 页面浏览量：`page_view` 数量。
- 访问用户：优先按登录 `user_id` 去重，否则按 `anonymous_id` 去重。
- 活跃停留：只累计页面可见期间的时间；每 30 秒和隐藏、切换、离开时上报增量，不累计后台标签页时间。
- 跳出：同一会话只有一个页面实例且活跃时间少于 10 秒；任务转化单独统计，不与页面会话强行关联。
- 滚动深度：每个页面实例只记录首次跨过 25%、50%、75%、100% 的里程碑。
- 任务完成率：统计窗口内开始的不同 `workflow_id` 中，在窗口结束前出现 `task_succeeded` 的比例。
- 任务失败率/取消率：同一开始任务 cohort 中分别出现失败/取消终态的比例。重试中的任务不提前记失败。

## 隐私与保留

- 页面只保存路由模板或路径，不保存 query/hash，避免课程、记录和 OAuth 参数进入分析库。
- `properties` 使用白名单；文件名、邮箱、手机号、正文和自由文本会被丢弃。
- 原始事件默认保留 180 天，可通过 `ANALYTICS_RAW_RETENTION_DAYS` 调整，最低 30 天；服务每天自动清理。
- 用户删除后，分析事件和旧操作日志的 `user_id` 置空，聚合历史保留为匿名数据。

## 驾驶舱与运维

管理员接口 `GET /api/admin/dashboard/behavior-metrics?days=7` 返回 PV、UV、会话数、活跃时长、跳出、滚动和任务终态。驾驶舱的时间范围支持 1～365 天。

上线后至少监控：上报接口 4xx/5xx、429、事件写入失败、重复事件比例、最新 `received_at` 延迟，以及开始后长期没有终态的任务数量。
