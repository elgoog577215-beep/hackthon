# 运营后台（Operations Admin Backend）

独立的运营后台页面，挂在现有 Vue 应用的 `/admin/*` 路径下，复用同一份后端服务与统一身份认证。

提供五大能力：

1. **智能体广场后台管理** — 全量 CRUD + 上下架开关 + **拖拽排序**；新建默认不上架；首页 `HomeView` 从数据库拉取。
2. **用户反馈管理** — 后台筛选 + 导出 Excel；附件列支持**缩略条 + 弹窗预览 + 下载**。
3. **数据驾驶舱** — 累计用户 / 日活 / 周活；用户明细导出；**功能使用排序 BarChart**（常驻 + 智能体）；**智能体使用 Top 10**。
4. **用户操作日志** — 统一 `user_operation_logs` 事件表，覆盖 10 项常驻功能（大纲 / PPT / 教案 / 题目生成、我的课程、智能对话、智云课堂分析、上传视频分析、文本分析待上线、PPT 分析待上线）+ 论文审查 / 反馈提交 / 智能体点击，**也是 DAU / WAU 唯一数据源**。
5. **审计日志** — 取证级 `audit_logs` 表 + `log_audit(...)` helper + 通用 `POST /audit/report` 上报端点；覆盖 admin 所有写入 / PII 导出 + 论文检测「上传 / 删除 / 导出」demo；保留 IP、User-Agent、payload（自动 PII 关键字脱敏 + 8KiB 截断）、`idempotency_key`。

---

## 鉴权机制

> 自 2026 May 27 起平台启用 RBAC 三角色体系（admin / teacher / student），权威源是 `users.role` 数据库字段。配置文件白名单 `ADMIN_ZJU_IDS` 保留作为启动 bootstrap 兜底，**日常增删管理员通过 `/admin/users` 改角色**，不再改环境变量。完整设计见 [`rbac.md`](./rbac.md)。

**配置文件白名单（bootstrap 兜底）**：在 `.env` 中以逗号分隔配置一组 ZJU 学工号；服务启动时会自动把这些用户的 `users.role` 写为 `admin`（若该用户已存在）；OAuth 首次登录时若 zju_id 在白名单内，新建的用户直接落 `role='admin'`。

```bash
# .env
ADMIN_ZJU_IDS=0010759,0011234,0012345
```

- 解析逻辑：`server/common/config.py::Settings.ADMIN_ZJU_IDS`，返回 `set[str]`。
- 启动回写：`server/infra/db/database.py::_bootstrap_admin_whitelist`，按白名单 `UPDATE users SET role='admin' WHERE zju_id = ANY(...)`，幂等。
- 后端校验：`server/service/admin/auth.py::is_admin_user`，**优先看 `user.role == 'admin'`**；白名单仅作 fallback（覆盖启动 bootstrap 之前的 race）。
- 前端探测：`GET /admin/check` 返回 `{is_admin: bool}`，逻辑同上。
- 教师守卫：`server/service/auth/service.py::get_current_teacher`（admin 自动覆盖 teacher 场景）；用于 `/resource/*`、`/course/*`、`/video/*` 等教学端点。

**管理员动态增删（推荐路径）**：通过 `/admin/users` 界面调用 `PATCH /admin/users/{id}/role`，写 `audit_logs.action=user.role_update`，admin 不能把自己改成非 admin。环境变量适合**首次部署**或**应急恢复**——日常运营走 UI。

---

## 数据库

### `agents` 表

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | String PK | snowflake 默认值 |
| `card_key` | String unique | 稳定标识，用于 seed 幂等；后台新建可为空 |
| `title` | String | 标题 |
| `description` | Text | 描述（避开 `desc` SQL 关键字） |
| `tags` | ARRAY(String) | 标签数组 |
| `popular` | Boolean | 是否热门 |
| `badge_bg` / `badge_fg` | String | 标签底色/前景色（hex） |
| `icon_path` | Text | SVG `d=` 属性值 |
| `href` | String nullable | 外链 URL（优先生效） |
| `route_to` | String nullable | 内部 Vue 路由 |
| `enabled` | Boolean | 是否上架 |
| `sort_order` | Integer | 升序排序 |
| `create_time` / `update_time` | DateTime(tz) | 同其它业务表规范 |

### 首次启动 seed

`server/infra/db/seeds/agent_seed.py` 在 `init_db()` 末尾调用 `seed_agents()`：

- 仅当 `agents` 表为空时，批量插入历史硬编码的 11 个智能体（6 启用 + 5 停用，`ppt` 标记为热门）。
- **幂等**：再次启动不会覆盖运营修改/删除的数据。
- 运营从后台删除的 agent 不会被 seed 复活。

### `user_operation_logs` 表

统一的用户操作事件日志，作为驾驶舱图表与「功能使用排序」的唯一数据源。

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | String PK | snowflake |
| `user_id` | String FK → users.id | 匿名用户跳过埋点 |
| `feature_type` | String 索引 | 见下方枚举 |
| `feature_key` | String 索引 nullable | 见下表「子类映射」一列 |
| `action` | String nullable | 动作语义：`send/submit/analyze/generate/visit` |
| `extra` | JSONB nullable | 写入时刻的轻量上下文（如 `{"video_id": "..."}`） |
| `create_time` | DateTime(tz) 索引 | server_default = 当前时间（精确到秒） |

`feature_type` 枚举见 `server/common/models/operation_log.py::FeatureType`：

- `chat`、`essay_check`、`video_analysis`、`resource`、`course`、`feedback`、`agent`、`text_analysis`（待上线）、`ppt_analysis`（待上线）

资源生成 / 视频分析两类通过 **`feature_key` 二级区分**（沿用 `agent` 用 `feature_key=agent_id` 的惯例），驾驶舱图表里展开成独立行：

| feature_type | feature_key | 展示名 |
| --- | --- | --- |
| `resource` | `outline` | 大纲生成 |
| `resource` | `ppt` | PPT 生成 |
| `resource` | `teaching_plan` | 教案生成 |
| `resource` | `question_bank` | 题目生成 |
| `video_analysis` | `upload` | 上传视频分析 |
| `video_analysis` | `zhiyun` | 智云课堂分析 |

精细化标签集中维护在 `operation_log.FEATURE_DISPLAY`；常驻 12 项顺序在 `RESIDENT_FEATURE_SLOTS`；待上线集合在 `PENDING_FEATURE_SLOTS`。

下次启动时 `Base.metadata.create_all` 会自动建表（含 4 个索引 + FK），**无需 alembic 迁移**。

### 埋点位置

由统一 helper `service.operation_log.log_operation(db, user_id, feature_type, feature_key?, action?, extra?)` 写入。失败仅 warning，不会让业务请求挂掉。

| feature_type | feature_key | 触发路由 | action |
| --- | --- | --- | --- |
| `chat` | — | `POST /chat/send` | `send` |
| `essay_check` | — | `POST /essay/upload` | `submit` |
| `video_analysis` | `upload` / `zhiyun` | `GET /video/analyze`（按 `videos.source` 决定） | `analyze` |
| `resource` | `outline` / `ppt` / `teaching_plan` / `question_bank` | `POST /resource/generate`（按 `params.resource_type`） | `generate` |
| `course` | — | `POST /course/visit`（前端 `MyCoursesView` onMounted 触发） | `visit` |
| `feedback` | — | `POST /feedback` | `submit` |
| `agent` | `agent_id` | `POST /agents/visit/{id}`（首页卡片点击） | `visit` |
| `text_analysis` | — | **待上线**，暂无埋点入口 | — |
| `ppt_analysis` | — | **待上线**，暂无埋点入口 | — |

`videos` 表加了 `source` 列（`upload` 默认，`import_zhiyun_video` 设 `zhiyun`），是「视频来源」的权威记录；`analyze_video` 读它给 `feature_key` 赋值，重复分析也能正确归类。

---

## API 接口

所有 `/admin/*` 接口要求 `Authorization: Bearer <jwt>` 且 ZJU ID 在白名单内，否则 401。

### 通用

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/admin/check` | 当前用户是否为管理员；非管理员返回 `{is_admin: false}`（不抛 401） |

### 智能体管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/agents/public` | **公开接口**（无需登录），首页 HomeView 使用：返回 `enabled=true` 的卡片，按 `sort_order` ASC |
| `POST` | `/agents/visit/{agent_id}` | **埋点专用**：用户点击首页智能体卡片时调用一次，仅写 user_operation_logs，不阻塞跳转 |
| `GET` | `/admin/agents` | 全量列表（含未上架），按 `sort_order` ASC |
| `POST` | `/admin/agents/operation` | `OperationEnum`：CREATE / UPDATE / DELETE。**CREATE 时 `enabled` 默认 false**（未传入时） |
| `POST` | `/admin/agents/toggle` | `{id, enabled}` 上下架快捷开关 |
| `POST` | `/admin/agents/reorder` | `{id_list: [...]}` 拖拽排序：完整新顺序，后端按 idx*10 重置 `sort_order`。`id_list` 必须覆盖全部 agent，缺/多/重复会报错 |

### 用户反馈

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/admin/feedbacks` | 查询参数 `rating_type` (positive/neutral/negative) 与 `min_length`；JOIN 用户表，返回的 `image_paths: list[str]` 用于附件渲染 |
| `GET` | `/admin/feedbacks/export` | 返回 `.xlsx`，列：序号 / 反馈ID / 用户姓名 / 学工号 / 学院 / 星级 / 评价文案 / 图片路径 / 提交时间 |

附件渲染：列头从「图片」改为「附件」。每行展示前 3 个缩略（按扩展名识别图/视频/其他），点击单元格唤起 `AttachmentLightbox`（图片原图、视频内嵌 `<video controls>`、其他类型显示文件名 + 下载提示）。底部有持久「下载」按钮。后端路径形如 `uploads/attachments/xxx.jpg` 会被前端规范化为 `/static/attachments/xxx.jpg`（FastAPI 在 `main.py:56` 把 `uploads` 目录挂在 `/static`）。

### 数据驾驶舱

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/admin/dashboard/stats` | `{total_users, dau, wau, as_of}` |
| `GET` | `/admin/dashboard/users` | `keyword?` + `role?`（admin/teacher/student）+ `limit/offset` 分页；返回项含 `role` 字段 |
| `GET` | `/admin/dashboard/users/export` | 返回 `.xlsx`，列：序号 / 用户ID / 姓名 / 学工号 / 学院 / 角色 / 手机号 / 邮箱 / 注册时间。支持 `keyword?` + `role?` 过滤 |
| `PATCH` | `/admin/users/{user_id}/role` | body `{role: admin\|teacher\|student}`，写 `audit_logs.action=user.role_update`；admin 不能把自己改成非 admin（`BizException("不能降级自己")`） |
| `GET` | `/admin/dashboard/feature-usage` | `days=7`，返回 `[{feature_type, feature_key?, label, count, unique_users, pending}]`。**常驻 12 个 slot 永远全量返回**（缺数据补 0），非待上线按 count 倒序、待上线钉到末尾；上架智能体按 count 倒序追加；`pending=true` 时前端会给 label 加「（待上线）」后缀 |
| `GET` | `/admin/dashboard/agent-usage` | `days=7&limit=10`，仅返回 `enabled=true` 的智能体使用 Top N，含 `agent_id, title, count, unique_users` |

#### 课程访问埋点

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/course/visit` | **埋点专用**：用户进入「我的课程」页面时由前端 `visitMyCourses()` fire-and-forget 调用，仅写 `user_operation_logs(feature_type=course, action=visit)` |

### DAU / WAU 语义

> **活跃 = `user_operation_logs` 表当日 / 本周内有至少一条记录的去重 `user_id`**
>
> 自 2026-05-17 起从 `session_histories` 切换到 `user_operation_logs`：原口径只覆盖「AI 对话」，对只用资源生成 / 视频分析 / 我的课程的用户漏算。新口径覆盖全部 10 项常驻功能 + 论文审查 / 反馈 / 智能体点击。

- 时区：Asia/Shanghai。
- 日界：当日 00:00 起。
- 周界：本周一 00:00 起。
- **新旧口径不可直接比较**：切换前后历史数值有断点；如果运营需要回溯历史，可一次性把 `session_histories` 当成「chat send」事件回填到 `user_operation_logs`（非本次范围）。
- 前端 tooltip 已明示该定义。

### 审计日志

> **本节是平台侧的实现 / 运维参考。**
> 想给自己的 agent / 微服务接审计上报，请直接看 **[`audit-reporting.md`](./audit-reporting.md)**，里面有端点选型、鉴权、schema、命名约定、幂等键、PII 脱敏边界、curl / Python / Node 示例、同进程 helper 用法 与常见问题。

**新表 `audit_logs`**（取证口径，与 `user_operation_logs` 分立，不进驾驶舱聚合）。

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | String PK | snowflake |
| `actor_type` | String(20) | `admin` / `user` / `agent` / `system`；**由路由层根据鉴权强制覆盖**，请求体里同名字段会被忽略，避免越权伪装 |
| `actor_id` | String | admin → `users.id`；agent → 服务名；system → NULL |
| `actor_label` | String(200) | 可读标识（如 `张三/0010759`、`论文检测服务`） |
| `action` | String(100) | `<service>.<verb>`，例：`agent.update` / `essay_check.delete` |
| `target_type` / `target_id` / `target_label` | 见列名 | 被操作的资源；可空 |
| `payload` | JSONB | 写入前 8KiB 截断 + 关键字递归脱敏（`password / passwd / pwd / token / access_token / refresh_token / id_token / secret / api_key / apikey / authorization / auth / cookie / credential / credentials`，大小写不敏感） |
| `result` | String(20) | `success` / `failure` / `partial` |
| `request_ip` | String(64) | `X-Forwarded-For` 首段 → `X-Real-IP` → socket 对端；统一走 `common.utils.http.get_client_ip` |
| `user_agent` | String(500) | 截断到 500 |
| `extra` | JSONB | 未来扩展位 |
| `idempotency_key` | String(128) | agent 重试幂等键；`(actor_type, idempotency_key)` 加 `WHERE IS NOT NULL` 的**部分唯一索引**，冲突时静默吞掉视为成功 |
| `create_time` | DateTime(tz) | 索引，列表默认 `ORDER BY create_time DESC` |

索引：`(actor_type, actor_id, create_time)`、`(action, create_time)`、`create_time`、`(target_type, target_id)`、`(actor_type, idempotency_key) WHERE idempotency_key IS NOT NULL`。**故意不加** `actor_id → users.id` 的 FK，审计必须跨越用户被删除的事件保留。

**写入路径**：

- 内部进程（业务路由）— 直接调用 `service.audit.log_audit(db, *, actor_type, action, ...)` helper（fail-safe：异常仅 warning + rollback，不污染业务请求）。
- 外置 agent — `POST /audit/report` HTTP 端点（鉴权头 `X-Audit-Service-Token`，匹配 `settings.AUDIT_SERVICE_TOKEN`；常量时间比较，token 未配置时端点关闭）。
- admin 手动补录 — `POST /admin/audit/report` HTTP 端点（admin JWT 鉴权）。

**已接入位置**：

| 端点 | action | actor_type |
| --- | --- | --- |
| `POST /admin/agents/operation` (create/update/delete) | `agent.create` / `agent.update` / `agent.delete` | admin |
| `POST /admin/agents/toggle` | `agent.toggle` | admin |
| `POST /admin/agents/reorder` | `agent.reorder` | admin |
| `GET /admin/feedbacks/export` | `feedback.export` | admin |
| `GET /admin/dashboard/users/export` | `user.export` | admin |
| `POST /essay/upload` | `essay_check.submit` | user |
| `DELETE /essay/{task_id}` | `essay_check.delete` | user |
| `POST /essay/export/stream` | `essay_check.export` | user |

**API 接口**：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/audit/report` | 外置 agent 上报。Header `X-Audit-Service-Token` 必填；body 见下方 schema。actor_type 路由层强制为 `agent` |
| `POST` | `/admin/audit/report` | admin 手动补录。actor_type / actor_id / actor_label 由当前 admin 强制覆盖 |
| `GET` | `/admin/audit-logs` | 查询参数：`actor_type, actor_id, action, target_type, target_id, time_from, time_to, limit (≤1000), offset` |
| `GET` | `/admin/audit-logs/export` | 同样的过滤参数（无分页），Excel 格式，hard cap 10000 行 |

**上报 body schema（`AuditReportParams`）**：

```json
{
  "action": "essay_check.delete",
  "actor_id": "essay_check",
  "actor_label": "论文检测服务",
  "target_type": "essay_task",
  "target_id": "abc123",
  "target_label": "user_paper.pdf",
  "payload": {"size_bytes": 1234567},
  "result": "success",
  "extra": null,
  "idempotency_key": "essay-delete-abc123"
}
```

`actor_type` **不接受** body 字段；admin 端点写 `admin`，service-token 端点写 `agent`。`request_ip` / `user_agent` / `create_time` 由 server-side 自动填充。

**新功能接审计的步骤**：

1. 业务路由签名加 `request: Request` + `db: AsyncSession = Depends(get_db)` 依赖（已经有的就不重复）。
2. 业务动作成功之后调 `await log_audit(db, actor_type=..., action="<svc>.<verb>", target_type=..., target_id=..., payload=..., request_ip=get_client_ip(request), user_agent=request.headers.get("User-Agent"))`。
3. 失败路径在调用方 try/except 里把 `result="failure"` 也写一条；helper 本身不会抛。

### Excel 中文文件名

响应头使用 RFC 5987 编码，保证中文文件名能稳定下载：

```http
Content-Disposition: attachment; filename*=UTF-8''%E7%94%A8%E6%88%B7%E5%8F%8D%E9%A6%88_20260512_100000.xlsx
```

---

## 前端架构

```
client/website/src/
├── api/
│   ├── admin.ts          运营后台 API（check / agents 含 reorder / feedbacks / dashboard 含 feature-usage、agent-usage / xlsx 下载工具）
│   ├── agents.ts         公开智能体广场 API + visitAgent 埋点
│   └── types.ts          + PublicAgentDetail / AdminAgentDetail / AdminAgentReorderParams / AdminFeedbackDetail / AdminUserDetail / DashboardStats / FeatureUsageItem / AgentUsageItem
├── components/
│   ├── AttachmentLightbox.vue       通用附件预览模态（图/视频/其他三态 + 翻页 + 下载）
│   └── charts/BarChart.vue          纯 SVG 水平柱状图（沿用 ResourceAnalysisReportView 的手写图惯例）
├── layouts/
│   └── AdminLayout.vue   240px sidebar + 主区，复用全局 Navbar
├── views/admin/
│   ├── AdminDashboardView.vue    3 张指标卡片 + 功能使用 BarChart + 智能体 Top BarChart + 用户表
│   ├── AdminAgentsView.vue       拖拽排序表格 + 上下架 toggle + 编辑/删除
│   ├── AdminAgentEditModal.vue   新建/编辑模态（新建时上架复选框默认未勾）
│   └── AdminFeedbacksView.vue    筛选 + 列表 + 附件缩略条 + lightbox + 导出
├── stores/user.ts        + isAdmin / adminChecked / refreshAdminStatus
└── router/index.ts       + /admin/* 路由 + admin 守卫
```

### 智能体拖拽排序

`AdminAgentsView.vue` 使用原生 HTML5 drag-and-drop（不引入第三方库）：

- 每行 `draggable="true"`，行首有 `⋮⋮` 把手 + sort 数字
- `@dragstart`/`@dragover`/`@dragleave`/`@drop`/`@dragend` 维护 `draggingIndex` + `dragOverIndex` + `dragOverPosition('above'|'below')`
- 落点指示：hover 行上半 → 顶部蓝色横线（drag-over-above）；下半 → 底部蓝色横线（drag-over-below）
- 落下时乐观更新本地数组，调 `reorderAdminAgents({id_list})` 后再 `loadAgents()` 拿权威 sort_order；失败回滚

### 首页智能体卡片埋点

`HomeView.handleAgentCardClick(card)` 调一次 `visitAgent(card.id)`（fire-and-forget），随后继续原有 href / route_to 跳转逻辑。埋点失败不会阻塞跳转。

### 路由守卫流程

```
beforeEach
├── 本机？
│   ├── 非 admin 路由 → 直接放行
│   └── admin 路由 → 调 /admin/check 实测；失败回 /
└── 非本机？
    ├── public 且非 admin → 放行
    ├── 无 token → 跳 /auth
    └── admin 路由 → 必要时 fetchCurrentUser → 检查 isAdmin → 失败回 /
```

### HomeView 迁移

`HomeView.vue` 移除原有的 11 项硬编码 `agentCards` 数组，改为：

- `onMounted` 调用 `fetchPublicAgents()`
- 收到响应后做 snake_case → camelCase 映射（`description→desc`、`badge_bg→badgeBg` 等）
- 后端已过滤 `enabled=True` + 排序，前端不再做二次过滤
- 模板绑定、`handleAgentCardClick` 完全保持不变；广场样式像素一致

---

## 部署与使用

### 后端

```bash
cd server
# 1. 写白名单 + 审计 service token（agent 上报必填，未配置则关闭外部上报端点）
echo "ADMIN_ZJU_IDS=你自己的学工号" >> .env
echo "AUDIT_SERVICE_TOKEN=请生成一个随机字符串" >> .env

# 2. 安装新增依赖
pip install -r requirements.txt   # 新增 openpyxl==3.1.5

# 3. 启动
python main.py
# 首次启动会自动建 agents 表并 seed 11 条历史数据
# 同时自动建 audit_logs 表（不需要手工 SQL）
```

#### 启动自动迁移

`videos` 表新增 `source` 列用于区分上传视频 vs 智云课堂导入。`Base.metadata.create_all` 不能给存量表加列，因此 `server/infra/db/database.py::_apply_startup_migrations()` 在每次启动会跑一批幂等 SQL（带 `IF NOT EXISTS`）补齐这类变更：

```sql
ALTER TABLE videos ADD COLUMN IF NOT EXISTS source VARCHAR NOT NULL DEFAULT 'upload';
```

**线上部署 = `git pull` + 重启服务**，不需要手工 SQL。如果未来需要再加列 / 加索引，统一往 `_STARTUP_MIGRATIONS` 列表里追加一条（必须带 `IF NOT EXISTS` 保持幂等）。

### 前端

```bash
cd client/website
npm install
npm run build      # 或 npm run dev 开发模式
```

### 验证清单

后端：

- [ ] `SELECT COUNT(*) FROM agents;` 应为 11（首次启动后）
- [ ] `\d user_operation_logs` 应能看到 4 个索引 + FK
- [ ] `\d videos` 应能看到 `source` 列（默认 'upload'）
- [ ] `curl /api/agents/public` 不带 token 也能返回已上架的卡片
- [ ] 用白名单内学号登录后 `GET /api/admin/check` 返回 `{is_admin: true}`
- [ ] `GET /api/admin/dashboard/stats` 返回三个数字，DAU/WAU 基于 `user_operation_logs` 计算
- [ ] `GET /api/admin/dashboard/feature-usage` 返回至少 12 条常驻 slot + N 条 agent；待上线两条 `pending=true`
- [ ] `GET /api/admin/feedbacks/export` 下载后用 Excel 打开，中文表头与文件名正常
- [ ] `POST /api/admin/agents/operation create`（不带 `enabled`）→ 新建行 `enabled=false`
- [ ] `POST /api/admin/agents/reorder` 提交反转的 id_list → 列表顺序整体反过来；缺/多 ID 会 400
- [ ] `POST /api/agents/visit/{id}` × N → `/admin/dashboard/agent-usage` 该 agent 的 count 同步增长
- [ ] 触发一次「大纲」/「PPT」/「教案」/「题目」生成 → `feature-usage` 对应行 count +1，其他三类不变
- [ ] 上传一段本地视频并分析 → 「上传视频分析」+1；导入并分析一节智云课堂视频 → 「智云课堂分析」+1
- [ ] `POST /course/visit` 200 + `user_operation_logs` 新增 `feature_type=course, action=visit` 一行
- [ ] `\d audit_logs` 看到全部列 + 5 个索引（含部分唯一索引 `ix_audit_idem`）
- [ ] `POST /admin/agents/toggle` 后 `SELECT * FROM audit_logs WHERE action='agent.toggle' ORDER BY create_time DESC LIMIT 1` 看到 admin 写入，`actor_type=admin`，`request_ip` / `user_agent` 非空
- [ ] `POST /audit/report` 不带 Header → 401；Header 正确 → 200，DB 中 `actor_type=agent`（body 里塞 admin 也被覆盖）
- [ ] `payload={"password": "p", "nested": {"api_key": "k"}}` → DB 中两个值都变 `"***"`
- [ ] 用同一 `idempotency_key` + `actor_type=agent` 调 `/audit/report` 两次 → 第二次也 200（IntegrityError 被吞），DB 仅一行
- [ ] 删除一个 essay task → `audit_logs` 多一条 `essay_check.delete` / `actor_type=user`

前端：

- [ ] 首页 Network 面板能看到 `/api/agents/public` 请求并渲染卡片；点击任一卡片 Network 出现 `/api/agents/visit/{id}` 200
- [ ] 管理员账号访问 `/admin/dashboard`：3 张数字卡 + 功能使用 BarChart（含 10 项常驻 + 论文审查 + 反馈，含两条「待上线」灰条）+ 智能体 Top BarChart + 用户表；切换时间范围（今天/近 7 天/近 30 天）数据更新
- [ ] DAU / WAU tooltip 文案为「在 user_operation_logs 留下任意一条记录的去重用户数」
- [ ] 打开 `/my-courses` → Network 面板看到 `POST /api/course/visit` 200；驾驶舱「我的课程」+1
- [ ] `/admin/agents`：每行左侧 `⋮⋮` 把手；拖拽落下后顺序保持，刷新页面仍然如此
- [ ] `/admin/agents` → 新建智能体：「上架」复选框默认未勾
- [ ] `/admin/feedbacks`：列头是「附件」；缩略条点击弹出 Lightbox；翻页 + 下载工作
- [ ] `/admin/audit-logs`：执行者类型 / 学工号 / 动作 / 目标类型 / 时间区间组合筛选生效；「加载更多」累计；「详情」按钮唤起 modal，`payload` 和 `extra` pretty-printed
- [ ] `/admin/audit-logs` →「导出 Excel」：文件名 `审计日志_YYYYMMDDHHmmss.xlsx`，与当前筛选一致
- [ ] 非管理员访问 `/admin/*`：跳回 `/`

---

## 常见问题

**Q：把某个 seed 出来的 agent 删除后重启会复活吗？**
A：不会。`seed_agents()` 仅在表为空时执行；只要表里还有任何一条记录就跳过 seed。

**Q：怎么把首页智能体广场恢复到原来的硬编码状态？**
A：不需要恢复。后台已经能完全管理，包括恢复 seed 数据 —— 把 `agents` 表清空后重启即可重新 seed。

**Q：DAU/WAU 与公司其它系统口径不一致？**
A：本项目无独立的登录日志，自 2026-05-17 起 DAU/WAU 改为按 `user_operation_logs` 表算（任意一条记录 = 当日活跃），等价于「至少使用或访问过一个功能的用户」。如需「登录即活跃」语义，需要先新增 `login_logs` 表。

**Q：升级前的 `feature_type='resource' / 'video_analysis'` 旧数据怎么办？**
A：这类行 `feature_key IS NULL`，无法逆向恢复子类（不知道是 outline 还是 ppt、upload 还是 zhiyun）。新驾驶舱图表 SQL 里显式排除这两类无 key 的旧行，**不展示在常驻图表里**；原始数据仍保留在 `user_operation_logs` 表，需要时可直接 SQL 查。升级窗口极短（eaedf9d 落地到本次切换），实际影响行数很少。

**Q：管理员能改自己的 ZJU ID 白名单吗？**
A：不能。白名单是 `.env` 配置项，改完需要重启后端。这是有意设计：避免「管理员把自己提权」的副作用。

**Q：图标想换怎么办？**
A：编辑智能体时，「图标 SVG path」字段粘贴新的 SVG path `d=` 值即可。MVP 不支持图片上传；如需要，未来可在该字段旁加一个文件上传入口，存到 OSS 并保留 URL。

**Q：埋点漏了某个功能（比如视频上传/资源手动创建）怎么办？**
A：在对应 `server/api/*.py` 路由入口加一行：

```python
from common.models.operation_log import FeatureType
from service.operation_log import log_operation
# 路由签名加 db: AsyncSession = Depends(get_db)
await log_operation(db, user_id=current_user.id, feature_type=FeatureType.X, action="...")
```

要让新功能出现在驾驶舱图表里，**三件事**：
1. `common/models/operation_log.py::FeatureType` 加新枚举（如果属于已有大类，沿用现有枚举 + 新 `feature_key`）；
2. `FEATURE_DISPLAY` 加 `(feature_type, feature_key)` → 展示名映射；
3. `RESIDENT_FEATURE_SLOTS` 加 slot；若是「待上线」也加进 `PENDING_FEATURE_SLOTS`，图表会自动展示 0 计数 + 「（待上线）」后缀。

子分类**优先用 `feature_key`** 而不是新建枚举（参考 `resource` 的 4 个子类 / `video_analysis` 的 upload-vs-zhiyun）。

**Q：智能体拖拽排序在大量数据下会不会卡？**
A：reorder 接口提交完整 id_list，后端用 idx*10 重置全表，对 100 量级以下毫无压力。超过 1000 时建议改为「邻位交换」或分页拖拽，并把 sort_order 改为浮点降低 reshuffle 频率——目前没这个量。

---

## 本地 Docker 调试（dashboard-local）

为了离线调试驾驶舱，提供一套独立 docker-compose：

```bash
# 准备 server/.env.dev（已 gitignore），最关键：
ENV=LOCAL
DATABASE_HOST=db
DATABASE_PORT=5432
DATABASE_USER=postgres
DATABASE_PASSWORD=postgres
DATABASE_NAME=edu_ai_home
ADMIN_ZJU_IDS=99999999

# 起栈
cd deploy && docker compose -f docker-compose.dashboard-local.yml up -d

# 起前端（独立终端）
cd client/website && npm run dev
```

特性：
- Postgres 17 + uvicorn `--reload`，源码 volume 挂载，改文件即热重载
- `ENV=LOCAL` 时 `init_db` 末尾会自动跑 `seed_dashboard()`，建 5 个假用户 + 跨今/本周/上周/上月的 session_histories，让驾驶舱卡片非零
- 宿主 5433 暴露 Postgres、8000 暴露后端；与生产 `docker-compose.yml` 互不冲突
- 镜像 / 卷 / 容器名都带 `dashboard-local` 前缀，避免被生产编排误清

测试登录（仅 LOCAL/DEV）：

```bash
curl -X POST "http://127.0.0.1:8000/auth/test-login?name=开发管理员&zju_id=99999999"
```

返回的 token 写入前端 `localStorage.auth_token` 即可绕过 ZJU OAuth 调试。
