#!/usr/bin/env python3
"""统计真实生成课程里六类知识关系的分布（A1 验收用）。

用法：
    python scripts/count_knowledge_relations.py <course_data.json>

A1 验收要求：真实课程重生成后，六类关系至少出现四类。
六类定义来自 `backend/course_knowledge_base.RELATION_TYPES`。

本脚本只读不写，不依赖后端进程。
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

# 与 backend/course_knowledge_base.RELATION_TYPES 保持一致。
RELATION_TYPES = (
    "prerequisite",
    "derives",
    "equivalent_to",
    "contrasts_with",
    "applies_to",
    "generalizes",
)
REQUIRED_DISTINCT = 4


def collect_relations(course: dict) -> list[dict]:
    """关系散落在多处，全部收齐后去重。

    - 教案分小节持有 `knowledge_relations`（主要来源）
    - 课程级 `knowledge_relations` 是汇总投影
    - 知识库编译后有 `relation_decisions`
    """
    found: list[dict] = []
    plan = course.get("course_teaching_plan") or {}
    for section in plan.get("sections") or []:
        for relation in section.get("knowledge_relations") or []:
            if isinstance(relation, dict):
                found.append({**relation, "_from": f"teaching_plan:{section.get('node_id')}"})
    for relation in course.get("knowledge_relations") or []:
        if isinstance(relation, dict):
            found.append({**relation, "_from": "course_level"})
    library = course.get("course_knowledge_library") or {}
    for relation in library.get("relations") or []:
        if isinstance(relation, dict):
            found.append({**relation, "_from": "knowledge_library"})
    return found


def endpoint_of(relation: dict, side: str) -> str:
    """关系端点在不同产物里字段名不同：教案用 *_name，编译后用 *_key。"""
    for key in (f"{side}_name", f"{side}_key", side):
        value = str(relation.get(key) or "").strip()
        if value:
            return value
    return ""


def relation_type_of(relation: dict) -> str:
    for key in ("relation_type", "type", "relation"):
        value = str(relation.get(key) or "").strip()
        if value:
            return value
    return ""


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = Path(sys.argv[1])
    course = json.loads(path.read_text(encoding="utf-8"))

    relations = collect_relations(course)
    counts = collections.Counter(relation_type_of(item) for item in relations)
    # 按 source/target/type 去重，避免汇总投影导致重复计数
    unique = {
        (endpoint_of(item, "source"), endpoint_of(item, "target"), relation_type_of(item))
        for item in relations
    }
    unique_counts = collections.Counter(triple[2] for triple in unique)

    plan = course.get("course_teaching_plan") or {}
    section_count = len(plan.get("sections") or [])

    print(f"课题       : {course.get('course_name') or course.get('subject') or '?'}")
    print(f"小节数     : {section_count}")
    print(f"关系条数   : {len(relations)} 条（去重后 {len(unique)} 条）")
    print(f"证据修订   : {(course.get('evidence_package') or {}).get('package_revision_id') or '(无)'}")
    print()
    print("六类关系分布（去重后）:")
    present = 0
    for name in RELATION_TYPES:
        n = unique_counts.get(name, 0)
        if n:
            present += 1
        print(f"  {name:16} {n}")
    extra = sorted(set(unique_counts) - set(RELATION_TYPES) - {""})
    if extra:
        print(f"  (白名单外类型: {', '.join(f'{k}={unique_counts[k]}' for k in extra)})")
    blank = unique_counts.get("", 0)
    if blank:
        print(f"  (无类型字段: {blank})")
    print()
    print(f"出现类型数 : {present} / 6   （A1 要求 >= {REQUIRED_DISTINCT}）")
    print(f"A1 验收    : {'PASS' if present >= REQUIRED_DISTINCT else 'FAIL'}")
    return 0 if present >= REQUIRED_DISTINCT else 1


if __name__ == "__main__":
    raise SystemExit(main())
