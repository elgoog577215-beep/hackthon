#!/usr/bin/env python3
"""统计真实课程里知识关系成环的普遍程度（需求 D4 决策依据）。

用法：
    python scripts/measure_relation_cycles.py [课程目录]
    默认扫 ~/lingzhi/backend/data/courses

背景：`validate_course_knowledge_base` 目前把前置成环判为 `major` 而非
`critical`，也就是**一门课带着前置环路仍然可以 `passed is True` 发布**。
要不要升成 critical，取决于成环是"个别脏数据"还是"普遍现象"：

- 若是少数 → 可以直接升 critical，顺手修掉那几门；
- 若是普遍 → 升 critical 会让存量课程大面积转红，必须先修存量或给迁移期。

所以先统计，不改行为。

**刻意复用生产代码里的 `_find_relation_cycle`**，而不是自己写一个环检测：
统计口径必须与校验层完全一致，否则算出来的数字不能用来做这个决策。
只读，不写任何课程文件。
"""

from __future__ import annotations

import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from course_knowledge_base import _find_relation_cycle  # noqa: E402

# 与 `validate_course_knowledge_base` 里的字面量保持一致
# （`course_knowledge_base.py:898`，那里写死了这两类，没有具名常量）。
# 若将来校验层改了这个集合，这里必须同步，否则统计口径会与校验层脱节。
ACYCLIC_RELATION_TYPES = ("prerequisite", "generalizes")


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
        "~/lingzhi/backend/data/courses"
    )
    paths = sorted(glob.glob(os.path.join(root, "*.json")))
    if not paths:
        print(f"没有找到课程文件：{root}")
        return 2

    scanned = with_kb = 0
    cyclic: list[tuple[str, str, int, list[str]]] = []
    clean: list[tuple[str, int]] = []

    # 目录里同时有 `<id>.json`（主文件）与 `<id>.vN.json`（历史版本）。
    # 按 course_id 归组：有主文件用主文件，否则退回该 id 版本号最大的那个
    # ——有些课程**只有** .vN 文件，一律跳过 .vN 会把它们整门漏掉。
    by_id: dict[str, str] = {}
    for path in paths:
        stem = os.path.basename(path)[: -len(".json")]
        if ".v" in stem:
            cid, _, ver = stem.rpartition(".v")
            if not ver.isdigit():
                continue
            key = ("v", int(ver))
        else:
            cid, key = stem, ("main", 0)
        prev = by_id.get(cid)
        if prev is None:
            by_id[cid] = path
            continue
        prev_stem = os.path.basename(prev)[: -len(".json")]
        prev_key = ("main", 0) if ".v" not in prev_stem else (
            "v", int(prev_stem.rpartition(".v")[2] or 0)
        )
        # 主文件优先；都是版本文件时取版本号最大的。
        if prev_key[0] == "v" and (key[0] == "main" or key[1] > prev_key[1]):
            by_id[cid] = path

    for path in sorted(by_id.values()):
        scanned += 1
        try:
            with open(path, encoding="utf-8") as handle:
                course = json.load(handle)
        except Exception:
            continue

        kb = course.get("course_knowledge_base") or {}
        relations = kb.get("relations") or []
        if not relations:
            continue
        with_kb += 1
        name = str(course.get("course_name") or stem)[:24]

        found = False
        for relation_type in ACYCLIC_RELATION_TYPES:
            cycle = _find_relation_cycle(relations, relation_type)
            if cycle:
                cyclic.append((name, relation_type, len(relations), cycle))
                found = True
        if not found:
            clean.append((name, len(relations)))

    print(f"扫描课程文件 {scanned} 个，其中有编译知识库且含关系的 {with_kb} 门\n")
    print(f"=== 成环课程：{len(cyclic)} 门 ===")
    for name, rtype, total, cycle in cyclic:
        chain = " -> ".join(node[:16] for node in cycle[:5])
        more = " ..." if len(cycle) > 5 else ""
        print(f"  [{name}] {rtype} 成环（该课共 {total} 条关系）")
        print(f"      环: {chain}{more}")

    print(f"\n=== 无环课程：{len(clean)} 门 ===")
    for name, total in clean:
        print(f"  [{name}] {total} 条关系")

    if with_kb:
        rate = len(cyclic) / with_kb
        print(f"\n成环占比：{len(cyclic)}/{with_kb} = {rate:.0%}")
        print(
            "→ 建议直接升 critical（成环是少数，顺手修掉即可）"
            if rate <= 0.2
            else "→ 建议先修存量或设迁移期（成环普遍，直接升会大面积转红）"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
