"""B-4：正文并行阶段的并发对照实测（打真实千问端点）。

为什么要单独做这个基准，而不是直接跑一门课：
生成链路的正文阶段被编排侧的信号量夹在 4（`task_manager._semaphore`），
而那个上限的硬夹在 `task_manager.py` 与 `course_generation_budget.py` 里，
不属于本分支可改的文件。所以"把并发放开之后会怎样"没法靠跑整门课测出来。

这个基准把正文阶段的形状原样搬过来——8 个小节、每个小节一次
长输出的模型调用、共享同一份课程上下文——只把并发上限当变量，
其余全部相同，打的是真实端点、真实 token。

用法::

    LINGZHI_GENERATION_TELEMETRY=1 python3 backend/tools/content_phase_bench.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ai_capacity  # noqa: E402
from ai_base import AIBase  # noqa: E402

# 一份"课程上下文"，正文阶段每个小节都会带上它——与真实链路一致。
SHARED_CONTEXT = (
    "## 课程上下文账本\n"
    "本课程为《计算机网络入门》，共 8 课时，面向大学二年级学生。\n"
    "全课目标：建立分层模型的直观，能解释一次 HTTP 请求经过的完整链路。\n\n"
    "## 全课教案要点\n"
    + "".join(
        f"- 第 {i} 节：{name}，需覆盖概念、例子与边界。\n"
        for i, name in enumerate(
            [
                "分层模型与封装", "物理层与链路层", "IP 与路由", "TCP 可靠传输",
                "UDP 与实时流", "DNS 解析", "HTTP 与缓存", "TLS 与安全",
            ],
            start=1,
        )
    )
    + "\n## 写作契约\n"
    "每节正文需包含：导入、核心概念、一个具体例子、一个反例、小结。\n"
    "使用 Markdown，不要输出 JSON。\n"
)

SECTIONS = [
    "分层模型与封装", "物理层与链路层", "IP 与路由", "TCP 可靠传输",
    "UDP 与实时流", "DNS 解析", "HTTP 与缓存", "TLS 与安全",
]


class _Bench(AIBase):
    pass


async def _one_section(service: _Bench, name: str, max_tokens: int) -> tuple[float, int]:
    started = time.perf_counter()
    text = await service._call_llm(
        prompt=(
            f"{SHARED_CONTEXT}\n## 本节\n请为「{name}」写出完整正文。"
        ),
        system_prompt="你是一位大学计算机课程的主讲教师。",
        max_tokens=max_tokens,
    )
    return (time.perf_counter() - started, len(text or ""))


async def run_phase(limit: int, max_tokens: int, telemetry_dir: Path) -> dict:
    """把 provider 并发上限固定在 ``limit``，跑一遍 8 个小节。

    有效并行度必须用**真正在飞的时间**算，不能用"从发起到返回"的时间：
    后者把排队等待也算进去了，在限额小的时候会把并行度算得比限额还高
    （第一版就犯了这个错，limit=4 却算出 5.83）。排队时长由 ai_capacity
    单独计量并写进账单，这里减掉它。
    """
    ai_capacity.reset_provider_capacity_controllers()
    os.environ["AI_PROVIDER_INITIAL_CONCURRENCY"] = str(limit)
    os.environ["AI_PROVIDER_MAX_CONCURRENCY"] = str(limit)
    run_dir = telemetry_dir / f"limit-{limit}"
    run_dir.mkdir(parents=True, exist_ok=True)
    os.environ["LINGZHI_GENERATION_TELEMETRY"] = "1"
    os.environ["LINGZHI_GENERATION_TELEMETRY_DIR"] = str(run_dir)
    import generation_telemetry

    service = _Bench()
    started = time.perf_counter()
    with generation_telemetry.generation_run(f"bench-{limit}"):
        results = await asyncio.gather(
            *[_one_section(service, name, max_tokens) for name in SECTIONS],
            return_exceptions=True,
        )
    wall = time.perf_counter() - started

    ok = [r for r in results if isinstance(r, tuple)]
    # 从账单里取真实在飞时长（总时长 - 排队等待）
    in_flight: list[float] = []
    queued = 0.0
    for path in run_dir.glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            queued += rec.get("queue_wait_ms", 0) / 1000
            in_flight.append(
                (rec.get("duration_ms", 0) - rec.get("queue_wait_ms", 0))
                / 1000
            )
    busy = sum(in_flight)
    durations = sorted(in_flight)
    return {
        "limit": limit,
        "wall_s": wall,
        "busy_s": busy,
        "queued_s": queued,
        "effective_parallelism": (busy / wall) if wall else 0.0,
        "ok": len(ok),
        "failed": len(results) - len(ok),
        "median_s": durations[len(durations) // 2] if durations else 0.0,
        "slowest_s": durations[-1] if durations else 0.0,
        "chars": sum(c for _, c in ok),
    }


def _render(rows: list[dict]) -> str:
    out = [
        "",
        "| 并发上限 | 墙钟(s) | 在飞合计(s) | 排队(s) | 有效并行度 | 单节中位(s) | 成功/失败 |",
        "|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        out.append(
            f"| {r['limit']} | {r['wall_s']:.1f} | {r['busy_s']:.1f} | "
            f"{r['queued_s']:.1f} | {r['effective_parallelism']:.2f} | "
            f"{r['median_s']:.1f} | {r['ok']}/{r['failed']} |"
        )
    if len(rows) >= 2:
        base, best = rows[0], rows[-1]
        if best["wall_s"] > 0:
            cut = (base["wall_s"] - best["wall_s"]) / base["wall_s"] * 100
            out += [
                "",
                f"并发 {base['limit']} -> {best['limit']}："
                f"墙钟 {base['wall_s']:.1f}s -> {best['wall_s']:.1f}s"
                f"（**下降 {cut:.1f}%**），"
                f"有效并行度 {base['effective_parallelism']:.2f} -> "
                f"{best['effective_parallelism']:.2f}",
            ]
    return "\n".join(out)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limits", default="4,8",
        help="要对照的并发上限，逗号分隔（默认 4,8）",
    )
    parser.add_argument("--max-tokens", type=int, default=3000)
    parser.add_argument("--telemetry-dir", type=Path,
                        default=Path("/tmp/lz-b4-bench"))
    args = parser.parse_args()

    rows = []
    for limit in [int(x) for x in args.limits.split(",") if x.strip()]:
        print(f"跑并发上限 {limit} ...", flush=True)
        row = await run_phase(limit, args.max_tokens, args.telemetry_dir)
        print(
            f"  墙钟 {row['wall_s']:.1f}s  有效并行度 "
            f"{row['effective_parallelism']:.2f}  "
            f"成功 {row['ok']}/{len(SECTIONS)}",
            flush=True,
        )
        rows.append(row)
    print(_render(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
