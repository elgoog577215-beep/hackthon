#!/usr/bin/env python3
"""把多轮取证报告里的填空逐空对照汇成一张分布表。

单轮数字说明不了问题——填空成品率历轮 1/3/7/8/3/4/2/3（均值 3.9、sd 2.4），
所以归因也必须跨轮看分布。本脚本只做汇总与原样导出，**不下结论、不改判等**。

用法：

    python scripts/fill_blank_mismatch_distribution.py 报告1.json 报告2.json ...
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    paths = [Path(value) for value in sys.argv[1:]]
    if not paths:
        print(__doc__, file=sys.stderr)
        return 2

    from assessment_fill_blank_diagnostics import CAUSE_BUCKETS, summarize

    all_entries: list[dict[str, Any]] = []
    per_round: list[dict[str, Any]] = []
    for path in paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        diagnostics = report.get("fill_blank_blank_diagnostics") or {}
        entries = diagnostics.get("comparisons") or []
        all_entries.extend(entries)
        fill_blank = (report.get("per_form") or {}).get("fill_blank") or {}
        per_round.append({
            "file": path.name,
            "generated": fill_blank.get("generated"),
            "requested": fill_blank.get("requested"),
            "elapsed_seconds": report.get("elapsed_seconds"),
            "logical_call_count": (
                report.get("run_vitals") or {}
            ).get("logical_call_count"),
            "provider_cooldowns": (
                report.get("run_vitals") or {}
            ).get("provider_cooldowns"),
            "summary": diagnostics.get("summary") or {},
        })

    combined = summarize(all_entries)
    print(json.dumps({
        "rounds": per_round,
        "combined": combined,
        "cause_buckets": CAUSE_BUCKETS,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
