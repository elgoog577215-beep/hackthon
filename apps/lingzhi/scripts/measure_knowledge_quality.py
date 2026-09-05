#!/usr/bin/env python3
"""统计真实生成课程的 B1 概念组分解与 C2 掌握标准枚举分布。

用法：
    python scripts/measure_knowledge_quality.py <course_data.json>

为什么需要它：`count_knowledge_relations.py`（lz-web-search 提交）只统计 A1
的六类关系分布。B1 与 C2 改的同样是 prompt，同样只能靠真实生成验证，但看的
是完全不同的两个量：

- **B1**：每个概念组聚合几个知识点。修复前实测"31 个概念组各 1 个知识点"，
  组数≈知识点数，概念组没有承担分组职责。判据是 `grouping_ratio`
  （组数/知识点数）明显小于 1，且多数组落在 2-4 个。
- **C2**：`required_independence` 与 `required_transfer` 的取值分布。修复前
  实测 146/146 全是 `independent`、142/146 全是 `variation`——两条 prompt 的
  JSON 样例把值写死了，模型照抄。判据是这两项不再是单一值。

本脚本只读不写，不依赖后端进程。
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

INDEPENDENCE = ("scaffolded", "guided", "independent")
TRANSFER = ("recall", "procedure", "variation", "novel")


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def concept_groups(course: dict) -> list[tuple[str, int]]:
    """返回 [(组名, 该组知识点数)]。

    优先读编译后的知识库（`course_knowledge_base`），它是最终产物；
    没有时退回教案里的 `knowledge_structure`，那是模型的原始输出。
    """
    kb = course.get("course_knowledge_base") or {}
    points = kb.get("knowledge_points") or []
    if points:
        counter = collections.Counter(
            str(p.get("primary_concept_group_id") or "") for p in points
        )
        names = {
            str(g.get("concept_group_id") or ""): str(g.get("name") or "")
            for g in kb.get("concept_groups") or []
        }
        return [(names.get(gid, gid), n) for gid, n in counter.items()]

    groups: list[tuple[str, int]] = []
    for node in course.get("nodes") or []:
        for g in node.get("knowledge_structure") or []:
            if isinstance(g, dict):
                groups.append((
                    str(g.get("concept_group") or ""),
                    len(g.get("knowledge_points") or []),
                ))
    return groups


def mastery_criteria(course: dict) -> list[dict]:
    kb = course.get("course_knowledge_base") or {}
    if kb.get("mastery_criteria"):
        return [c for c in kb["mastery_criteria"] if isinstance(c, dict)]
    found = []
    for node in course.get("nodes") or []:
        for g in node.get("knowledge_structure") or []:
            for p in (g or {}).get("knowledge_points") or []:
                for c in (p or {}).get("mastery_criteria") or []:
                    if isinstance(c, dict):
                        found.append(c)
    return found


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    course = load(sys.argv[1])
    print(f"课程：{course.get('course_name', '?')}")
    print(f"小节数：{len(course.get('nodes') or [])}")

    # --- B1 ---
    groups = concept_groups(course)
    point_total = sum(n for _, n in groups)
    print("\n=== B1 概念组分解 ===")
    print(f"概念组 {len(groups)} 个 / 知识点 {point_total} 个")
    if groups and point_total:
        ratio = len(groups) / point_total
        singles = sum(1 for _, n in groups if n == 1)
        in_range = sum(1 for _, n in groups if 2 <= n <= 4)
        print(f"grouping_ratio = {ratio:.3f}（越接近 1 越说明没分组；修复前实测 ≈1.0）")
        print(f"单点组 {singles} 个；落在 2-4 个区间的组 {in_range} 个")
        dist = collections.Counter(n for _, n in groups)
        print("每组知识点数分布：" + "、".join(
            f"{k}个×{v}组" for k, v in sorted(dist.items())
        ))
        verdict = "PASS" if ratio < 0.75 and singles < len(groups) / 2 else "FAIL"
        print(f"B1 判定：{verdict}")

    # --- C2 ---
    criteria = mastery_criteria(course)
    print("\n=== C2 掌握标准枚举分布 ===")
    print(f"掌握标准 {len(criteria)} 条")
    for field, vocab in (("required_independence", INDEPENDENCE),
                         ("required_transfer", TRANSFER)):
        dist = collections.Counter(str(c.get(field) or "(空)") for c in criteria)
        total = sum(dist.values()) or 1
        top_share = max(dist.values()) / total if dist else 1.0
        detail = "、".join(f"{k}={v}" for k, v in dist.most_common())
        print(f"{field}: {detail}")
        print(f"  最高占比 {top_share:.0%}"
              f"（修复前 independent 100% / variation 97%）"
              f" -> {'PASS 已分化' if len(dist) > 1 else 'FAIL 仍是单一值'}")
        unknown = sorted(set(dist) - set(vocab) - {"(空)"})
        if unknown:
            print(f"  ⚠ 词表外取值：{unknown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
