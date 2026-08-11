"""Deterministic teaching-plan impact analysis and downstream source state.

This module is read-only analysis. It resolves which downstream objects a
teaching-plan change touches, and which ones stay untouched, from the course's
own knowledge base, knowledge bindings and teaching-representation registry.
It never rewrites the official plan, course document, practice or slide decks;
the actual rebuild is started by the course/representation pipelines.

Two guarantees drive the design:

1. Impact is computed from explicit references, not from a model guess. When a
   course has no compiled knowledge base the analysis degrades to the
   conservative section-wide answer and says so, instead of inventing a
   narrower blast radius.
2. A failed rebuild never costs the teacher the last usable artifact. The
   downstream state always carries `last_available` for anything that was
   readable before, so old body text, practice and slide decks stay readable.
"""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

IMPACT_REPORT_SCHEMA = "teaching_plan_impact_report_v1"
DOWNSTREAM_STATE_SCHEMA = "teaching_plan_downstream_state_v1"

IMPACT_GROUPS = ("changed", "needs_regeneration", "stale", "unchanged", "blocked")

# Downstream lifecycle for objects derived from the official teaching plan.
DOWNSTREAM_STATES = (
    "current",          # 来源修订一致，无需处理
    "candidate",        # 已生成重建候选，等待教师选择
    "rebuild_required", # 待重建：来源已变，旧产物继续可读
    "lock_conflict",    # 锁定冲突：其他链路正在写，同一对象不重复重建
    "blocked",          # 影响不可判定，禁止静默重建
)

CHANGE_CATEGORIES = (
    "descriptive",   # 描述性变更
    "objective",     # 目标变更
    "module",        # 模块变更
    "knowledge",     # 知识变更
    "relation",      # 关系变更
    "chapter",       # 章节变更
    "classroom",     # 课堂执行约束
    "unknown",
)

_SECTION_CLASSROOM_LIST_FIELDS = {
    "key_difficulties",
    "teacher_activities",
    "student_activities",
    "resource_refs",
    "in_class_checks",
    "homework",
    "teaching_notes",
}

_DESCRIPTIVE_OVERALL_PATHS = {
    "overall/positioning",
    "overall/target_audience",
    "overall/teaching_strategy/rationale",
    "overall/academic_term",
    "overall/class_size",
    "overall/class_profile",
    "overall/teaching_preparation",
    "overall/course_assessment_plan",
}
_CLASSROOM_OVERALL_PATHS = {
    "overall/total_class_hours",
    "overall/lesson_duration_minutes",
    "overall/teaching_context",
}
_OBJECTIVE_OVERALL_PATHS = {
    "overall/learning_objectives",
    "overall/prerequisites",
}

# KnowledgeBinding.target_type -> the downstream object type shown to teachers.
_BINDING_TARGET_TYPES = {
    "course_block": "section_content",
    "question": "practice",
    "criterion": "mastery_criterion",
    "objective": "learning_objective",
    "section": "knowledge_binding",
}

# Representation types that must keep their last usable version on failure.
_READABLE_REPRESENTATION_TYPES = {
    "slide_deck",
    "handout",
    "practice_sheet",
    "lesson_plan",
    "outline",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_name(value: Any) -> str:
    return re.sub(r"[^0-9a-z一-鿿]+", "", str(value or "").lower())


def _course_sections(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    course_plan = snapshot.get("course_plan")
    if not isinstance(course_plan, dict):
        return []
    return [
        section
        for chapter in course_plan.get("chapters") or []
        if isinstance(chapter, dict)
        for section in chapter.get("sections") or []
        if isinstance(section, dict)
    ]


def change_category(path: str) -> str:
    """Classify one changed field path into the六类变更 of the impact matrix."""
    normalized = _text(path).strip("/")
    parts = normalized.split("/")
    if normalized in _DESCRIPTIVE_OVERALL_PATHS:
        return "descriptive"
    if normalized in _CLASSROOM_OVERALL_PATHS:
        return "classroom"
    if normalized in _OBJECTIVE_OVERALL_PATHS:
        return "objective"
    if "chapter" in normalized or "outline" in normalized:
        return "chapter"
    if len(parts) >= 3 and parts[0] == "sections":
        field = parts[2]
        if field == "learning_objective":
            return "objective"
        if field == "teaching_modules":
            return "module"
        if field == "knowledge":
            return "knowledge"
        if field in {"key_points", "knowledge_relations", "reused_knowledge_names"}:
            return "relation"
        if field == "planned_minutes" or field in _SECTION_CLASSROOM_LIST_FIELDS:
            return "classroom"
    return "unknown"


class KnowledgeReferenceIndex:
    """Reverse lookup from a plan knowledge point to everything that cites it.

    Built from the course's own `course_knowledge_base`: knowledge points carry
    stable `knowledge_id`s and `section_refs`, and `bindings` record which
    course block, question, mastery criterion or objective consumes them. When
    the course has no compiled knowledge base the index reports `available =
    False` so callers keep the conservative section-wide answer.
    """

    def __init__(self, knowledge_base: dict[str, Any] | None) -> None:
        self.available = bool(
            isinstance(knowledge_base, dict)
            and knowledge_base.get("knowledge_points")
            and knowledge_base.get("bindings")
        )
        self._by_section_name: dict[tuple[str, str], str] = {}
        self._bindings_by_knowledge: dict[str, list[dict[str, Any]]] = {}
        self._name_by_knowledge: dict[str, str] = {}
        if not self.available or not isinstance(knowledge_base, dict):
            return
        for point in knowledge_base.get("knowledge_points") or []:
            if not isinstance(point, dict):
                continue
            knowledge_id = _text(point.get("knowledge_id"))
            if not knowledge_id:
                continue
            self._name_by_knowledge[knowledge_id] = _text(point.get("name"))
            names = {_normalize_name(point.get("name"))}
            names.update(_normalize_name(alias) for alias in point.get("aliases") or [])
            for section_id in point.get("section_refs") or []:
                for name in names:
                    if name:
                        self._by_section_name[(_text(section_id), name)] = knowledge_id
        for binding in knowledge_base.get("bindings") or []:
            if not isinstance(binding, dict) or binding.get("status") == "retired":
                continue
            for knowledge_id in binding.get("knowledge_ids") or []:
                self._bindings_by_knowledge.setdefault(_text(knowledge_id), []).append(binding)

    def resolve(self, section_id: str, knowledge_name: str) -> str:
        """Return the stable knowledge_id for a plan knowledge point, or ''."""
        return self._by_section_name.get(
            (_text(section_id), _normalize_name(knowledge_name)), "",
        )

    def display_name(self, knowledge_id: str) -> str:
        return self._name_by_knowledge.get(_text(knowledge_id), "")

    def referencing_targets(self, knowledge_id: str) -> list[tuple[str, str]]:
        """Return sorted (object_type, object_id) pairs that cite this knowledge."""
        targets: set[tuple[str, str]] = set()
        for binding in self._bindings_by_knowledge.get(_text(knowledge_id), []):
            object_type = _BINDING_TARGET_TYPES.get(_text(binding.get("target_type")))
            target_id = _text(binding.get("target_id"))
            if object_type and target_id:
                targets.add((object_type, target_id))
        return sorted(targets)

    def sections_for_knowledge(self, knowledge_id: str) -> list[str]:
        sections = {
            _text(binding.get("target_id"))
            for binding in self._bindings_by_knowledge.get(_text(knowledge_id), [])
            if _text(binding.get("target_type")) == "section"
        }
        return sorted(item for item in sections if item)


def _blocks_by_section(course_data: dict[str, Any] | None) -> dict[str, str]:
    """Map course block id -> owning section id from the canonical document."""
    document = (course_data or {}).get("course_document")
    if not isinstance(document, dict):
        return {}
    return {
        _text(block.get("block_id")): _text(block.get("section_id"))
        for block in document.get("blocks") or []
        if isinstance(block, dict) and _text(block.get("block_id"))
    }


def _knowledge_impact(
    *,
    section_id: str,
    knowledge_name: str,
    index: KnowledgeReferenceIndex,
    course_data: dict[str, Any] | None,
    reason: str,
) -> list[dict[str, Any]]:
    """Local impact preview for one knowledge point via its explicit bindings."""
    knowledge_id = index.resolve(section_id, knowledge_name) if index.available else ""
    if not knowledge_id:
        # No stable binding: stay conservative and say why, rather than
        # pretending the change is narrower than we can prove.
        return [
            {
                "group": "needs_regeneration",
                "type": item_type,
                "id": section_id,
                "reason": f"{reason}（该课程尚无稳定知识绑定，按整节保守失效）",
                "resolution": "section_fallback",
            }
            for item_type in ("knowledge_binding", "section_content", "practice", "slide_deck")
        ]

    outcome: list[dict[str, Any]] = [{
        "group": "needs_regeneration",
        "type": "knowledge_binding",
        "id": knowledge_id,
        "reason": reason,
        "resolution": "knowledge_binding",
        "knowledge_id": knowledge_id,
    }]
    block_sections = _blocks_by_section(course_data)
    touched_sections: set[str] = {section_id}
    for object_type, object_id in index.referencing_targets(knowledge_id):
        if object_type == "knowledge_binding":
            touched_sections.add(object_id)
            continue
        item: dict[str, Any] = {
            "group": "needs_regeneration",
            "type": object_type,
            "id": object_id,
            "reason": reason,
            "resolution": "knowledge_reference",
            "knowledge_id": knowledge_id,
        }
        if object_type == "section_content":
            owning = block_sections.get(object_id)
            if owning:
                item["section_id"] = owning
                touched_sections.add(owning)
        outcome.append(item)

    # Slide decks and handouts are section-scoped derivations, so they follow
    # the sections that actually cite the knowledge point.
    for touched in sorted(touched_sections):
        outcome.append({
            "group": "needs_regeneration",
            "type": "slide_deck",
            "id": touched,
            "reason": reason,
            "resolution": "knowledge_reference",
            "knowledge_id": knowledge_id,
            "section_id": touched,
        })
    return outcome


def impact_for_operation(
    operation: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    course_data: dict[str, Any] | None = None,
    index: KnowledgeReferenceIndex | None = None,
) -> list[dict[str, Any]]:
    """Deterministic impact of one changed field path."""
    path = _text(operation.get("path")).strip("/")
    parts = path.split("/") if path else []
    category = change_category(path)
    reference_index = index if index is not None else KnowledgeReferenceIndex(
        (course_data or {}).get("course_knowledge_base"),
    )
    outcome: list[dict[str, Any]] = []

    def add(group: str, item_type: str, item_id: str, reason: str, **extra: Any) -> None:
        outcome.append({
            "group": group,
            "type": item_type,
            "id": item_id,
            "reason": reason,
            **extra,
        })

    if category == "chapter":
        # 章节增删与排序回到目录真源；教案链路不得静默改写全课结构。
        add(
            "blocked",
            "course_outline",
            path or "outline",
            "章节增删与排序必须回到目录编辑器，不能在教案工作台绕过目录真源。",
            redirect="redirect_to_outline_edit",
        )
        return outcome

    if path in _DESCRIPTIVE_OVERALL_PATHS:
        add("changed", "teaching_plan", "overall", "总体教学设计已更新")
        add("changed", "teacher_projection", "overall", "教师阅读投影需要同步")
        return outcome

    if path in _CLASSROOM_OVERALL_PATHS:
        add("changed", "teaching_plan", "overall", "课堂执行约束已更新")
        for section in _course_sections(snapshot):
            section_id = _text(section.get("node_id"))
            if section_id:
                add(
                    "needs_regeneration",
                    "teaching_representation",
                    section_id,
                    "课堂时间或场景变化",
                )
        return outcome

    if path in _OBJECTIVE_OVERALL_PATHS:
        add("changed", "teaching_plan", "overall", "总体教学设计已更新")
        for section in _course_sections(snapshot):
            section_id = _text(section.get("node_id"))
            if section_id:
                add(
                    "needs_regeneration",
                    "section_content",
                    section_id,
                    "总体目标或前置要求变化",
                )
        return outcome

    if len(parts) >= 2 and parts[0] == "sections":
        section_id = parts[1]
        add("changed", "teaching_plan_section", section_id, "小节教案已更新")
        field = parts[2] if len(parts) >= 3 else ""

        if field == "learning_objective":
            for item_type in ("section_content", "practice", "slide_deck"):
                add("needs_regeneration", item_type, section_id, "小节目标变化")
        elif field == "key_points":
            # 知识范围（首次负责/复用）变化属于关系变更：必须审阅，不静默应用。
            add(
                "needs_regeneration",
                "knowledge_binding",
                section_id,
                "知识范围变化需要重新编译绑定",
            )
            for item_type in ("section_content", "practice", "slide_deck"):
                add("needs_regeneration", item_type, section_id, "知识范围变化")
        elif field in {"knowledge_relations", "reused_knowledge_names"}:
            add(
                "blocked",
                "knowledge_relation",
                section_id,
                "知识关系变化会改变依赖闭包，必须先完成关系审阅再应用。",
                requires_review=True,
            )
        elif field == "teaching_modules":
            for item_type in ("section_content", "lecture", "slide_deck"):
                add("needs_regeneration", item_type, section_id, "教学环节职责变化")
        elif field == "knowledge":
            knowledge_name = parts[3] if len(parts) >= 4 else ""
            outcome.extend(_knowledge_impact(
                section_id=section_id,
                knowledge_name=knowledge_name,
                index=reference_index,
                course_data=course_data,
                reason="知识语义变化",
            ))
        elif field == "planned_minutes":
            for item_type in ("lecture", "slide_deck"):
                add("needs_regeneration", item_type, section_id, "小节课堂时长变化")
        elif field in _SECTION_CLASSROOM_LIST_FIELDS:
            for item_type in ("lecture", "slide_deck"):
                add("needs_regeneration", item_type, section_id, "小节课堂执行安排变化")
        return outcome

    add("blocked", "unknown", path or "unknown", "无法确定字段的教学语义与影响范围")
    return outcome


def _unchanged_sections(
    snapshot: dict[str, Any],
    touched_section_ids: set[str],
) -> list[dict[str, Any]]:
    """Sections that provably keep their current derivations."""
    items = []
    for section in _course_sections(snapshot):
        section_id = _text(section.get("node_id"))
        if section_id and section_id not in touched_section_ids:
            items.append({
                "type": "section_content",
                "id": section_id,
                "reason": "该小节没有被本次教案变更引用，沿用原修订。",
            })
    return items


def build_impact_report(
    operations: list[dict[str, Any]],
    snapshot: dict[str, Any],
    *,
    course_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Group the deterministic impact of a change set for teacher review."""
    groups: dict[str, list[dict[str, Any]]] = {group: [] for group in IMPACT_GROUPS}
    index = KnowledgeReferenceIndex((course_data or {}).get("course_knowledge_base"))
    seen: set[tuple[str, str, str]] = set()
    categories: set[str] = set()
    touched_sections: set[str] = set()

    for operation in operations or []:
        path = _text(operation.get("path")).strip("/")
        categories.add(change_category(path))
        parts = path.split("/") if path else []
        if len(parts) >= 2 and parts[0] == "sections":
            touched_sections.add(parts[1])
        for item in impact_for_operation(
            operation, snapshot, course_data=course_data, index=index,
        ):
            key = (item["group"], item["type"], item["id"])
            if key in seen:
                continue
            seen.add(key)
            groups[item["group"]].append(item)
            if item.get("section_id"):
                touched_sections.add(_text(item["section_id"]))
            if item["type"] in {"section_content", "slide_deck", "lecture"}:
                touched_sections.add(_text(item["id"]))

    if not operations:
        groups["unchanged"].append({
            "type": "teaching_plan",
            "id": "current",
            "reason": "草稿尚未包含修改。",
        })
    else:
        # A full-course change (总体目标/课堂约束) touches every section, so this
        # only reports the sections we can positively prove stay unchanged.
        groups["unchanged"].extend(_unchanged_sections(snapshot, touched_sections))

    return {
        "schema_version": IMPACT_REPORT_SCHEMA,
        **groups,
        "blocking": bool(groups["blocked"]),
        "change_categories": sorted(categories - {"unknown"}) or sorted(categories),
        "knowledge_index_available": index.available,
    }


def _representation_items(registry: Any) -> list[dict[str, Any]]:
    """Normalize a representation registry (model or dict) to plain rows."""
    if registry is None:
        return []
    payload = registry
    if hasattr(registry, "model_dump"):
        payload = registry.model_dump(mode="json")
    if not isinstance(payload, dict):
        return []
    rows = []
    for item in payload.get("representations") or []:
        if not isinstance(item, dict):
            continue
        rows.append(item)
    return rows


def _objective_revisions(course_data: dict[str, Any]) -> dict[str, str]:
    """Current objective_id -> objective_revision_id for the course's sections.

    Reuses the canonical `learning_objective_identity` so the expected revision
    is computed exactly the way the asset pipeline computed the recorded one.
    """
    # Imported locally: learning_progress pulls in the learning-event and
    # practice-attempt repositories, which this read-only analysis never needs.
    from learning_progress import learning_objective_identity

    course_id = _text(course_data.get("course_id"))
    revisions: dict[str, str] = {}
    nodes = [
        node for node in course_data.get("nodes") or []
        if isinstance(node, dict)
    ]
    if not nodes:
        # Canonical courses keep sections on the document rather than `nodes`.
        document = course_data.get("course_document")
        if isinstance(document, dict):
            nodes = [
                {
                    "node_id": section.get("section_id"),
                    "node_name": section.get("title"),
                    "learning_objective": section.get("learning_objective"),
                }
                for section in document.get("sections") or []
                if isinstance(section, dict)
            ]
    for node in nodes:
        identity = learning_objective_identity(course_id, node)
        revisions[identity["objective_id"]] = identity["objective_revision_id"]
    return revisions


def downstream_source_check(
    *,
    plan_revision_id: str,
    course_data: dict[str, Any] | None = None,
    registry: Any = None,
) -> list[dict[str, Any]]:
    """Compare每个下游产物记录的来源修订与当前正式教案修订.

    Covers CourseDocument/课程块 (via the course envelope), 正式练习 and
    SlideDeckSpec/讲义/TeachingRepresentation (via the registry). Returns one row
    per downstream object with `source_state` of `current` or `stale`.
    """
    plan_revision_id = _text(plan_revision_id)
    rows: list[dict[str, Any]] = []
    course = course_data or {}

    document = course.get("course_document")
    if isinstance(document, dict):
        document_revision = _text(
            course.get("course_document_revision") or document.get("document_revision"),
        )
        recorded = _text(
            (course.get("course_revision_vector") or {})
            .get("revisions", {})
            .get("course_teaching_plan"),
        )
        rows.append({
            "type": "course_document",
            "id": _text(document.get("course_id")) or "course_document",
            "revision": document_revision,
            "recorded_plan_revision_id": recorded,
            "source_state": "current" if recorded == plan_revision_id else "stale",
            "readable": True,
        })
        for block in document.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            block_id = _text(block.get("block_id"))
            if not block_id:
                continue
            rows.append({
                "type": "section_content",
                "id": block_id,
                "section_id": _text(block.get("section_id")),
                "revision": _text(block.get("internal_revision")),
                "recorded_plan_revision_id": recorded,
                "source_state": "current" if recorded == plan_revision_id else "stale",
                "readable": _text(block.get("status")) != "retired",
            })

    assets = course.get("learning_assets")
    if isinstance(assets, dict):
        # 练习没有"来源教案修订"字段，但每道题都记了它所服务目标的
        # objective_revision_id，而该值是目标陈述的稳定 hash。教师改小节目标
        # 后当前目标身份会变，旧题记录的修订就对不上 —— 这是练习真实可用的
        # 失效信号，比读一个没有生产者写入的字段可靠。
        current_objective_revisions = _objective_revisions(course)
        for question in (assets.get("assets") or {}).get("questions") or []:
            if not isinstance(question, dict):
                continue
            question_id = _text(question.get("question_id") or question.get("asset_id"))
            if not question_id:
                continue
            recorded_objective = _text(question.get("objective_revision_id"))
            expected_objective = current_objective_revisions.get(
                _text(question.get("objective_id")),
            )
            if not recorded_objective or expected_objective is None:
                # 无法证明新鲜度时保守判为 stale，并说明原因。
                source_state = "stale"
                basis = "objective_revision_unavailable"
            elif recorded_objective == expected_objective:
                source_state = "current"
                basis = "objective_revision"
            else:
                source_state = "stale"
                basis = "objective_revision"
            rows.append({
                "type": "practice",
                "id": question_id,
                "section_id": _text(question.get("node_id")),
                "revision": recorded_objective,
                "recorded_plan_revision_id": "",
                "source_state": source_state,
                "source_basis": basis,
                "readable": True,
            })

    for representation in _representation_items(registry):
        recorded = _text(
            (representation.get("source_revision_vector") or {}).get("course_teaching_plan"),
        )
        status = _text(representation.get("status"))
        rows.append({
            "type": _text(representation.get("representation_type")) or "teaching_representation",
            "id": _text(representation.get("representation_id")),
            "variant_key": _text(representation.get("variant_key")),
            "revision": _text(representation.get("revision")),
            "recorded_plan_revision_id": recorded,
            "source_state": (
                "current"
                if recorded == plan_revision_id and status not in {"stale", "failed"}
                else "stale"
            ),
            # A stale or failed rebuild must never hide the artifact the teacher
            # already had; only an archived object stops being readable.
            "readable": status != "archived" and bool(representation.get("artifact_ids") or status in {
                "ready", "stale", "failed",
            }),
            "representation_status": status,
        })

    return sorted(rows, key=lambda row: (row["type"], row["id"]))


def _last_available_for(
    row: dict[str, Any] | None,
    previous_item: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Keep whatever version was readable before the new build was attempted."""
    if isinstance(previous_item, dict) and isinstance(previous_item.get("last_available"), dict):
        # Once recorded, the last usable version is never downgraded by a
        # subsequent failure — that is the product promise behind 3.6.
        return deepcopy(previous_item["last_available"])
    if isinstance(row, dict) and row.get("readable"):
        return {
            "type": row.get("type"),
            "id": row.get("id"),
            "revision": row.get("revision"),
            "variant_key": row.get("variant_key", ""),
            "readable": True,
        }
    return None


def build_downstream_state(
    impact_report: dict[str, Any],
    *,
    plan_revision_id: str,
    course_data: dict[str, Any] | None = None,
    registry: Any = None,
    previous: dict[str, Any] | None = None,
    locked_object_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Project the impact report onto下游候选/待重建/锁定冲突 states.

    The returned state is a read-only plan for the rebuild pipelines. Every item
    that was readable keeps `last_available`, so a failed rebuild downgrades the
    state but never the teacher's ability to open the old artifact.
    """
    locked = {_text(item) for item in locked_object_ids or [] if _text(item)}
    previous_items = {
        (_text(item.get("type")), _text(item.get("id"))): item
        for item in (previous or {}).get("items") or []
        if isinstance(item, dict)
    }
    source_rows = {
        (_text(row["type"]), _text(row["id"])): row
        for row in downstream_source_check(
            plan_revision_id=plan_revision_id,
            course_data=course_data,
            registry=registry,
        )
    }

    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for group in IMPACT_GROUPS:
        for entry in impact_report.get(group) or []:
            if not isinstance(entry, dict):
                continue
            item_type = _text(entry.get("type"))
            item_id = _text(entry.get("id"))
            key = (item_type, item_id)
            if key in seen:
                continue
            seen.add(key)
            row = source_rows.get(key)
            previous_item = previous_items.get(key)

            if group == "blocked":
                state = "blocked"
            elif item_id in locked or item_type in locked:
                state = "lock_conflict"
            elif group == "needs_regeneration":
                state = "rebuild_required"
            elif group == "changed":
                state = "current"
            elif group == "stale":
                state = "rebuild_required"
            else:
                state = "current"

            item = {
                "type": item_type,
                "id": item_id,
                "state": state,
                "impact_group": group,
                "reason": _text(entry.get("reason")),
                "last_available": _last_available_for(row, previous_item),
            }
            for optional in ("section_id", "knowledge_id", "resolution", "redirect"):
                if entry.get(optional):
                    item[optional] = entry[optional]
            if row is not None:
                item["source_state"] = row.get("source_state")
            if state == "lock_conflict":
                item["reason"] = (
                    f"{item['reason']}（该对象正在被其他链路重建，已保留最后可用版本）"
                ).strip("（）")
            items.append(item)

    # Downstream objects the impact report never named keep their old state and
    # stay readable; they are reported so the teacher sees the whole picture.
    for key, row in source_rows.items():
        if key in seen:
            continue
        previous_item = previous_items.get(key)
        items.append({
            "type": row["type"],
            "id": row["id"],
            "state": "current" if row.get("source_state") == "current" else "rebuild_required",
            "impact_group": "unchanged",
            "reason": (
                "未被本次教案变更引用，沿用原修订。"
                if row.get("source_state") == "current"
                else "来源修订早于当前正式教案，等待重建。"
            ),
            "last_available": _last_available_for(row, previous_item),
            "source_state": row.get("source_state"),
        })

    items.sort(key=lambda item: (item["type"], item["id"]))
    return {
        "schema_version": DOWNSTREAM_STATE_SCHEMA,
        "source_plan_revision_id": _text(plan_revision_id),
        "items": items,
        "counts": {
            state: sum(1 for item in items if item["state"] == state)
            for state in DOWNSTREAM_STATES
        },
        "readable_fallback_count": sum(
            1 for item in items if isinstance(item.get("last_available"), dict)
        ),
        "updated_at": _now(),
    }


def record_rebuild_outcome(
    downstream: dict[str, Any],
    *,
    object_type: str,
    object_id: str,
    outcome: str,
    revision: str = "",
    error: str = "",
) -> dict[str, Any]:
    """Fold one rebuild result into the downstream state.

    `outcome` is `succeeded`, `failed` or `candidate_ready`. A failure keeps the
    item in `rebuild_required` and preserves `last_available` untouched, so the
    old body text, practice or slide deck stays readable — a failed new artifact
    never overwrites a usable old one.
    """
    state = deepcopy(downstream or {})
    object_type = _text(object_type)
    object_id = _text(object_id)
    for item in state.get("items") or []:
        if _text(item.get("type")) != object_type or _text(item.get("id")) != object_id:
            continue
        if outcome == "succeeded":
            item["state"] = "current"
            item["reason"] = "已按当前正式教案重建。"
            item.pop("last_build_error", None)
            if revision:
                item["last_available"] = {
                    "type": object_type,
                    "id": object_id,
                    "revision": _text(revision),
                    "variant_key": (item.get("last_available") or {}).get("variant_key", ""),
                    "readable": True,
                }
        elif outcome == "candidate_ready":
            item["state"] = "candidate"
            item["reason"] = "已生成重建候选，等待教师确认。"
            if revision:
                item["candidate_revision"] = _text(revision)
        elif outcome == "failed":
            item["state"] = "rebuild_required"
            item["last_build_error"] = _text(error) or "重建失败"
            fallback = item.get("last_available")
            item["reason"] = (
                "新产物重建失败，已保留最后一个可用版本，教师仍可查看旧内容。"
                if isinstance(fallback, dict)
                else "新产物重建失败，且没有可回退的历史版本。"
            )
        else:
            raise ValueError(f"unsupported rebuild outcome: {outcome}")
        break
    state["counts"] = {
        value: sum(1 for item in state.get("items") or [] if item.get("state") == value)
        for value in DOWNSTREAM_STATES
    }
    state["readable_fallback_count"] = sum(
        1 for item in state.get("items") or []
        if isinstance(item.get("last_available"), dict)
    )
    state["updated_at"] = _now()
    return state


def impact_matrix_snapshot(impact_report: dict[str, Any]) -> dict[str, Any]:
    """Compact, stable projection of an impact report for snapshot tests.

    Deliberately drops reasons, revisions and timestamps: the regression值 is在
    "哪些对象进入哪一组"，而不是整棵对象树。
    """
    return {
        "categories": list(impact_report.get("change_categories") or []),
        "knowledge_index_available": bool(impact_report.get("knowledge_index_available")),
        "blocking": bool(impact_report.get("blocking")),
        "groups": {
            group: sorted(
                f"{_text(item.get('type'))}:{_text(item.get('id'))}"
                for item in impact_report.get(group) or []
                if isinstance(item, dict)
            )
            for group in IMPACT_GROUPS
            if impact_report.get(group)
        },
    }


def downstream_state_snapshot(downstream: dict[str, Any]) -> dict[str, Any]:
    """Compact, stable projection of a downstream state for snapshot tests."""
    return {
        "states": {
            f"{_text(item.get('type'))}:{_text(item.get('id'))}": _text(item.get("state"))
            for item in downstream.get("items") or []
        },
        "readable": sorted(
            f"{_text(item.get('type'))}:{_text(item.get('id'))}"
            for item in downstream.get("items") or []
            if isinstance(item.get("last_available"), dict)
        ),
    }


__all__ = [
    "CHANGE_CATEGORIES",
    "DOWNSTREAM_STATES",
    "DOWNSTREAM_STATE_SCHEMA",
    "IMPACT_GROUPS",
    "IMPACT_REPORT_SCHEMA",
    "KnowledgeReferenceIndex",
    "build_downstream_state",
    "build_impact_report",
    "change_category",
    "downstream_source_check",
    "downstream_state_snapshot",
    "impact_for_operation",
    "impact_matrix_snapshot",
    "record_rebuild_outcome",
]
