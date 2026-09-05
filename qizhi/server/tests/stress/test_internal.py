"""
内网服务压力测试脚本
目标: http://127.0.0.1:8000
只读查询，不改库

运行:
    cd /Users/qyao/Code/edu_ai_home/server
    PYTHONPATH=/Users/qyao/Code/edu_ai_home/server uv run python tests/stress/test_internal.py
"""

import os

import asyncio
import time
import statistics
from dataclasses import dataclass, field

import httpx

# ============ 配置 ============
BASE_URL = "http://127.0.0.1:8000"
TEST_TOKEN = os.getenv("QIZHI_TEST_TOKEN", "")

# 只读 CRUD 接口
CRUD_ENDPOINTS = [
    {"method": "GET", "url": "/api/course/list?page=1&size=10", "name": "course_list"},
    {"method": "GET", "url": "/api/resource/list?page=1&size=10", "name": "resource_list"},
    {"method": "GET", "url": "/api/video/list?page=1&size=10", "name": "video_list"},
    {"method": "GET", "url": "/api/session/list", "name": "session_list"},
]

# AI 接口
AI_ENDPOINT = {
    "method": "POST",
    "url": "/api/ai/chat",
    "name": "ai_chat_ttfb",
    "body": {"query": "你好", "session_id": None, "file_paths": None, "extra_params": None},
}

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


def print_report(results: list[Result], duration_sec: float, concurrent: int, title: str):
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
    print(f"🚀 {title} — {concurrent} 并发")
    print("=" * 80)
    print(f"每用户请求: {REQUESTS_PER_USER} | 总耗时: {duration_sec:.2f}s")
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
    timeout: float,
) -> Result:
    async with semaphore:
        headers = {"Authorization": f"Bearer {token}"}
        if endpoint.get("body"):
            headers["Content-Type"] = "application/json"

        url = BASE_URL + endpoint["url"]
        method = endpoint.get("method", "GET")
        body = endpoint.get("body")
        name = endpoint["name"]

        start = time.perf_counter()
        ttfb = 0.0
        try:
            if method == "GET":
                resp = await client.get(url, headers=headers, timeout=timeout)
            elif method == "POST":
                resp = await client.post(url, json=body, headers=headers, timeout=timeout)
            else:
                return Result(name=name, status=0, latency_ms=0, error=f"Unsupported: {method}")

            latency = (time.perf_counter() - start) * 1000
            status = resp.status_code
            if status >= 400:
                text = (await resp.aread())[:200]
                return Result(name=name, status=status, latency_ms=latency, error=f"HTTP {status}: {text}")
            return Result(name=name, status=status, latency_ms=latency)

        except httpx.TimeoutException:
            latency = (time.perf_counter() - start) * 1000
            return Result(name=name, status=0, latency_ms=latency, error="Timeout")
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return Result(name=name, status=0, latency_ms=latency, error=type(e).__name__ + ":" + str(e)[:50])


async def request_ai_ttfb(
    client: httpx.AsyncClient,
    endpoint: dict,
    token: str,
    semaphore: asyncio.Semaphore,
) -> Result:
    """AI 接口：测量收到第一个有效 data chunk 的时间"""
    async with semaphore:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        url = BASE_URL + endpoint["url"]
        body = endpoint["body"]
        name = endpoint["name"]

        start = time.perf_counter()
        first_data_time = None
        status = 0
        error = ""
        chunks = 0

        try:
            resp = await client.post(url, json=body, headers=headers, timeout=AI_TIMEOUT)
            status = resp.status_code
            if status >= 400:
                text = (await resp.aread())[:200]
                error = f"HTTP {status}: {text}"
            else:
                async for chunk in resp.aiter_text():
                    chunks += 1
                    stripped = chunk.strip()
                    if stripped and stripped != "data:" and not stripped.startswith("data: "):
                        first_data_time = (time.perf_counter() - start) * 1000
                        break
                    elif stripped.startswith("data: ") and len(stripped) > 10:
                        first_data_time = (time.perf_counter() - start) * 1000
                        break
                    if chunks > 50 and first_data_time is None:
                        first_data_time = (time.perf_counter() - start) * 1000
                        break
                if first_data_time is None:
                    first_data_time = (time.perf_counter() - start) * 1000
            await resp.aclose()
        except httpx.TimeoutException:
            error = "Timeout"
            first_data_time = (time.perf_counter() - start) * 1000
        except Exception as e:
            error = type(e).__name__ + ":" + str(e)[:50]
            first_data_time = (time.perf_counter() - start) * 1000

        total_time = (time.perf_counter() - start) * 1000
        return Result(
            name=name,
            status=status,
            latency_ms=total_time,
            ttfb_ms=first_data_time,
            error=error,
        )


async def user_task_crud(client, endpoints, token, semaphore, count) -> list[Result]:
    results = []
    for _ in range(count):
        for ep in endpoints:
            r = await request_one(client, ep, token, semaphore, CRUD_TIMEOUT)
            results.append(r)
            await asyncio.sleep(0.02)
    return results


async def user_task_ai(client, endpoint, token, semaphore) -> list[Result]:
    r = await request_ai_ttfb(client, endpoint, token, semaphore)
    return [r]


async def run_crud_test(client: httpx.AsyncClient, concurrent: int) -> list[Result]:
    semaphore = asyncio.Semaphore(concurrent)
    print(f"\n🚀 CRUD 压测开始: {concurrent} 并发 × {REQUESTS_PER_USER} 轮")
    start = time.perf_counter()

    tasks = [
        asyncio.create_task(user_task_crud(client, CRUD_ENDPOINTS, TEST_TOKEN, semaphore, REQUESTS_PER_USER))
        for _ in range(concurrent)
    ]
    all_results = []
    for t in asyncio.as_completed(tasks):
        all_results.extend(await t)

    duration = time.perf_counter() - start
    print_report(all_results, duration, concurrent, "CRUD 查询接口压测报告")
    return all_results


async def run_ai_test(client: httpx.AsyncClient, concurrent: int) -> list[Result]:
    semaphore = asyncio.Semaphore(concurrent)
    print(f"\n🤖 AI Chat 首Token测试开始: {concurrent} 并发")
    start = time.perf_counter()

    tasks = [
        asyncio.create_task(user_task_ai(client, AI_ENDPOINT, TEST_TOKEN, semaphore))
        for _ in range(concurrent)
    ]
    all_results = []
    for t in asyncio.as_completed(tasks):
        all_results.extend(await t)

    duration = time.perf_counter() - start
    print_report(all_results, duration, concurrent, "AI Chat 首Token (TTFB) 压测报告")
    return all_results


async def main():
    print("=" * 80)
    print("内网服务压力测试")
    print(f"目标: {BASE_URL}")
    print("=" * 80)

    limits = httpx.Limits(max_connections=200)
    async with httpx.AsyncClient(limits=limits) as client:
        # 预热
        print("🔥 预热中...")
        try:
            await client.get(BASE_URL + "/api/health", timeout=5)
            print("✅ 服务器连通")
        except Exception as e:
            print(f"❌ 无法连接服务器: {e}")
            print("   请确保你在能访问该内网的网络环境中")
            return

        # 验证 token
        try:
            resp = await client.get(
                BASE_URL + "/api/course/list?page=1&size=1",
                headers={"Authorization": f"Bearer {TEST_TOKEN}"},
                timeout=10,
            )
            if resp.status_code == 401:
                print("❌ Token 无效")
                return
            print(f"✅ Token 有效 (course_list 返回 {resp.status_code})")
        except Exception as e:
            print(f"⚠️  Token 验证失败: {e}")

        # 并发级别列表
        levels = [10, 50, 100]

        for level in levels:
            print(f"\n{'#' * 80}")
            print(f"# 并发级别: {level}")
            print(f"{'#' * 80}")
            await run_crud_test(client, level)
            # AI 测试间隔长一点，避免把 LLM 打挂
            await asyncio.sleep(3)
            await run_ai_test(client, level)
            if level != levels[-1]:
                await asyncio.sleep(5)

    print("\n" + "=" * 80)
    print("✅ 全部测试完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
