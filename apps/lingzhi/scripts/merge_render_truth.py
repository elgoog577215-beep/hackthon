#!/usr/bin/env python3
"""把 `render_gate.mjs` 的逐门课输出并成一份「渲染真值」，供误报率探针使用。

误报率的判定基准必须是**真实渲染器**的结论，而 `render_gate.mjs` 是按课程
逐个跑的。这个脚本只做一件事：把若干份 gate 输出并成
`f1_render_gate_false_positive_probe.py --render` 需要的那个数组。

单独成脚本而不是写进文档的 here-doc，是因为交接文档里的命令必须能直接粘贴
执行——嵌套 here-doc 在 shell 里极易踩引号的坑。

    python3 scripts/merge_render_truth.py --gate '/tmp/gate-*.json' --out /tmp/render_results.json
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="合并 render_gate 输出为渲染真值")
    parser.add_argument(
        "--gate",
        required=True,
        help="render_gate.mjs 输出的 glob，例如 '/tmp/gate-*.json'（记得加引号）",
    )
    parser.add_argument("--out", required=True, help="输出文件")
    args = parser.parse_args()

    paths = sorted(glob.glob(args.gate))
    if not paths:
        print(f"没有匹配到任何文件：{args.gate}")
        return 1

    rows: list[dict] = []
    for path in paths:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        for node in report.get("nodes") or []:
            diagnostics = node.get("render_diagnostics") or {}
            rows.append({
                "node_id": node.get("node_id", ""),
                "node_name": node.get("node_name", ""),
                # 探针只认这个字段作为「渲染是否正常」的真值。
                "render_ok": bool(node.get("passed")),
                "katex_error_count": int(node.get("katex_error_count") or 0),
                "math_fallback_count": int(node.get("math_fallback_count") or 0),
                "reported_failure_count": int(
                    diagnostics.get("block_failure_count") or 0
                ),
                "math_fallback_samples": [
                    str(sample.get("detail", ""))
                    for sample in node.get("samples") or []
                ],
            })

    Path(args.out).write_text(
        json.dumps(rows, ensure_ascii=False), encoding="utf-8"
    )
    broken = sum(1 for row in rows if not row["render_ok"])
    print(f"合并 {len(paths)} 份报告，共 {len(rows)} 节，其中渲染失败 {broken} 节 → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
