"""Measure knowledge reverse-lookup and impact analysis on real courses.

The complexity-protection tests in `backend/tests/test_teaching_plan_impact.py`
use constructed data. Constructed data proves the algorithm is bounded; it does
not tell you what a teacher actually sees, because it cannot reproduce how a
real course distributes its knowledge relations. This script answers the two
questions constructed data cannot:

1. Is a knowledge edit fast enough to preview interactively?
2. Is the resulting impact surface *localized*, or does one edit light up most
   of the course? A precise-looking list that always names 80% of the course is
   worse than useless — teachers would learn to ignore it.

Usage (courses are read-only; nothing is written):

    backend/.venv/bin/python scripts/measure_knowledge_impact.py \
        ~/lingzhi/backend/data/courses/*.json

Only courses that already carry a compiled `course_knowledge_base` are measured;
the rest are reported as skipped so the sample size stays honest.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from copy import deepcopy
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from course_knowledge_impact import (  # noqa: E402
    build_knowledge_impact_report,
    dependent_knowledge_ids,
)
from course_knowledge_revisions import knowledge_revision_event  # noqa: E402
from teaching_plan_impact import KnowledgeReferenceIndex  # noqa: E402


def _edited(knowledge_base: dict[str, Any], knowledge_id: str) -> dict[str, Any]:
    after = deepcopy(knowledge_base)
    for point in after.get("knowledge_points") or []:
        if point.get("knowledge_id") == knowledge_id:
            point["statement"] = f"{point.get('statement', '')} [measurement edit]"
            point["revision_id"] = "ckpr_measure"
    after["revision_id"] = "ckbr_measure"
    return after


def measure(path: str, depths: tuple[int, ...]) -> dict[str, Any] | None:
    with open(path, encoding="utf-8") as handle:
        course = json.load(handle)
    knowledge_base = course.get("course_knowledge_base") or {}
    points = knowledge_base.get("knowledge_points") or []
    if not points:
        return None

    document = course.get("course_document") or {}
    started = time.perf_counter()
    index = KnowledgeReferenceIndex(knowledge_base)
    index_ms = (time.perf_counter() - started) * 1000

    lookup_us = []
    for point in points:
        started = time.perf_counter()
        index.referencing_targets(point["knowledge_id"])
        lookup_us.append((time.perf_counter() - started) * 1e6)

    per_depth: dict[int, dict[str, Any]] = {}
    for depth in depths:
        dependents, stale, report_ms = [], [], []
        for point in points:
            after = _edited(knowledge_base, point["knowledge_id"])
            event = knowledge_revision_event(knowledge_base, after)
            started = time.perf_counter()
            report = build_knowledge_impact_report(
                event, course_data=course, knowledge_base=after, max_relation_depth=depth,
            )
            report_ms.append((time.perf_counter() - started) * 1000)
            dependents.append(len(report["dependent_knowledge_ids"]))
            stale.append(len(report["stale"]))
        per_depth[depth] = {
            "mean_dependents": statistics.mean(dependents),
            "median_dependents": statistics.median(dependents),
            "max_dependents": max(dependents),
            "coverage_pct": statistics.mean(dependents) / len(points) * 100,
            "mean_stale": statistics.mean(stale),
            "max_stale": max(stale),
            "mean_report_ms": statistics.mean(report_ms),
        }

    hubs = sorted(
        (
            (len(dependent_knowledge_ids(knowledge_base, [point["knowledge_id"]], max_depth=3)),
             point.get("name", ""))
            for point in points
        ),
        reverse=True,
    )[:3]

    return {
        "course_name": course.get("course_name", ""),
        "size_mb": os.path.getsize(path) / 1024 / 1024,
        "sections": len(document.get("sections") or []),
        "blocks": len(document.get("blocks") or []),
        "points": len(points),
        "relations": len(knowledge_base.get("relations") or []),
        "bindings": len(knowledge_base.get("bindings") or []),
        "index_ms": index_ms,
        "lookup_us_mean": statistics.mean(lookup_us),
        "lookup_us_max": max(lookup_us),
        "per_depth": per_depth,
        "hubs": hubs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("courses", nargs="+", help="course JSON files (read-only)")
    parser.add_argument("--depths", default="1,2,3", help="relation depths to compare")
    args = parser.parse_args()
    depths = tuple(int(item) for item in args.depths.split(",") if item.strip())

    measured, skipped = [], 0
    for path in args.courses:
        try:
            result = measure(path, depths)
        except (OSError, ValueError, KeyError) as error:
            print(f"skip {os.path.basename(path)}: {error}")
            skipped += 1
            continue
        if result is None:
            skipped += 1
            continue
        measured.append(result)
        print(f"\n=== {result['course_name']} ({result['size_mb']:.1f} MB) ===")
        print(f"  sections={result['sections']} blocks={result['blocks']} "
              f"points={result['points']} relations={result['relations']} "
              f"bindings={result['bindings']}")
        print(f"  index build {result['index_ms']:.2f} ms | "
              f"reverse lookup {result['lookup_us_mean']:.1f} us avg, "
              f"{result['lookup_us_max']:.1f} us max")
        for depth, row in sorted(result["per_depth"].items()):
            print(f"  depth={depth}: dependents mean {row['mean_dependents']:.1f} "
                  f"median {row['median_dependents']:.0f} max {row['max_dependents']} "
                  f"({row['coverage_pct']:.1f}% of course) | "
                  f"stale mean {row['mean_stale']:.1f} max {row['max_stale']} | "
                  f"report {row['mean_report_ms']:.2f} ms")
        print("  widest-impact points: "
              + ", ".join(f"{count} <- {name}" for count, name in result["hubs"]))

    print(f"\nmeasured {len(measured)} course(s), skipped {skipped} without a knowledge base")
    return 0 if measured else 1


if __name__ == "__main__":
    raise SystemExit(main())
