"""Compile semantic patches against original text, and project readable prose."""
from copy import deepcopy
from typing import Any

EXACT_AUTHORING_ACTION = 'exact_script_block'


def is_exact_text_operation(operation: Any) -> bool:
    return operation.operation_type == 'REPLACE_COURSE_BLOCK' or (
        operation.operation_type == 'APPLY_DOMAIN_CANDIDATE' and operation.payload.get('action') == EXACT_AUTHORING_ACTION)


def readable_body(fields: dict[str, str]) -> str:
    for key in ('/markdown', '/text', '/content', 'markdown', 'text', 'content'):
        value = fields.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return '\n\n'.join(dict.fromkeys(value for value in fields.values() if isinstance(value, str) and value.strip()))


def compile_patches(payload: dict[str, Any], patches: list[dict[str, Any]], *, literal: bool = False):
    proposed = deepcopy(payload)
    ranges: dict[str, list[tuple[int, int, str]]] = {}
    applied, warnings, seen = [], [], set()
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        field, before, after = (str(patch.get(key) or '') for key in ('field', 'before', 'after'))
        replace_all = bool(patch.get('replace_all', True))
        identity = (field, before, after, replace_all)
        if identity in seen or not before or before == after:
            continue
        seen.add(identity)
        original = payload.get(field)
        if not isinstance(original, str) or before not in original:
            continue
        # A semantic paragraph expansion is one proposed insertion. Repeated
        # anchors must not multiply a newly authored project. Explicit literal
        # replacements retain their all-occurrences contract.
        if not literal and replace_all and original.count(before) > 1 and '\n\n' in after and len(after) > len(before):
            replace_all = False
            warnings.append('原片段出现多次，新增段落仅放在第一处，请在详情中核对位置。')
        matches, start = [], 0
        while (position := original.find(before, start)) >= 0:
            matches.append((position, position + len(before), after))
            start = position + len(before)
            if not replace_all:
                break
        existing = ranges.setdefault(field, [])
        added = 0
        for match in matches:
            if match in existing:
                continue
            if any(match[0] < end and begin < match[1] for begin, end, _ in existing):
                raise ValueError('修改片段相互重叠且建议不一致，请重新生成或手动明确修改内容')
            existing.append(match)
            added += 1
        if added:
            applied.append({**patch, 'replace_all': replace_all, 'occurrences': added})
    for field, edits in ranges.items():
        text = payload[field]
        for begin, end, replacement in sorted(edits, reverse=True):
            text = text[:begin] + replacement + text[end:]
        proposed[field] = text
    return proposed, applied, list(dict.fromkeys(warnings))


def refresh_exact_candidates(plan: Any, selected_ids: list[str]) -> None:
    from .text_fields import editable_text_fields
    for migration in plan.teacher_change_planning.unit_migrations:
        if migration.migration_id not in selected_ids or migration.metadata.get('manually_edited'):
            continue
        operation = next((op for op in plan.operations if op.operation_id == migration.metadata.get('operation_id')), None)
        if operation is None or not is_exact_text_operation(operation) or not operation.payload.get('content_patches'):
            continue
        try:
            before = (operation.payload.get('before_block') or {}).get('payload')
            if not isinstance(before, dict):
                raise ValueError('原文快照缺失，请重新分析此项修改')
            after, patches, warnings = compile_patches(before, operation.payload['content_patches'],
                literal=plan.impact_summary.get('analysis_mode') == 'deterministic_exact_replace')
            if not patches:
                raise ValueError('没有匹配原文的有效修改片段，请重新分析')
        except ValueError as error:
            migration.candidate_status = 'failed'
            migration.metadata['candidate_error'] = str(error)
            migration.metadata['candidate_error_detail'] = {'code': 'patch_conflict', 'retryable': False}
            migration.metadata.pop('operation_id', None)
            plan.operations = [op for op in plan.operations if op.operation_id != operation.operation_id]
        else:
            operation.payload['proposed_block']['payload'] = after
            operation.payload['content_patches'] = patches
            before_fields, after_fields = editable_text_fields(before), editable_text_fields(after)
            migration.metadata.update(before_fields=before_fields, after_fields=after_fields,
                before_content=readable_body(before_fields), after_content=readable_body(after_fields),
                applied_patches=patches, change_count=sum(p['occurrences'] for p in patches),
                candidate_warning=' '.join(warnings) or migration.metadata.get('candidate_warning', ''))
        for item in plan.impact_summary.get('affected_units') or []:
            if item.get('migration_id') == migration.migration_id:
                for key in ('before_fields', 'after_fields', 'before_content', 'after_content', 'change_count', 'candidate_warning', 'candidate_error', 'candidate_error_detail'):
                    if key in migration.metadata:
                        item[key] = deepcopy(migration.metadata[key])
                item['candidate_status'] = migration.candidate_status
                item['operation_id'] = migration.metadata.get('operation_id', '')


def require_current_patch_preview(plan: Any, operation_ids: list[str] | None) -> None:
    if plan.status != 'pending' or plan.teacher_change_planning is None:
        return
    manual_ids = {m.metadata.get('operation_id') for m in plan.teacher_change_planning.unit_migrations if m.metadata.get('manually_edited')}
    for op in plan.operations:
        if (operation_ids is not None and op.operation_id not in operation_ids) or op.operation_id in manual_ids:
            continue
        if not is_exact_text_operation(op) or not op.payload.get('content_patches'):
            continue
        before = (op.payload.get('before_block') or {}).get('payload')
        if not isinstance(before, dict):
            raise ValueError('原文快照缺失，请重新分析此项修改')
        after, _, _ = compile_patches(before, op.payload['content_patches'],
            literal=plan.impact_summary.get('analysis_mode') == 'deterministic_exact_replace')
        if after != op.payload['proposed_block']['payload']:
            raise ValueError('修改建议包含重复插入，请先重新确认所选范围并核对更新后的详情')
