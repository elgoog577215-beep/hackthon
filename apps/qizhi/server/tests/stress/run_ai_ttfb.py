"""
AI 接口首 Token 精确测试 —— 测量收到第一个有效 data chunk 的时间
"""

import os

import asyncio
import time
import statistics

import httpx

BASE_URL = "http://127.0.0.1:5173"
TEST_TOKEN = os.getenv("QIZHI_TEST_TOKEN", "")

AI_ENDPOINTS = [
    {
        "method": "POST",
        "url": "/api/ai/chat",
        "name": "ai_chat",
        "body": {"query": "你好", "session_id": None, "file_paths": None, "extra_params": None},
    },
    {
        "method": "POST",
        "url": "/api/ai/outline",
        "name": "ai_outline",
        "body": {
            "subject": "计算机科学",
            "grade": "大学",
            "course_name": "Python程序设计",
            "hours": 32,
            "teaching_objectives": "掌握Python基础编程",
            "teaching_contents": "变量、函数、面向对象",
            "teaching_methods": "讲授+实验",
            "assessment_methods": "考试+作业",
            "textbooks": "Python编程从入门到实践",
        },
    },
]

CONCURRENT = 10
TIMEOUT = 120.0


async def test_ai_ttfb(client: httpx.AsyncClient, endpoint: dict, token: str) -> dict:
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
        resp = await client.post(url, json=body, headers=headers, timeout=TIMEOUT)
        status = resp.status_code
        if status >= 400:
            text = (await resp.aread())[:200]
            error = f"HTTP {status}: {text}"
        else:
            async for chunk in resp.aiter_text():
                chunks += 1
                # 跳过 SSE 空白行和仅包含 'data: ' 前缀的空内容
                stripped = chunk.strip()
                if stripped and stripped != "data:" and not stripped.startswith("data: "):
                    first_data_time = (time.perf_counter() - start) * 1000
                    break
                elif stripped.startswith("data: ") and len(stripped) > 10:
                    first_data_time = (time.perf_counter() - start) * 1000
                    break
                # 如果读了太多空行还没内容，给一个上限
                if chunks > 50 and first_data_time is None:
                    first_data_time = (time.perf_counter() - start) * 1000
                    break
            if first_data_time is None:
                first_data_time = (time.perf_counter() - start) * 1000
    except httpx.TimeoutException:
        error = "Timeout"
        first_data_time = (time.perf_counter() - start) * 1000
    except Exception as e:
        error = type(e).__name__ + ":" + str(e)[:50]
        first_data_time = (time.perf_counter() - start) * 1000

    total_time = (time.perf_counter() - start) * 1000
    return {
        "name": name,
        "status": status,
        "ttfb_ms": first_data_time,
        "total_ms": total_time,
        "chunks": chunks,
        "error": error,
    }


async def run_parallel(endpoint: dict, concurrent: int) -> list[dict]:
    limits = httpx.Limits(max_connections=concurrent * 2)
    async with httpx.AsyncClient(limits=limits) as client:
        tasks = [test_ai_ttfb(client, endpoint, TEST_TOKEN) for _ in range(concurrent)]
        return await asyncio.gather(*tasks)


def print_results(results: list[dict], endpoint_name: str, concurrent: int):
    print(f"\n{'='*80}")
    print(f"🤖 AI 接口首 Token 测试: {endpoint_name}")
    print(f"{'='*80}")
    print(f"并发数: {concurrent} | 总请求: {len(results)}")
    print("-" * 80)

    successes = [r for r in results if not r["error"]]
    failures = [r for r in results if r["error"]]

    if successes:
        ttfbs = [r["ttfb_ms"] for r in successes]
        totals = [r["total_ms"] for r in successes]
        ttfbs.sort()
        totals.sort()

        print(f"✅ 成功: {len(successes)} | ❌ 失败: {len(failures)}")
        print(f"\n📌 首 Token 耗时 (TTFB):")
        print(f"   平均: {statistics.mean(ttfbs):.1f}ms")
        print(f"   P50:  {statistics.median(ttfbs):.1f}ms")
        print(f"   P95:  {ttfbs[min(int(len(ttfbs)*0.95), len(ttfbs)-1)]:.1f}ms")
        print(f"   P99:  {ttfbs[min(int(len(ttfbs)*0.99), len(ttfbs)-1)]:.1f}ms")
        print(f"   范围: {min(ttfbs):.1f}ms ~ {max(ttfbs):.1f}ms")

        print(f"\n📌 完整流耗时:")
        print(f"   平均: {statistics.mean(totals):.1f}ms")
        print(f"   P50:  {statistics.median(totals):.1f}ms")
        print(f"   P95:  {totals[min(int(len(totals)*0.95), len(totals)-1)]:.1f}ms")
    else:
        print(f"❌ 全部失败: {len(failures)} 个")

    if failures:
        errors = {}
        for r in failures:
            err = r["error"][:40]
            errors[err] = errors.get(err, 0) + 1
        print(f"\n📌 错误分布: {errors}")
    print("=" * 80)


async def main():
    print("=" * 80)
    print("AI 接口首 Token 精确测试")
    print(f"目标: {BASE_URL}")
    print("=" * 80)

    for ep in AI_ENDPOINTS:
        results = await run_parallel(ep, CONCURRENT)
        print_results(results, ep["name"], CONCURRENT)
        # 接口之间间隔，避免把 LLM 打挂
        await asyncio.sleep(5)

    print("\n✅ AI 测试完成")


if __name__ == "__main__":
    asyncio.run(main())
