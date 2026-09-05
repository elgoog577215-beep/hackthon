"""把正式题目直接绑定到课程知识库里真实存在的知识点/能力点/易错点。

## 这个模块补的是哪一段（清单 G4）

`PUBLIC_QUESTION_FIELDS` 早就有 `concept_ids` / `skill_unit_ids` /
`mistake_point_ids` 三个绑定字段，但主生成链路从来没有真正写对过它们。

调查到的实况比"绑定是间接的"更糟——**绑定是悬空的**：

- 课程知识库里知识点的正式 ID 是 `ckp_…`
  （`course_knowledge_base._local_id(course_id, group_id, "knowledge_point", name, "ckp_")`），
  能力点 `cks_…`、易错点 `ckm_…`、掌握标准 `ckmc_…`；
- 而 `question_bank._node_knowledge_refs` 在小节没有自带 refs 时，会用
  `stable_hash({course, node, knowledge: name}, prefix="ck_")` **自己造一个 ID**。

`ck_…` 与 `ckp_…` 不是一个命名空间。于是题目上记的"知识点 ID"在知识库里
**根本查不到对应的知识点**。这直接导致：

- 回答不了"这道题考的是哪个知识点"（ID 查不到实体）；
- 做不了知识点级覆盖率统计（连接不上知识库的知识点集合）；
- 张老师要的"这一节讲清楚哪些知识点/能力点/易错点，并据此出题"没有落点。

## 边界

本模块**只读** `course_knowledge_base` 编译出的结果，不改它、不重新编译、
不自己定义任何知识 ID（知识库归 lz-knowledge 那条线）。解析不出来就如实返回
空并说明原因，由调用方决定是否退回旧的合成 ID——不猜、不造。
"""

from __future__ import annotations

from typing import Any

QUESTION_KNOWLEDGE_BINDING_SCHEMA = "question_knowledge_binding_v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in _as_list(value) if isinstance(item, dict)]


def course_knowledge_base_of(course_data: dict[str, Any]) -> dict[str, Any]:
    """取当前课程已编译的知识库，取不到返回空 dict。

    只认 `course_knowledge_base` 这一个位置。不去 `learning_assets` 里翻投影，
    也不触发重新编译——重新编译会产生第二份知识身份，正是要避免的。
    """
    bundle = (course_data or {}).get("course_knowledge_base")
    return bundle if isinstance(bundle, dict) else {}


def resolve_node_knowledge_binding(
    course_data: dict[str, Any],
    node_id: str,
) -> dict[str, Any]:
    """小节 -> 该小节真实的知识点/能力点/易错点/掌握标准 ID。

    走知识库自己记录的归属关系，不做名称模糊匹配：

    - 知识点：`section_refs` 含该 `node_id`；
    - 能力点/易错点：`primary_knowledge_id` 落在上面那批知识点里；
    - 掌握标准：`knowledge_ids` 与上面那批有交集（掌握标准是多对多）。

    `resolved` 为 False 表示这门课还没有可用知识库、或这一节没有任何知识点。
    调用方必须区分"解析出空"和"没解析"——前者是事实，后者不能当事实用。
    """
    target = _text(node_id)
    bundle = course_knowledge_base_of(course_data)
    if not target or not bundle:
        return _binding(
            resolved=False,
            reason=(
                "课程没有已编译的知识库"
                if not bundle
                else "缺少 node_id"
            ),
        )

    knowledge_ids: list[str] = []
    for point in _dicts(bundle.get("knowledge_points")):
        point_id = _text(point.get("knowledge_id"))
        if not point_id:
            continue
        section_refs = {_text(item) for item in _as_list(point.get("section_refs"))}
        if target in section_refs:
            knowledge_ids.append(point_id)
    knowledge_ids = _unique(knowledge_ids)
    if not knowledge_ids:
        return _binding(
            resolved=False,
            reason="知识库中没有归属该小节的知识点",
        )

    owned = set(knowledge_ids)
    skill_ids = _unique([
        _text(skill.get("skill_id"))
        for skill in _dicts(bundle.get("skill_units"))
        if _text(skill.get("skill_id"))
        and _text(skill.get("primary_knowledge_id")) in owned
    ])
    misconception_ids = _unique([
        _text(item.get("misconception_id"))
        for item in _dicts(bundle.get("misconceptions"))
        if _text(item.get("misconception_id"))
        and _text(item.get("primary_knowledge_id")) in owned
    ])
    mastery_ids = _unique([
        _text(item.get("criterion_id"))
        for item in _dicts(bundle.get("mastery_criteria"))
        if _text(item.get("criterion_id"))
        and owned.intersection(
            {_text(value) for value in _as_list(item.get("knowledge_ids"))}
        )
    ])
    return _binding(
        resolved=True,
        knowledge_ids=knowledge_ids,
        skill_ids=skill_ids,
        misconception_ids=misconception_ids,
        mastery_ids=mastery_ids,
    )


def _binding(
    *,
    resolved: bool,
    knowledge_ids: list[str] | None = None,
    skill_ids: list[str] | None = None,
    misconception_ids: list[str] | None = None,
    mastery_ids: list[str] | None = None,
    reason: str = "",
) -> dict[str, Any]:
    return {
        "schema_version": QUESTION_KNOWLEDGE_BINDING_SCHEMA,
        "resolved": bool(resolved),
        "knowledge_ids": list(knowledge_ids or []),
        "skill_ids": list(skill_ids or []),
        "misconception_ids": list(misconception_ids or []),
        "mastery_ids": list(mastery_ids or []),
        "reason": _text(reason),
    }


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def knowledge_point_coverage(
    course_data: dict[str, Any],
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """每个知识点被几道题覆盖（清单 G4 的验收物）。

    只统计知识库里真实存在的知识点，并且只认题目上能对上的 ID。题目引用了一个
    知识库里不存在的 ID 时计入 `dangling_refs` 而不是静默忽略——那正是 G4 之前
    的病灶（题上记着 `ck_…`，库里只有 `ckp_…`，两边都"看起来有绑定"）。
    """
    bundle = course_knowledge_base_of(course_data)
    points = {
        _text(point.get("knowledge_id")): point
        for point in _dicts(bundle.get("knowledge_points"))
        if _text(point.get("knowledge_id"))
    }
    counts = {point_id: 0 for point_id in points}
    dangling: dict[str, int] = {}
    unbound_items: list[str] = []

    for item in _dicts(items):
        refs = _unique([
            _text(value)
            for value in (
                _as_list(item.get("course_knowledge_refs"))
                or _as_list(item.get("concept_ids"))
            )
        ])
        matched = [ref for ref in refs if ref in counts]
        for ref in matched:
            counts[ref] += 1
        for ref in refs:
            if ref not in counts:
                dangling[ref] = dangling.get(ref, 0) + 1
        if not matched:
            identifier = _text(item.get("revision_id")) or _text(item.get("item_id"))
            if identifier:
                unbound_items.append(identifier)

    covered = [point_id for point_id, count in counts.items() if count > 0]
    return {
        "schema_version": "question_knowledge_coverage_v1",
        "knowledge_point_total": len(points),
        "covered_knowledge_point_count": len(covered),
        "uncovered_knowledge_ids": sorted(
            point_id for point_id, count in counts.items() if count == 0
        ),
        "questions_per_knowledge_id": dict(sorted(counts.items())),
        # 悬空引用：题上写了、库里没有。G4 之前主链路产出的全是这种。
        "dangling_refs": dict(sorted(dangling.items())),
        "items_without_knowledge_binding": sorted(unbound_items),
    }


__all__ = [
    "QUESTION_KNOWLEDGE_BINDING_SCHEMA",
    "course_knowledge_base_of",
    "knowledge_point_coverage",
    "resolve_node_knowledge_binding",
]
