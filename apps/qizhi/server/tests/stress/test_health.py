"""
轻量级并发压测脚本 —— 针对 /health 等无认证接口
使用 Python asyncio + httpx，零依赖（已包含在 requirements.txt 中）

运行方式:
    cd /Users/qyao/Code/edu_ai_home/server
    PYTHONPATH=/Users/qyao/Code/edu_ai_home/server uv run python tests/stress/test_health.py

或先启动服务再测试:
    # 终端1
    PYTHONPATH=/Users/qyao/Code/edu_ai_home/server uv run python main.py
    # 终端2
    PYTHONPATH=/Users/qyao/Code/edu_ai_home/server uv run python tests/stress/test_health.py
"""

import asyncio
import time
import statistics
from dataclasses import dataclass, field

import httpx

# ============ 配置 ============
BASE_URL = "http://127.0.0.1:8000"
ENDPOINTS = [
    {"method": "GET", "url": "/health", "name": "health_check"},
    # 添加更多无认证接口
    # {"method": "GET", "url": "/auth/url", "name": "auth_url"},
]
CONCURRENT_USERS = 50       # 并发虚拟用户数
REQUESTS_PER_USER = 20      # 每个用户发送的请求数
TIMEOUT = 30.0              # 单请求超时（秒）
# ==============================


@dataclass
class Result:
    """单次请求结果"""
    name: str
    status: int
    latency_ms: float
    error: str = ""


@dataclass
class Summary:
    """汇总统计"""
    name: str
    total: int = 0
    success: int = 0
    failed: int = 0
    latencies: list[float] = field(default_factory=list)
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
        sorted_lat = sorted(self.latencies)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]

    @property
    def p99_latency(self) -> float:
        if not self.latencies:
            return 0
        sorted_lat = sorted(self.latencies)
        idx = int(len(sorted_lat) * 0.99)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]

    @property
    def min_latency(self) -> float:
        return min(self.latencies) if self.latencies else 0

    @property
    def max_latency(self) -> float:
        return max(self.latencies) if self.latencies else 0

    @property
    def qps(self) -> float:
        if not self.latencies:
            return 0
        total_time_sec = sum(self.latencies) / 1000
        return self.total / total_time_sec if total_time_sec > 0 else 0


def print_report(results: list[Result], duration_sec: float):
    """打印测试报告"""
    from collections import defaultdict

    summaries: dict[str, Summary] = defaultdict(lambda: Summary(name=""))

    for r in results:
        if summaries[r.name].name == "":
            summaries[r.name].name = r.name
        s = summaries[r.name]
        s.total += 1
        if r.error:
            s.failed += 1
            s.errors[r.error] = s.errors.get(r.error, 0) + 1
        else:
            s.success += 1
            s.latencies.append(r.latency_ms)

    print("\n" + "=" * 70)
    print(f"🚀 压力测试报告")
    print("=" * 70)
    print(f"总耗时: {duration_sec:.2f}s | 并发数: {CONCURRENT_USERS} | 每用户请求: {REQUESTS_PER_USER}")
    print("-" * 70)

    total_requests = 0
    total_success = 0
    for name, s in sorted(summaries.items()):
        total_requests += s.total
        total_success += s.success
        print(f"\n📌 接口: {name}")
        print(f"   总请求: {s.total} | 成功: {s.success} | 失败: {s.failed}")
        print(f"   平均延迟: {s.avg_latency:.2f}ms")
        print(f"   P50: {s.p50_latency:.2f}ms | P95: {s.p95_latency:.2f}ms | P99: {s.p99_latency:.2f}ms")
        print(f"   Min: {s.min_latency:.2f}ms | Max: {s.max_latency:.2f}ms")
        print(f"   QPS: {s.qps:.2f}")
        if s.errors:
            print(f"   错误分布: {dict(s.errors)}")

    print("\n" + "-" * 70)
    overall_qps = total_requests / duration_sec if duration_sec > 0 else 0
    print(f"📊 总计: 请求 {total_requests} | 成功 {total_success} | 失败 {total_requests - total_success}")
    print(f"📊 整体 QPS: {overall_qps:.2f}")
    print("=" * 70)


async def request_one(
    client: httpx.AsyncClient, endpoint: dict, semaphore: asyncio.Semaphore
) -> Result:
    """发送单个请求"""
    async with semaphore:
        start = time.perf_counter()
        name = endpoint["name"]
        url = BASE_URL + endpoint["url"]
        method = endpoint.get("method", "GET")
        try:
            if method == "GET":
                resp = await client.get(url, timeout=TIMEOUT)
            elif method == "POST":
                resp = await client.post(url, json=endpoint.get("body", {}), timeout=TIMEOUT)
            else:
                return Result(name=name, status=0, latency_ms=0, error=f"Unsupported method: {method}")
            latency = (time.perf_counter() - start) * 1000
            if resp.status_code >= 400:
                return Result(name=name, status=resp.status_code, latency_ms=latency, error=f"HTTP {resp.status_code}")
            return Result(name=name, status=resp.status_code, latency_ms=latency)
        except httpx.TimeoutException:
            latency = (time.perf_counter() - start) * 1000
            return Result(name=name, status=0, latency_ms=latency, error="Timeout")
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return Result(name=name, status=0, latency_ms=latency, error=str(e)[:50])


async def user_task(
    client: httpx.AsyncClient,
    endpoints: list[dict],
    semaphore: asyncio.Semaphore,
    count: int,
) -> list[Result]:
    """单个虚拟用户的任务"""
    results = []
    for _ in range(count):
        for ep in endpoints:
            r = await request_one(client, ep, semaphore)
            results.append(r)
    return results


async def main():
    limits = httpx.Limits(max_connections=CONCURRENT_USERS * 2, max_keepalive_connections=CONCURRENT_USERS)
    semaphore = asyncio.Semaphore(CONCURRENT_USERS)

    async with httpx.AsyncClient(limits=limits) as client:
        # 预热
        print("🔥 预热中...")
        try:
            await client.get(BASE_URL + "/health", timeout=5)
        except Exception as e:
            print(f"⚠️  预热请求失败（服务可能未启动）: {e}")
            print(f"   请确保服务已运行在 {BASE_URL}")
            return

        print(f"🚀 开始压测: {CONCURRENT_USERS} 并发 × {REQUESTS_PER_USER} 请求")
        start_time = time.perf_counter()

        tasks = [
            asyncio.create_task(user_task(client, ENDPOINTS, semaphore, REQUESTS_PER_USER))
            for _ in range(CONCURRENT_USERS)
        ]
        all_results = []
        for t in asyncio.as_completed(tasks):
            all_results.extend(await t)

        duration = time.perf_counter() - start_time
        print_report(all_results, duration)


if __name__ == "__main__":
    asyncio.run(main())
