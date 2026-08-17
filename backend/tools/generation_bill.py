"""把 A-1 的 JSONL 账单汇总成可读报告。

用法::

    python3 backend/tools/generation_bill.py <账单.jsonl> [--json]

回答任务书 A-1 的三个验收问题：

* ① 总共调了多少次模型
* ② 每个阶段各占多少时间
* ③ 重复发送的上下文占多少 token

关于②的口径：并行阶段里各次调用的耗时相加会超过墙钟时间，所以同时给出
``wall_s``（该阶段首尾之间的真实墙钟跨度）与 ``busy_s``（各次调用耗时之
和）。两者的比值就是该阶段的有效并行度，B-4 对齐容量时要看的正是它。
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    total_calls = len(records)
    total_input = sum(r.get("input_tokens", 0) for r in records)
    total_output = sum(r.get("output_tokens", 0) for r in records)

    stages: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "calls": 0,
            "busy_ms": 0,
            "queue_ms": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "retries": 0,
            "failures": 0,
            "first_s": None,
            "last_s": None,
        }
    )
    for record in records:
        bucket = stages[record.get("stage") or "(未标注)"]
        bucket["calls"] += 1
        bucket["busy_ms"] += record.get("duration_ms", 0)
        bucket["queue_ms"] += record.get("queue_wait_ms", 0)
        bucket["input_tokens"] += record.get("input_tokens", 0)
        bucket["output_tokens"] += record.get("output_tokens", 0)
        if record.get("is_retry"):
            bucket["retries"] += 1
        if record.get("status") not in {"completed"}:
            bucket["failures"] += 1
        started = record.get("elapsed_s", 0) - record.get("duration_ms", 0) / 1000
        ended = record.get("elapsed_s", 0)
        if bucket["first_s"] is None or started < bucket["first_s"]:
            bucket["first_s"] = started
        if bucket["last_s"] is None or ended > bucket["last_s"]:
            bucket["last_s"] = ended

    # ③ 重复上下文：同一块内容被发送 n 次，其中 n-1 次是重复。
    #
    # 分块 token 是本地估算，而 input_tokens 在 provider 支持 usage 时是真实
    # 计数——两者单位不同，直接相除会算出「重复占比 >100%」这种不可能的数。
    # 所以按记录做一次标定：把该次调用的各块估算值按
    # ``真实输入 / 估算合计`` 缩放到真实 token 口径，再汇总。
    block_sends: dict[str, int] = defaultdict(int)
    block_tokens: dict[str, float] = {}
    for record in records:
        blocks = [
            entry
            for entry in (record.get("context_blocks") or [])
            if isinstance(entry, list) and len(entry) == 2
        ]
        if not blocks:
            continue
        estimated_sum = sum(int(entry[1]) for entry in blocks) or 1
        real_input = record.get("input_tokens") or 0
        # 只有 provider 真实计数才值得标定；估算对估算无需换算。
        scale = (
            real_input / estimated_sum
            if record.get("tokens_source") == "provider" and real_input
            else 1.0
        )
        # 上下文块只覆盖 prompt 的一部分（短段落被过滤掉了），缩放系数不应
        # 大于 1，否则会把未纳入统计的部分摊到已统计的块上。
        scale = min(scale, 1.0)
        for digest, tokens in blocks:
            block_sends[digest] += 1
            block_tokens[digest] = int(tokens) * scale

    blocked_total = sum(
        block_tokens[d] * n for d, n in block_sends.items()
    )
    repeated_total = sum(
        block_tokens[d] * (n - 1) for d, n in block_sends.items() if n > 1
    )
    top_repeats = sorted(
        (
            {
                "digest": d,
                "sends": n,
                "tokens_each": round(block_tokens[d]),
                "repeated_tokens": round(block_tokens[d] * (n - 1)),
            }
            for d, n in block_sends.items()
            if n > 1
        ),
        key=lambda item: item["repeated_tokens"],
        reverse=True,
    )[:20]

    wall_s = max((r.get("elapsed_s", 0) for r in records), default=0)
    return {
        "answer_1_total_calls": total_calls,
        "physical_requests": sum(
            r.get("physical_request_count", 1) for r in records
        ),
        "wall_clock_s": round(wall_s, 1),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "retries": sum(1 for r in records if r.get("is_retry")),
        "failures": sum(
            1 for r in records if r.get("status") != "completed"
        ),
        "tokens_from_provider": sum(
            1 for r in records if r.get("tokens_source") == "provider"
        ),
        "answer_2_stages": {
            name: {
                "calls": b["calls"],
                "busy_s": round(b["busy_ms"] / 1000, 1),
                "wall_s": round((b["last_s"] or 0) - (b["first_s"] or 0), 1),
                "queue_s": round(b["queue_ms"] / 1000, 1),
                "input_tokens": b["input_tokens"],
                "output_tokens": b["output_tokens"],
                "retries": b["retries"],
                "failures": b["failures"],
            }
            for name, b in sorted(
                stages.items(),
                key=lambda kv: kv[1]["busy_ms"],
                reverse=True,
            )
        },
        "answer_3_repeated_context": {
            "measured_context_tokens": round(blocked_total),
            "repeated_tokens": round(repeated_total),
            "repeated_share_of_input": (
                round(repeated_total / total_input, 4) if total_input else 0
            ),
            "distinct_blocks": len(block_sends),
            "top_repeated_blocks": top_repeats,
        },
        "queue_wait_reasons": dict(
            sorted(
                (
                    (reason, count)
                    for reason, count in _count(
                        records, "queue_wait_reason"
                    ).items()
                ),
                key=lambda kv: kv[1],
                reverse=True,
            )
        ),
    }


def _count(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        value = record.get(field) or ""
        if value:
            counts[str(value)] += 1
    return dict(counts)


def render(summary: dict[str, Any]) -> str:
    lines = [
        "# 生成链路调用账单",
        "",
        f"① 总调用次数：**{summary['answer_1_total_calls']}**"
        f"（物理请求 {summary['physical_requests']}，"
        f"其中重试 {summary['retries']}，非成功 {summary['failures']}）",
        f"墙钟总时长：{summary['wall_clock_s']} 秒",
        f"输入 token 合计：{summary['total_input_tokens']}，"
        f"输出 token 合计：{summary['total_output_tokens']}"
        f"（{summary['tokens_from_provider']} 条为 provider 真实计数）",
        "",
        "## ② 各阶段耗时",
        "",
        "| 阶段 | 次数 | 墙钟(s) | 忙时(s) | 排队(s) | 输入tok | 输出tok | 重试 | 失败 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, stage in summary["answer_2_stages"].items():
        lines.append(
            f"| {name} | {stage['calls']} | {stage['wall_s']} | "
            f"{stage['busy_s']} | {stage['queue_s']} | "
            f"{stage['input_tokens']} | {stage['output_tokens']} | "
            f"{stage['retries']} | {stage['failures']} |"
        )
    repeated = summary["answer_3_repeated_context"]
    lines += [
        "",
        "## ③ 重复上下文",
        "",
        f"- 纳入统计的上下文 token：{repeated['measured_context_tokens']}",
        f"- 其中重复发送：**{repeated['repeated_tokens']}**"
        f"（占总输入 {repeated['repeated_share_of_input'] * 100:.1f}%）",
        f"- 去重后的独立块数：{repeated['distinct_blocks']}",
        "",
        "重复量最大的上下文块：",
        "",
        "| 指纹 | 发送次数 | 每次tok | 重复tok |",
        "|---|---:|---:|---:|",
    ]
    for block in repeated["top_repeated_blocks"]:
        lines.append(
            f"| {block['digest']} | {block['sends']} | "
            f"{block['tokens_each']} | {block['repeated_tokens']} |"
        )
    if summary["queue_wait_reasons"]:
        lines += ["", "## 排队原因分布", ""]
        for reason, count in summary["queue_wait_reasons"].items():
            lines.append(f"- {reason}: {count}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    records = load(args.path)
    if not records:
        print(f"没有可用记录：{args.path}")
        return 1
    summary = summarize(records)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
