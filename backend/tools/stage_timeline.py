"""把 A-1 账单按**生成阶段**切开，给逐阶段耗时对照。

账单里的 `stage` 在自动模式下是服务类名（`CourseService` 之类），粒度不够。
真正区分阶段要靠**调用特征 + 时间顺序**：

* 目录阶段：最早的一批，输入较小；
* 教案阶段：输入大（含骨架与全课契约）、输出长；
* 正文阶段：**流式**调用（`stream=true`），这是最可靠的判据——
  只有正文走 `_stream_llm`。

用法::

    python3 backend/tools/stage_timeline.py <账单.jsonl>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return sorted(records, key=lambda r: r.get("seq", 0))


def classify(records: list[dict]) -> dict[str, list[dict]]:
    """按阶段归类。流式 = 正文，这是硬判据。"""
    stages: dict[str, list[dict]] = {"目录": [], "教案": [], "正文": [], "其他": []}
    # 正文一定是流式
    content = [r for r in records if r.get("stream")]
    non_stream = [r for r in records if not r.get("stream")]
    stages["正文"] = content

    # 非流式里，正文开始之前的都属于目录/教案。
    first_content_seq = min(
        (r["seq"] for r in content), default=10**9
    )
    before = [r for r in non_stream if r.get("seq", 0) < first_content_seq]
    after = [r for r in non_stream if r.get("seq", 0) >= first_content_seq]

    # 目录阶段是最早的一段连续调用；教案批次的输入明显更大。
    # 用输入 token 的中位数当分界，比写死阈值稳。
    if before:
        sizes = sorted(r.get("input_tokens", 0) for r in before)
        pivot = sizes[len(sizes) // 2]
        for r in before:
            # 早期 + 输入小 => 目录；其余 => 教案
            if r.get("input_tokens", 0) <= pivot and r["seq"] <= len(before) // 2:
                stages["目录"].append(r)
            else:
                stages["教案"].append(r)
    stages["其他"] = after
    return stages


def summarize(name: str, rows: list[dict]) -> dict:
    if not rows:
        return {"stage": name, "calls": 0}
    starts = [r["elapsed_s"] - r.get("duration_ms", 0) / 1000 for r in rows]
    ends = [r["elapsed_s"] for r in rows]
    busy = sum(r.get("duration_ms", 0) for r in rows) / 1000
    wall = max(ends) - min(starts)
    return {
        "stage": name,
        "calls": len(rows),
        "wall_s": wall,
        "busy_s": busy,
        "queued_s": sum(r.get("queue_wait_ms", 0) for r in rows) / 1000,
        "parallelism": (busy / wall) if wall > 0 else 0.0,
        "in_tok": sum(r.get("input_tokens", 0) for r in rows),
        "out_tok": sum(r.get("output_tokens", 0) for r in rows),
        "retries": sum(1 for r in rows if r.get("is_retry")),
        "failed": sum(1 for r in rows if r.get("status") != "completed"),
    }


BASELINE = {"目录": 139.0, "教案": 28 * 60.0, "正文": 14 * 60 + 35}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    records = load(args.path)
    if not records:
        print(f"没有记录：{args.path}")
        return 1
    stages = classify(records)

    print("| 阶段 | 调用数 | 墙钟 | 忙时 | 排队 | 有效并行度 | 输入tok | 输出tok | 重试 | 失败 |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name in ("目录", "教案", "正文", "其他"):
        s = summarize(name, stages[name])
        if not s["calls"]:
            continue
        print(
            f"| {name} | {s['calls']} | {s['wall_s']:.0f}s "
            f"({s['wall_s']/60:.1f}min) | {s['busy_s']:.0f}s | "
            f"{s['queued_s']:.1f}s | {s['parallelism']:.2f} | "
            f"{s['in_tok']} | {s['out_tok']} | {s['retries']} | {s['failed']} |"
        )

    total_wall = max(r["elapsed_s"] for r in records)
    print(f"\n**总墙钟（首次调用到末次调用）：{total_wall:.0f}s "
          f"= {total_wall/60:.1f} 分钟**")
    print(f"总调用数：{len(records)}，"
          f"输入 {sum(r.get('input_tokens',0) for r in records)} tok，"
          f"输出 {sum(r.get('output_tokens',0) for r in records)} tok")

    print("\n### 与基线对照\n")
    print("| 阶段 | 基线 | 本次 | 变化 |")
    print("|---|---:|---:|---:|")
    for name, base in BASELINE.items():
        s = summarize(name, stages[name])
        if not s["calls"]:
            print(f"| {name} | {base:.0f}s | **未到达** | — |")
            continue
        cur = s["wall_s"]
        pct = (base - cur) / base * 100
        print(
            f"| {name} | {base:.0f}s ({base/60:.1f}min) | "
            f"{cur:.0f}s ({cur/60:.1f}min) | **{pct:+.1f}%** |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
