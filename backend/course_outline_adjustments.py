"""Deterministic two-level course-outline editing and projection compilation."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable


ALLOWED_OPERATIONS = {"add_node", "remove_node", "move_node", "update_node"}

_CHAPTER_NUMBER_PREFIX = re.compile(
    r"^\s*第\s*[0-9一二三四五六七八九十百零〇两]+\s*章\s*[:：、.．\-]?\s*"
)
_SECTION_NUMBER_PREFIX = re.compile(
    r"^\s*\d+\s*[.．]\s*\d+\s*[:：、.．\-]?\s*"
)
_SEMANTIC_PUNCTUATION = re.compile(r"[\W_]+", re.UNICODE)
_RESPONSIBILITY_CONCEPTS = {
    "release": ("打包", "构建设置", "多平台", "发布", "构建发布"),
    "verification": ("调试", "测试验证", "验证流程", "缺陷修复", "消除致命bug"),
    "delivery": ("交付", "交付物", "可独立运行", "最终产物"),
}


class OutlineAdjustmentError(ValueError):
    """A proposal cannot be safely applied to the current outline."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def as_issue(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.details}


@dataclass
class _OutlineState:
    nodes: dict[str, dict[str, Any]]
    chapters: list[str]
    sections: dict[str, list[str]]


def apply_outline_operations(
    draft: dict[str, Any],
    operations: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Apply model operations, validate the final tree, and rebuild every projection."""
    source = deepcopy(draft)
    state = _state_from_nodes(source.get("nodes") or [])
    operation_list = [deepcopy(item) for item in operations]
    if not operation_list:
        raise OutlineAdjustmentError("operations_empty", "调整方案没有包含任何操作")

    touched: dict[str, set[str]] = {}
    for index, operation in enumerate(operation_list):
        if not isinstance(operation, dict):
            raise OutlineAdjustmentError(
                "operation_invalid",
                f"第 {index + 1} 个操作不是对象",
            )
        op = str(operation.get("op") or "").strip()
        if op not in ALLOWED_OPERATIONS:
            raise OutlineAdjustmentError(
                "operation_type_invalid",
                f"第 {index + 1} 个操作类型不受支持",
                details={"operation_index": index, "operation_type": op},
            )
        if op == "add_node":
            _add_node(state, operation)
        elif op == "remove_node":
            ref = _required_ref(operation, "node_ref")
            touched.setdefault(ref, set()).add("structure")
            _remove_node(state, ref)
        elif op == "move_node":
            ref = _required_ref(operation, "node_ref")
            touched.setdefault(ref, set()).add("structure")
            _move_node(state, ref, operation)
        else:
            ref = _required_ref(operation, "node_ref")
            categories = touched.setdefault(ref, set())
            if "node_name" in operation or "learning_objective" in operation:
                categories.add("semantic")
            if "prerequisite_refs" in operation:
                categories.add("dependency")
            _update_node(state, ref, operation)

    _validate_lock_changes(source.get("blueprint_locks") or {}, touched)
    ordered_refs = _validate_final_state(state)
    adjusted, id_map = _compile_draft(source, state, ordered_refs)
    return {
        "draft": adjusted,
        "id_map": id_map,
        "operations": operation_list,
        "constraint_report": _constraint_report(adjusted),
    }


def compile_outline_draft(draft: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize an already edited outline and rebuild its derived projections."""
    source = deepcopy(draft)
    state = _state_from_nodes(source.get("nodes") or [])
    ordered_refs = _validate_final_state(state)
    compiled, _ = _compile_draft(source, state, ordered_refs)
    return compiled


def describe_outline_diff(
    before: dict[str, Any],
    after: dict[str, Any],
    id_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return a user-facing structural diff without relying on canonical IDs alone."""
    old_nodes = {
        str(node.get("node_id") or ""): node
        for node in before.get("nodes") or []
        if isinstance(node, dict) and node.get("node_id")
    }
    new_nodes = {
        str(node.get("node_id") or ""): node
        for node in after.get("nodes") or []
        if isinstance(node, dict) and node.get("node_id")
    }
    mapping = id_map or {node_id: node_id for node_id in old_nodes}
    mapped_targets = {target for source, target in mapping.items() if source in old_nodes}
    inverse = {target: source for source, target in mapping.items() if source in old_nodes}

    added = [
        _diff_item(node, new_nodes)
        for node_id, node in new_nodes.items()
        if node_id not in mapped_targets
    ]
    removed = [
        _diff_item(node, old_nodes, old=True)
        for node_id, node in old_nodes.items()
        if node_id not in mapping
    ]
    moved: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []
    for new_id, old_id in inverse.items():
        old = old_nodes[old_id]
        new = new_nodes.get(new_id)
        if not new:
            continue
        old_position = _node_position(old_id, old_nodes)
        new_position = _node_position(new_id, new_nodes)
        old_parent = str(old.get("parent_node_id") or "")
        mapped_old_parent = mapping.get(old_parent, old_parent)
        if old_position != new_position or mapped_old_parent != new.get("parent_node_id"):
            moved.append({
                "node_id": new_id,
                "node_name": new.get("node_name") or old.get("node_name") or new_id,
                "old_position": old_position,
                "new_position": new_position,
            })
        changes: dict[str, Any] = {}
        for field in ("node_name", "learning_objective", "prerequisite_node_ids"):
            old_value = old.get(field)
            if field == "prerequisite_node_ids":
                old_value = [
                    mapping.get(str(item), str(item))
                    for item in old.get(field) or []
                ]
            if old_value != new.get(field):
                changes[field] = {"before": old_value, "after": new.get(field)}
        if changes:
            updated.append({
                "node_id": new_id,
                "node_name": new.get("node_name") or old.get("node_name") or new_id,
                "changes": changes,
            })
    return {
        "added": added,
        "removed": removed,
        "moved": moved,
        "updated": updated,
        "before": _shape(before),
        "after": _shape(after),
    }


def _state_from_nodes(nodes: list[dict[str, Any]]) -> _OutlineState:
    if not isinstance(nodes, list) or not nodes:
        raise OutlineAdjustmentError("outline_empty", "课程目录必须至少包含一个章节和一个小节")
    by_ref: dict[str, dict[str, Any]] = {}
    chapters: list[str] = []
    sections: dict[str, list[str]] = {}
    for raw in nodes:
        if not isinstance(raw, dict):
            raise OutlineAdjustmentError("node_invalid", "课程目录包含无效节点")
        ref = str(raw.get("node_id") or "").strip()
        if not ref or ref in by_ref:
            raise OutlineAdjustmentError("node_id_invalid", "课程目录节点 ID 缺失或重复")
        level = int(raw.get("node_level") or 0)
        if level not in (1, 2):
            raise OutlineAdjustmentError("node_level_invalid", "课程目录只支持章节和小节两层结构")
        node = deepcopy(raw)
        node["_ref"] = ref
        node["_prerequisite_refs"] = [
            str(item) for item in raw.get("prerequisite_node_ids") or [] if str(item)
        ]
        by_ref[ref] = node
        if level == 1:
            chapters.append(ref)
            sections[ref] = []
    for ref, node in by_ref.items():
        if int(node.get("node_level") or 0) != 2:
            continue
        parent = str(node.get("parent_node_id") or "").strip()
        if parent not in sections:
            raise OutlineAdjustmentError(
                "parent_invalid",
                f"小节 {ref} 必须属于一个有效章节",
                details={"node_ref": ref, "parent_ref": parent},
            )
        sections[parent].append(ref)
    return _OutlineState(nodes=by_ref, chapters=chapters, sections=sections)


def _add_node(state: _OutlineState, operation: dict[str, Any]) -> None:
    ref = _required_ref(operation, "temp_ref")
    if ref in state.nodes:
        raise OutlineAdjustmentError("temporary_ref_duplicate", f"临时引用 {ref} 已存在")
    level = int(operation.get("node_level") or 0)
    if level not in (1, 2):
        raise OutlineAdjustmentError("node_level_invalid", "新增节点只能是章节或小节")
    name = str(operation.get("node_name") or "").strip()
    objective = str(operation.get("learning_objective") or "").strip()
    if not name or not objective:
        raise OutlineAdjustmentError("node_content_missing", "新增节点必须包含名称和学习目标")
    node = {
        "_ref": ref,
        "_prerequisite_refs": [
            str(item) for item in operation.get("prerequisite_refs") or [] if str(item)
        ],
        "node_id": ref,
        "node_level": level,
        "node_name": name,
        "learning_objective": objective,
        "prerequisite_node_ids": [],
    }
    for field in ("scope_boundary", "assessment", "learning_path_role", "path_reason"):
        if field in operation:
            node[field] = deepcopy(operation[field])
    state.nodes[ref] = node
    after_ref = _optional_ref(operation.get("after_ref"))
    if level == 1:
        parent = _optional_ref(operation.get("parent_ref"))
        if parent not in (None, "root"):
            raise OutlineAdjustmentError("parent_invalid", "章节只能位于课程根节点下")
        node["parent_node_id"] = "root"
        state.sections[ref] = []
        _insert_after(state.chapters, ref, after_ref, level=1)
        return
    parent = _required_ref(operation, "parent_ref")
    if parent not in state.sections:
        raise OutlineAdjustmentError("parent_invalid", f"新增小节的章节 {parent} 不存在")
    node["parent_node_id"] = parent
    _insert_after(state.sections[parent], ref, after_ref, level=2)


def _remove_node(state: _OutlineState, ref: str) -> None:
    node = _known_node(state, ref)
    if int(node.get("node_level") or 0) == 1:
        if state.sections.get(ref):
            raise OutlineAdjustmentError(
                "chapter_not_empty",
                f"章节“{node.get('node_name') or ref}”仍包含小节，不能直接删除",
                details={"node_ref": ref},
            )
        state.chapters.remove(ref)
        state.sections.pop(ref, None)
    else:
        parent = str(node.get("parent_node_id") or "")
        state.sections[parent].remove(ref)
    state.nodes.pop(ref, None)


def _move_node(state: _OutlineState, ref: str, operation: dict[str, Any]) -> None:
    node = _known_node(state, ref)
    after_ref = _optional_ref(operation.get("after_ref"))
    level = int(node.get("node_level") or 0)
    if level == 1:
        parent = _optional_ref(operation.get("parent_ref"))
        if parent not in (None, "root"):
            raise OutlineAdjustmentError("parent_invalid", "章节只能在课程根节点下排序")
        state.chapters.remove(ref)
        _insert_after(state.chapters, ref, after_ref, level=1)
        node["parent_node_id"] = "root"
        return
    old_parent = str(node.get("parent_node_id") or "")
    parent = _required_ref(operation, "parent_ref")
    if parent not in state.sections:
        raise OutlineAdjustmentError("parent_invalid", f"目标章节 {parent} 不存在")
    state.sections[old_parent].remove(ref)
    _insert_after(state.sections[parent], ref, after_ref, level=2)
    node["parent_node_id"] = parent


def _update_node(state: _OutlineState, ref: str, operation: dict[str, Any]) -> None:
    node = _known_node(state, ref)
    allowed = {"op", "node_ref", "node_name", "learning_objective", "prerequisite_refs"}
    unexpected = set(operation) - allowed
    if unexpected:
        raise OutlineAdjustmentError(
            "update_field_invalid",
            "目录节点只允许修改名称、学习目标和前置依赖",
            details={"fields": sorted(unexpected)},
        )
    for field in ("node_name", "learning_objective"):
        if field in operation:
            value = str(operation.get(field) or "").strip()
            if not value:
                raise OutlineAdjustmentError("node_content_missing", f"{field} 不能为空")
            node[field] = value
    if "prerequisite_refs" in operation:
        if int(node.get("node_level") or 0) == 1 and operation.get("prerequisite_refs"):
            raise OutlineAdjustmentError("chapter_dependency_invalid", "章节不能设置小节前置依赖")
        node["_prerequisite_refs"] = [
            str(item) for item in operation.get("prerequisite_refs") or [] if str(item)
        ]


def _insert_after(items: list[str], ref: str, after_ref: str | None, *, level: int) -> None:
    if after_ref is None:
        items.insert(0, ref)
        return
    if after_ref == ref or after_ref not in items:
        label = "章节" if level == 1 else "同章小节"
        raise OutlineAdjustmentError(
            "position_invalid",
            f"插入位置必须引用一个现有{label}",
            details={"after_ref": after_ref},
        )
    items.insert(items.index(after_ref) + 1, ref)


def _validate_final_state(state: _OutlineState) -> list[str]:
    if not state.chapters:
        raise OutlineAdjustmentError("outline_empty", "课程目录至少需要一个章节")
    ordered: list[str] = []
    for chapter in state.chapters:
        children = state.sections.get(chapter) or []
        if not children:
            raise OutlineAdjustmentError(
                "chapter_empty",
                f"章节“{state.nodes[chapter].get('node_name') or chapter}”至少需要一个小节",
                details={"node_ref": chapter},
            )
        ordered.append(chapter)
        ordered.extend(children)

    positions = {ref: index for index, ref in enumerate(ordered)}
    graph: dict[str, list[str]] = {}
    for ref in ordered:
        node = state.nodes[ref]
        dependencies = list(dict.fromkeys(node.get("_prerequisite_refs") or []))
        graph[ref] = dependencies
        for dependency in dependencies:
            if dependency not in state.nodes:
                raise OutlineAdjustmentError(
                    "dependency_target_missing",
                    f"节点“{node.get('node_name') or ref}”的前置节点已不存在",
                    details={"node_ref": ref, "dependency_ref": dependency},
                )
            if int(state.nodes[dependency].get("node_level") or 0) != 2:
                raise OutlineAdjustmentError(
                    "dependency_level_invalid",
                    "前置依赖只能指向小节",
                    details={"node_ref": ref, "dependency_ref": dependency},
                )
    _ensure_dependency_acyclic(graph)
    for ref, dependencies in graph.items():
        for dependency in dependencies:
            if positions[dependency] >= positions[ref]:
                raise OutlineAdjustmentError(
                    "dependency_points_forward",
                    f"节点“{state.nodes[ref].get('node_name') or ref}”不能依赖后序节点",
                    details={"node_ref": ref, "dependency_ref": dependency},
                )
    _validate_sibling_semantic_duplicates(state)
    return ordered


def _validate_sibling_semantic_duplicates(state: _OutlineState) -> None:
    for chapter_ref in state.chapters:
        section_refs = state.sections.get(chapter_ref) or []
        for index, left_ref in enumerate(section_refs):
            for right_ref in section_refs[index + 1:]:
                left = state.nodes[left_ref]
                right = state.nodes[right_ref]
                if not _sections_semantically_duplicate(left, right):
                    continue
                left_name = str(left.get("node_name") or left_ref)
                right_name = str(right.get("node_name") or right_ref)
                raise OutlineAdjustmentError(
                    "semantic_duplicate_sections",
                    f"同一章节中的“{left_name}”与“{right_name}”职责重复，请合并或删除其一",
                    details={
                        "chapter_ref": chapter_ref,
                        "node_refs": [left_ref, right_ref],
                        "node_names": [left_name, right_name],
                    },
                )


def _sections_semantically_duplicate(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_title = _normalize_semantic_text(str(left.get("node_name") or ""), level=2)
    right_title = _normalize_semantic_text(str(right.get("node_name") or ""), level=2)
    left_objective = _normalize_semantic_text(str(left.get("learning_objective") or ""))
    right_objective = _normalize_semantic_text(str(right.get("learning_objective") or ""))
    if left_title and left_title == right_title:
        return True
    if min(len(left_objective), len(right_objective)) >= 12:
        if SequenceMatcher(None, left_objective, right_objective).ratio() >= 0.82:
            return True
    left_concepts = _responsibility_concepts(f"{left_title}{left_objective}")
    right_concepts = _responsibility_concepts(f"{right_title}{right_objective}")
    return len(left_concepts & right_concepts) >= 3


def _normalize_semantic_text(value: str, *, level: int | None = None) -> str:
    text = value.strip().lower()
    if level == 1:
        text = _CHAPTER_NUMBER_PREFIX.sub("", text, count=1)
    elif level == 2:
        text = _SECTION_NUMBER_PREFIX.sub("", text, count=1)
    return _SEMANTIC_PUNCTUATION.sub("", text)


def _responsibility_concepts(value: str) -> set[str]:
    normalized = value.lower()
    return {
        concept
        for concept, markers in _RESPONSIBILITY_CONCEPTS.items()
        if any(marker in normalized for marker in markers)
    }


def _ensure_dependency_acyclic(graph: dict[str, list[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(ref: str) -> None:
        if ref in visiting:
            raise OutlineAdjustmentError("dependency_cycle", "课程目录的前置依赖形成循环")
        if ref in visited:
            return
        visiting.add(ref)
        for dependency in graph.get(ref, []):
            visit(dependency)
        visiting.remove(ref)
        visited.add(ref)

    for ref in graph:
        visit(ref)


def _validate_lock_changes(locks: dict[str, Any], touched: dict[str, set[str]]) -> None:
    for ref, categories in touched.items():
        node_locks = locks.get(ref) or {}
        if not isinstance(node_locks, dict):
            continue
        if any(bool(value) for value in node_locks.values()):
            raise OutlineAdjustmentError(
                "lock_conflict",
                f"节点 {ref} 已锁定，不能执行该目录调整",
                details={"node_ref": ref, "categories": sorted(categories)},
            )


def _compile_draft(
    source: dict[str, Any],
    state: _OutlineState,
    ordered_refs: list[str],
) -> tuple[dict[str, Any], dict[str, str]]:
    id_map: dict[str, str] = {}
    chapter_numbers: dict[str, int] = {}
    section_numbers: dict[str, tuple[int, int]] = {}
    for chapter_index, chapter_ref in enumerate(state.chapters, start=1):
        chapter_numbers[chapter_ref] = chapter_index
        id_map[chapter_ref] = f"L1-{chapter_index}"
        for section_index, section_ref in enumerate(state.sections[chapter_ref], start=1):
            id_map[section_ref] = f"L2-{chapter_index}-{section_index}"
            section_numbers[section_ref] = (chapter_index, section_index)

    compiled_nodes: list[dict[str, Any]] = []
    for ref in ordered_refs:
        raw = state.nodes[ref]
        level = int(raw.get("node_level") or 0)
        node = {
            key: deepcopy(value)
            for key, value in raw.items()
            if not key.startswith("_")
        }
        node["node_id"] = id_map[ref]
        node["node_level"] = level
        if level == 1:
            node["node_name"] = _canonical_node_name(
                str(raw.get("node_name") or ""),
                level=1,
                chapter_number=chapter_numbers[ref],
            )
        else:
            chapter_number, section_number = section_numbers[ref]
            node["node_name"] = _canonical_node_name(
                str(raw.get("node_name") or ""),
                level=2,
                chapter_number=chapter_number,
                section_number=section_number,
            )
        node["parent_node_id"] = (
            "root" if level == 1 else id_map[str(raw.get("parent_node_id") or "")]
        )
        node["prerequisite_node_ids"] = [
            id_map[dependency] for dependency in raw.get("_prerequisite_refs") or []
        ]
        compiled_nodes.append(node)

    by_id = {node["node_id"]: node for node in compiled_nodes}
    chapters: list[dict[str, Any]] = []
    for chapter_ref in state.chapters:
        chapter_number = chapter_numbers[chapter_ref]
        chapter_node = by_id[id_map[chapter_ref]]
        chapter: dict[str, Any] = {
            "chapter_number": chapter_number,
            "node_id": chapter_node["node_id"],
            "title": chapter_node.get("node_name") or f"第{chapter_number}章",
            "learning_objective": chapter_node.get("learning_objective") or "",
            "sections": [],
        }
        for field in ("learning_path_role", "path_reason", "scope_boundary", "assessment"):
            if field in chapter_node:
                chapter[field] = deepcopy(chapter_node[field])
        for section_index, section_ref in enumerate(state.sections[chapter_ref], start=1):
            section_node = by_id[id_map[section_ref]]
            section = {
                key: deepcopy(value)
                for key, value in section_node.items()
                if key not in {"parent_node_id", "node_level", "node_name"}
            }
            section["section_number"] = f"{chapter_number}.{section_index}"
            section["title"] = section_node.get("node_name") or section["section_number"]
            chapter["sections"].append(section)
        chapters.append(chapter)

    compiled = deepcopy(source)
    compiled["nodes"] = compiled_nodes
    plan = deepcopy(source.get("course_plan") or source.get("course_outline") or {})
    plan["chapters"] = chapters
    compiled["course_plan"] = plan
    compiled["course_outline"] = deepcopy(plan)
    blueprint = deepcopy(source.get("course_blueprint") or {})
    blueprint["sections"] = deepcopy(chapters)
    blueprint["nodes"] = deepcopy(compiled_nodes)
    compiled["course_blueprint"] = blueprint

    shape_constraints = {
        "chapter_count": len(chapters),
        "section_count": sum(len(chapter["sections"]) for chapter in chapters),
        "chapter_count_source": "outline_adjustment",
        "section_count_source": "outline_adjustment",
    }
    brief = deepcopy(source.get("course_generation_brief") or {})
    brief["course_shape_constraints"] = deepcopy(shape_constraints)
    compiled["course_generation_brief"] = brief
    compiled["course_shape_constraints"] = deepcopy(shape_constraints)

    locks = source.get("blueprint_locks") or {}
    compiled["blueprint_locks"] = {
        id_map[ref]: deepcopy(value)
        for ref, value in locks.items()
        if ref in id_map
    }
    return compiled, id_map


def _canonical_node_name(
    value: str,
    *,
    level: int,
    chapter_number: int,
    section_number: int | None = None,
) -> str:
    if level == 1:
        title = _CHAPTER_NUMBER_PREFIX.sub("", value.strip(), count=1).strip()
        return f"第{chapter_number}章 {title}".strip()
    title = _SECTION_NUMBER_PREFIX.sub("", value.strip(), count=1).strip()
    return f"{chapter_number}.{section_number or 1} {title}".strip()


def _constraint_report(draft: dict[str, Any]) -> dict[str, Any]:
    shape = _shape(draft)
    return {
        "valid": True,
        **shape,
        "course_type": draft.get("course_type") or "systematic",
        "course_purpose": draft.get("course_purpose") or "systematic",
        "shape_constraint_source": "outline_adjustment",
    }


def _shape(draft: dict[str, Any]) -> dict[str, int]:
    nodes = draft.get("nodes") or []
    return {
        "chapter_count": sum(int(node.get("node_level") or 0) == 1 for node in nodes),
        "section_count": sum(int(node.get("node_level") or 0) == 2 for node in nodes),
    }


def _diff_item(
    node: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    *,
    old: bool = False,
) -> dict[str, Any]:
    position = _node_position(str(node.get("node_id") or ""), nodes)
    return {
        "node_id": node.get("node_id"),
        "node_name": node.get("node_name") or node.get("node_id"),
        "old_position" if old else "new_position": position,
    }


def _node_position(node_id: str, nodes: dict[str, dict[str, Any]]) -> str:
    node = nodes.get(node_id) or {}
    level = int(node.get("node_level") or 0)
    if level == 1:
        chapters = [item for item in nodes.values() if int(item.get("node_level") or 0) == 1]
        index = next((i for i, item in enumerate(chapters, 1) if item.get("node_id") == node_id), 0)
        return f"第{index}章"
    parent = str(node.get("parent_node_id") or "")
    chapters = [item for item in nodes.values() if int(item.get("node_level") or 0) == 1]
    chapter_index = next((i for i, item in enumerate(chapters, 1) if item.get("node_id") == parent), 0)
    siblings = [
        item for item in nodes.values()
        if int(item.get("node_level") or 0) == 2 and str(item.get("parent_node_id") or "") == parent
    ]
    section_index = next((i for i, item in enumerate(siblings, 1) if item.get("node_id") == node_id), 0)
    return f"第{chapter_index}章 · 第{section_index}节"


def _required_ref(data: dict[str, Any], field: str) -> str:
    value = str(data.get(field) or "").strip()
    if not value:
        raise OutlineAdjustmentError("reference_missing", f"操作缺少 {field}")
    return value


def _optional_ref(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _known_node(state: _OutlineState, ref: str) -> dict[str, Any]:
    node = state.nodes.get(ref)
    if node is None:
        raise OutlineAdjustmentError(
            "node_reference_missing",
            f"操作引用的节点 {ref} 不存在",
            details={"node_ref": ref},
        )
    return node


__all__ = [
    "ALLOWED_OPERATIONS",
    "OutlineAdjustmentError",
    "apply_outline_operations",
    "compile_outline_draft",
    "describe_outline_diff",
]
