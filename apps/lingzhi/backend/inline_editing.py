"""Resolve an inline text range without broadening a teacher's edit scope."""
from __future__ import annotations

import re


def inline_text_span(content: str, selected: str) -> tuple[int, int]:
    selected = selected.strip()
    if not selected:
        raise ValueError("请先选择要修改的内容。")
    matches = list(re.finditer(re.escape(selected), content))
    if not matches:
        # Browser text can fold whitespace; retain offsets into the original.
        pattern = r"\s+".join(re.escape(part) for part in re.split(r"\s+", selected))
        matches = list(re.finditer(pattern, content))
    if len(matches) != 1:
        raise ValueError("无法唯一定位选中内容，请扩大选区或选择完整段落后重试。")
    return matches[0].span()


def replace_inline_text(content: str, selected: str, replacement: str) -> str:
    start, end = inline_text_span(content, selected)
    if not replacement.strip():
        raise ValueError("AI 返回了空修改，原文未改变。")
    result = content[:start] + replacement.strip() + content[end:]
    if result == content:
        raise ValueError("没有产生内容变化，请补充具体修改要求。")
    return result


def outline_inline_target(draft: dict, selected: str, node_id: str = "", field: str = "") -> tuple[dict, str, list]:
    """Find one editable source value, never a duplicate derived projection."""
    from course_outline_adjustments import COURSE_PLAN_EDITABLE_FIELDS, LECTURE_CONTRACT_FIELDS
    matches = []

    def visit(value, path, operation, key):
        if isinstance(value, str):
            try:
                start, end = inline_text_span(value, selected)
            except ValueError:
                return
            matches.append((operation, key, path, value, start, end))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, [*path, index], operation, key)
        elif isinstance(value, dict):
            for name, item in value.items():
                if name.endswith(('_id', '_ids', '_refs')) or name in {'id', 'url', 'href'}:
                    continue
                visit(item, [*path, name], operation, key)

    if node_id:
        nodes = draft.get('nodes') or (draft.get('course_blueprint') or {}).get('nodes') or []
        node = next((item for item in nodes if item.get('node_id') == node_id), None)
        if not node:
            raise ValueError('当前讲次已变化，请重新选择。')
        fields = {'node_name', 'learning_objective', 'scope_boundary', 'assessment', *LECTURE_CONTRACT_FIELDS}
        for key in fields:
            if field and key != field:
                continue
            visit(node.get(key), [], {'op': 'update_node', 'node_ref': node_id, key: node.get(key)}, key)
    else:
        plan = draft.get('course_plan') or draft.get('course_outline') or {}
        for key in COURSE_PLAN_EDITABLE_FIELDS:
            if field and key != field:
                continue
            visit(plan.get(key), [], {'op': 'update_course_plan', key: plan.get(key)}, key)
    if len(matches) != 1:
        raise ValueError('无法唯一定位大纲原文，请选择一条完整内容后重试。')
    operation, key, path, content, start, end = matches[0]
    return operation, content[start:end], [key, *path]


def patch_outline_inline(operation: dict, path: list, selected: str, replacement: str) -> dict:
    from copy import deepcopy
    result = deepcopy(operation)
    parent = result
    for key in path[:-1]:
        parent = parent[key]
    key = path[-1]
    parent[key] = replace_inline_text(parent[key], selected, replacement)
    return result
