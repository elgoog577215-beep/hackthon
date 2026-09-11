"""One dependency gate for partial review, generation and application."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def incomplete(plan: Any) -> bool:
    return bool(plan.teacher_change_planning and (
        plan.teacher_change_planning.intent.system_blockers
        or plan.impact_summary.get('coverage', {}).get('unscanned_unit_ids')
    ))


def independent_text_edit(plan: Any, migration: Any, *, allow_title: bool = False) -> bool:
    from .content_patches import is_exact_text_operation
    if migration.asset_type != 'course_content' or migration.disposition != 'rewrite_partial' or migration.candidate_status != 'ready':
        return False
    operation = next((op for op in plan.operations if op.operation_id == migration.metadata.get('operation_id')), None)
    if operation is None or not is_exact_text_operation(operation) or migration.metadata.get('structure_dependency_blocked'):
        return False
    before = operation.payload.get('before_block') or {}
    after = operation.payload.get('proposed_block') or {}
    if not allow_title and (before.get('payload') or {}).get('title') != (after.get('payload') or {}).get('title'):
        return False
    return bool(before.get('block_id') and before.get('section_id')
                and before.get('block_id') == operation.target_block_id
                and before.get('section_id') == operation.target_section_id
                and {k: v for k, v in before.items() if k != 'payload'} == {k: v for k, v in after.items() if k != 'payload'})


def repairable_text_draft(plan: Any, migration: Any) -> bool:
    """Editing a source-bound draft grants no authority to apply it."""
    block = migration.metadata.get('course_block') or {}
    if (plan.status != 'pending' or migration.asset_type != 'course_content'
            or migration.disposition not in {'rewrite_partial', 'regenerate'} or migration.metadata.get('source_state') == 'stale'
            or not block.get('block_id') or not block.get('section_id') or not block.get('internal_revision')):
        return False
    fields = block.get('payload') or {}
    if not any(isinstance(fields.get(key), str) and fields[key].strip() for key in ('markdown', 'text', 'content')):
        return False
    if incomplete(plan):
        coverage = plan.impact_summary.get('coverage') or {}
        scanned = set(coverage.get('source_revisions') or {}).difference(coverage.get('unscanned_unit_ids') or [])
        return bool(migration.source_unit_ids and set(migration.source_unit_ids).issubset(scanned))
    return True


def readiness(plan: Any) -> dict[str, Any]:
    planning = plan.teacher_change_planning
    if planning is None or not incomplete(plan):
        return {'incomplete': False, 'eligible_migration_ids': [], 'waiting': {}}
    coverage = plan.impact_summary.get('coverage') or {}
    missing = set(coverage.get('unscanned_unit_ids') or [])
    scanned = set(coverage.get('source_revisions') or {}).difference(missing)
    index = plan.impact_summary.get('scan_unit_index') or {}
    parents = {str(n.get('node_id')): str(n.get('parent_node_id') or 'root')
               for n in plan.impact_summary.get('current_outline') or []}
    affected_structure = set()
    for op in planning.structural_operations:
        affected_structure.update(op.source_node_ids)
        if op.target_parent_id:
            affected_structure.add(op.target_parent_id)
    for _ in parents:
        affected_structure.update(k for k, v in parents.items() if v in affected_structure)
    unknown_structure = ('structural_regeneration' in planning.execution_strategies and not planning.structural_operations)
    eligible, waiting, editable = [], {}, []
    for migration in planning.unit_migrations:
        local_edit = independent_text_edit(plan, migration)
        sources = set(migration.source_unit_ids)
        if sources and sources.issubset(scanned) and migration.metadata.get('source_state') != 'stale' and (independent_text_edit(plan, migration, allow_title=True) or repairable_text_draft(plan, migration)):
            editable.append(migration.migration_id)
        scope = set(migration.dependency_ids) | {str(migration.metadata.get('parent_id') or '')}
        reason = ''
        if not sources or not sources.issubset(scanned):
            reason = 'source_unscanned'
        elif migration.metadata.get('source_state') == 'stale':
            reason = 'source_stale'
        elif independent_text_edit(plan, migration, allow_title=True) and not local_edit:
            reason = 'title_dependency'
        elif unknown_structure:
            reason = 'structure_dependency'
        elif planning.intent.blocking_questions and not local_edit:
            reason = 'teacher_decision'
        elif scope.intersection(affected_structure) and not local_edit:
            reason = 'structure_dependency'
        elif migration.asset_type == 'outline' or migration.disposition in {'retire', 'reuse_rebind', 'blocked'}:
            reason = 'shared_scope'
        elif migration.asset_type not in {'course_content', 'lesson_plan', 'script', 'ppt', 'question_bank'}:
            reason = 'unknown_scope'
        elif migration.asset_type != 'course_content':
            # These executors publish a whole lecture or question bundle.
            # A locally scanned block alone does not prove that write scope ready.
            parent = str(migration.metadata.get('parent_id') or '')
            upstream = {'lesson_plan': {'lesson_plan', 'outline'},
                        'script': {'script', 'lesson_plan', 'outline'},
                        'ppt': {'ppt', 'script', 'lesson_plan', 'outline'},
                        'question_bank': {'question_bank'}}[migration.asset_type]
            relevant = {key for key, value in index.items()
                        if value.get('asset_type') in upstream
                        and (migration.asset_type == 'question_bank'
                             or value.get('parent_id') == parent
                             or set(value.get('section_ids') or []).intersection(scope))}
            if not index or not relevant or not relevant.issubset(scanned):
                reason = 'shared_scope'
        if reason:
            waiting[migration.migration_id] = reason
        else:
            eligible.append(migration.migration_id)
    return {'incomplete': True, 'eligible_migration_ids': eligible, 'editable_migration_ids': editable, 'waiting': waiting,
            'scanned_units': int(coverage.get('scanned_units') or 0),
            'pending_units': len(missing), 'can_preview': any(
                set(m.source_unit_ids) and set(m.source_unit_ids).issubset(scanned)
                for m in planning.unit_migrations)}


def require_partial_selection(plan: Any, migration_ids: list[str], *, structural: bool = False) -> None:
    if not incomplete(plan):
        return
    gate = readiness(plan)
    if structural or not migration_ids or not set(migration_ids).issubset(gate['eligible_migration_ids']):
        raise ValueError('所选修改仍依赖未完成检查、共同结构或待确认问题，请只选择已独立就绪的项目')


def require_partial_operations(plan: Any, operation_ids: list[str] | None) -> None:
    if not incomplete(plan):
        return
    reviewed = plan.impact_summary.get('scope_review') or {}
    if not operation_ids or not set(operation_ids).issubset(reviewed.get('selected_operation_ids') or []):
        raise ValueError('部分应用必须明确选择已经审阅的独立修改')
    migrations = [m for m in plan.teacher_change_planning.unit_migrations
                  if m.metadata.get('operation_id') in operation_ids]
    if {m.metadata.get('operation_id') for m in migrations} != set(operation_ids):
        raise ValueError('结构修改或未绑定来源的操作不能在部分扫描时应用')
    require_partial_selection(plan, [m.migration_id for m in migrations])


def applied_units(plan: Any) -> set[str]:
    completed = set((plan.impact_summary.get('coverage') or {}).get('completed_unit_ids') or [])
    if plan.status != 'applied':
        return completed
    receipt = plan.application_receipt or {}
    operation_ids = {item.get('operation_id') for item in receipt.get('items') or []
                     if item.get('status') in {'applied', 'unchanged'}
                     and item.get('operation_id') in set(plan.selected_operation_ids or [])}
    operation_ids.update(item.operation_id for item in plan.operation_journal if item.status == 'applied')
    for migration in plan.teacher_change_planning.unit_migrations:
        if migration.metadata.get('operation_id') in operation_ids:
            completed.update(migration.source_unit_ids)
    return completed


def retained_analysis(plan: Any, retained_ids: set[str]) -> dict[str, Any]:
    """Use the persisted normalized result; legacy plans have the same information in migrations."""
    snapshot = deepcopy(plan.impact_summary.get('scan_analysis') or {})
    if not snapshot:
        intent = plan.teacher_change_planning.intent
        snapshot = {'interpreted_goal': intent.interpreted_goal,
                    'signal_kind': intent.signals[0].kind if intent.signals else 'uncertain',
                    'blocking_questions': list(intent.blocking_questions),
                    'clarifications': [q.model_dump(mode='json') for q in intent.clarifications],
                    'hard_constraints': list(intent.hard_constraints),
                    'protected_requirements': list(intent.protected_requirements),
                    'structure': {'required': bool(plan.teacher_change_planning.structural_operations),
                                  'proposed_outline': deepcopy(plan.impact_summary.get('proposed_outline') or [])},
                    'affected_units': [dict(unit_id=m.source_unit_ids[0], disposition=m.disposition,
                        reason=m.reason, confidence=m.confidence,
                        content_patches=deepcopy(m.metadata.get('content_patches') or []))
                        for m in plan.teacher_change_planning.unit_migrations if m.source_unit_ids]}
    snapshot['affected_units'] = [item for item in snapshot.get('affected_units') or [] if item.get('unit_id') in retained_ids]
    return snapshot
