#!/usr/bin/env python3
"""并发爬坡实测：为 AI_PROVIDER_MAX_CONCURRENCY 找一个有证据的值。

为什么需要这个脚本：自部署 vLLM 的批处理容量是固定的（张量并行度、KV cache
大小、调度器批大小共同决定），拐点必须实测，不能照搬别的部署的经验值。之前
一轮 400 max_tokens 的探测不足以代表课程蓝图那种长结构化 JSON 负载，所以这里
用贴近真实的请求体量。

负载形态刻意贴近生产：长结构化 JSON 输出（课程蓝图/教案批次那一类），而不是
几十 token 的玩具请求——两者在 vLLM 上的排队行为完全不同。

安全约束：
- 端点只从环境变量读，不硬编码；
- 每档之间留冷却，避免上一档的排队尾巴污染下一档；
- 出错率或 P95 明显恶化时**自动停止**并如实记录当时的并发数——
  这台机器可能有别的间歇性消费方，压出一个漂亮数字没有意义。

用法：
    scripts/qwen_concurrency_ramp.py --dry-run
    scripts/qwen_concurrency_ramp.py --levels 1,2,4,6,8,12,16 --out /tmp/ramp.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Any

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover - surfaced by --dry-run
    AsyncOpenAI = None  # type: ignore[assignment]


# 贴近真实负载：要求模型产出一份结构化课程蓝图片段，而不是一句话。
LOAD_SYSTEM_PROMPT = (
    "你是课程结构规划器。只输出一个合法 JSON 对象，不要输出解释或 Markdown 围栏。"
)
LOAD_USER_PROMPT = (
    "为「概率论与数理统计」生成一个课程蓝图片段，严格输出如下 JSON："
    '{"chapters":[{"chapter_id":"C1","title":"...","sections":['
    '{"node_id":"L2-1-1","title":"...","learning_objective":"...",'
    '"scope_boundary":"...","key_points":["...","...","..."],'
    '"misconceptions":[{"name":"...","why":"..."}],'
    '"assessment":[{"task":"...","evidence":"..."}]}]}]}'
    "要求：恰好 3 章，每章恰好 3 节；每节 key_points 至少 4 条、"
    "misconceptions 至少 2 条、assessment 至少 2 条；"
    "所有文本用中文，内容必须具体、不得占位。"
)


@dataclass
class RequestOutcome:
    ok: bool
    latency_s: float
    output_chars: int = 0
    completion_tokens: int = 0
    finish_reason: str = ""
    error: str = ""


@dataclass
class LevelResult:
    concurrency: int
    wall_clock_s: float
    outcomes: list[RequestOutcome] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for item in self.outcomes if item.ok)

    @property
    def error_rate(self) -> float:
        if not self.outcomes:
            return 0.0
        return 1.0 - (self.ok_count / len(self.outcomes))

    @property
    def truncated_count(self) -> int:
        return sum(1 for item in self.outcomes if item.finish_reason == "length")

    def _latencies(self) -> list[float]:
        return sorted(item.latency_s for item in self.outcomes if item.ok)

    @property
    def p50_s(self) -> float:
        values = self._latencies()
        return statistics.median(values) if values else 0.0

    @property
    def p95_s(self) -> float:
        values = self._latencies()
        if not values:
            return 0.0
        index = max(0, min(len(values) - 1, int(round(0.95 * (len(values) - 1)))))
        return values[index]

    @property
    def total_completion_tokens(self) -> int:
        return sum(item.completion_tokens for item in self.outcomes if item.ok)

    @property
    def throughput_tok_s(self) -> float:
        if self.wall_clock_s <= 0:
            return 0.0
        return self.total_completion_tokens / self.wall_clock_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "concurrency": self.concurrency,
            "wall_clock_s": round(self.wall_clock_s, 2),
            "requests": len(self.outcomes),
            "ok": self.ok_count,
            "error_rate": round(self.error_rate, 4),
            "truncated": self.truncated_count,
            "p50_s": round(self.p50_s, 2),
            "p95_s": round(self.p95_s, 2),
            "completion_tokens": self.total_completion_tokens,
            "throughput_tok_s": round(self.throughput_tok_s, 1),
            "errors": [item.error for item in self.outcomes if item.error][:5],
        }


async def _one_request(
    client: Any,
    model: str,
    max_tokens: int,
) -> RequestOutcome:
    started = time.perf_counter()
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": LOAD_SYSTEM_PROMPT},
                {"role": "user", "content": LOAD_USER_PROMPT},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
            # 关闭 thinking：本脚本测的是吞吐，不是推理质量。
            # vLLM 只认嵌套写法，扁平写法会被静默忽略。
            extra_body={
                "enable_thinking": False,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
    except Exception as exc:  # noqa: BLE001 - 需要把任何失败都计入错误率
        return RequestOutcome(
            ok=False,
            latency_s=time.perf_counter() - started,
            error=f"{type(exc).__name__}: {str(exc)[:120]}",
        )
    latency = time.perf_counter() - started
    choice = response.choices[0] if response.choices else None
    content = ""
    finish_reason = ""
    if choice is not None:
        content = getattr(choice.message, "content", "") or ""
        finish_reason = str(getattr(choice, "finish_reason", "") or "")
    usage = getattr(response, "usage", None)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    if not completion_tokens:
        # 端点没报 usage 时用字符数保守折算，避免吞吐一栏空着。
        completion_tokens = max(1, len(content) // 2)
    return RequestOutcome(
        ok=bool(content),
        latency_s=latency,
        output_chars=len(content),
        completion_tokens=completion_tokens,
        finish_reason=finish_reason,
        error="" if content else "empty_content",
    )


async def run_level(
    client: Any,
    model: str,
    concurrency: int,
    max_tokens: int,
) -> LevelResult:
    started = time.perf_counter()
    outcomes = await asyncio.gather(
        *(_one_request(client, model, max_tokens) for _ in range(concurrency))
    )
    return LevelResult(
        concurrency=concurrency,
        wall_clock_s=time.perf_counter() - started,
        outcomes=list(outcomes),
    )


def _should_stop(
    result: LevelResult,
    baseline_p95: float,
    best_throughput: float,
) -> str:
    """判断是否该停止爬坡，返回停止原因（空串表示继续）。

    宁可早停也不要硬压：这台机器可能有别的间歇性消费方，
    压出来的漂亮数字既不可复现，也可能影响到对方。
    """
    if result.error_rate > 0.1:
        return f"错误率 {result.error_rate:.0%} 超过 10%"
    if result.truncated_count:
        return f"{result.truncated_count} 个请求被截断"
    if baseline_p95 > 0 and result.p95_s > baseline_p95 * 4:
        return (
            f"P95 {result.p95_s:.1f}s 超过单并发基线 "
            f"{baseline_p95:.1f}s 的 4 倍"
        )
    if best_throughput > 0 and result.throughput_tok_s < best_throughput * 0.8:
        return (
            f"吞吐 {result.throughput_tok_s:.0f} tok/s 跌破峰值 "
            f"{best_throughput:.0f} 的 80%"
        )
    return ""


async def main_async(args: argparse.Namespace) -> int:
    base_url = os.getenv("AI_API_BASE", "").strip()
    api_key = os.getenv("AI_API_KEY", "").strip()
    model = os.getenv("AI_MODEL", "").strip()
    if not base_url or not model:
        print("需要 AI_API_BASE 与 AI_MODEL 环境变量（端点不硬编码）", file=sys.stderr)
        return 2
    if AsyncOpenAI is None:
        print("openai 包不可用", file=sys.stderr)
        return 2

    levels = [int(item) for item in args.levels.split(",") if item.strip()]
    client = AsyncOpenAI(
        base_url=base_url,
        api_key=api_key or "EMPTY",
        timeout=args.timeout,
        max_retries=0,
    )

    results: list[LevelResult] = []
    baseline_p95 = 0.0
    best_throughput = 0.0
    stop_reason = ""
    for index, level in enumerate(levels):
        result = await run_level(client, model, level, args.max_tokens)
        results.append(result)
        row = result.to_dict()
        print(json.dumps({"level_result": row}, ensure_ascii=False), flush=True)
        if level == 1:
            baseline_p95 = result.p95_s
        stop_reason = _should_stop(result, baseline_p95, best_throughput)
        best_throughput = max(best_throughput, result.throughput_tok_s)
        if stop_reason:
            print(
                json.dumps(
                    {"ramp_stopped": {"at_concurrency": level, "reason": stop_reason}},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            break
        if index < len(levels) - 1:
            await asyncio.sleep(args.cooldown)

    healthy = [
        item for item in results
        if item.error_rate == 0 and item.truncated_count == 0
    ]
    recommended = 1
    peak_throughput_concurrency = 1
    if healthy:
        peak = max(healthy, key=lambda item: item.throughput_tok_s)
        peak_throughput_concurrency = peak.concurrency
        # 纯取吞吐峰值只适合批处理。课程生成是用户等待型任务，P95 就是
        # 用户感知的等待时间，所以取"性价比膝点"：边际吞吐增益仍高于
        # 边际 P95 代价的最后一档。
        recommended = healthy[0].concurrency
        for previous, current in zip(healthy, healthy[1:]):
            if previous.throughput_tok_s <= 0 or previous.p95_s <= 0:
                continue
            gain = (
                current.throughput_tok_s - previous.throughput_tok_s
            ) / previous.throughput_tok_s
            cost = (current.p95_s - previous.p95_s) / previous.p95_s
            if gain <= cost:
                break
            recommended = current.concurrency
    report = {
        "schema_version": "qwen_concurrency_ramp_v1",
        "model": model,
        "max_tokens": args.max_tokens,
        "levels": [item.to_dict() for item in results],
        "stopped_early": bool(stop_reason),
        "stop_reason": stop_reason,
        "recommended_max_concurrency": recommended,
        "peak_throughput_concurrency": peak_throughput_concurrency,
        "note": (
            "recommended 取性价比膝点（边际吞吐增益仍高于边际 P95 代价的"
            "最后一档），不是吞吐峰值——课程生成是用户等待型任务，"
            "P95 即用户感知等待时间。peak_throughput_concurrency 另列，"
            "供批处理型场景参考。"
            "AI_PROVIDER_INITIAL_CONCURRENCY 仍应从低起爬，保留 AIMD 机制。"
            "本结果为独占场景；若同机有其他消费方需另留余量。"
        ),
    }
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"ramp_report": report}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="自部署 Qwen 并发爬坡实测")
    parser.add_argument("--levels", default="1,2,4,6,8,12,16")
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--cooldown", type=float, default=5.0)
    parser.add_argument("--out", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print("并发爬坡计划（dry-run，不发起任何请求）")
        print(f"  档位     : {args.levels}")
        print(f"  max_tokens: {args.max_tokens}（贴近长结构化 JSON 负载）")
        print(f"  档间冷却 : {args.cooldown}s")
        print("  端点     : 从 AI_API_BASE / AI_MODEL 读取，不硬编码")
        print("  早停条件 : 错误率>10% / 出现截断 / P95>基线4倍 / 吞吐跌破峰值80%")
        return 0
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
