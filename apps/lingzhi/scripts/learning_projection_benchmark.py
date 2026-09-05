#!/usr/bin/env python3
"""度量学习投影重算在真实课程规模下的耗时与复杂度。

**只读**：脚本在隔离的临时数据目录里合成课程与学习事实，不读取也不写入任何真实
课程数据。目的是找出投影重算的热点与复杂度量级，为长期校准提供依据。

用法：

    backend/.venv/bin/python scripts/learning_projection_benchmark.py
    backend/.venv/bin/python scripts/learning_projection_benchmark.py --json out.json

度量对象是三个每次请求都会重算的投影：

- ``build_learning_progress``：目标 × 事实 的匹配
- ``build_learner_model``：在进度之上再叠加证据编目与知识/技能状态
- ``build_learning_runtime``：完整运行时（含上面两者）

关注的是**随规模增长的方式**，不是绝对毫秒数——后者依赖机器负载。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

# 必须在导入任何 backend 模块之前重定向数据目录：storage 与派生仓库在导入期就把
# 根路径固化下来。这保证脚本绝不碰真实课程数据。
_ISOLATED_DIR = tempfile.mkdtemp(prefix="lingzhi-benchmark-")
os.environ.setdefault("LINGZHI_DATA_DIR", _ISOLATED_DIR)

for module_root in (ROOT, BACKEND):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from learner_model import build_learner_model  # noqa: E402
from learning_progress import build_learning_progress  # noqa: E402
from learning_runtime import build_runtime_revision_vector  # noqa: E402

USER_ID = "benchmark-learner"


def synthetic_course(section_count: int) -> dict[str, Any]:
    """合成一门指定规模的课程。内容是占位文本，不取自任何真实课程。"""
    return {
        "course_id": "benchmark-course",
        "course_name": "基准课程",
        "current_course_version_id": "cv-1",
        "nodes": [
            {
                "node_id": f"node-{index}",
                "parent_node_id": "root",
                "node_name": f"第 {index} 节",
                "node_level": 2,
                "learning_objective": f"掌握第 {index} 节的核心概念",
                "node_content": f"第 {index} 节的正文内容。" * 12,
            }
            for index in range(section_count)
        ],
    }


def synthetic_events(section_count: int, per_section: int) -> list[dict[str, Any]]:
    """合成学习事实。刻意覆盖多种事件类型，贴近真实分布。"""
    event_types = [
        "node_learning_started",
        "node_learning_completed",
        "learner_self_reported",
    ]
    events: list[dict[str, Any]] = []
    for section in range(section_count):
        for index in range(per_section):
            event_type = event_types[index % len(event_types)]
            events.append({
                "event_id": f"evt_{section}_{index}",
                "event_type": event_type,
                "user_id": USER_ID,
                "actor": "user",
                "course_id": "benchmark-course",
                "course_version_id": "cv-1",
                "node_id": f"node-{section}",
                "evidence": {"statement": "占位自述内容"} if event_type == "learner_self_reported" else {},
                "result": {},
                "metadata": {},
                "created_at": f"2026-08-{(index % 27) + 1:02d}T00:00:00",
                "schema_version": 8,
            })
    return events


def _time_it(fn, *, repeats: int) -> dict[str, float]:
    samples: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return {
        "median_ms": round(statistics.median(samples), 2),
        "min_ms": round(min(samples), 2),
        "max_ms": round(max(samples), 2),
    }


def measure(section_count: int, per_section: int, *, repeats: int) -> dict[str, Any]:
    course = synthetic_course(section_count)
    events = synthetic_events(section_count, per_section)

    progress_timing = _time_it(
        lambda: build_learning_progress(course, user_id=USER_ID, events=events, attempts=[]),
        repeats=repeats,
    )
    progress = build_learning_progress(course, user_id=USER_ID, events=events, attempts=[])

    revision_vector = build_runtime_revision_vector(
        course=course,
        events=events,
        snapshot=None,
        records=[],
        attempts=[],
        workflow={},
        continuation={},
    )
    model_timing = _time_it(
        lambda: build_learner_model(
            course,
            user_id=USER_ID,
            events=events,
            snapshot=None,
            records=[],
            attempts=[],
            workflow={},
            progress=progress,
            source_revision_vector=revision_vector,
        ),
        repeats=repeats,
    )

    return {
        "section_count": section_count,
        "events_per_section": per_section,
        "event_count": len(events),
        "learning_progress": progress_timing,
        "learner_model": model_timing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5, help="每个规模重复次数，取中位数")
    parser.add_argument("--json", type=Path, default=None, help="把结果写入 JSON 文件")
    args = parser.parse_args()

    # 覆盖从小课程到大课程的量级，用于观察增长方式。
    scenarios = [
        (10, 5),
        (20, 5),
        (40, 5),
        (40, 20),
        (80, 20),
    ]

    results = [
        measure(sections, per_section, repeats=args.repeats)
        for sections, per_section in scenarios
    ]

    print(f"{'节数':>6} {'事实数':>8} {'进度(ms)':>12} {'学习者模型(ms)':>16}")
    for item in results:
        print(
            f"{item['section_count']:>6} {item['event_count']:>8} "
            f"{item['learning_progress']['median_ms']:>12} "
            f"{item['learner_model']['median_ms']:>16}"
        )

    # 复杂度观察：节数与事实数同时翻倍时，耗时的增长倍率。
    print("\n增长观察（相对前一档）：")
    for previous, current in zip(results, results[1:]):
        event_ratio = current["event_count"] / max(previous["event_count"], 1)
        progress_ratio = current["learning_progress"]["median_ms"] / max(
            previous["learning_progress"]["median_ms"], 0.01
        )
        model_ratio = current["learner_model"]["median_ms"] / max(
            previous["learner_model"]["median_ms"], 0.01
        )
        print(
            f"  事实数 ×{event_ratio:.1f} -> 进度 ×{progress_ratio:.1f}，"
            f"学习者模型 ×{model_ratio:.1f}"
        )

    # 分离变量：分别固定事实数与节数，看哪一维真正驱动耗时。
    print("\n变量分离：")
    fixed_events = synthetic_events(10, 20)  # 恒定 200 条
    for sections in (10, 20, 40, 80):
        timing = _time_it(
            lambda s=sections: build_learning_progress(
                synthetic_course(s), user_id=USER_ID, events=fixed_events, attempts=[],
            ),
            repeats=args.repeats,
        )
        print(f"  事实数恒定 200，节数 {sections:>3} -> 进度 {timing['median_ms']:>8} ms")
    for per_section in (5, 10, 20, 40):
        events = synthetic_events(20, per_section)
        timing = _time_it(
            lambda e=events: build_learning_progress(
                synthetic_course(20), user_id=USER_ID, events=e, attempts=[],
            ),
            repeats=args.repeats,
        )
        print(f"  节数恒定  20，事实 {len(events):>4} -> 进度 {timing['median_ms']:>8} ms")

    if args.json:
        args.json.write_text(
            json.dumps({"scenarios": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n已写入 {args.json}")

    print(f"\n（本次度量使用隔离数据目录 {os.environ['LINGZHI_DATA_DIR']}，未接触真实课程数据）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
