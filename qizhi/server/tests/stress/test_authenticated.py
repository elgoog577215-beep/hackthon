"""
认证接口并发压测脚本

需要准备一个长期有效的测试 JWT Token，或实现自动登录获取 Token 的逻辑。

运行方式:
    export TEST_TOKEN="your_jwt_token_here"
    cd /Users/qyao/Code/edu_ai_home/server
    PYTHONPATH=/Users/qyao/Code/edu_ai_home/server uv run python tests/stress/test_authenticated.py

获取测试 Token 的方式:
    1. 正常登录后从浏览器开发者工具 Network 面板复制 Authorization header
    2. 或调用 /auth/callback?code=xxx 获取（需要有效 OAuth code）
    3. 或直接在数据库里找一个用户，用项目的 JWT 逻辑签发一个测试 token
"""

import asyncio
import os
import time
import statistics
from dataclasses import dataclass, field

import httpx

# ============ 配置 ============
BASE_URL = "http://127.0.0.1:8000"
TEST_TOKEN = os.getenv("TEST_TOKEN", "")

ENDPOINTS = [
    # AI 流式接口（只测连接建立时间，不读取完整 SSE 流）
    {
        "method": "POST",
        "url": "/ai/chat",
        "name": "ai_chat_connect",
        "body": {"message": "你好", "session_id": None, "conversation_id": None},
        "stream": True,   # SSE 接口，只测首字节时间 (TTFB)
    },
    # 普通 JSON 接口示例
    # {
    #     "method": "GET",
    #     "url": "/user/profile",
    #     "name": "user_profile",
    # },
]

CONCURRENT_USERS = 20
REQUESTS_PER_USER = 10
TIMEOUT = 60.0
# ==============================


@dataclass
class Result:
    name: str
    status: int
    latency_ms: float
    ttfb_ms: float = 0.0   # Time To First Byte（SSE 接口特别有用）
    error: str = ""


@dataclass
class Summary:
    name: str
    total: int = 0
    success: int = 0
    failed: int = 0
    latencies: list[float] = field(default_factory=list)
    ttfbs: list[float] = field(default_factory=list)
    errors: dict[str, int] = field(default_factory=dict)

    @property
    def avg_latency(self) -> float:
        return statistics.mean(self.latencies) if self.latencies else 0

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0
        sorted_lat = sorted(self.latencies)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]


async def request_with_auth(
    client: httpx.AsyncClient,
    endpoint: dict,
    token: str,
    semaphore: asyncio.Semaphore,
) -> Result:
    """发送带认证的请求，对 SSE 接口测量 TTFB"""
    async with semaphore:
        headers = {"Authorization": f"Bearer {token}"}
        url = BASE_URL + endpoint["url"]
        method = endpoint.get("method", "GET")
        body = endpoint.get("body")
        is_stream = endpoint.get("stream", False)
        name = endpoint["name"]

        start = time.perf_counter()
        ttfb = 0.0
        try:
            if method == "GET":
                resp = await client.get(url, headers=headers, timeout=TIMEOUT)
            elif method == "POST":
                resp = await client.post(url, json=body, headers=headers, timeout=TIMEOUT)
            else:
                return Result(name=name, status=0, latency_ms=0, error=f"Unsupported method: {method}")

            if is_stream:
                # SSE 流式接口：测量首字节时间，然后关闭连接
                ttfb_start = time.perf_counter()
                async for _ in resp.aiter_text():
                    ttfb = (time.perf_counter() - ttfb_start) * 1000
                    break  # 只读第一个 chunk

            latency = (time.perf_counter() - start) * 1000
            status = resp.status_code
            if status >= 400:
                text = (await resp.aread())[:200]
                return Result(name=name, status=status, latency_ms=latency, ttfb_ms=ttfb, error=f"HTTP {status}: {text}")
            return Result(name=name, status=status, latency_ms=latency, ttfb_ms=ttfb)

        except httpx.TimeoutException:
            latency = (time.perf_counter() - start) * 1000
            return Result(name=name, status=0, latency_ms=latency, error="Timeout")
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return Result(name=name, status=0, latency_ms=latency, error=type(e).__name__ + ":" + str(e)[:40])


async def user_task(client, endpoints, token, semaphore, count) -> list[Result]:
    results = []
    for _ in range(count):
        for ep in endpoints:
            r = await request_with_auth(client, ep, token, semaphore)
            results.append(r)
            # 接口间稍作间隔，模拟真实用户行为
            await asyncio.sleep(0.05)
    return results


def print_report(results: list[Result], duration_sec: float, concurrent: int):
    from collections import defaultdict
    summaries: dict[str, Summary] = defaultdict(lambda: Summary(name=""))

    for r in results:
        s = summaries[r.name]
        if s.name == "":
            s.name = r.name
        s.total += 1
        if r.error:
            s.failed += 1
            s.errors[r.error] = s.errors.get(r.error, 0) + 1
        else:
            s.success += 1
            s.latencies.append(r.latency_ms)
            if r.ttfb_ms > 0:
                s.ttfbs.append(r.ttfb_ms)

    print("\n" + "=" * 70)
    print("🚀 认证接口压力测试报告")
    print("=" * 70)
    print(f"并发: {concurrent} | 总耗时: {duration_sec:.2f}s")
    print("-" * 70)

    total = 0
    for name, s in sorted(summaries.items()):
        total += s.total
        print(f"\n📌 {name}")
        print(f"   请求: {s.total} | 成功: {s.success} | 失败: {s.failed}")
        if s.latencies:
            print(f"   完整延迟: avg={s.avg_latency:.1f}ms  p95={s.p95_latency:.1f}ms")
        if s.ttfbs:
            print(f"   TTFB:      avg={statistics.mean(s.ttfbs):.1f}ms  p95={sorted(s.ttfbs)[int(len(s.ttfbs)*0.95)]:.1f}ms")
        if s.errors:
            print(f"   错误: {dict(s.errors)}")

    overall_qps = total / duration_sec if duration_sec > 0 else 0
    print(f"\n📊 整体 QPS: {overall_qps:.2f}")
    print("=" * 70)


async def main():
    if not TEST_TOKEN:
        print("❌ 未设置 TEST_TOKEN 环境变量")
        print("   请执行: export TEST_TOKEN='your_jwt_token'")
        print("\n获取 Token 的方式:")
        print("   1. 浏览器登录后从请求头复制")
        print("   2. 或运行: PYTHONPATH=/Users/qyao/Code/edu_ai_home/server uv run python -c \"from service.auth.service import create_access_token; print(create_access_token({'sub': 'test-user-id'}))\"")
        return

    limits = httpx.Limits(max_connections=CONCURRENT_USERS * 2)
    semaphore = asyncio.Semaphore(CONCURRENT_USERS)

    async with httpx.AsyncClient(limits=limits, follow_redirects=True) as client:
        # 验证 token
        print("🔑 验证 Token...")
        try:
            resp = await client.get(
                BASE_URL + "/user/profile",
                headers={"Authorization": f"Bearer {TEST_TOKEN}"},
                timeout=10,
            )
            if resp.status_code == 401:
                print("❌ Token 无效或已过期，请重新获取")
                return
            print(f"✅ Token 有效 (profile 返回 {resp.status_code})")
        except Exception as e:
            print(f"⚠️  验证请求失败: {e}")

        print(f"🚀 开始压测: {CONCURRENT_USERS} 并发 × {REQUESTS_PER_USER} 轮")
        start = time.perf_counter()

        tasks = [
            asyncio.create_task(user_task(client, ENDPOINTS, TEST_TOKEN, semaphore, REQUESTS_PER_USER))
            for _ in range(CONCURRENT_USERS)
        ]
        all_results = []
        for t in asyncio.as_completed(tasks):
            all_results.extend(await t)

        duration = time.perf_counter() - start
        print_report(all_results, duration, CONCURRENT_USERS)


if __name__ == "__main__":
    asyncio.run(main())
