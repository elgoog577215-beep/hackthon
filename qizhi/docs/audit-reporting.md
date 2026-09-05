# 审计日志上报指南（Agent / Service Integrator Guide）

> 本文档是给「需要把自己的关键行为留痕到平台」的智能体 / 微服务作者看的。
> 平台侧的实现细节、表结构、运维清单请去 [`admin-backend.md`](./admin-backend.md#审计日志)。

---

## 1. 这套审计日志是干什么的

`audit_logs` 表是 **取证级** 流水：

- 谁（actor_id + actor_label）在什么时间（create_time）从哪（request_ip / user_agent）做了什么动作（action）影响了哪个资源（target_*），结果如何（result），附带什么上下文（payload）。
- 与 `user_operation_logs`（驾驶舱用，聚合 DAU / 功能使用频次）**分立**：一个按行查取证，一个按次聚合分析，**不要混着用**。
- 写失败永远只是 warning，**不会让业务请求挂掉**（fail-safe 内置在 helper / endpoint 里）。

**该不该上报一条 audit？** 自问三个：

1. 这是会改变状态、销毁数据、或导出 PII 的动作吗？→ 报。
2. 出问题时运营要查「谁在什么时候动了它」吗？→ 报。
3. 这是高频的「访问/查询」类无副作用动作吗？→ 不报，那是 `user_operation_logs` 的活。

---

## 2. 两个上报端点选哪个

| 场景 | 端点 | 鉴权 | actor_type 落库值 |
| --- | --- | --- | --- |
| **同进程业务路由**（如已经在 `edu_ai_home/server` 里的 service） | **直接调 helper**，不走 HTTP | 复用业务路由本身的鉴权 | `user` / `admin` / `system`（按上下文） |
| **外置 agent / 独立微服务**（如 `plugins/essay_check` 端口 8001） | `POST /audit/report` | `X-Audit-Service-Token` Header | **`agent`**（路由强制覆盖） |
| **管理员手动补录**（页面没有按钮但需要补一笔） | `POST /admin/audit/report` | 复用 admin JWT (`Authorization: Bearer <token>`) | **`admin`**（路由强制覆盖） |

⚠️ **`actor_type` 不接受请求体决定**。即使 body 里塞了 `"actor_type": "admin"`，service-token 端点也只会落库为 `agent`。这是有意的：避免凭 service-token 就能伪装成 admin。

⚠️ **不要尝试让一个端点同时接受两种鉴权**。是 admin 走 admin 端点，是 agent 走 agent 端点；混用 = 提权漏洞。

---

## 3. 鉴权：申请并使用 `X-Audit-Service-Token`

### 3.1 平台侧配置

运维在 `server/.env`（生产）或 `server/.env.dev`（dashboard-local）里设：

```bash
AUDIT_SERVICE_TOKEN=请生成一段够长够随机的字符串（建议 ≥ 32 字符）
```

- **未配置**（空串）时 `POST /audit/report` 直接返回 401，外置 agent 上报通道关闭。`POST /admin/audit/report`（admin JWT 路径）不受影响。
- 比对走 `secrets.compare_digest`，无时序攻击。
- 修改 token 后必须**重启后端**才生效。

### 3.2 agent 侧使用

每次 HTTP 请求加 Header：

```
X-Audit-Service-Token: <token>
Content-Type: application/json
```

返回 401 时不要重试同一 token —— 大概率是 token 失效或拼写错。

---

## 4. 请求体 schema

```jsonc
{
  // ====== 必填 ======
  "action": "essay_check.delete",          // <service>.<verb>，≤ 100 字符

  // ====== 强烈建议填 ======
  "actor_id": "essay_check",               // 你自己的稳定服务名 / 实例 ID
  "actor_label": "论文检测服务",            // 人类可读，例 "论文检测 / v2.3"

  // ====== 描述被操作对象 ======
  "target_type": "essay_task",             // 资源类型，例 "essay_task" / "user_paper"
  "target_id": "task-abc123",              // 资源主键
  "target_label": "user_paper_2026.pdf",   // 人类可读，例文件名

  // ====== 上下文 ======
  "payload": {                             // 任意 JSON，但 >8KiB 会被截断
    "size_bytes": 1234567,
    "reason": "user_initiated_delete"
  },
  "result": "success",                     // success / failure / partial，≤ 20 字符

  // ====== 重试幂等 ======
  "idempotency_key": "essay-del-abc123-v1", // 见 §6
  "extra": null
}
```

### 字段细节

| 字段 | 必填 | 上限 | 注意 |
| --- | --- | --- | --- |
| `action` | ✅ | 100 字符 | 唯一必填项。命名约定见 §5 |
| `actor_id` | 建议 | — | service-token 端点强烈建议填。在 admin 端点会被当前 admin 覆盖 |
| `actor_label` | 建议 | 200 字符 | service-token 端点建议填。在 admin 端点会被当前 admin 覆盖 |
| `target_type` | 否 | 50 字符 | 影响 `/admin/audit-logs?target_type=...` 查询效率 |
| `target_id` | 否 | — | 用于「这条资源经历过什么」溯源 |
| `target_label` | 否 | 200 字符 | 列表页直接展示，建议给人类可读字符串 |
| `payload` | 否 | 8 KiB | 见 §7 脱敏与截断 |
| `result` | 否 | 20 字符 | 推荐 `success` / `failure` / `partial` 三选一 |
| `request_ip` | — | 64 字符 | **不要传**，server 端从 HTTP header 取 |
| `user_agent` | — | 500 字符 | **不要传**，server 端从 HTTP header 取 |
| `idempotency_key` | 否 | 128 字符 | 见 §6 |
| `extra` | 否 | 8 KiB | 同 payload 处理；自由发挥的扩展位 |

`actor_type` **不接受**任何请求体字段，全部由路由层根据鉴权决定。

### 响应

成功：

```json
{ "success": true, "data": null, "error": null }
```

鉴权失败（401）：

```json
{ "success": false, "data": null, "error": "invalid audit service token" }
```

`AUDIT_SERVICE_TOKEN` 未配置时也是 401，`error: "audit service disabled"`。

参数校验失败（422，FastAPI 默认）会返回 detail 数组，按 pydantic 的报错格式。

---

## 5. `action` 命名约定

格式：`<service>.<verb>`，全小写蛇形。

### 5.1 verb 词表（推荐）

| verb | 语义 | 例 |
| --- | --- | --- |
| `create` | 新建资源 | `agent.create` |
| `update` | 修改已有资源 | `agent.update` |
| `delete` | 销毁资源 | `essay_check.delete` |
| `toggle` | 二元状态切换 | `agent.toggle` |
| `reorder` | 顺序调整 | `agent.reorder` |
| `submit` | 提交了一项任务（异步处理） | `essay_check.submit` |
| `export` | 导出 PII / 业务数据 | `feedback.export` |
| `revoke` | 撤销已发出的资源 / 令牌 | `agent.revoke` |
| `archive` | 归档但不删除 | `course.archive` |

新加 verb 前先看看上面有没有近义词能复用；多个近义词分散在不同 service 里会让查询语义模糊。

### 5.2 service 命名

- 复用现有 service 名：`agent` / `feedback` / `user` / `course` / `resource` / `video_analysis` / `chat` / `essay_check`。
- 外置 agent 用自己的服务标识：`paper_review` / `quiz_generator` / `lecture_summarizer` 等，**全平台唯一**。
- 别用 dot 之外的分隔符；别用大写；别加版本号到 service 名里（版本放 `payload.version`）。

### 5.3 命名反例

| 反例 | 问题 | 改成 |
| --- | --- | --- |
| `EssayCheckDelete` | 驼峰、漏 dot | `essay_check.delete` |
| `delete-essay` | dot 改 dash、service 在后 | `essay_check.delete` |
| `essay.check.delete` | 多 dot 制造层级幻觉 | `essay_check.delete` |
| `essay_v2.delete` | service 名带版本 | `essay_check.delete` + `payload.version=2` |
| `user_logged_in` | 高频访问类事件 | 走 `user_operation_logs`，不上 audit |

---

## 6. 幂等（`idempotency_key`）

任何 agent 都可能因网络抖动重试 HTTP 请求。审计层提供原生幂等：

- DB 索引 `(actor_type, idempotency_key) WHERE idempotency_key IS NOT NULL` 是部分唯一索引；
- 同 `(actor_type, idempotency_key)` 第二次插入会触发 `IntegrityError`，**端点照样返回 200**，DB 不增行；
- 不传 `idempotency_key` 则每次都新建一行（最差只是产生重复的日志条目，不会出错）。

**最佳实践**：

- 在你的「这个动作就是一回事」的边界生成 key，例如：`essay_check.delete-task_<task_id>-attempt_<retry_no>` 或 `<service>-<uuid>`。
- key **必须稳定**：同一个语义动作的重试要用同一个 key；不同语义动作要用不同 key。
- key ≤ 128 字符。
- 不要把 key 跟当前时间戳挂钩 —— 这会让重试也产生新行，失去幂等。

---

## 7. PII 脱敏与 8 KiB 截断

`log_audit` helper 在写库前 **递归扫描** `payload` 和 `extra`，命中以下任意 key 名（小写匹配）的 value 替换为 `"***"`：

```
password, passwd, pwd,
token, access_token, refresh_token, id_token,
secret, api_key, apikey,
authorization, auth,
cookie, credential, credentials
```

例：

```jsonc
// 你发的
{ "payload": {"password": "hunter2", "headers": {"authorization": "Bearer xyz"}} }

// DB 里实际存的
{ "password": "***", "headers": {"authorization": "***"} }
```

**注意脱敏边界**：

- 只看 **key 名**，不看 value 内容。`"random_field": "passw0rd"` 不会被脱敏。
- 嵌套 dict / list 全部递归。
- 大小写不敏感（`API_KEY` / `ApiKey` / `apikey` 都命中）。
- 想新增需脱敏的 key？改 `server/service/audit/service.py::_REDACT_KEYS` 并发 PR。

**截断规则**：

- `payload` / `extra` 各自单独 JSON 序列化；如果 >8 KiB，**整段 value** 被替换为：

```json
{
  "_truncated": true,
  "_size": 9728,
  "_preview": "<前 1KiB 的 JSON 字符串>"
}
```

- 这意味着你想看完整 payload 时已经晚了。**不要把多 MB 的数据塞进 payload**，那是任务/资源 ID 的活，原始数据该放对象存储或独立表里。
- `_preview` 里的脱敏已经生效（先 redact 再 truncate）。

---

## 8. 上报错误如何处理

| 状态 | 你该做的 |
| --- | --- |
| 200 + `success:true` | 完事。 |
| 401（鉴权失败） | 检查 token、检查后端配置。**不要疯狂重试**，token 错只会一直错。 |
| 422（pydantic 校验失败） | 看 detail，最常见原因：`action` 缺失或超长；payload 不是合法 JSON。修请求体。 |
| 5xx | 走指数退避重试（最多 3 次），**带上同一个 idempotency_key**。 |
| 网络超时 | 同 5xx；带 idempotency_key 重试。 |
| 永久失败 | **吞掉这条 audit**，本地 warning 日志，**绝不让审计失败阻塞业务**。 |

**关键准则**：审计是「附带的留痕」，不是业务的一部分。任何审计上报失败都不应该影响业务结果——这条约束在平台侧的 helper 里也是同样实现的。

---

## 9. 端到端示例

### 9.1 curl（最小验证）

```bash
curl -X POST "http://127.0.0.1:8000/audit/report" \
  -H "X-Audit-Service-Token: $AUDIT_SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "essay_check.delete",
    "actor_id": "essay_check",
    "actor_label": "论文检测服务",
    "target_type": "essay_task",
    "target_id": "task-abc123",
    "target_label": "示例论文.pdf",
    "result": "success",
    "idempotency_key": "essay-del-task-abc123"
  }'
```

### 9.2 Python（外置服务用）

```python
import httpx
import os
import uuid

AUDIT_URL = os.getenv("AUDIT_REPORT_URL", "http://edu-ai-home/audit/report")
AUDIT_TOKEN = os.environ["AUDIT_SERVICE_TOKEN"]


def report_audit(
    action: str,
    *,
    actor_id: str,
    actor_label: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    target_label: str | None = None,
    payload: dict | None = None,
    result: str | None = "success",
    idempotency_key: str | None = None,
) -> None:
    """对外置 agent 的封装：审计失败仅 warning，不抛。"""
    body = {
        "action": action,
        "actor_id": actor_id,
        "actor_label": actor_label,
        "target_type": target_type,
        "target_id": target_id,
        "target_label": target_label,
        "payload": payload,
        "result": result,
        "idempotency_key": idempotency_key or f"{action}-{uuid.uuid4()}",
    }
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.post(
                AUDIT_URL,
                headers={"X-Audit-Service-Token": AUDIT_TOKEN},
                json={k: v for k, v in body.items() if v is not None},
            )
            if r.status_code != 200:
                # 审计失败不抛业务异常
                print(f"[audit] non-200: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"[audit] error: {e}")


# 调用点
report_audit(
    "essay_check.delete",
    actor_id="essay_check",
    actor_label="论文检测服务",
    target_type="essay_task",
    target_id="task-abc123",
    target_label="示例论文.pdf",
    payload={"reason": "user_initiated", "size_bytes": 1234567},
    idempotency_key="essay-del-task-abc123",
)
```

### 9.3 Node.js / TypeScript（外置 agent）

```ts
const AUDIT_URL = process.env.AUDIT_REPORT_URL ?? 'http://edu-ai-home/audit/report'
const AUDIT_TOKEN = process.env.AUDIT_SERVICE_TOKEN!

export async function reportAudit(params: {
  action: string
  actorId: string
  actorLabel?: string
  targetType?: string
  targetId?: string
  targetLabel?: string
  payload?: Record<string, unknown>
  result?: 'success' | 'failure' | 'partial'
  idempotencyKey?: string
}): Promise<void> {
  const body = {
    action: params.action,
    actor_id: params.actorId,
    actor_label: params.actorLabel,
    target_type: params.targetType,
    target_id: params.targetId,
    target_label: params.targetLabel,
    payload: params.payload,
    result: params.result ?? 'success',
    idempotency_key: params.idempotencyKey ?? `${params.action}-${crypto.randomUUID()}`,
  }
  try {
    const res = await fetch(AUDIT_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Audit-Service-Token': AUDIT_TOKEN,
      },
      body: JSON.stringify(body),
      // 5s 超时
      signal: AbortSignal.timeout(5000),
    })
    if (!res.ok) {
      console.warn(`[audit] non-2xx: ${res.status} ${(await res.text()).slice(0, 200)}`)
    }
  } catch (err) {
    console.warn('[audit] error:', err)
  }
}
```

### 9.4 同进程（FastAPI 路由内）

外置 HTTP 调用是给 **另一个进程** 的 agent 用的。如果你写的就是 `edu_ai_home/server` 里的代码，**直接调 helper** 性能更好也更可靠：

```python
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.http import get_client_ip
from infra.db import User, get_db
from service.audit import AuditActorType, log_audit
from service.auth import get_current_user

router = APIRouter()


@router.post("/my/feature")
async def do_something(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result_id = await my_business_logic(db, current_user)

    # 业务成功后审计
    await log_audit(
        db,
        actor_type=AuditActorType.USER,
        actor_id=current_user.id,
        actor_label=f"{current_user.name or ''}/{current_user.zju_id or ''}",
        action="my_service.do_something",
        target_type="my_resource",
        target_id=result_id,
        payload={"some_context": "..."},
        result="success",
        request_ip=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    return {"id": result_id}
```

**helper 永不抛错**——异常一律 warning + rollback，不需要你裹 try/except 救场。

---

## 10. 查看自己上报的审计

平台运营在 `/admin/audit-logs` 页面能筛选 `actor_type=agent` + `actor_id=<你的服务名>` 看到你上报的所有事件。也可以走 API：

```bash
curl -s "http://127.0.0.1:8000/admin/audit-logs?actor_type=agent&actor_id=essay_check&limit=20" \
  -H "Authorization: Bearer $ADMIN_JWT"
```

agent 自己**不能查询自己的审计**（service-token 只能写不能读）。如果你有这个需求，去找运营走一次 GET，或者另开一个「服务自查」端点（不在本期范围）。

---

## 11. 常见疑问

**Q：我上报失败了，业务也会失败吗？**
A：不会。HTTP 调用方按 §8 处理（warning 吞掉）；同进程 helper 内置 fail-safe。

**Q：能补传昨天的事件吗？**
A：不能改 `create_time`。`create_time` 永远是 server 写入时刻。补录的事件用 `payload.original_event_time` 自己标。

**Q：我上报了 1 万条，会有问题吗？**
A：单条数 KB 没问题。高频上报建议走批量队列内部聚合后再上报，避免审计成为热点。

**Q：能删审计记录吗？**
A：API 上不行。**审计日志是 append-only**。线下有特殊合规需求时走 DB 手工 SQL 删除（并自留更高一级的删除留痕）。

**Q：我需要自己签名 / 加密吗？**
A：v1 不需要。`X-Audit-Service-Token` 已是共享秘密；走 HTTPS 即可。如未来要做不可抵赖的链式审计，会单独发版本。

**Q：跨网络上报怎么处理双向 TLS / VPN？**
A：超出审计本身的范畴，由部署架构决定。审计端点本身只看 `X-Audit-Service-Token`。

---

## 12. 加入你的 service 到平台 audit（give-back）

如果你的 agent 已经成熟，准备把上报点固化进平台仓库：

1. 在 `docs/admin-backend.md` 的「已接入位置」表里加一行 `<service>.<verb>`。
2. 如果你的 service 命名是全新的（不在现有 8 个之列），把它加进 `docs/audit-reporting.md` §5.2 的复用列表。
3. PR 描述里附一段示例：`curl` 调用 + 期待的 DB 行示例。

平台同学会评审命名是否合理、是否能复用现有 service / verb，避免命名空间膨胀。
