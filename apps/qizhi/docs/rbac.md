# RBAC 体系（管理员 / 教师 / 学生）

> 本文档面向「需要理解角色边界、改用户角色、或在自己的 service / agent 里读身份」的人。
> 与 [`audit-reporting.md`](./audit-reporting.md) 配合食用——所有角色变更都会写审计。

---

## 1. 三个角色

| role | 来源 | 能力 |
| --- | --- | --- |
| `admin` | `ADMIN_ZJU_IDS` 白名单（启动自动升级）或 admin 通过后台改 | 运营后台全部 + 教师全部 + 学生全部 |
| `teacher` | admin 通过 `/admin/users` 改 | 全部教学功能（大纲 / 教案 / PPT / 题目生成、视频分析、资源 / 课程、智能对话、广场、论文检测、反馈） |
| `student` | 新用户默认 | 智能对话、智能体广场、论文检测、意见反馈 |

**关键约束**：
- 新用户默认 `student`，OAuth 自动创建时同样默认 `student`。
- `admin` 角色的守卫自动覆盖 `teacher` 守卫（避免管理员被自己的 RBAC 拒之门外）。
- `admin` 不能把自己改成非 `admin`（后端 `BizException("不能降级自己")`）；要降级自己，让另一个 admin 改。

---

## 2. 数据库 schema

```sql
-- users.role
ALTER TABLE users
  ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'student';
CREATE INDEX ix_users_role ON users(role);
```

- 字段位置：`server/infra/db/models/user.py::User.role`
- 启动迁移：`server/infra/db/database.py::_STARTUP_MIGRATIONS`，幂等（`ADD COLUMN IF NOT EXISTS`）
- 白名单自动 bootstrap：`server/infra/db/database.py::_bootstrap_admin_whitelist`，启动后立即把 `ADMIN_ZJU_IDS` 中的用户 `role` 置为 `admin`
- 迁移顺序：`create_all → _apply_startup_migrations → _bootstrap_admin_whitelist → seed_*`（写死，必须按这个顺序）

**老用户处理**：启动迁移会给所有现有行写默认值 `student`；如果某用户应该是 admin 但不在白名单，让一个白名单 admin 通过后台把 ta 的角色改成 admin。

---

## 3. 鉴权守卫

### 3.1 守卫依赖

```python
# server/service/auth/service.py
def require_roles(*allowed: UserRole): ...

get_current_teacher = require_roles(UserRole.TEACHER, UserRole.ADMIN)  # admin 自动覆盖

# server/service/admin/auth.py
async def get_current_admin(current_user: User = Depends(get_current_user)) -> User: ...
```

### 3.2 端点对照表

| 守卫 | 端点 | 学生能用？ | 教师能用？ | 管理员能用？ |
| --- | --- | :---: | :---: | :---: |
| `get_current_user` | `/chat/*`、`/agents/public`、`/essay/*`、`/feedback/*`、`/auth/*`、`/user/*` | ✅ | ✅ | ✅ |
| `get_current_teacher` | `/resource/*`、`/course/*`、`/video/*`（含 zhiyun） | ❌ | ✅ | ✅ |
| `get_current_admin` | `/admin/*` | ❌ | ❌ | ✅ |

**改守卫规则**：在 API 层切换 `Depends(get_current_user)` → `Depends(get_current_teacher)` 即可。`current_user` 变量名保持不变（守卫返回的仍是 `User` 对象）。

### 3.3 `is_admin_user` 兼容白名单

```python
# server/service/admin/auth.py
def is_admin_user(user: User | None) -> bool:
    if user is None:
        return False
    if user.role == UserRole.ADMIN.value:
        return True
    # 兜底：白名单里但 DB role 还没回填（启动 race 极小窗口）
    return bool(user.zju_id) and user.zju_id in settings.ADMIN_ZJU_IDS
```

DB 是权威源，白名单只是兜底。**不要新增白名单作为正式提权途径**——新管理员通过 `/admin/users` 改角色。

---

## 4. 改用户角色

### 4.1 API：`PATCH /admin/users/{user_id}/role`

```bash
curl -X PATCH "http://127.0.0.1:8000/admin/users/$USER_ID/role" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"role": "teacher"}'
```

成功响应：`{"success": true, "data": null}`。
失败：`BizException("用户不存在")` / `BizException("不能降级自己")`。

副作用：写 `audit_logs`，`action=user.role_update`，`payload={"from": "<old>", "to": "<new>"}`。

### 4.2 UI：`/admin/users`

- 列表列：姓名 / 学工号 / 学院 / 角色徽章 / 注册时间 / 改角色
- 过滤：搜索（zju_id / 姓名）+ 角色下拉（全部 / 学生 / 教师 / 管理员）
- 分页：30 条 / 页，「加载更多」追加
- 改角色弹窗：单选 admin / teacher / student；admin 改自己时弹黄色二次确认条「即将把自己降级，确认后将立刻失去管理员入口」（实际后端也会再拦一次）
- 乐观更新：改完直接更新本地行徽章，不重拉

### 4.3 列表 API：`GET /admin/dashboard/users`

```bash
GET /admin/dashboard/users?keyword=张&role=teacher&limit=30&offset=0
```

`role` 参数可选，传了就过滤；不传返回全部角色。导出 `/admin/dashboard/users/export?role=teacher` 同样支持。

---

## 5. 智能体调用协议传身份

**为什么传**：智能体 / LLM 后端按调用者身份做权限控制（如学生调起教学三件套时 prompt 拒绝、教师调用全功能）；外部插件做自己的细粒度审计。

### 5.1 本进程 agent（`server/agents/`）

`stream_chat / complete_chat` 增加 `actor: User | None = None` kw-only 参数：

```python
# server/agents/llm.py
async def stream_chat(
    system_prompt: str = "",
    user_prompt: str = "",
    *,
    history: list[dict[str, str]] | None = None,
    enable_thinking: bool = False,
    actor: User | None = None,
) -> AsyncIterator[str]: ...
```

注入两路冗余信号：

1. **system prompt 前缀**（一定生效）：
   ```
   [CALLER name=<name> zju_id=<zju_id> role=<role>]
   <原 system prompt>
   ```
2. **`extra_body.metadata`**（vLLM 0.6+ 识别；老版本忽略，不报错）：
   ```json
   {"actor_id": "...", "actor_role": "teacher", "actor_zju_id": "..."}
   ```

`actor` 从 API 层透传：
- `assistant`：`stream_chat(actor=self.context.current_user)`
- `outline / question_bank / teaching_plan`：service 函数加 `actor` kw-only 参数；上游 `service/resource/service.py::generate_resource` 接收 `current_user` 并向下传

### 5.2 外部插件（HTTP 调用）

主进程统一 helper `server/common/utils/http.py::actor_headers(user)`：

```python
def actor_headers(user: User | None) -> dict[str, str]:
    if user is None:
        return {}
    return {
        "X-Actor-Id": user.id,
        "X-Actor-Role": user.role or "",
        "X-Actor-Zju-Id": user.zju_id or "",
        "X-Actor-Label": f"{user.name or ''}/{user.zju_id or ''}",
    }
```

调插件时合并到 headers：

```python
# server/service/essay_check/service.py
async with httpx.AsyncClient(timeout=60.0) as client:
    resp = await client.post(
        f"{settings.ESSAY_CHECK_SERVICE_URL}/api/v1/tasks/upload",
        files={"file": (filename, file_bytes, "application/pdf")},
        headers=actor_headers(current_user),
    )
```

**插件侧读取**（FastAPI Header dependency）：

```python
# plugins/essay_check/app/api/router.py
class ActorContext:
    __slots__ = ("user_id", "role", "zju_id", "label")
    ...

def read_actor(
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
    x_actor_zju_id: str | None = Header(default=None),
    x_actor_label: str | None = Header(default=None),
) -> ActorContext: ...

@router.post("/tasks/upload")
async def upload_task(
    file: UploadFile = File(...),
    actor: ActorContext = Depends(read_actor),
):
    if actor.is_present:
        logger.info("upload_task actor=%s role=%s ...", actor.user_id, actor.role, ...)
    ...
```

**协议约定**（HTTP 头规范常量）：
- `X-Actor-Id`：User.id（系统内主键）
- `X-Actor-Role`：`admin` / `teacher` / `student`
- `X-Actor-Zju-Id`：学工号
- `X-Actor-Label`：`{name}/{zju_id}` 人类可读

未来其他外部插件按同样规范读这四个头即可。

### 5.3 外部插件回报审计：`on_behalf_of_*`

当外部插件回调 `POST /audit/report` 时，可在 body 里携带「这条操作代表哪个用户做的」：

```bash
curl -X POST "http://127.0.0.1:8000/audit/report" \
  -H "X-Audit-Service-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "essay_check.delete",
    "actor_id": "essay_check",
    "actor_label": "论文检测服务",
    "target_type": "essay_task",
    "target_id": "task-001",
    "on_behalf_of_user_id": "7465...",
    "on_behalf_of_role": "teacher",
    "on_behalf_of_label": "张三/12345"
  }'
```

落库后 `audit_logs.extra` 中：

```json
{
  "on_behalf_of": {
    "user_id": "7465...",
    "role": "teacher",
    "label": "张三/12345"
  }
}
```

**字段约束**：三个 `on_behalf_of_*` 都可选；任一非空则合并写 extra；全空则 extra 不增字段。

---

## 6. 前端使用

### 6.1 Pinia store

```ts
// client/website/src/stores/user.ts
const role = computed<AppUserRole>(() => normalizeAppRole(currentUser.value?.role))
const isAdmin = computed(() => role.value === 'admin')
const isTeacher = computed(() => role.value === 'teacher')
const isStudent = computed(() => role.value === 'student')
```

`currentUser.role` 是单一真值源，所有衍生标志都是 computed。`fetchCurrentUser` 拉 `/user/current` 时后端会返回 `role` 字段，前端无需额外调 `/admin/check`。

### 6.2 路由 meta

```ts
// client/website/src/router/index.ts
import type { AppUserRole } from '../api/types'

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    requiresAuth?: boolean
    admin?: boolean
    requiredRoles?: AppUserRole[]  // 命中任一即可
  }
}

const TEACHER_ROLES: AppUserRole[] = ['teacher', 'admin']

// 教师专属
{ path: '/outline-form', meta: { requiresAuth: true, requiredRoles: TEACHER_ROLES }, ... }
// 全员
{ path: '/chat', meta: { requiresAuth: true }, ... }
// 管理员
{ path: '/admin', meta: { admin: true }, children: [...] }
```

守卫顺序（`router.beforeEach`）：
1. `public && !admin` → 放过
2. 无 token → 跳 `/auth`（本机开发对非 `requiresAuth` 路由放行）
3. 缺 `currentUser` → `await userStore.fetchCurrentUser()`；失败回 `/auth`
4. `requiresAdmin && !isAdmin` → 跳 `/`
5. `requiredRoles.length && !requiredRoles.includes(role)` → dispatch `rbac:denied` + 跳 `/`
6. 通过

### 6.3 `rbac:denied` 事件

`App.vue` 监听 `window.addEventListener('rbac:denied', ...)`，弹 3 秒 toast「该功能仅对教师开放」。任何自定义组件也可以监听这个事件做自己的提示。

### 6.4 Navbar / HomeView 角色过滤

```ts
// client/website/src/components/layout/Navbar.vue
const ALL_NAV: NavLink[] = [
  { to: '/my-resources', label: '我的资源', roles: ['teacher', 'admin'], ... },
  { to: '/my-courses', label: '我的课程', roles: ['teacher', 'admin'], ... },
  { to: '/chat', label: '智能对话', ... },                                   // 全员
  { to: '/resource-analysis', label: '资源分析', roles: ['teacher', 'admin'], ... },
]

const visibleNav = computed(() => {
  const role = userStore.role
  return ALL_NAV.filter((item) => !item.roles || item.roles.includes(role))
})
```

HomeView 第一屏 `introFeatureEntries` 卡片用同样模式过滤。`role` 缺省（未登录）时 `normalizeAppRole` 降级为 `student`，所以未登录访客看到的就是学生视图。

---

## 7. 验证

### 7.1 端到端 Playwright 脚本

```bash
# 前置：dashboard-local stack 起来，前端 npm run dev
node client/website/e2e/verify-rbac.mjs
```

10 张截图覆盖：学生 / 教师 / 管理员各自的 navbar、URL 拦截、用户管理 UI、改角色弹窗、乐观更新、audit log 写入、防自降级。产物落 `tmp/screenshots/rbac/`，详情见 [`/Users/kingcyk/.claude/plans/lazy-strolling-moler.md`](../tmp/screenshots/rbac/) §7 截图表。

### 7.2 数据库验证

```bash
# 用户角色分布
docker exec edu-ai-home-db-dashboard-local psql -U postgres -d edu_ai_home \
  -c "SELECT role, COUNT(*) FROM users GROUP BY role;"

# 最近的 role_update 审计
docker exec edu-ai-home-db-dashboard-local psql -U postgres -d edu_ai_home \
  -c "SELECT actor_label, target_label, payload, create_time
      FROM audit_logs WHERE action='user.role_update'
      ORDER BY create_time DESC LIMIT 10;"

# on_behalf_of 写入
docker exec edu-ai-home-db-dashboard-local psql -U postgres -d edu_ai_home \
  -c "SELECT actor_id, action, extra->'on_behalf_of'
      FROM audit_logs WHERE extra ? 'on_behalf_of'
      ORDER BY create_time DESC LIMIT 10;"
```

### 7.3 协议验证（LLM actor metadata）

在 `server/agents/llm.py::stream_chat` 入口加临时 `logger.debug` 打印 `messages[0]` 与 `sampling`，调一次 `POST /resource/generate`，应看到：
- `messages[0].content` 以 `[CALLER name=... zju_id=... role=...]` 开头
- `sampling.extra_body.metadata` 含 `{"actor_id", "actor_role", "actor_zju_id"}`

老版本 vLLM 不识别 `metadata`，会被原样丢弃，不影响功能。

---

## 8. 常见疑问

**Q：用户改完角色后要重新登录吗？**
A：不需要。JWT 只放 `user_id`，每次请求由 `get_current_user` 从 DB 加载完整 User 对象（含 role），所以下一次请求就生效。前端 store 里的 role 可以通过 `userStore.fetchCurrentUser()` 主动刷新。

**Q：旧用户老登录用户在迁移后的角色是什么？**
A：`student`。启动迁移给所有现有行写默认值；如果 ta 应该是教师 / 管理员，需要管理员通过 `/admin/users` 改一次。`ADMIN_ZJU_IDS` 白名单里的用户在启动时自动升 admin。

**Q：能给"教师"再细分（如普通教师 / 高级教师）吗？**
A：可以，但 v1 不做。在 `UserRole` 枚举加值 + 守卫工厂加新 `get_current_xxx` + 前端 `APP_USER_ROLES` 补充即可。注意路由 meta 的 `requiredRoles` 是 OR 关系，加新角色后不需要改现有路由。

**Q：学生角色能做"只读"我的课程吗？**
A：可以，但需要后端拆"读 / 写"两套端点：`GET /course/*` 改用 `get_current_user`，`POST /course/operation` 仍用 `get_current_teacher`。前端路由 meta 同步放宽。**v1 没做，因为推荐方案是教师专属**——产品要变再加。

**Q：智能体能在 prompt 里看到 caller 信息后被注入提示绕过吗？**
A：模型层面无法保证绝对安全（典型 prompt injection 问题）。安全边界靠两层：(1) API 层的 `get_current_teacher` 守卫已经拒绝学生访问 `/resource/generate`，模型即便被绕过也拿不到入口；(2) 外部插件通过 `X-Actor-Role` HTTP 头独立判断，不依赖模型自觉。模型层只是"建议"，不是"强制"。

**Q：管理员能看到所有用户的资源 / 视频吗？**
A：当前不能。所有 `service/{resource,course,video}/service.py` 按 `creator_id == current_user.id` 过滤，admin 也只能看自己创建的。如要"管理员视角"列全部，建议另开 `/admin/resources` 端点而不是放宽现有过滤——避免普通教师误用自己的 admin 身份看到他人数据。

**Q：白名单 `ADMIN_ZJU_IDS` 还有用吗？**
A：保留作 bootstrap 兜底——启动时把白名单 zju_id 对应的用户 role 写为 admin。日常增删管理员**通过 `/admin/users` 改角色**，不要再改环境变量。环境变量的角色相当于"这台部署的首批管理员"。
