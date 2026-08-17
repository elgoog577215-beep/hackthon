#!/usr/bin/env python3
"""Cross-tabulate the publication gate against a real renderer, on real courses.

This is the measurement Gap B1 has been asking for since 8/11. The gate is a
release blocker whose render rules had only unit tests, so we knew they fire on
content we wrote and nothing about how they behave on real model output.

Operational definitions, fixed before looking at any number:

* Ground truth is the real frontend pipeline — markdown-it + KaTeX + DOMPurify,
  the same `renderMarkdown` the learner's browser runs, executed headlessly by
  `render_corpus.mjs`. A node "renders clean" when KaTeX emitted no error node,
  nothing degraded to `math-fallback`, and the diagnostics channel recorded
  nothing.
* FALSE POSITIVE = the gate raises a *blocking* (critical) render issue on a
  node that renders clean. Blocking is the operative word: only a critical
  stops a release, so only a critical can wrongly stop one. Warnings on clean
  nodes are counted separately as `advisory_on_clean` — untidy source is worth
  reporting and never worth a launch.
* FALSE NEGATIVE = the node fails to render but the gate blocks nothing. This
  is the `cases/aligned` class of defect — the reason F-1 exists. Closing it
  needs a real parse, which is what `scripts/render_gate.mjs` provides.

Only render-dimension codes are scored. Content and hygiene codes are judgements
about teaching quality; a renderer cannot adjudicate them, so counting them here
would be measuring the wrong thing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for module_root in (ROOT, BACKEND):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from course_quality import _issue_dimension, evaluate_node_content  # noqa: E402


def _wilson_upper_bound(events: int, trials: int, z: float = 1.96) -> float:
    """One-sided 95% upper bound, so 0/N is never read as "proven safe"."""
    if trials <= 0:
        return 1.0
    phat = events / trials
    denominator = 1 + z * z / trials
    centre = phat + z * z / (2 * trials)
    margin = z * ((phat * (1 - phat) / trials + z * z / (4 * trials * trials)) ** 0.5)
    return round(min(1.0, (centre + margin) / denominator), 4)


def _bare_node(record: dict) -> dict:
    """Evaluate the body against an empty contract.

    The corpus is legacy flat-schema courses with no `module_plan`,
    `key_points` or `difficulty_contract`. Supplying an empty node keeps every
    contract-driven content rule silent, so the only codes that can fire are the
    ones driven by the text itself — which is exactly the render tier we are
    measuring. Inventing contracts would inject our own assumptions into the
    measurement.
    """
    return {
        "node_id": record["node_id"],
        "node_name": record.get("node_name", ""),
        "module_plan": [],
        "key_points": [],
        "grounding_contract": {},
        "difficulty_contract": {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="在真实课程正文上测量发布门渲染判据的误报率"
    )
    parser.add_argument("--corpus", required=True, help="git 历史导出的课程 JSON 目录")
    parser.add_argument("--render", required=True, help="render_corpus.mjs 的输出")
    parser.add_argument("--out", default="", help="把逐节点明细写到这个文件")
    parser.add_argument("--show", type=int, default=10)
    args = parser.parse_args()

    render_by_id = {
        item["node_id"]: item
        for item in json.loads(Path(args.render).read_text(encoding="utf-8"))
    }

    rows: list[dict] = []
    for path in sorted(Path(args.corpus).glob("*.json")):
        course = json.loads(path.read_text(encoding="utf-8"))
        for node in course.get("nodes") or []:
            content = str(node.get("node_content") or "")
            if not content.strip():
                continue
            node_id = str(node.get("node_id") or "")
            truth = render_by_id.get(node_id)
            if truth is None:
                continue
            report = evaluate_node_content(content, _bare_node({
                "node_id": node_id,
                "node_name": node.get("node_name", ""),
            }))
            render_issues = [
                item for item in report["issues"]
                if _issue_dimension(str(item.get("code") or "")) == "render"
            ]
            # Only a `critical` issue stops a release (`_has_critical` drives
            # `passed`). A warning costs the author a glance, not a launch, so
            # the two are counted separately: conflating them would let a rule
            # look "fixed" merely by being reported more quietly, and would also
            # overstate the risk this probe exists to measure.
            blocking = [
                item for item in render_issues
                if str(item.get("severity")) == "critical"
            ]
            rows.append({
                "course": course.get("course_name", path.name),
                "node_id": node_id,
                "node_name": str(node.get("node_name") or ""),
                "chars": len(content),
                "renders_clean": bool(truth["render_ok"]),
                "gate_render_codes": sorted({str(i["code"]) for i in render_issues}),
                "gate_blocking_codes": sorted({str(i["code"]) for i in blocking}),
                "gate_flags": bool(render_issues),
                "gate_blocks": bool(blocking),
                "katex_error_count": truth["katex_error_count"],
                "math_fallback_count": truth["math_fallback_count"],
                "math_fallback_samples": truth.get("math_fallback_samples", []),
            })

    clean = [r for r in rows if r["renders_clean"]]
    broken = [r for r in rows if not r["renders_clean"]]
    false_positives = [r for r in clean if r["gate_blocks"]]
    true_positives = [r for r in broken if r["gate_blocks"]]
    false_negatives = [r for r in broken if not r["gate_blocks"]]
    advisory_on_clean = [
        r for r in clean if r["gate_flags"] and not r["gate_blocks"]
    ]

    fp_rate = len(false_positives) / len(clean) if clean else 0.0
    fn_rate = len(false_negatives) / len(broken) if broken else 0.0

    by_code: dict[str, dict[str, int]] = {}
    for row in rows:
        for code in row["gate_render_codes"]:
            bucket = by_code.setdefault(code, {"on_clean": 0, "on_broken": 0})
            bucket["on_clean" if row["renders_clean"] else "on_broken"] += 1

    report = {
        "status": "measured",
        "corpus": {
            "courses": len({r["course"] for r in rows}),
            "nodes": len(rows),
            "chars": sum(r["chars"] for r in rows),
        },
        "ground_truth": {
            "renders_clean": len(clean),
            "renders_broken": len(broken),
        },
        "false_positive": {
            "count": len(false_positives),
            "denominator": len(clean),
            "rate": round(fp_rate, 4),
            "rate_upper_95": _wilson_upper_bound(len(false_positives), len(clean)),
            "meaning": "渲染正常却被判 critical、直接卡住发布的节点占比——这是 B1 要关的那个数",
        },
        "advisory_on_clean": {
            "count": len(advisory_on_clean),
            "meaning": "渲染正常但收到 warning 的节点：源码确实不整洁，不阻断发布",
        },
        "false_negative": {
            "count": len(false_negatives),
            "denominator": len(broken),
            "rate": round(fn_rate, 4),
            "rate_upper_95": _wilson_upper_bound(len(false_negatives), len(broken)),
            "meaning": "真的渲染坏了却被放行的节点占比——只有真实渲染关卡能补上",
        },
        "true_positive": {"count": len(true_positives)},
        "by_code": {
            code: {
                **counts,
                "precision": (
                    round(counts["on_broken"] / (counts["on_broken"] + counts["on_clean"]), 4)
                    if (counts["on_broken"] + counts["on_clean"])
                    else None
                ),
            }
            for code, counts in sorted(by_code.items())
        },
        "false_positive_samples": [
            {k: v for k, v in row.items() if k != "math_fallback_samples"}
            for row in false_positives[: args.show]
        ],
        "false_negative_samples": [
            {
                "course": row["course"],
                "node_id": row["node_id"],
                "node_name": row["node_name"],
                "math_fallback_count": row["math_fallback_count"],
                "katex_error_count": row["katex_error_count"],
                "samples": row["math_fallback_samples"],
            }
            for row in false_negatives[: args.show]
        ],
    }
    if args.out:
        Path(args.out).write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
