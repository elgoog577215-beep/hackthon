"""B-4：**正文并行阶段**的并发对照实测（走真实生成路径）。

与 `content_phase_bench.py` 的区别，也是这个脚本存在的理由：

* 那个脚本是"同形状"基准——自己拼 prompt 调 `_call_llm`，**非流式**。
* 这个脚本调的是真实的 `CourseService.generate_node_content_stream`，
  **走流式路径**，与 `task_manager._schedule_nodes` 调度 8 个小节的方式一致。
  正文阶段真正跑的是这条路，`_stream_llm` 的排队、重试、心跳都算在内。

正文阶段**不依赖教案语义门**（`generation_dependency: frozen_teaching_plan_only`），
所以可以在教案门修好之前先单独测这一段。

用法::

    python3 backend/tools/content_parallel_bench.py --limits 4,8
    python3 backend/tools/content_parallel_bench.py --limits 2,4,6,8,12  # 找拐点
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ai_capacity  # noqa: E402
from models import NodeGenerationConfig  # noqa: E402

SECTIONS = [
    ("L2-1-1", "进程与线程的区别"),
    ("L2-1-2", "进程调度与上下文切换"),
    ("L2-2-1", "虚拟内存与分页"),
    ("L2-2-2", "缺页中断与置换算法"),
    ("L2-3-1", "文件系统与 inode"),
    ("L2-3-2", "磁盘调度与缓冲"),
    ("L2-4-1", "并发原语与互斥锁"),
    ("L2-4-2", "死锁的必要条件与预防"),
]


def _build_course(course_id: str) -> dict:
    """构造一份"教案已冻结"的课程，正文阶段只读它。"""
    return {
        "course_id": course_id,
        "course_name": "操作系统入门",
        "target_audience": "大学二年级学生",
        "difficulty": "intermediate",
        "nodes": [
            {
                "node_id": node_id,
                "node_level": 2,
                "node_name": name,
                "node_content": "",
                "teaching_plan": {
                    "summary": f"本节讲解{name}，需覆盖概念、例子与边界。",
                    "knowledge_points": [
                        {"name": f"{name}的核心机制", "statement": f"能解释{name}的成立条件。"},
                    ],
                },
            }
            for node_id, name in SECTIONS
        ],
    }


async def _one_node(
    service, course_id: str, node: dict, course_data: dict,
    config: NodeGenerationConfig,
) -> dict:
    chars = 0
    first_chunk_at: float | None = None
    started = time.perf_counter()

    async def on_chunk(chunk: str) -> None:
        nonlocal chars, first_chunk_at
        if first_chunk_at is None:
            first_chunk_at = time.perf_counter()
        chars += len(chunk)

    try:
        await service.generate_node_content_stream(
            course_id=course_id,
            node=node,
            config=config,
            on_chunk=on_chunk,
            course_data=course_data,
        )
        error = ""
    except Exception as exc:  # 单节失败不该让整个对照作废
        error = f"{type(exc).__name__}: {exc}"[:120]
    return {
        "node": node["node_name"],
        "duration_s": time.perf_counter() - started,
        "ttfb_s": (
            (first_chunk_at - started) if first_chunk_at is not None else None
        ),
        "chars": chars,
        "error": error,
    }


async def run_phase(limit: int, telemetry_dir: Path, words: int = 0) -> dict:
    """把并发上限固定在 ``limit``，跑一遍 8 个小节的正文阶段。"""
    ai_capacity.reset_provider_capacity_controllers()
    os.environ["AI_PROVIDER_INITIAL_CONCURRENCY"] = str(limit)
    os.environ["AI_PROVIDER_MAX_CONCURRENCY"] = str(limit)
    os.environ["COURSE_CONTENT_CONCURRENCY"] = str(limit)
    run_dir = telemetry_dir / f"limit-{limit}"
    run_dir.mkdir(parents=True, exist_ok=True)
    os.environ["LINGZHI_GENERATION_TELEMETRY"] = "1"
    os.environ["LINGZHI_GENERATION_TELEMETRY_DIR"] = str(run_dir)

    import generation_telemetry
    from course_generation.service import CourseService

    service = CourseService()
    course_id = f"bench-{limit}"
    course_data = _build_course(course_id)
    nodes = course_data["nodes"]

    # 正文阶段的调度形状：所有小节同时进入，由信号量控制实际并发。
    gate = asyncio.Semaphore(limit)

    # 真实正文单节中位 4 分 11 秒，比默认配置产出的长得多。
    # 要让对照有可比性，就得把单节规模拉到同一量级。
    config = NodeGenerationConfig(
        target_word_range=(words, int(words * 1.2)) if words else None,
    )

    async def guarded(node: dict) -> dict:
        async with gate:
            return await _one_node(
                service, course_id, node, course_data, config
            )

    started = time.perf_counter()
    with generation_telemetry.generation_run(f"content-{limit}"):
        results = await asyncio.gather(*[guarded(n) for n in nodes])
    wall = time.perf_counter() - started

    # 有效并行度要用**真正在飞**的时间：总时长减掉排队等待。
    in_flight: list[float] = []
    queued = 0.0
    for path in run_dir.glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            queued += rec.get("queue_wait_ms", 0) / 1000
            in_flight.append(
                (rec.get("duration_ms", 0) - rec.get("queue_wait_ms", 0)) / 1000
            )
    ok = [r for r in results if not r["error"]]
    durations = sorted(r["duration_s"] for r in ok)
    return {
        "limit": limit,
        "wall_s": wall,
        "busy_s": sum(in_flight),
        "queued_s": queued,
        "effective_parallelism": (sum(in_flight) / wall) if wall else 0.0,
        "ok": len(ok),
        "failed": len(results) - len(ok),
        "median_s": statistics.median(durations) if durations else 0.0,
        "slowest_s": durations[-1] if durations else 0.0,
        "chars": sum(r["chars"] for r in ok),
        "errors": [r["error"] for r in results if r["error"]][:3],
    }


def render(rows: list[dict]) -> str:
    out = [
        "",
        "| 并发 | 墙钟(s) | 在飞合计(s) | 排队(s) | 有效并行度 | 单节中位(s) | 最慢(s) | 成功/失败 |",
        "|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        out.append(
            f"| {r['limit']} | {r['wall_s']:.1f} | {r['busy_s']:.1f} | "
            f"{r['queued_s']:.1f} | {r['effective_parallelism']:.2f} | "
            f"{r['median_s']:.1f} | {r['slowest_s']:.1f} | "
            f"{r['ok']}/{r['failed']} |"
        )
    if len(rows) >= 2:
        base, best = rows[0], rows[-1]
        if base["wall_s"] > 0:
            cut = (base["wall_s"] - best["wall_s"]) / base["wall_s"] * 100
            out += [
                "",
                f"并发 {base['limit']} -> {best['limit']}："
                f"墙钟 {base['wall_s']:.1f}s -> {best['wall_s']:.1f}s"
                f"（{cut:+.1f}%），有效并行度 "
                f"{base['effective_parallelism']:.2f} -> "
                f"{best['effective_parallelism']:.2f}",
            ]
    for r in rows:
        if r["errors"]:
            out.append(f"  并发 {r['limit']} 的失败样例：{r['errors']}")
    return "\n".join(out)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limits", default="4,8")
    parser.add_argument(
        "--words", type=int, default=0,
        help="每节目标字数；设大一些让单节耗时贴近真实基线（真实中位 4分11秒）",
    )
    parser.add_argument(
        "--telemetry-dir", type=Path, default=Path("/tmp/lz-content-bench")
    )
    args = parser.parse_args()

    rows = []
    for limit in [int(x) for x in args.limits.split(",") if x.strip()]:
        print(f"跑正文阶段，并发 {limit} ...", flush=True)
        row = await run_phase(limit, args.telemetry_dir, args.words)
        print(
            f"  墙钟 {row['wall_s']:.1f}s  有效并行度 "
            f"{row['effective_parallelism']:.2f}  "
            f"成功 {row['ok']}/{len(SECTIONS)}  "
            f"产出 {row['chars']} 字",
            flush=True,
        )
        rows.append(row)
    print(render(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
