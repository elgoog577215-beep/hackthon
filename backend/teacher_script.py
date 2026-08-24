"""教师讲稿的结构化真源与确定性质量门。

讲稿不重新选择教学模式、课型或教学模板。它把已确认教案中的教学模块
编译为教师可讲、可逐块编辑、可继续投影到 PPT V6 的唯一内容结构。
"""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any

from course_pedagogy import MODULES, module_block_role


SCRIPT_SCHEMA_VERSION = "teacher_script_v2"
SCRIPT_PIPELINE_VERSION = "structured_teacher_script_v1"
SCRIPT_QUALITY_VERSION = "teacher_script_quality_v1"

_ALLOWED_ROLES = {
    "orientation",
    "prerequisite",
    "objective",
    "concept",
    "reasoning",
    "example",
    "counterexample",
    "application",
    "activity",
    "feedback",
    "misconception",
    "checkpoint",
    "remediation",
    "summary",
    "transfer",
}
_HEADING_PATTERN = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.splitlines() if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _stable_block_id(section_id: str, module_id: str, index: int) -> str:
    digest = hashlib.sha256(
        f"{section_id}:{module_id}:{index}".encode("utf-8")
    ).hexdigest()[:12]
    return f"tsb-{digest}"


def compile_teacher_script_module_contract(
    outline_section: dict[str, Any],
    confirmed_plan_section: dict[str, Any],
) -> dict[str, Any]:
    """Compile the frozen plan modules into the script's exact block contract."""
    section_id = _text(
        confirmed_plan_section.get("node_id") or outline_section.get("node_id")
    )
    frozen_modules = [
        item
        for item in outline_section.get("module_plan") or []
        if isinstance(item, dict) and item.get("module_id")
    ]
    frozen_by_id = {
        _text(item.get("module_id")): item for item in frozen_modules
    }
    plan_modules = [
        item
        for item in confirmed_plan_section.get("teaching_modules") or []
        if isinstance(item, dict) and item.get("module_id")
    ]
    # A confirmed mature plan owns the actual module order. The frozen outline
    # contract enriches it with labels/roles; it never appends a second module list.
    source_modules = plan_modules or frozen_modules
    modules: list[dict[str, Any]] = []
    for index, actual in enumerate(source_modules, start=1):
        module_id = _text(actual.get("module_id")) or "core_explanation"
        frozen = frozen_by_id.get(module_id) or {}
        registry = MODULES.get(module_id)
        role = _text(
            actual.get("block_role")
            or frozen.get("block_role")
            or module_block_role(module_id)
        )
        if role not in _ALLOWED_ROLES:
            role = "concept"
        label = _text(
            actual.get("label")
            or frozen.get("label")
            or (registry.label if registry else "")
            or module_id
        )
        modules.append({
            "block_id": _stable_block_id(section_id, module_id, index),
            "module_id": module_id,
            "role": role,
            "title": label,
            "required": bool(
                frozen.get("required", True) if frozen else actual.get("required", True)
            ),
            "knowledge_names": _text_list(actual.get("knowledge_names")),
            "planned_minutes": actual.get("planned_minutes"),
            "teaching_purpose": _text(actual.get("teaching_purpose")),
            "teaching_guidance": _text(actual.get("teaching_guidance")),
            "teacher_activity": _text(actual.get("teacher_activity")),
            "student_activity": _text(actual.get("student_activity")),
            "output_contract": _text(
                frozen.get("output_contract")
                or (registry.output_contract if registry else "")
            ),
            "prompt_instruction": _text(
                frozen.get("prompt_instruction")
                or (registry.prompt_instruction if registry else "")
            ),
        })
    archetype = deepcopy(
        confirmed_plan_section.get("lesson_archetype")
        or outline_section.get("lesson_archetype")
        or {}
    )
    if not archetype and frozen_modules:
        archetype = {
            "archetype_id": _text(frozen_modules[0].get("lesson_archetype_id")),
            "label": _text(frozen_modules[0].get("lesson_archetype_label")),
        }
    return {
        "schema_version": SCRIPT_SCHEMA_VERSION,
        "section_node_id": section_id,
        "title": _text(
            outline_section.get("node_name")
            or confirmed_plan_section.get("title")
        ),
        "lesson_archetype": archetype,
        "learning_objective": _text(
            confirmed_plan_section.get("learning_objective")
            or outline_section.get("learning_objective")
        ),
        "key_points": _text_list(confirmed_plan_section.get("key_points")),
        "key_difficulties": _text_list(
            confirmed_plan_section.get("key_difficulties")
        ),
        "in_class_checks": _text_list(
            confirmed_plan_section.get("in_class_checks")
        ),
        "modules": modules,
    }


def teacher_script_blocks_to_markdown(blocks: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"## {_text(block.get('title'))}\n\n{_text(block.get('content'))}".strip()
        for block in blocks
        if isinstance(block, dict)
        and _text(block.get("title"))
        and _text(block.get("content"))
    )


def _segments(markdown: str) -> list[tuple[str, str]]:
    text = _text(markdown)
    matches = list(_HEADING_PATTERN.finditer(text))
    if not matches:
        return []
    return [
        (
            _text(match.group(1)),
            text[match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(text)].strip(),
        )
        for index, match in enumerate(matches)
    ]


def parse_teacher_script_markdown(
    markdown: str,
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    """Bind model Markdown to the preselected modules without guessing a new template."""
    expected = [item for item in contract.get("modules") or [] if isinstance(item, dict)]
    parsed = _segments(markdown)
    if not parsed and len(expected) == 1 and _text(markdown):
        parsed = [(_text(expected[0].get("title")), _text(markdown))]
    blocks: list[dict[str, Any]] = []
    for index, (title, content) in enumerate(parsed):
        module = expected[index] if index < len(expected) else {}
        blocks.append({
            "block_id": _text(module.get("block_id")) or _stable_block_id(
                _text(contract.get("section_node_id")),
                _text(module.get("module_id")) or "extra",
                index + 1,
            ),
            "module_id": _text(module.get("module_id")),
            "role": _text(module.get("role")) or "concept",
            "title": title,
            "content": content,
            "required": bool(module.get("required", True)),
            "knowledge_names": deepcopy(module.get("knowledge_names") or []),
            "planned_minutes": module.get("planned_minutes"),
            "teacher_activity": _text(module.get("teacher_activity")),
            "student_activity": _text(module.get("student_activity")),
        })
    return blocks


def normalize_teacher_script_section(
    section: dict[str, Any],
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize v2 blocks and preserve v1 Markdown through a one-way adapter."""
    value = deepcopy(section)
    has_contract = contract is not None
    compiled = contract or {
        "section_node_id": _text(value.get("section_node_id")),
        "title": _text(value.get("title")),
        "modules": [],
    }
    raw_blocks = [
        item for item in value.get("blocks") or [] if isinstance(item, dict)
    ]
    if raw_blocks:
        expected = [item for item in compiled.get("modules") or [] if isinstance(item, dict)]
        blocks: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_blocks, start=1):
            module = expected[index - 1] if index <= len(expected) else {}
            module_id = _text(raw.get("module_id") or module.get("module_id"))
            role = _text(raw.get("role") or module.get("role") or module_block_role(module_id))
            if role not in _ALLOWED_ROLES:
                role = "concept"
            blocks.append({
                "block_id": _text(raw.get("block_id") or module.get("block_id"))
                or _stable_block_id(
                    _text(compiled.get("section_node_id")), module_id or "legacy", index
                ),
                "module_id": module_id,
                "role": role,
                "title": _text(raw.get("title") or module.get("title") or f"教学块 {index}"),
                "content": _text(raw.get("content")),
                "required": bool(raw.get("required", module.get("required", True))),
                "knowledge_names": _text_list(
                    raw.get("knowledge_names") or module.get("knowledge_names")
                ),
                "planned_minutes": raw.get("planned_minutes", module.get("planned_minutes")),
                "teacher_activity": _text(
                    raw.get("teacher_activity") or module.get("teacher_activity")
                ),
                "student_activity": _text(
                    raw.get("student_activity") or module.get("student_activity")
                ),
            })
    else:
        content = _text(value.get("content"))
        blocks = parse_teacher_script_markdown(content, compiled) if has_contract else []
        if not blocks and content:
            blocks = [{
                "block_id": _stable_block_id(
                    _text(compiled.get("section_node_id")), "legacy", 1
                ),
                "module_id": "legacy_script",
                "role": "concept",
                "title": _text(value.get("title") or compiled.get("title") or "讲稿正文"),
                "content": content,
                "required": True,
                "knowledge_names": [],
                "planned_minutes": None,
                "teacher_activity": "",
                "student_activity": "",
            }]
    return {
        "schema_version": SCRIPT_SCHEMA_VERSION,
        "section_node_id": _text(
            value.get("section_node_id") or compiled.get("section_node_id")
        ),
        "title": _text(value.get("title") or compiled.get("title")),
        "lesson_archetype": deepcopy(compiled.get("lesson_archetype") or {}),
        "blocks": blocks,
        "content": teacher_script_blocks_to_markdown(blocks),
    }


def validate_teacher_script_section(
    section: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    normalized = normalize_teacher_script_section(section, contract)
    blocks = normalized["blocks"]
    expected = [item for item in contract.get("modules") or [] if isinstance(item, dict)]
    blocking: list[dict[str, str]] = []
    review: list[dict[str, str]] = []

    def add(target: list[dict[str, str]], code: str, message: str) -> None:
        target.append({"code": code, "message": message})

    if not normalized["section_node_id"]:
        add(blocking, "teacher_script:section_identity", "讲稿小节缺少稳定标识。")
    if not blocks:
        add(blocking, "teacher_script:blocks_empty", "讲稿没有可用的教学块。")
    if any(not _text(block.get("content")) for block in blocks):
        add(blocking, "teacher_script:block_empty", "讲稿仍有空白教学块。")
    block_ids = [_text(block.get("block_id")) for block in blocks]
    if any(not block_id for block_id in block_ids) or len(block_ids) != len(set(block_ids)):
        add(blocking, "teacher_script:block_identity", "讲稿教学块标识缺失或重复。")
    expected_ids = [_text(item.get("module_id")) for item in expected]
    actual_ids = [_text(item.get("module_id")) for item in blocks]
    if expected_ids and actual_ids != expected_ids:
        add(
            blocking,
            "teacher_script:module_contract",
            "讲稿必须按已确认教案的模块顺序完整覆盖，不能另选通用模板。",
        )
    expected_block_ids = [_text(item.get("block_id")) for item in expected]
    if expected_block_ids and block_ids != expected_block_ids:
        add(
            blocking,
            "teacher_script:block_contract",
            "讲稿块身份必须沿用已确认教案模块，不能重排或替换。",
        )
    expected_titles = [_text(item.get("title")) for item in expected]
    actual_titles = [_text(item.get("title")) for item in blocks]
    if expected_titles and actual_titles != expected_titles:
        add(
            blocking,
            "teacher_script:module_heading",
            "讲稿块标题必须与已确认教学模块一致。",
        )
    expected_roles = [_text(item.get("role")) for item in expected]
    actual_roles = [_text(item.get("role")) for item in blocks]
    if expected_roles and actual_roles != expected_roles:
        add(
            blocking,
            "teacher_script:role_contract",
            "讲稿块角色必须沿用已确认教学模块。",
        )
    for index, block in enumerate(blocks):
        if index >= len(expected):
            continue
        allowed_knowledge = set(_text_list(expected[index].get("knowledge_names")))
        actual_knowledge = set(_text_list(block.get("knowledge_names")))
        if actual_knowledge - allowed_knowledge:
            add(
                blocking,
                "teacher_script:knowledge_scope",
                f"“{_text(block.get('title'))}”引用了当前教案范围外的知识。",
            )
    for block in blocks:
        if len(_text(block.get("content"))) < 20:
            add(
                review,
                "teacher_script:block_too_short",
                f"“{_text(block.get('title'))}”内容较短，建议确认能否直接用于课堂讲授。",
            )
    return {
        "schema_version": SCRIPT_QUALITY_VERSION,
        "pipeline_version": SCRIPT_PIPELINE_VERSION,
        "passed": not blocking,
        "blocking_issues": blocking,
        "review_issues": review,
        "metrics": {
            "block_count": len(blocks),
            "module_count": len(expected),
            "character_count": sum(len(_text(block.get("content"))) for block in blocks),
        },
    }


def compile_teacher_script_section(
    markdown: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    section = normalize_teacher_script_section(
        {
            "section_node_id": contract.get("section_node_id"),
            "title": contract.get("title"),
            "content": markdown,
        },
        contract,
    )
    section["quality_report"] = validate_teacher_script_section(section, contract)
    section["pipeline_version"] = SCRIPT_PIPELINE_VERSION
    return section
