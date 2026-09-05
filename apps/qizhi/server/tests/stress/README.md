# 并发压力测试指南

## 快速开始

### 1. 先启动服务

```bash
cd qizhi/server
PYTHONPATH=qizhi/server uv run python main.py
```

### 2. 测试无认证接口（最简单）

```bash
cd qizhi/server
PYTHONPATH=qizhi/server uv run python tests/stress/test_health.py
```

### 3. 测试认证接口

```bash
# 先获取测试 Token（方法见下方）
export TEST_TOKEN="replace_with_test_token"

# asyncio 轻量脚本
PYTHONPATH=qizhi/server uv run python tests/stress/test_authenticated.py

# 或 Locust（推荐，有 Web UI）
uv add --dev locust
PYTHONPATH=qizhi/server uv run locust -f tests/stress/test_locustfile.py \
    --host=http://127.0.0.1:8000 --headless -u 50 -r 10 -t 60s

# 或 k6（极限压测）
# brew install k6
k6 run --vus 50 --duration 60s tests/stress/test_k6.js
```

---

## 获取测试 Token 的方法

### 方法 A：从浏览器复制（最简单）

1. 打开浏览器开发者工具（F12）→ Network 面板
2. 正常登录系统，操作任意功能
3. 找到任意 API 请求，复制 `Authorization: Bearer xxx` 中的 xxx

### 方法 B：手动签发测试 Token（推荐，长期有效）

```bash
cd qizhi/server
PYTHONPATH=qizhi/server uv run python -c "
import asyncio
from infra.db import init_db, get_db
from service.auth.service import create_access_token

init_db()

async def main():
    async for db in get_db():
        # 查询第一个用户
        from sqlalchemy import select
        from infra.db import User
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        if user:
            token = create_access_token({'sub': str(user.id)})
            print(f'Token for user {user.id}:')
            print(token)
        else:
            print('No user found in database')
        break

asyncio.run(main())
"
```

### 方法 C：通过 OAuth 登录流程获取

需要有效的 OAuth authorization code，适合集成测试场景：

```bash
curl "http://127.0.0.1:8000/auth/callback?code=YOUR_OAUTH_CODE"
```

---

## 各工具对比与选型

| 场景 | 推荐工具 | 原因 |
|-----|---------|------|
| 快速验证单接口 | `test_health.py` | 零额外依赖，即写即跑 |
| 日常迭代测试 | `test_authenticated.py` | 支持 SSE TTFB 测量，代码可控 |
| 全链路/复杂场景 | Locust | Web UI 直观，支持事务编排 |
| 极限 QPS 测试 | k6 / wrk | Go 编写，性能开销极低 |
| CI/CD 自动化 | k6 / Locust headless | 命令行输出，可配置阈值 |

---

## 关键指标解释

| 指标 | 含义 | 健康参考值 |
|-----|------|----------|
| QPS/RPS | 每秒请求数 | 视接口复杂度，健康检查应 > 1000 |
| Avg Latency | 平均延迟 | < 200ms（简单查询）|
| P95/P99 | 95%/99% 分位延迟 | P95 < 500ms，P99 < 1000ms |
| TTFB | 首字节时间（SSE 关键指标）| < 2s（AI 接口）|
| Error Rate | 错误率 | < 0.1% |
| Concurrency | 并发连接数 | 根据服务器配置调整 |

---

## 针对本项目的特殊注意

### SSE 流式接口（/ai/chat, /ai/outline 等）

- **不要**用普通 HTTP 客户端测量完整响应时间，因为流会持续数十秒
- 正确做法：**测量 TTFB**（Time To First Byte），即服务端开始推送第一个 chunk 的时间
- `test_authenticated.py` 已内置 TTFB 测量
- 也可以用 `curl -w "@curl-format.txt"` 测量：
  ```bash
  curl -N -H "Authorization: Bearer $TEST_TOKEN" \
       -H "Content-Type: application/json" \
       -d '{"message":"你好","session_id":null}' \
       -w "\nTTFB: %{time_starttransfer}s\nTotal: %{time_total}s\n" \
       http://127.0.0.1:8000/ai/chat
  ```

### 数据库连接池

如果压测出现大量超时，优先检查：

1. **PostgreSQL 连接池大小**（SQLAlchemy `pool_size` / `max_overflow`）
2. **asyncpg 并发连接数**是否达到上限
3. **Uvicorn worker 数**：单进程模式下 Python GIL 限制，生产环境应使用多 worker：
   ```bash
   uvicorn main:app --workers 4  # 或多进程 + gunicorn
   ```

### LLM 调用瓶颈

AI 相关接口的延迟主要来自外部 LLM API（OpenAI / 百炼），服务端本身不是瓶颈：
- 压测 AI 接口时，关注 **TTFB** 而非总耗时
- 如果需要压测服务端并发处理能力，**Mock LLM 响应**（使用本地 fake server）

---

## 扩展：编写自定义压测场景

参考 `test_authenticated.py` 的结构，可以模拟真实用户旅程：

```python
async def user_journey(client, token):
    # 1. 获取用户资料
    await request(client, "GET", "/user/profile", token)
    await sleep(random.uniform(0.5, 1.5))

    # 2. 查询课程列表
    await request(client, "GET", "/course/list", token)
    await sleep(random.uniform(1, 3))

    # 3. 发送 AI 消息（SSE）
    await request(client, "POST", "/ai/chat", token, body={...})
    await sleep(random.uniform(2, 5))
```

Locust 中可用 `SequentialTaskSet` 实现顺序任务编排。
