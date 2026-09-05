"""
远程服务器压力测试脚本
目标: http://127.0.0.1:5173
"""

import os

import asyncio
import time
import statistics
from dataclasses import dataclass, field

import httpx

# ============ 配置 ============
BASE_URL = "http://127.0.0.1:5173"
TEST_TOKEN = os.getenv("QIZHI_TEST_TOKEN", "")

# CRUD 接口列表
CRUD_ENDPOINTS = [
    {"method": "GET", "url": "/api/health", "name": "health_check"},
    {"method": "GET", "url": "/api/session/list", "name": "session_list"},
    {"method": "GET", "url": "/api/course/list?page=1&size=10", "name": "course_list"},
    {"method": "GET", "url": "/api/resource/list?page=1&size=10", "name": "resource_list"},
    {"method": "GET", "url": "/api/essay/list?page=1&size=10", "name": "essay_list"},
    {"method": "GET", "url": "/api/video/list?page=1&size=10", "name": "video_list"},
]

# AI 接口
AI_ENDPOINTS = [
    {
        "method": "POST",
        "url": "/api/ai/chat",
        "name": "ai_chat_ttfb",
        "body": {"query": "简要介绍一下Python语言的特点", "session_id": None, "file_paths": None, "extra_params": None},
        "stream": True,
    },
]

CONCURRENT_USERS = 100
REQUESTS_PER_USER = 5
CRUD_TIMEOUT = 30.0
AI_TIMEOUT = 60.0
# ==============================


@dataclass
class Result:
    name: str
    status: int
    latency_ms: float
    ttfb_ms: float = 0.0
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
    def p50_latency(self) -> float:
        return statistics.median(self.latencies) if self.latencies else 0

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0
        s = sorted(self.latencies)
        return s[min(int(len(s) * 0.95), len(s) - 1)]

    @property
    def p99_latency(self) -> float:
        if not self.latencies:
            return 0
        s = sorted(self.latencies)
        return s[min(int(len(s) * 0.99), len(s) - 1)]

    @property
    def min_latency(self) -> float:
        return min(self.latencies) if self.latencies else 0

    @property
    def max_latency(self) -> float:
        return max(self.latencies) if self.latencies else 0


def print_report(results: list[Result], duration_sec: float, title: str):
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

    print("\n" + "=" * 80)
    print(f"🚀 {title}")
    print("=" * 80)
    print(f"并发数: {CONCURRENT_USERS} | 每用户请求: {REQUESTS_PER_USER} | 总耗时: {duration_sec:.2f}s")
    print("-" * 80)

    total_reqs = 0
    for name, s in sorted(summaries.items()):
        total_reqs += s.total
        print(f"\n📌 {name}")
        print(f"   请求: {s.total} | 成功: {s.success} | 失败: {s.failed}")
        if s.latencies:
            print(f"   平均延迟: {s.avg_latency:.1f}ms | P50: {s.p50_latency:.1f}ms | P95: {s.p95_latency:.1f}ms | P99: {s.p99_latency:.1f}ms")
            print(f"   延迟范围: {s.min_latency:.1f}ms ~ {s.max_latency:.1f}ms")
        if s.ttfbs:
            print(f"   TTFB:     avg={statistics.mean(s.ttfbs):.1f}ms | p95={sorted(s.ttfbs)[int(len(s.ttfbs)*0.95)]:.1f}ms")
        if s.errors:
            print(f"   错误: {dict(s.errors)}")

    overall_qps = total_reqs / duration_sec if duration_sec > 0 else 0
    print(f"\n📊 整体 QPS: {overall_qps:.2f}")
    print("=" * 80)


async def request_one(
    client: httpx.AsyncClient,
    endpoint: dict,
    token: str,
    semaphore: asyncio.Semaphore,
) -> Result:
    async with semaphore:
        headers = {}
        if token and endpoint["url"] != "/api/health":
            headers["Authorization"] = f"Bearer {token}"
        if endpoint.get("body"):
            headers["Content-Type"] = "application/json"

        url = BASE_URL + endpoint["url"]
        method = endpoint.get("method", "GET")
        body = endpoint.get("body")
        is_stream = endpoint.get("stream", False)
        name = endpoint["name"]
        timeout = AI_TIMEOUT if is_stream else CRUD_TIMEOUT

        start = time.perf_counter()
        ttfb = 0.0
        try:
            if method == "GET":
                resp = await client.get(url, headers=headers, timeout=timeout)
            elif method == "POST":
                resp = await client.post(url, json=body, headers=headers, timeout=timeout)
            else:
                return Result(name=name, status=0, latency_ms=0, error=f"Unsupported: {method}")

            if is_stream:
                ttfb_start = time.perf_counter()
                async for _ in resp.aiter_text():
                    ttfb = (time.perf_counter() - ttfb_start) * 1000
                    break
                await resp.aclose()

            latency = (time.perf_counter() - start) * 1000
            status = resp.status_code
            if status >= 400:
                text = (await resp.aread())[:200] if not is_stream else ""
                return Result(name=name, status=status, latency_ms=latency, ttfb_ms=ttfb, error=f"HTTP {status}: {text}")
            return Result(name=name, status=status, latency_ms=latency, ttfb_ms=ttfb)

        except httpx.TimeoutException:
            latency = (time.perf_counter() - start) * 1000
            return Result(name=name, status=0, latency_ms=latency, error="Timeout")
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return Result(name=name, status=0, latency_ms=latency, error=type(e).__name__ + ":" + str(e)[:50])


async def user_task(client, endpoints, token, semaphore, count) -> list[Result]:
    results = []
    for _ in range(count):
        for ep in endpoints:
            r = await request_one(client, ep, token, semaphore)
            results.append(r)
            await asyncio.sleep(0.02)
    return results


async def run_crud_test():
    limits = httpx.Limits(max_connections=CONCURRENT_USERS * 2)
    semaphore = asyncio.Semaphore(CONCURRENT_USERS)

    async with httpx.AsyncClient(limits=limits) as client:
        print("🔥 CRUD 压测预热...")
        try:
            await client.get(BASE_URL + "/api/health", timeout=5)
            print("✅ 服务器连通")
        except Exception as e:
            print(f"❌ 无法连接服务器: {e}")
            return

        print(f"🚀 CRUD 压测开始: {CONCURRENT_USERS} 并发 × {REQUESTS_PER_USER} 轮")
        start = time.perf_counter()

        tasks = [
            asyncio.create_task(user_task(client, CRUD_ENDPOINTS, TEST_TOKEN, semaphore, REQUESTS_PER_USER))
            for _ in range(CONCURRENT_USERS)
        ]
        all_results = []
        for t in asyncio.as_completed(tasks):
            all_results.extend(await t)

        duration = time.perf_counter() - start
        print_report(all_results, duration, "普通 CRUD 接口压测报告")
        return all_results


async def run_ai_test():
    limits = httpx.Limits(max_connections=CONCURRENT_USERS * 2)
    # AI 接口不要同时跑太多，避免把 LLM 服务打挂，这里用 20 并发测 TTFB
    ai_concurrent = 20
    semaphore = asyncio.Semaphore(ai_concurrent)

    async with httpx.AsyncClient(limits=limits, follow_redirects=True) as client:
        print(f"\n🤖 AI 接口首 Token 测试开始: {ai_concurrent} 并发")
        start = time.perf_counter()

        tasks = [
            asyncio.create_task(user_task(client, AI_ENDPOINTS, TEST_TOKEN, semaphore, 1))
            for _ in range(ai_concurrent)
        ]
        all_results = []
        for t in asyncio.as_completed(tasks):
            all_results.extend(await t)

        duration = time.perf_counter() - start
        print_report(all_results, duration, "AI 接口首 Token (TTFB) 压测报告")
        return all_results


async def main():
    print("=" * 80)
    print("远程服务器压力测试")
    print(f"目标: {BASE_URL}")
    print("=" * 80)

    await run_crud_test()
    await run_ai_test()

    print("\n✅ 全部测试完成")


if __name__ == "__main__":
    asyncio.run(main())
