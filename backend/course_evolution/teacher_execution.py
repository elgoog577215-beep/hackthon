"""Execution adapters for the existing whole-course change plan.

This module deliberately does not introduce another workflow.  It turns the
reviewed migrations already stored on ``CourseEvolutionPlan`` into candidates
owned by the existing lesson-plan, script, PPT and question-bank repositories,
then lets the existing change-set accept/undo endpoints apply those candidates.
"""

from __future__ import annotations

import asyncio
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from course_document import stable_hash
from course_repository import CourseDocumentRepository
from question_bank import (
    QuestionBankRepository,
    refresh_question_bank_bundle,
    review_question_bank_item,
    revise_question_bank_item,
)
from runtime_metrics import (
    record_cross_asset_partial,
    record_persistence_failure,
)
from slide_deck_v6 import SlideDeckV6, project_ppt_manuscript_from_deck_v1
from teacher_lesson_authoring import (
    TeacherLessonAuthoringError,
    TeacherLessonAuthoringRepository,
    TeacherLessonAuthoringService,
    lesson_scope,
    generation_failure,
    teacher_lesson_v6_source,
)
from teacher_script import (
    compile_teacher_script_module_contract,
    normalize_teacher_script_section,
    teacher_script_blocks_to_markdown,
    validate_teacher_script_section,
)
from teaching_representations import (
    TeachingRepresentationRepository,
    TeachingRepresentationSpec,
)

from .core import (
    CourseEvolutionJournalPersistenceError,
    CourseEvolutionOperation,
    CourseEvolutionOperationJournalEntry,
    CourseEvolutionPlan,
    CourseEvolutionRepository,
)
from .text_fields import readable_text, replace_editable_text

DOMAIN_OPERATION_TYPE = "APPLY_DOMAIN_CANDIDATE"
CANDIDATE_BUNDLE_SCHEMA = "teacher_course_domain_candidates_v1"
RECEIPT_SCHEMA = "teacher_course_domain_receipt_v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact(value: Any, limit: int = 360) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _journal_entry(
    plan: CourseEvolutionPlan,
    operation_id: str,
) -> CourseEvolutionOperationJournalEntry:
    entry = next(
        (item for item in plan.operation_journal if item.operation_id == operation_id),
        None,
    )
    if entry is None:
        operation = next(
            (item for item in plan.operations if item.operation_id == operation_id),
            None,
        )
        payload = operation.payload if operation is not None else {}
        now = _now()
        entry = CourseEvolutionOperationJournalEntry(
            operation_id=operation_id,
            domain=str((payload or {}).get("domain") or ""),
            previous_revision_id=str(
                (payload or {}).get("previous_revision_id")
                or (payload or {}).get("previous_spec_id")
                or ""
            ),
            created_at=now,
            updated_at=now,
        )
        plan.operation_journal.append(entry)
    return entry


def _persist_journal_entry(
    plan: CourseEvolutionPlan,
    entry: CourseEvolutionOperationJournalEntry,
    *,
    repository: CourseEvolutionRepository,
) -> None:
    snapshot = entry.model_copy(deep=True)

    def update(current: Any) -> Any:
        stored_plan = next(
            (
                item for item in current.change_sets
                if item.change_set_id == plan.change_set_id
            ),
            None,
        )
        if stored_plan is None:
            raise KeyError(plan.change_set_id)
        index = next(
            (
                index
                for index, item in enumerate(stored_plan.operation_journal)
                if item.operation_id == snapshot.operation_id
            ),
            None,
        )
        if index is None:
            stored_plan.operation_journal.append(snapshot.model_copy(deep=True))
        else:
            stored_plan.operation_journal[index] = snapshot.model_copy(deep=True)
        stored_plan.updated_at = snapshot.updated_at
        current.updated_at = snapshot.updated_at
        return current

    try:
        repository.update(plan.user_id, plan.course_id, update)
    except Exception as exc:  # noqa: BLE001 - preserve applying for reconciliation
        record_persistence_failure(
            component="course_evolution_journal",
            operation="update",
            error=exc,
            reason_code="journal_save_failed",
        )
        raise CourseEvolutionJournalPersistenceError(
            f"课程修改操作日志保存失败：{snapshot.operation_id}"
        ) from exc
    index = next(
        (
            index
            for index, item in enumerate(plan.operation_journal)
            if item.operation_id == snapshot.operation_id
        ),
        None,
    )
    if index is None:
        plan.operation_journal.append(snapshot)
    else:
        plan.operation_journal[index] = snapshot


def _base_operation_receipt(
    operation: CourseEvolutionOperation,
) -> dict[str, Any]:
    payload = operation.payload or {}
    return {
        "operation_id": operation.operation_id,
        "domain": str(payload.get("domain") or ""),
        "migration_ids": list(payload.get("migration_ids") or []),
        "unit_ids": list(payload.get("unit_ids") or []),
        "status": "failed",
        "detail": "",
        "previous_revision_id": str(
            payload.get("previous_revision_id")
            or payload.get("previous_spec_id")
            or ""
        ),
        "result_revision_id": "",
    }


def _stable_operation_revision(
    plan: CourseEvolutionPlan,
    operation: CourseEvolutionOperation,
    *,
    prefix: str,
) -> str:
    return stable_hash(
        {
            "course_id": plan.course_id,
            "change_set_id": plan.change_set_id,
            "operation_id": operation.operation_id,
            "candidate_id": str((operation.payload or {}).get("candidate_id") or ""),
        },
        prefix=prefix,
    )


def _revision(values: list[dict[str, Any]], revision_id: str) -> dict[str, Any]:
    return next(
        (
            item for item in values
            if isinstance(item, dict) and str(item.get("revision_id") or "") == revision_id
        ),
        {},
    )


def _migration_unit_id(migration: Any) -> str:
    return str((migration.metadata or {}).get("unit_id") or (
        migration.source_unit_ids[0] if migration.source_unit_ids else ""
    ))


def _selected_migrations(plan: CourseEvolutionPlan) -> list[Any]:
    planning = plan.teacher_change_planning
    if planning is None:
        raise ValueError("当前方案不是全课联动修改方案")
    review = plan.impact_summary.get("scope_review") or {}
    selected = {
        str(value) for value in review.get("selected_migration_ids") or [] if str(value)
    }
    if not selected and not (review and planning.structure_review_status == "confirmed" and planning.structural_operations):
        raise ValueError("请先确认本次修改的影响范围")
    if planning.structural_operations and planning.structure_review_status != "confirmed":
        raise ValueError("请先确认新课程结构与迁移原则")
    return [item for item in planning.unit_migrations if item.migration_id in selected]


def _group(migrations: list[Any], asset_type: str) -> dict[str, list[Any]]:
    groups: dict[str, list[Any]] = {}
    for migration in migrations:
        if migration.asset_type != asset_type:
            continue
        parent = str((migration.metadata or {}).get("parent_id") or "")
        if not parent:
            parts = _migration_unit_id(migration).split(":", 2)
            if len(parts) >= 2 and parts[0] in {"lesson_plan", "script", "ppt"}:
                parent = parts[1]
        key = parent or asset_type
        groups.setdefault(key, []).append(migration)
    return groups


def _operation(
    *,
    plan: CourseEvolutionPlan,
    domain: str,
    migrations: list[Any],
    payload: dict[str, Any],
) -> CourseEvolutionOperation:
    operation_id = f"domain-{uuid.uuid4().hex}"
    for migration in migrations:
        migration.candidate_status = "ready"
        migration.metadata["operation_id"] = operation_id
    return CourseEvolutionOperation(
        operation_id=operation_id,
        operation_type=DOMAIN_OPERATION_TYPE,
        target_block_id=str(payload.get("candidate_id") or payload.get("candidate_revision_id") or operation_id),
        target_section_id=str((migrations[0].dependency_ids or [""])[0]),
        scope="current",
        reason=f"应用已审阅的{domain}候选",
        payload={
            "schema_version": CANDIDATE_BUNDLE_SCHEMA,
            "domain": domain,
            "migration_ids": [item.migration_id for item in migrations],
            "unit_ids": [_migration_unit_id(item) for item in migrations],
            "plan_id": plan.change_set_id,
            **deepcopy(payload),
        },
    )


def _fail(migrations: list[Any], error: Exception | str) -> None:
    message = _compact(error, 500) or "候选生成失败"
    for migration in migrations:
        migration.candidate_status = "failed"
        migration.metadata["candidate_error"] = message
        migration.metadata["candidate_error_detail"] = generation_failure(error if isinstance(error, Exception) else ValueError(str(error)), "course_change_candidate_failed")
        migration.metadata.pop("operation_id", None)


def _literal_terms(migrations: list[Any]) -> tuple[str, str] | None:
    for migration in migrations:
        value = (migration.metadata or {}).get("literal_replacement") or {}
        before = str(value.get("before") or "")
        after = str(value.get("after") or "")
        if before and before != after:
            return before, after
    return None


def _replace_human_text(value: Any, before: str, after: str, *, key: str = "") -> tuple[Any, int]:
    return replace_editable_text(value, before, after, key=key)


async def _generate_lesson_plan_candidates(
    *,
    course_id: str,
    plan: CourseEvolutionPlan,
    migrations: list[Any],
    repository: TeacherLessonAuthoringRepository,
    course_service: Any,
) -> list[CourseEvolutionOperation]:
    operations: list[CourseEvolutionOperation] = []
    for lesson_id, items in _group(migrations, "lesson_plan").items():
        try:
            lesson = repository.lesson(course_id, lesson_id)
            base_revision_id = str(lesson.get("working_revision_id") or "")
            if any(str(item.base_revisions.get(_migration_unit_id(item)) or base_revision_id) != base_revision_id for item in items):
                raise TeacherLessonAuthoringError("lesson_plan_revision_conflict", "教案已在分析后变化，请重新分析修改范围。")
            revision = _revision(lesson.get("revisions") or [], base_revision_id)
            candidate_plan = deepcopy(revision.get("plan") or {})
            if not base_revision_id or not candidate_plan:
                raise ValueError("当前课节没有可优化的教案工作稿")
            section_ids = list(dict.fromkeys(
                section_id
                for item in items
                for section_id in item.dependency_ids
                if section_id
            ))
            instruction = "\n".join(filter(None, [
                plan.request_text,
                "只修改被选中的教案单元，保持课时、教学目标、教学活动和评价证据一致。",
            ]))
            literal = _literal_terms(items)
            if literal:
                before, after = literal
                total_changes = 0
                for section in candidate_plan.get("sections") or []:
                    if not isinstance(section, dict):
                        continue
                    section_id = str(section.get("node_id") or section.get("section_node_id") or "")
                    if section_ids and section_id not in section_ids:
                        continue
                    replaced, count = _replace_human_text(section, before, after)
                    section.clear()
                    section.update(replaced)
                    total_changes += count
                if not total_changes:
                    raise ValueError("教案已不再包含待替换术语")
            else:
                for section_id in section_ids or [""]:
                    optimized = await course_service.optimize_teacher_lesson_plan(
                        plan=candidate_plan,
                        instruction=instruction,
                        section_node_id=section_id,
                        material_evidence=[],
                    )
                    candidate_plan = deepcopy(optimized.get("plan") or candidate_plan)
            candidate = repository.save_ai_candidate(
                course_id,
                lesson_id,
                base_revision_id=base_revision_id,
                instruction=plan.request_text,
                section_node_id=section_ids[0] if len(section_ids) == 1 else "",
                plan=candidate_plan,
                material_asset_ids=[],
            )
            for item in items:
                section_id = next(iter(item.dependency_ids), "")
                before_section = next((v for v in (revision.get("plan") or {}).get("sections") or [] if str(v.get("node_id") or v.get("section_node_id") or "") == section_id), {})
                after_section = next((v for v in candidate_plan.get("sections") or [] if str(v.get("node_id") or v.get("section_node_id") or "") == section_id), {})
                item.metadata["before_content"] = readable_text(before_section)
                item.metadata["after_content"] = readable_text(after_section)
                item.metadata["after_preview"] = _compact(item.metadata["after_content"])
                item.metadata["change_count"] = readable_text(before_section).count(literal[0]) if literal else 1
            operations.append(_operation(
                plan=plan,
                domain="lesson_plan",
                migrations=items,
                payload={
                    "candidate_id": candidate["candidate_id"],
                    "lesson_unit_id": lesson_id,
                    "base_revision_id": base_revision_id,
                    "previous_revision_id": base_revision_id,
                },
            ))
        except Exception as error:  # noqa: BLE001 - one lesson must not abort the course
            _fail(items, error)
    return operations


async def _generate_script_candidates(
    *,
    course_data: dict[str, Any],
    course_id: str,
    user_id: str,
    plan: CourseEvolutionPlan,
    migrations: list[Any],
    repository: TeacherLessonAuthoringRepository,
    course_service: Any,
) -> list[CourseEvolutionOperation]:
    operations: list[CourseEvolutionOperation] = []
    for lesson_id, items in _group(migrations, "script").items():
        try:
            lesson = repository.lesson(course_id, lesson_id)
            base_revision_id = str(lesson.get("working_script_revision_id") or "")
            if any(str(item.base_revisions.get(_migration_unit_id(item)) or base_revision_id) != base_revision_id for item in items):
                raise TeacherLessonAuthoringError("lesson_script_revision_conflict", "讲义已在分析后变化，请重新分析修改范围。")
            revision = _revision(lesson.get("script_revisions") or [], base_revision_id)
            if not base_revision_id or not revision:
                raise ValueError("当前课节没有可优化的讲义工作稿")
            upstream_items = [m for m in plan.teacher_change_planning.unit_migrations if m.asset_type == "lesson_plan" and str(m.metadata.get("parent_id") or "") == lesson_id and m.migration_id in set((plan.impact_summary.get("scope_review") or {}).get("selected_migration_ids") or []) and m.disposition not in {"reuse_exact", "reuse_rebind"}]
            upstream_operation = next((op for op in plan.operations if op.payload.get("domain") == "lesson_plan" and op.payload.get("lesson_unit_id") == lesson_id), None)
            if upstream_items and upstream_operation is None:
                raise ValueError("本讲教案候选尚未成功，请先重试教案，再生成讲义候选")
            upstream_candidate = next((v for v in lesson.get("ai_candidates") or [] if upstream_operation and v.get("candidate_id") == upstream_operation.payload.get("candidate_id")), None)
            source_plan = deepcopy((upstream_candidate or {}).get("plan") or _revision(lesson.get("revisions") or [], str(revision.get("source_lesson_plan_revision_id") or "")).get("plan") or {})
            source_context = readable_text(source_plan)
            scope = lesson_scope(course_data, lesson_id)
            outline_by_id = {
                str(item.get("node_id") or ""): item for item in scope["sections"]
            }
            target_section_ids = list(dict.fromkeys(
                section_id
                for item in items
                for section_id in item.dependency_ids
                if section_id
            ))
            target_block_ids = list(dict.fromkeys(
                parts[2]
                for item in items
                if len(parts := _migration_unit_id(item).split(":", 2)) == 3
                and parts[0] == "script"
                and parts[2]
            ))
            section_replacements: dict[str, str] = {}
            block_replacements: dict[str, dict[str, Any]] = {}
            literal = _literal_terms(items)
            for section_id in target_section_ids:
                section = next(
                    (
                        item for item in revision.get("sections") or []
                        if str(item.get("section_node_id") or "") == section_id
                    ),
                    None,
                )
                if not isinstance(section, dict):
                    continue
                section_blocks = [
                    block
                    for block in section.get("blocks") or []
                    if isinstance(block, dict)
                ]
                targeted_blocks = [
                    block
                    for block in section_blocks
                    if str(block.get("block_id") or "") in set(target_block_ids)
                ]
                if target_block_ids:
                    for block in targeted_blocks:
                        block_id = str(block.get("block_id") or "")
                        source_content = (
                            str(block.get("content") or "").strip()
                            or teacher_script_blocks_to_markdown([block])
                        )
                        if literal:
                            before, after = literal
                            replaced, count = _replace_human_text(
                                block,
                                before,
                                after,
                            )
                            if not count:
                                continue
                            block_replacements[block_id] = replaced
                            continue
                        result = await course_service.rewrite_selection(
                            course_id=course_id,
                            node=(
                                outline_by_id.get(section_id)
                                or {"node_id": section_id, "title": section.get("title")}
                            ),
                            selected_text=source_content,
                            node_content=source_content,
                            heading_path=[
                                str(section.get("title") or ""),
                                str(block.get("title") or ""),
                            ],
                            user_requirement="\n".join(filter(None, [
                                plan.request_text,
                                "只改写当前讲义块，保留它的职责、稳定标识和同小节其他讲义块。",
                                "改成教师可以直接在课堂上说出口的自然表达，不写系统内部语言，不虚构资料或课堂事实。",
                            ])),
                            action_type="rewrite",
                            course_context=str({
                                "lesson_sections": [
                                    item.get("title") for item in scope["sections"]
                                ],
                                "teacher_requirements": revision.get("requirements") or "",
                                "current_lesson_plan": source_context,
                                "script_block_id": block_id,
                                "script_block_role": block.get("role") or "",
                            }),
                            user_id=user_id,
                        )
                        replacement = str(result.get("replacement_text") or "").strip()
                        if not replacement:
                            raise ValueError("讲义块候选为空")
                        candidate_block = deepcopy(block)
                        candidate_block["content"] = replacement
                        block_replacements[block_id] = candidate_block
                    continue
                source_content = str(section.get("content") or "").strip() or teacher_script_blocks_to_markdown(
                    section_blocks
                )
                if literal:
                    before, after = literal
                    if before not in source_content:
                        continue
                    section_replacements[section_id] = source_content.replace(before, after)
                    continue
                headings = [
                    str(block.get("title") or "").strip()
                    for block in section.get("blocks") or []
                    if isinstance(block, dict) and str(block.get("title") or "").strip()
                ]
                result = await course_service.rewrite_selection(
                    course_id=course_id,
                    node=outline_by_id.get(section_id) or {"node_id": section_id, "title": section.get("title")},
                    selected_text=source_content,
                    node_content=source_content,
                    heading_path=[str(section.get("title") or "")],
                    user_requirement="\n".join(filter(None, [
                        plan.request_text,
                        "改成教师可以直接在课堂上说出口的自然表达，不写系统内部语言，不虚构资料或课堂事实。",
                        (
                            "保留并仅使用这些二级标题，顺序与名称不变："
                            + "、".join(f"## {title}" for title in headings)
                        ) if headings else "",
                    ])),
                    action_type="rewrite",
                    course_context=str({
                        "lesson_sections": [item.get("title") for item in scope["sections"]],
                        "teacher_requirements": revision.get("requirements") or "",
                                "current_lesson_plan": source_context,
                    }),
                    user_id=user_id,
                )
                replacement = str(result.get("replacement_text") or "").strip()
                if not replacement:
                    raise ValueError("讲义候选为空")
                section_replacements[section_id] = replacement
            if not section_replacements and not block_replacements:
                raise ValueError("没有找到可修改的讲义块")
            first_section_id = (
                next(iter(section_replacements))
                if section_replacements
                else target_section_ids[0]
            )
            first_replacement = (
                section_replacements[first_section_id]
                if section_replacements
                else str(next(iter(block_replacements.values())).get("content") or "")
            )
            candidate = repository.save_script_ai_candidate(
                course_id,
                lesson_id,
                base_revision_id=base_revision_id,
                section_node_id=first_section_id,
                instruction=plan.request_text,
                replacement_text=first_replacement,
                section_replacements=section_replacements,
                block_replacements=block_replacements,
                source_lesson_plan_revision_id=str(revision.get("source_lesson_plan_revision_id") or ""),
                source_lesson_plan_candidate_id=str((upstream_candidate or {}).get("candidate_id") or ""),
                candidate_group_id=plan.change_set_id,
                material_asset_ids=[],
            )
            for item in items:
                parts = _migration_unit_id(item).split(":", 2)
                block_id = parts[2] if len(parts) == 3 and parts[0] == "script" else ""
                section_id = next(
                    (
                        value
                        for value in item.dependency_ids
                        if value in section_replacements
                    ),
                    first_section_id,
                )
                item.metadata["after_content"] = readable_text(block_replacements[block_id]) if block_id in block_replacements else section_replacements.get(section_id, "")
                item.metadata["after_preview"] = _compact(item.metadata["after_content"])
                item.metadata["change_count"] = str(item.metadata.get("before_content") or item.metadata.get("before_preview") or "").count(literal[0]) if literal else 1
            operations.append(_operation(
                plan=plan,
                domain="script",
                migrations=items,
                payload={
                    "candidate_id": candidate["candidate_id"],
                    "lesson_unit_id": lesson_id,
                    "base_revision_id": base_revision_id,
                    "previous_revision_id": base_revision_id,
                },
            ))
        except Exception as error:  # noqa: BLE001
            _fail(items, error)
    return operations


async def _generate_ppt_candidates(
    *,
    course_id: str,
    plan: CourseEvolutionPlan,
    migrations: list[Any],
    repository: TeacherLessonAuthoringRepository,
    representation_repository: TeachingRepresentationRepository,
    course_service: Any,
) -> list[CourseEvolutionOperation]:
    operations: list[CourseEvolutionOperation] = []
    for lesson_id, items in _group(migrations, "ppt").items():
        try:
            first = items[0].metadata or {}
            synthetic_course_id = str(first.get("synthetic_course_id") or "")
            representation_id = str(first.get("representation_id") or "")
            base_spec_id = str(first.get("spec_id") or "")
            if not synthetic_course_id or not representation_id or not base_spec_id:
                lesson = repository.lesson(course_id, lesson_id)
                asset = next(
                    (
                        value for value in lesson.get("ppt_assets") or []
                        if isinstance(value, dict)
                        and value.get("role") == "primary"
                        and value.get("engine") == "slide_deck_v6"
                    ),
                    None,
                )
                if not isinstance(asset, dict):
                    raise ValueError("当前课节没有 V6 PPT 工作稿")
                binding = _revision(
                    asset.get("v6_revisions") or [],
                    str(asset.get("working_v6_revision_id") or ""),
                )
                synthetic_course_id = str(asset.get("synthetic_course_id") or binding.get("synthetic_course_id") or "")
                representation_id = str(asset.get("working_representation_id") or binding.get("representation_id") or "")
                base_spec_id = str(binding.get("spec_id") or "")
            registry = representation_repository.load(synthetic_course_id)
            representation = next(
                (item for item in registry.representations if item.representation_id == representation_id),
                None,
            )
            spec = next(
                (item for item in registry.specs if item.spec_id == base_spec_id),
                None,
            )
            if representation is None or spec is None:
                raise ValueError("当前 PPT 版本不存在")
            pages = list((spec.payload.get("content") or {}).get("pages") or [])
            page_changes: list[dict[str, Any]] = []
            ready_items: list[Any] = []
            by_page = {
                _migration_unit_id(item).split(":", 2)[-1]: item for item in items
            }
            for page_id, migration in by_page.items():
                page = next(
                    (item for item in pages if str(item.get("page_id") or "") == page_id),
                    None,
                )
                if not isinstance(page, dict):
                    raise ValueError(f"PPT 页面 {page_id} 不存在")
                literal = _literal_terms([migration])
                if literal:
                    before, after = literal
                    candidate_page = {
                        "page_id": page_id,
                        "title": str(page.get("title") or ""),
                        "subtitle": "",
                        "key_message": "",
                    }
                    changed_fields: list[str] = []
                    if before in candidate_page["title"]:
                        candidate_page["title"] = candidate_page["title"].replace(before, after)
                        changed_fields.append("title")
                    region_changes = []
                    for region in page.get("regions") or []:
                        if not isinstance(region, dict):
                            continue
                        content = str(region.get("content") or "")
                        if before in content:
                            region_changes.append({
                                "region_id": str(region.get("region_id") or ""),
                                "content": content.replace(before, after),
                            })
                    if not changed_fields and not region_changes:
                        migration.candidate_status = "not_required"
                        migration.metadata["candidate_note"] = "当前可编辑页面文字已无待替换术语"
                        continue
                else:
                    optimized = await course_service.optimize_teacher_lesson_v6_page(
                        page=page,
                        instruction=plan.request_text,
                    )
                    candidate_page = deepcopy(optimized.get("page") or {})
                    changed_fields = list(optimized.get("changed_fields") or [])
                    region_changes = []
                page_changes.append({
                    "page_id": page_id,
                    "candidate_page": candidate_page,
                    "changed_fields": changed_fields,
                    "region_changes": region_changes,
                })
                ready_items.append(migration)
                migration.metadata["after_preview"] = _compact(candidate_page)
                migration.metadata["change_count"] = len(changed_fields) + len(region_changes)
            if not page_changes:
                continue
            first_change = page_changes[0]
            candidate = repository.save_v6_ppt_ai_candidate(
                course_id,
                lesson_id,
                representation_id=representation_id,
                base_spec_id=spec.spec_id,
                base_spec_revision=spec.revision,
                page_id=str(first_change["page_id"]),
                instruction=plan.request_text,
                candidate_page=first_change["candidate_page"],
                changed_fields=first_change["changed_fields"],
                page_changes=page_changes,
            )
            operations.append(_operation(
                plan=plan,
                domain="ppt",
                migrations=ready_items,
                payload={
                    "candidate_id": candidate["candidate_id"],
                    "lesson_unit_id": lesson_id,
                    "synthetic_course_id": synthetic_course_id,
                    "representation_id": representation_id,
                    "base_spec_id": spec.spec_id,
                    "base_spec_revision": spec.revision,
                    "previous_spec_id": spec.spec_id,
                },
            ))
        except Exception as error:  # noqa: BLE001
            _fail(items, error)
    return operations


async def _generate_question_bank_candidate(
    *,
    course_data: dict[str, Any],
    course_id: str,
    user_id: str,
    plan: CourseEvolutionPlan,
    migrations: list[Any],
    repository: QuestionBankRepository,
    course_service: Any,
) -> list[CourseEvolutionOperation]:
    items = [item for item in migrations if item.asset_type == "question_bank"]
    if not items:
        return []
    try:
        current = repository.load_bundle(course_id)
        if not current:
            raise ValueError("当前课程没有可修改的题库")
        candidate_bundle = deepcopy(current)
        changed_revision_ids: list[str] = []
        candidate_migrations: list[Any] = []
        for migration in items:
            item_id = _migration_unit_id(migration).split(":", 1)[-1]
            revision_id = str((migration.metadata or {}).get("item_revision_id") or "")
            current_item = next(
                (
                    item for item in candidate_bundle.get("items") or []
                    if (
                        (revision_id and str(item.get("revision_id") or "") == revision_id)
                        or (not revision_id and str(item.get("item_id") or item.get("question_id") or "") == item_id)
                    )
                ),
                None,
            )
            if not isinstance(current_item, dict):
                raise ValueError("题目已变化，请重新分析")
            revision_id = str(current_item.get("revision_id") or "")
            if migration.disposition == "retire":
                candidate_bundle["items"] = [
                    item for item in candidate_bundle.get("items") or []
                    if str(item.get("revision_id") or "") != revision_id
                ]
                migration.metadata["after_preview"] = "本题将从题库工作版中移除"
                migration.metadata["change_count"] = 1
                candidate_migrations.append(migration)
                continue
            prompt = str(current_item.get("prompt") or current_item.get("stem") or "").strip()
            literal = _literal_terms([migration])
            if literal:
                before, after = literal
                patch = {
                    field: str(current_item.get(field) or "").replace(before, after)
                    for field in ("prompt", "explanation", "deliverable")
                    if before in str(current_item.get(field) or "")
                }
                if not patch and before in prompt:
                    patch = {"prompt": prompt.replace(before, after)}
                replacement = str(patch.get("prompt") or patch.get("explanation") or patch.get("deliverable") or "")
                if not patch:
                    migration.candidate_status = "not_required"
                    migration.metadata["candidate_note"] = "当前可编辑题面已无待替换术语"
                    continue
            else:
                result = await course_service.rewrite_selection(
                    course_id=course_id,
                    node={
                        "node_id": str(current_item.get("node_id") or "question_bank"),
                        "title": str(current_item.get("title") or "题目"),
                    },
                    selected_text=prompt,
                    node_content=prompt,
                    heading_path=["题库", str(current_item.get("question_type") or "题目")],
                    user_requirement="\n".join(filter(None, [
                        plan.request_text,
                        "只改题面表达，不改正确答案、计分逻辑和已确认的事实边界。",
                    ])),
                    action_type="rewrite",
                    course_context=str({
                        "course_title": course_data.get("title") or course_data.get("course_name"),
                        "question_type": current_item.get("question_type"),
                    }),
                    user_id=user_id,
                )
                replacement = str(result.get("replacement_text") or "").strip()
                patch = {"prompt": replacement}
            if not replacement:
                raise ValueError("题面候选为空")
            candidate_bundle = revise_question_bank_item(
                candidate_bundle,
                revision_id,
                patch=patch,
                editor_id=user_id,
            )
            revised = next(
                (
                    item for item in candidate_bundle.get("items") or []
                    if str(item.get("parent_revision_id") or "") == revision_id
                ),
                None,
            )
            if not isinstance(revised, dict) or not (revised.get("quality_report") or {}).get("passed"):
                raise ValueError("题面候选未通过题库质量门")
            changed_revision_ids.append(str(revised.get("revision_id") or ""))
            candidate_migrations.append(migration)
            migration.metadata["after_preview"] = _compact(replacement)
            migration.metadata["change_count"] = 1
        if not candidate_migrations:
            return []
        stored = repository.save_bundle(course_id, candidate_bundle, activate=False)
        operation = _operation(
            plan=plan,
            domain="question_bank",
            migrations=candidate_migrations,
            payload={
                "candidate_revision_id": stored["bundle_revision_id"],
                "previous_revision_id": current["bundle_revision_id"],
                "changed_item_revision_ids": changed_revision_ids,
            },
        )
        return [operation]
    except Exception as error:  # noqa: BLE001
        _fail(items, error)
        return []


async def _generate_teacher_asset_candidates_through_shared_executor(
    *,
    course_data: dict[str, Any],
    course_id: str,
    user_id: str,
    plan: CourseEvolutionPlan,
    migrations: list[Any],
    repository: TeacherLessonAuthoringRepository,
    course_service: Any,
    on_checkpoint: Any = None,
) -> tuple[list[CourseEvolutionOperation], dict[str, Any]]:
    """Create lesson-plan/script candidates under the shared rebuild contract.

    The shared executor remains the single owner of selection, per-object
    receipts and last-good lifecycle state. The existing teacher-course
    candidate builders remain the only writers of authoring candidates.
    """
    from downstream_rebuild import execute_rebuild, plan_rebuild

    selected = [
        item
        for item in migrations
        if item.asset_type in {"lesson_plan", "script"}
    ]
    downstream = {
        "schema_version": "teaching_plan_downstream_v1",
        "source_plan_revision_id": plan.change_set_id,
        "items": [
            {
                "type": (
                    "lesson_plan_section"
                    if item.asset_type == "lesson_plan"
                    else "script_block"
                ),
                "id": _migration_unit_id(item),
                "section_id": str((item.dependency_ids or [""])[0]),
                "state": "rebuild_required",
                "impact_group": "needs_regeneration",
                "reason": item.reason,
                "last_available": (
                    {
                        "type": item.unit_type,
                        "id": _migration_unit_id(item),
                        "revision": str(
                            item.base_revisions.get(_migration_unit_id(item)) or ""
                        ),
                        "readable": True,
                    }
                    if item.base_revisions.get(_migration_unit_id(item))
                    else None
                ),
            }
            for item in selected
        ],
    }
    work_ids = {
        str(item.get("id") or "")
        for item in plan_rebuild(downstream)
    }
    actionable = [
        item for item in selected if _migration_unit_id(item) in work_ids
    ]
    operations: list[CourseEvolutionOperation] = []
    results: dict[tuple[str, str], dict[str, Any]] = {}

    async def generate_group(asset_type: str, grouped: list[Any]) -> None:
        generated = (
            await _generate_lesson_plan_candidates(
                course_id=course_id,
                plan=plan,
                migrations=grouped,
                repository=repository,
                course_service=course_service,
            )
            if asset_type == "lesson_plan"
            else await _generate_script_candidates(
                course_data=course_data,
                course_id=course_id,
                user_id=user_id,
                plan=plan,
                migrations=grouped,
                repository=repository,
                course_service=course_service,
            )
        )
        operation = generated[0] if generated else None
        if operation is not None:
            operations.extend(generated)
        if on_checkpoint is not None:
            await on_checkpoint(generated)
        for migration in grouped:
            item_type = (
                "lesson_plan_section"
                if asset_type == "lesson_plan"
                else "script_block"
            )
            results[(item_type, _migration_unit_id(migration))] = (
                {
                    "status": "succeeded",
                    "revision": str(
                        (operation.payload or {}).get("candidate_id") or ""
                    ),
                }
                if operation is not None
                else {
                    "status": "failed",
                    "error": str(
                        migration.metadata.get("candidate_error")
                        or "教师资产候选生成失败"
                    ),
                }
            )

    for grouped in _group(actionable, "lesson_plan").values():
        await generate_group("lesson_plan", grouped)
    for grouped in _group(actionable, "script").values():
        await generate_group("script", grouped)

    def cached(entry: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(
            results.get(
                (str(entry.get("type") or ""), str(entry.get("id") or "")),
                {"status": "failed", "error": "定向重建结果未生成"},
            )
        )

    execution = execute_rebuild(
        downstream,
        runners={"lesson_plan": cached, "script": cached},
        only_ids=sorted(work_ids),
        candidate_only=True,
    )
    return operations, execution


async def generate_teacher_course_change_candidates(
    *,
    course_data: dict[str, Any],
    user_id: str,
    change_set_id: str,
    repository: CourseEvolutionRepository,
    authoring_repository: TeacherLessonAuthoringRepository,
    representation_repository: TeachingRepresentationRepository,
    question_bank_repository: QuestionBankRepository,
    course_service: Any,
    job_id: str = "",
    on_progress: Any = None,
) -> Any:
    """Generate every reviewed downstream candidate through its owning store."""
    course_id = str(course_data.get("course_id") or "")
    state = repository.load(user_id, course_id)
    plan = next(
        (item for item in state.change_sets if item.change_set_id == change_set_id),
        None,
    )
    if plan is None:
        raise KeyError(change_set_id)
    if plan.status != "pending":
        raise ValueError("当前方案已不能生成新候选")
    migrations = _selected_migrations(plan)
    expected_review_revision = plan.review_revision
    attempt_id = uuid.uuid4().hex
    def claim(current: Any) -> Any:
        target = next(p for p in current.change_sets if p.change_set_id == change_set_id)
        if target.status != "pending" or target.review_revision != expected_review_revision:
            raise ValueError("方案已变化，请重新分析")
        if job_id and target.generation_job_id != job_id:
            raise ValueError("生成任务已变化")
        target.generation_attempt_id = attempt_id
        target.generation_status = "generating"
        return current
    repository.update(user_id, course_id, claim)
    plan.generation_attempt_id = attempt_id
    selected_ids = [item.migration_id for item in migrations]
    existing_operation_ids = {item.operation_id for item in plan.operations}
    for migration in migrations:
        existing_operation_id = str(migration.metadata.get("operation_id") or "")
        if existing_operation_id and existing_operation_id in existing_operation_ids:
            migration.candidate_status = "ready"
            continue
        if migration.asset_type == "outline" or migration.disposition in {"reuse_exact", "reuse_rebind"}:
            migration.candidate_status = "not_required"
            migration.metadata.pop("operation_id", None)
            continue
        if migration.disposition == "blocked":
            _fail([migration], "当前单元的影响无法安全判定，需要教师先补充要求")
            continue
        if migration.disposition == "retire" and migration.asset_type != "question_bank":
            _fail([migration], "该资产不支持脱离上游结构单独删除，请先调整课程结构")
            continue
        if migration.candidate_status == "failed" and (migration.metadata.get("candidate_error_detail") or {}).get("retryable") is False:
            continue
        migration.candidate_status = "not_started"
        migration.metadata.pop("candidate_error", None)
        migration.metadata.pop("candidate_error_detail", None)
        migration.metadata.pop("operation_id", None)
        migration.metadata.pop("after_preview", None)

    operations: list[CourseEvolutionOperation] = []
    def persist(*, partial: bool = False) -> Any:
        # Exact course-document operations were already compiled during analysis.
        preserved = [
            operation for operation in plan.operations
            if (
                operation.operation_id in existing_operation_ids
                or operation.operation_type != DOMAIN_OPERATION_TYPE
                or str((operation.payload or {}).get("action") or "")
                == "rebind_section_references"
            )
        ]
        plan.operations = [*preserved, *operations]
        plan.allowed_scopes = ["current"] if plan.operations else []
        reviewed_operation_ids = list(dict.fromkeys([
            str(item.metadata.get("operation_id") or "")
            for item in migrations
            if item.disposition not in {"reuse_exact", "reuse_rebind"}
            and item.metadata.get("operation_id")
        ]))
        if (
            plan.teacher_change_planning is not None
            and plan.teacher_change_planning.structure_review_status == "confirmed"
        ):
            reviewed_operation_ids.extend(
                item.operation_id
                for item in plan.operations
                if (
                    item.operation_type in {
                        "RESEQUENCE_COURSE_PATH",
                        "REBUILD_COURSE_OUTLINE",
                    }
                    or str((item.payload or {}).get("action") or "")
                    == "rebind_section_references"
                )
            )
        reviewed_operation_ids = list(dict.fromkeys(reviewed_operation_ids))
        plan.selected_operation_ids = reviewed_operation_ids
        plan.excluded_operation_ids = [
            item.operation_id
            for item in plan.operations
            if item.operation_id not in reviewed_operation_ids
        ]
        plan.impact_summary.setdefault("scope_review", {})["selected_operation_ids"] = reviewed_operation_ids
        ready = sum(item.candidate_status in {"ready", "not_required"} for item in migrations)
        failed = sum(item.candidate_status == "failed" for item in migrations)
        planning = plan.teacher_change_planning
        if planning is not None:
            planning.status = "candidate_ready" if plan.operations else "blocked"
            planning.updated_at = _now()
        plan.generation_status = "generating" if partial else ("ready" if plan.operations else "failed")
        plan.impact_summary["affected_units"] = [
            {
                **item,
                "candidate_status": next(
                    migration.candidate_status
                    for migration in planning.unit_migrations
                    if migration.migration_id == item.get("migration_id")
                ),
                "operation_id": str(next(
                    migration.metadata.get("operation_id") or ""
                    for migration in planning.unit_migrations
                    if migration.migration_id == item.get("migration_id")
                )),
                "after_content": next((m.metadata.get("after_content") or "" for m in planning.unit_migrations if m.migration_id == item.get("migration_id")), ""),
                "after_preview": str(next(
                    migration.metadata.get("after_preview") or ""
                    for migration in planning.unit_migrations
                    if migration.migration_id == item.get("migration_id")
                )),
                "change_count": int(next(
                    migration.metadata.get("change_count") or 0
                    for migration in planning.unit_migrations
                    if migration.migration_id == item.get("migration_id")
                )),
                "candidate_error_detail": next((m.metadata.get("candidate_error_detail") or {} for m in planning.unit_migrations if m.migration_id == item.get("migration_id")), {}),
            "candidate_error": str(next(
                    migration.metadata.get("candidate_error") or ""
                    for migration in planning.unit_migrations
                    if migration.migration_id == item.get("migration_id")
                )),
            }
            for item in plan.impact_summary.get("affected_units") or []
        ]
        plan.impact_summary["candidate_bundle"] = {
            "schema_version": CANDIDATE_BUNDLE_SCHEMA,
            "operation_count": len(plan.operations),
            "operation_ids": [item.operation_id for item in plan.operations],
            "domain_operation_count": len(operations),
            "ready_migration_count": ready,
            "failed_migration_count": failed,
            "selected_migration_ids": selected_ids,
            "generated_at": _now(),
        }
        plan.impact_summary["application_capability"] = "course_evolution_operation_group"
        plan.updated_at = _now()

        def save_if_scope_unchanged(latest: Any) -> Any:
            target = next(
                (item for item in latest.change_sets if item.change_set_id == change_set_id),
                None,
            )
            if target is None:
                raise KeyError(change_set_id)
            if (target.status != "pending" or target.review_revision != expected_review_revision
                    or target.generation_attempt_id != attempt_id
                    or (job_id and target.generation_job_id != job_id)):
                raise ValueError("方案已修改或放弃，迟到的候选未保存")
            latest_selected = list((target.impact_summary.get("scope_review") or {}).get("selected_migration_ids") or [])
            if set(latest_selected) != set(selected_ids):
                raise ValueError("影响范围已变化，请重新生成候选")
            index = latest.change_sets.index(target)
            latest.change_sets[index] = plan.model_copy(deep=True)
            latest.updated_at = _now()
            return latest

        return repository.update(user_id, course_id, save_if_scope_unchanged)
    async def checkpoint(generated: list[CourseEvolutionOperation]) -> None:
        operations.extend(generated)
        persist(partial=True)
        if on_progress is not None:
            await on_progress(sum(m.candidate_status != "not_started" for m in migrations), len(migrations))

    persist(partial=True)
    actionable = [item for item in migrations if item.candidate_status == "not_started"]
    teacher_asset_operations, teacher_asset_rebuild = (
        await _generate_teacher_asset_candidates_through_shared_executor(
            course_data=course_data,
            course_id=course_id,
            user_id=user_id,
            plan=plan,
            migrations=actionable,
            repository=authoring_repository,
            course_service=course_service,
            on_checkpoint=checkpoint,
        )
    )
    plan.impact_summary["teacher_asset_targeted_rebuild"] = teacher_asset_rebuild
    operations.extend(await _generate_ppt_candidates(
        course_id=course_id,
        plan=plan,
        migrations=actionable,
        repository=authoring_repository,
        representation_repository=representation_repository,
        course_service=course_service,
    ))
    operations.extend(await _generate_question_bank_candidate(
        course_data=course_data,
        course_id=course_id,
        user_id=user_id,
        plan=plan,
        migrations=actionable,
        repository=question_bank_repository,
        course_service=course_service,
    ))

    return persist()


def _apply_script_candidate(
    *,
    course_data: dict[str, Any],
    user_id: str,
    course_id: str,
    lesson_id: str,
    candidate_id: str,
    repository: TeacherLessonAuthoringRepository,
    result_revision_id_override: str = "",
) -> str:
    lesson = repository.lesson(course_id, lesson_id)
    candidate = repository.script_ai_candidate(course_id, lesson_id, candidate_id)
    base_revision_id = str(candidate.get("base_revision_id") or "")
    if str(lesson.get("working_script_revision_id") or "") != base_revision_id:
        raise TeacherLessonAuthoringError(
            "lesson_script_revision_conflict", "讲义工作稿已变化，不能覆盖新修改。"
        )
    base = _revision(lesson.get("script_revisions") or [], base_revision_id)
    plan_revision_id = str(candidate.get("source_lesson_plan_revision_id") or "")
    source_candidate_id = str(candidate.get("source_lesson_plan_candidate_id") or "")
    if source_candidate_id:
        source_candidate = next((v for v in lesson.get("ai_candidates") or [] if v.get("candidate_id") == source_candidate_id), {})
        if source_candidate.get("status") != "accepted" or not source_candidate.get("result_revision_id"):
            raise TeacherLessonAuthoringError("lesson_plan_candidate_dependency_pending", "本讲教案候选尚未应用，讲义候选已保留。")
        plan_revision_id = str(source_candidate["result_revision_id"])
        if str(lesson.get("working_revision_id") or "") != plan_revision_id:
            raise TeacherLessonAuthoringError("lesson_plan_revision_conflict", "本讲教案已有后续修改，请重新分析。")
    plan_revision = _revision(lesson.get("revisions") or [], plan_revision_id)
    plan_sections = {
        str(item.get("node_id") or item.get("section_node_id") or ""): item
        for item in (plan_revision.get("plan") or {}).get("sections") or []
        if isinstance(item, dict)
    }
    outline_sections = {
        str(item.get("node_id") or ""): item for item in lesson_scope(course_data, lesson_id)["sections"]
    }
    replacements = dict(candidate.get("section_replacements") or {})
    block_replacements = {
        str(block_id): deepcopy(block)
        for block_id, block in (candidate.get("block_replacements") or {}).items()
        if str(block_id) and isinstance(block, dict)
    }
    if not replacements and not block_replacements:
        replacements[str(candidate.get("section_node_id") or "")] = str(candidate.get("replacement_text") or "")
    normalized_sections: list[dict[str, Any]] = []
    for section in base.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("section_node_id") or "")
        candidate_section = deepcopy(section)
        if block_replacements:
            candidate_section["blocks"] = [
                deepcopy(
                    block_replacements.get(str(block.get("block_id") or ""))
                    or block
                )
                for block in section.get("blocks") or []
                if isinstance(block, dict)
            ]
        elif section_id in replacements:
            candidate_section.pop("blocks", None)
            candidate_section["content"] = str(replacements[section_id]).strip()
        contract = compile_teacher_script_module_contract(
            outline_sections.get(section_id) or {},
            plan_sections.get(section_id) or {},
        )
        normalized = normalize_teacher_script_section(candidate_section, contract)
        normalized["quality_report"] = validate_teacher_script_section(normalized, contract)
        normalized_sections.append(normalized)
    saved = repository.save_script_revision(
        course_id,
        lesson_id,
        normalized_sections,
        source_lesson_plan_revision_id=plan_revision_id,
        generation_source="ai_optimization",
        requirements=str(base.get("requirements") or ""),
        material_asset_ids=list(candidate.get("material_asset_ids") or base.get("material_asset_ids") or []),
        actor=user_id,
        expected_working_revision_id=base_revision_id,
        revision_id_override=result_revision_id_override,
    )
    result_revision_id = str(saved.get("working_script_revision_id") or "")
    repository.mark_script_ai_candidate(
        course_id,
        lesson_id,
        candidate_id,
        status="accepted",
        result_revision_id=result_revision_id,
    )
    return result_revision_id


def _apply_page_field(page: dict[str, Any], field: str, candidate_page: dict[str, Any]) -> None:
    if field == "title":
        page["title"] = str(candidate_page.get("title") or "").strip()
        return
    region_id = str(candidate_page.get(
        "key_region_id" if field == "key_message" else f"{field}_region_id"
    ) or "")
    if not region_id:
        raise ValueError(f"PPT 页面缺少 {field} 区域")
    region = next(
        (
            item for item in page.get("regions") or []
            if isinstance(item, dict) and str(item.get("region_id") or "") == region_id
        ),
        None,
    )
    if region is None:
        raise ValueError(f"PPT 页面的 {field} 区域已变化")
    region["content"] = str(candidate_page.get(field) or "").strip()


def _refresh_manuscript(content: dict[str, Any], course_view: dict[str, Any], plan_revision_id: str) -> str:
    deck = SlideDeckV6.model_validate({
        key: content[key] for key in SlideDeckV6.model_fields if key in content
    })
    teacher_source = dict(course_view.get("teacher_lesson_source") or {})
    previous = content.get("ppt_manuscript") if isinstance(content.get("ppt_manuscript"), dict) else {}
    manuscript = project_ppt_manuscript_from_deck_v1(
        deck,
        source_lesson_plan_revision_id=plan_revision_id,
        source_script_revision_id=str(teacher_source.get("script_revision_id") or ""),
        material_bindings=list(teacher_source.get("material_bindings") or previous.get("material_bindings") or []),
        page_material_evidence_ids={
            str(page.get("page_id") or ""): list(page.get("source_material_evidence_ids") or [])
            for page in previous.get("pages") or []
            if isinstance(page, dict) and page.get("page_id")
        },
    )
    content["ppt_manuscript"] = manuscript.model_dump(mode="json")
    return str(manuscript.manuscript_revision or "")


def _apply_ppt_candidate(
    *,
    course_data: dict[str, Any],
    course_id: str,
    lesson_id: str,
    payload: dict[str, Any],
    authoring_repository: TeacherLessonAuthoringRepository,
    representation_repository: TeachingRepresentationRepository,
) -> tuple[str, str, str]:
    lesson = authoring_repository.lesson(course_id, lesson_id)
    asset = next(
        (
            item for item in lesson.get("ppt_assets") or []
            if isinstance(item, dict) and item.get("role") == "primary" and item.get("engine") == "slide_deck_v6"
        ),
        None,
    )
    if not isinstance(asset, dict):
        raise ValueError("当前课节没有 V6 PPT")
    previous_binding_id = str(asset.get("working_v6_revision_id") or "")
    synthetic_course_id = str(payload.get("synthetic_course_id") or "")
    representation_id = str(payload.get("representation_id") or "")
    base_spec_id = str(payload.get("base_spec_id") or "")
    registry = representation_repository.load(synthetic_course_id)
    original_registry = registry.model_copy(deep=True)
    representation = next(
        (item for item in registry.representations if item.representation_id == representation_id),
        None,
    )
    spec = next((item for item in registry.specs if item.spec_id == base_spec_id), None)
    if representation is None or spec is None or representation.spec_id != base_spec_id:
        raise ValueError("PPT 工作稿已变化")
    candidate = authoring_repository.pending_v6_ppt_ai_candidate(
        course_id,
        lesson_id,
        representation_id=representation_id,
        spec_id=base_spec_id,
        spec_revision=str(payload.get("base_spec_revision") or ""),
    )
    if not isinstance(candidate, dict) or candidate.get("candidate_id") != payload.get("candidate_id"):
        raise ValueError("PPT 候选已过期")
    edited_payload = deepcopy(spec.payload)
    content = edited_payload.get("content") or {}
    pages = content.get("pages") if isinstance(content.get("pages"), list) else []
    changes = list(candidate.get("page_changes") or []) or [{
        "page_id": candidate.get("page_id"),
        "candidate_page": candidate.get("candidate_page") or {},
        "changed_fields": candidate.get("changed_fields") or [],
    }]
    for change in changes:
        page = next(
            (item for item in pages if str(item.get("page_id") or "") == str(change.get("page_id") or "")),
            None,
        )
        if not isinstance(page, dict):
            raise ValueError("PPT 页面已变化")
        candidate_page = change.get("candidate_page") or {}
        for field in change.get("changed_fields") or []:
            if field in {"title", "subtitle", "key_message"}:
                _apply_page_field(page, field, candidate_page)
        for region_change in change.get("region_changes") or []:
            region_id = str(region_change.get("region_id") or "")
            region = next(
                (
                    item for item in page.get("regions") or []
                    if isinstance(item, dict) and str(item.get("region_id") or "") == region_id
                ),
                None,
            )
            if not region_id or region is None:
                raise ValueError("PPT 页面内容区域已变化")
            region["content"] = str(region_change.get("content") or "")
    plan_revision_id = str(lesson.get("working_revision_id") or "")
    script_revision_id = str(lesson.get("working_script_revision_id") or "")
    plan_revision = _revision(lesson.get("revisions") or [], plan_revision_id)
    script_revision = _revision(lesson.get("script_revisions") or [], script_revision_id)
    if (
        str(lesson.get("source_state") or "current") != "current"
        or not plan_revision_id
        or not script_revision_id
        or str(script_revision.get("source_lesson_plan_revision_id") or "")
        != plan_revision_id
    ):
        raise ValueError("教案或讲义已变化，请基于当前内容重新生成 PPT 修改候选")
    _document, course_view, _synthetic = teacher_lesson_v6_source(
        course_data,
        lesson_unit_id=lesson_id,
        plan_revision=plan_revision,
        script_revision=script_revision,
    )
    manuscript_revision = _refresh_manuscript(content, course_view, plan_revision_id)
    now = _now()
    spec_revision = stable_hash(edited_payload, prefix="tsr_")
    edited_spec = TeachingRepresentationSpec(
        spec_id=stable_hash({
            "course_id": spec.course_id,
            "representation_type": spec.representation_type,
            "source_bindings": [item.model_dump(mode="json") for item in spec.source_bindings],
            "payload": edited_payload,
        }, prefix="trs_"),
        course_id=spec.course_id,
        representation_type=spec.representation_type,
        variant_key=spec.variant_key,
        source_bindings=spec.source_bindings,
        unit_bindings=spec.unit_bindings,
        payload=edited_payload,
        revision=spec_revision,
        created_at=now,
        updated_at=now,
    )
    edited_representation = representation.model_copy(deep=True)
    edited_representation.spec_id = edited_spec.spec_id
    edited_representation.semantic_fingerprint = stable_hash(content, prefix="sem_")
    edited_representation.render_fingerprint = stable_hash(
        {"spec_revision": spec_revision, "renderer": "slide_deck_v6"}, prefix="rnd_"
    )
    edited_representation.revision = stable_hash({
        "spec_revision": spec_revision,
        "source_revision_vector": edited_representation.source_revision_vector,
    }, prefix="rpr_")
    edited_representation.updated_at = now
    try:
        representation_repository.publish_spec_and_representation(
            edited_spec,
            edited_representation,
        )
        bound = authoring_repository.bind_v6_ppt_revision(
            course_id,
            lesson_id,
            source_lesson_plan_revision_id=plan_revision_id,
            source_script_revision_id=script_revision_id,
            synthetic_course_id=synthetic_course_id,
            representation_id=edited_representation.representation_id,
            spec_id=edited_spec.spec_id,
            candidate_status=str(content.get("status") or content.get("candidate_status") or "v6_ready"),
            ppt_manuscript_revision=manuscript_revision,
            ppt_manuscript_status="draft",
        )
    except Exception:
        representation_repository.save(original_registry)
        raise
    authoring_repository.mark_v6_ppt_ai_candidate(
        course_id,
        lesson_id,
        str(candidate["candidate_id"]),
        status="accepted",
        result_spec_id=edited_spec.spec_id,
    )
    return (
        edited_spec.spec_id,
        str(bound.get("working_v6_revision_id") or ""),
        previous_binding_id,
    )


def _prepare_question_bank_candidate(
    *,
    plan: CourseEvolutionPlan,
    payload: dict[str, Any],
    user_id: str,
    course_id: str,
    repository: QuestionBankRepository,
) -> dict[str, Any]:
    candidate = repository.load_bundle(
        course_id,
        str(payload.get("candidate_revision_id") or ""),
    )
    if not candidate:
        raise ValueError("题库候选已不存在")
    approved = deepcopy(candidate)
    for revision_id in payload.get("changed_item_revision_ids") or []:
        approved = review_question_bank_item(
            approved,
            str(revision_id),
            decision="approved",
            reviewer_id=user_id,
            note=f"确认全课修改方案 {plan.change_set_id}",
        )
    return refresh_question_bank_bundle(approved)


_STRUCTURE_REFERENCE_SCALAR_FIELDS = {
    "node_id",
    "section_id",
    "section_node_id",
    "lesson_unit_id",
    "parent_section_id",
    "parent_node_id",
}
_STRUCTURE_REFERENCE_LIST_FIELDS = {
    "node_ids",
    "section_ids",
    "section_node_ids",
    "lesson_unit_ids",
}


def _structure_affected_migrations(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        deepcopy(item)
        for item in payload.get("reference_migrations") or []
        if isinstance(item, dict)
        and item.get("source_section_id")
        and (
            list(item.get("target_section_ids") or [])
            != [str(item.get("source_section_id") or "")]
            or str(item.get("resolution") or "")
            in {"merge_primary", "primary_preserved"}
        )
    ]


def _contains_structure_reference(
    value: Any,
    affected_section_ids: set[str],
) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                key in _STRUCTURE_REFERENCE_SCALAR_FIELDS
                and str(item or "") in affected_section_ids
            ):
                return True
            if (
                key in _STRUCTURE_REFERENCE_LIST_FIELDS
                and isinstance(item, list)
                and affected_section_ids.intersection(str(entry) for entry in item)
            ):
                return True
            if _contains_structure_reference(item, affected_section_ids):
                return True
    elif isinstance(value, list):
        return any(
            _contains_structure_reference(item, affected_section_ids)
            for item in value
        )
    return False


def _rebind_structure_references(
    value: Any,
    primary_by_source: dict[str, str],
) -> None:
    if isinstance(value, dict):
        for key in list(value):
            item = value[key]
            if (
                key in _STRUCTURE_REFERENCE_SCALAR_FIELDS
                and isinstance(item, str)
                and primary_by_source.get(item)
                and primary_by_source[item] != item
            ):
                value[key] = primary_by_source[item]
                continue
            if key in _STRUCTURE_REFERENCE_LIST_FIELDS and isinstance(item, list):
                value[key] = list(dict.fromkeys(
                    primary_by_source.get(str(entry), str(entry))
                    for entry in item
                ))
                continue
            _rebind_structure_references(item, primary_by_source)
    elif isinstance(value, list):
        for item in value:
            _rebind_structure_references(item, primary_by_source)


def _prepare_question_bank_structure_rebind(
    *,
    active: dict[str, Any],
    operation: CourseEvolutionOperation,
) -> dict[str, Any]:
    payload = operation.payload or {}
    affected = _structure_affected_migrations(payload)
    affected_ids = {
        str(item.get("source_section_id") or "") for item in affected
    }
    primary_by_source = {
        str(item.get("source_section_id") or ""): str(
            item.get("primary_target_section_id") or ""
        )
        for item in affected
    }
    result = deepcopy(active)
    generation_audit = result.setdefault("generation_audit", {})
    previous_records = deepcopy(
        generation_audit.pop("structure_reference_rebinds", [])
    )
    affected_item_ids = [
        str(item.get("item_id") or item.get("revision_id") or "")
        for item in result.get("items") or []
        if isinstance(item, dict)
        and _contains_structure_reference(item, affected_ids)
    ]
    _rebind_structure_references(result, primary_by_source)
    for item in result.get("items") or []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("item_id") or item.get("revision_id") or "")
        if item_id not in affected_item_ids:
            continue
        item["source_state"] = "stale"
        item["rebuild_required"] = True
        item["structure_reference_rebind"] = {
            "operation_id": operation.operation_id,
            "mapping_revision": str(payload.get("mapping_revision") or ""),
        }
    generation_audit = result.setdefault("generation_audit", {})
    records = previous_records
    records = [
        item
        for item in records
        if isinstance(item, dict)
        and item.get("operation_id") != operation.operation_id
    ]
    records.append({
        "operation_id": operation.operation_id,
        "mapping_revision": str(payload.get("mapping_revision") or ""),
        "affected_section_ids": sorted(affected_ids),
        "affected_item_ids": sorted(affected_item_ids),
        "section_tombstones": deepcopy(payload.get("section_tombstones") or []),
    })
    generation_audit["structure_reference_rebinds"] = records
    result["generation_audit"] = generation_audit
    return refresh_question_bank_bundle(result)


def _structure_ppt_registry_ids(
    *,
    authoring_repository: TeacherLessonAuthoringRepository,
    course_id: str,
    payload: dict[str, Any],
) -> list[str]:
    affected_ids = {
        str(item.get("source_section_id") or "")
        for item in _structure_affected_migrations(payload)
    }
    state = authoring_repository.load(course_id)
    registry_ids: list[str] = []
    for lesson_id, lesson in (state.get("lessons") or {}).items():
        if not isinstance(lesson, dict):
            continue
        reference = lesson.get("structure_reference") or {}
        reference_matches = (
            reference.get("mapping_revision") == payload.get("mapping_revision")
        )
        if lesson_id not in affected_ids and not reference_matches:
            continue
        for asset in lesson.get("ppt_assets") or []:
            if not isinstance(asset, dict):
                continue
            registry_id = str(asset.get("synthetic_course_id") or "")
            if registry_id:
                registry_ids.append(registry_id)
    return sorted(set(registry_ids))


def _reconciled_operation_receipt(
    *,
    operation: CourseEvolutionOperation,
    entry: CourseEvolutionOperationJournalEntry,
    course_id: str,
    authoring_repository: TeacherLessonAuthoringRepository,
    representation_repository: TeachingRepresentationRepository,
    question_bank_repository: QuestionBankRepository,
    document_repository: CourseDocumentRepository,
) -> dict[str, Any] | None:
    """Return durable proof that an interrupted asset operation already landed."""
    payload = operation.payload or {}
    domain = str(payload.get("domain") or "")
    lesson_id = str(payload.get("lesson_unit_id") or "")
    expected = str(
        entry.result_revision_id or entry.expected_result_revision_id or ""
    )
    receipt = _base_operation_receipt(operation)

    if domain == "authoring_structure_refs":
        record = authoring_repository.structure_reference_rebind(
            course_id,
            operation.operation_id,
        )
        if (
            isinstance(record, dict)
            and record.get("status") == "applied"
            and record.get("mapping_revision") == payload.get("mapping_revision")
        ):
            receipt.update({
                "status": "applied",
                "detail": "已与教案讲义结构引用回执对账，无需重复应用",
                "previous_revision_id": str(
                    record.get("previous_repository_revision") or ""
                ),
                "result_revision_id": str(
                    record.get("result_repository_revision") or ""
                ),
                "mapping_revision": str(payload.get("mapping_revision") or ""),
                "affected_section_ids": list(
                    record.get("affected_section_ids") or []
                ),
                "retryable": False,
            })
            return receipt
        return None

    if domain == "ppt_structure_refs":
        registry_ids = list(
            entry.result_receipt.get("target_registry_ids") or []
        )
        reconciled_registries: list[dict[str, Any]] = []
        for registry_id in registry_ids:
            result = representation_repository.structure_reference_rebind(
                str(registry_id),
                operation.operation_id,
            )
            record = (result or {}).get("record") or {}
            if (
                record.get("status") != "applied"
                or record.get("mapping_revision") != payload.get("mapping_revision")
            ):
                return None
            reconciled_registries.append({
                "registry_id": str(registry_id),
                "registry_revision": str(
                    (result or {}).get("registry_revision") or ""
                ),
            })
        result_revision_id = stable_hash(
            {
                "operation_id": operation.operation_id,
                "mapping_revision": payload.get("mapping_revision"),
                "target_registry_ids": registry_ids,
            },
            prefix="ppt-structure-ref-",
        )
        receipt.update({
            "status": "applied",
            "detail": "已与 PPT 结构引用回执对账，无需重复应用",
            "result_revision_id": result_revision_id,
            "mapping_revision": str(payload.get("mapping_revision") or ""),
            "target_registry_ids": registry_ids,
            "registries": reconciled_registries,
            "retryable": False,
        })
        return receipt

    if domain == "question_bank_structure_refs" and expected:
        active = question_bank_repository.load_bundle(course_id)
        raw = document_repository.load_raw(course_id)
        active_revision_id = str((active or {}).get("bundle_revision_id") or "")
        metadata_revision_id = str(
            raw.get("question_bank_bundle_revision_id") or ""
        )
        no_asset = expected.startswith("question-bank-none:")
        if (
            (no_asset and not active_revision_id and not metadata_revision_id)
            or (
                active_revision_id == expected
                and metadata_revision_id == expected
            )
        ):
            receipt.update({
                "status": "applied",
                "detail": "已与题库结构引用修订对账，无需重复应用",
                "previous_revision_id": entry.previous_revision_id,
                "result_revision_id": expected,
                "mapping_revision": str(payload.get("mapping_revision") or ""),
                "retryable": False,
            })
            return receipt
        return None

    if domain in {"lesson_plan", "script"}:
        lesson = authoring_repository.lesson(course_id, lesson_id)
        candidates_key = "ai_candidates" if domain == "lesson_plan" else "script_ai_candidates"
        candidate = next(
            (
                item for item in lesson.get(candidates_key) or []
                if isinstance(item, dict)
                and item.get("candidate_id") == payload.get("candidate_id")
            ),
            None,
        )
        candidate_result = str((candidate or {}).get("result_revision_id") or "")
        result_revision_id = candidate_result or expected
        revisions_key = "revisions" if domain == "lesson_plan" else "script_revisions"
        working_key = (
            "working_revision_id"
            if domain == "lesson_plan"
            else "working_script_revision_id"
        )
        result_exists = any(
            isinstance(item, dict)
            and str(item.get("revision_id") or "") == result_revision_id
            for item in lesson.get(revisions_key) or []
        )
        if result_revision_id and (
            str(lesson.get(working_key) or "") == result_revision_id
            or (candidate_result and result_exists)
        ):
            receipt.update({
                "status": "applied",
                "detail": "已与正式修订对账，无需重复应用",
                "result_revision_id": result_revision_id,
                "retryable": False,
            })
            return receipt
        return None

    if domain == "ppt":
        lesson = authoring_repository.lesson(course_id, lesson_id)
        asset = next(
            (
                item for item in lesson.get("ppt_assets") or []
                if isinstance(item, dict)
                and item.get("role") == "primary"
                and item.get("engine") == "slide_deck_v6"
            ),
            None,
        )
        if not isinstance(asset, dict):
            return None
        candidate = next(
            (
                candidate
                for candidate in asset.get("v6_ai_candidates") or []
                if isinstance(candidate, dict)
                and candidate.get("candidate_id") == payload.get("candidate_id")
            ),
            None,
        )
        result_spec_id = str((candidate or {}).get("result_spec_id") or expected)
        working_binding_id = str(asset.get("working_v6_revision_id") or "")
        binding = next(
            (
                item for item in asset.get("v6_revisions") or []
                if isinstance(item, dict)
                and item.get("revision_id") == working_binding_id
            ),
            None,
        )
        result_binding = next(
            (
                item for item in asset.get("v6_revisions") or []
                if isinstance(item, dict) and item.get("spec_id") == result_spec_id
            ),
            None,
        )
        if result_spec_id and (
                str((binding or {}).get("spec_id") or "") == result_spec_id
                or (
                    str((candidate or {}).get("status") or "") == "accepted"
                    and result_binding is not None
                )
        ):
            receipt.update({
                "status": "applied",
                "detail": "已与正式修订对账，无需重复应用",
                "result_revision_id": result_spec_id,
                "result_binding_id": str(
                    (result_binding or {}).get("revision_id") or working_binding_id
                ),
                "previous_binding_id": entry.result_receipt.get("previous_binding_id", ""),
                "representation_id": str(payload.get("representation_id") or ""),
                "synthetic_course_id": str(payload.get("synthetic_course_id") or ""),
                "lesson_unit_id": lesson_id,
                "retryable": False,
            })
            return receipt
        return None

    if domain == "question_bank" and expected:
        active = question_bank_repository.load_bundle(course_id)
        raw = document_repository.load_raw(course_id)
        metadata_revision_id = str(
            raw.get("question_bank_bundle_revision_id") or ""
        )
        if (
            str((active or {}).get("bundle_revision_id") or "") == expected
            and metadata_revision_id == expected
        ):
            receipt.update({
                "status": "applied",
                "detail": "已与正式修订对账，无需重复应用",
                "result_revision_id": expected,
                "retryable": False,
            })
            return receipt
    return None


def build_domain_candidate_applier(
    *,
    course_data: dict[str, Any],
    user_id: str,
    authoring_repository: TeacherLessonAuthoringRepository,
    representation_repository: TeachingRepresentationRepository,
    question_bank_repository: QuestionBankRepository,
    document_repository: CourseDocumentRepository,
    evolution_repository: CourseEvolutionRepository | None = None,
) -> Any:
    course_id = str(course_data.get("course_id") or "")

    def apply(
        plan: CourseEvolutionPlan,
        operation_ids: list[str],
        *,
        evolution_repository_override: CourseEvolutionRepository | None = None,
    ) -> dict[str, Any]:
        journal_repository = evolution_repository_override or evolution_repository
        if journal_repository is None:
            raise CourseEvolutionJournalPersistenceError(
                "课程修改操作日志未连接正式仓储"
            )
        selected = set(operation_ids)
        items: list[dict[str, Any]] = []
        for operation in plan.operations:
            if operation.operation_id not in selected or operation.operation_type != DOMAIN_OPERATION_TYPE:
                continue
            payload = operation.payload or {}
            domain = str(payload.get("domain") or "")
            action = str(payload.get("action") or "")
            receipt = _base_operation_receipt(operation)
            entry = _journal_entry(plan, operation.operation_id)
            if entry.status == "applied":
                durable_receipt = deepcopy(entry.result_receipt) or receipt
                durable_receipt.update({
                    "operation_id": operation.operation_id,
                    "domain": domain,
                    "status": "applied",
                    "previous_revision_id": entry.previous_revision_id,
                    "result_revision_id": entry.result_revision_id,
                    "detail": entry.detail or "已写入该资产的正式工作版",
                    "retryable": False,
                })
                items.append(durable_receipt)
                continue
            if entry.status == "failed":
                failed_receipt = deepcopy(entry.result_receipt) or receipt
                failed_receipt.update({
                    "operation_id": operation.operation_id,
                    "domain": domain,
                    "status": "failed",
                    "previous_revision_id": entry.previous_revision_id,
                    "result_revision_id": entry.result_revision_id,
                    "detail": entry.detail or "应用失败，已保留原版本",
                    "error_code": entry.error_code or "domain_candidate_apply_failed",
                    "retryable": entry.retryable,
                })
                items.append(failed_receipt)
                continue
            if entry.status == "applying":
                reconciled = _reconciled_operation_receipt(
                    operation=operation,
                    entry=entry,
                    course_id=course_id,
                    authoring_repository=authoring_repository,
                    representation_repository=representation_repository,
                    question_bank_repository=question_bank_repository,
                    document_repository=document_repository,
                )
                if reconciled is not None:
                    completed_at = _now()
                    entry.status = "applied"
                    entry.result_revision_id = str(
                        reconciled.get("result_revision_id") or ""
                    )
                    entry.result_receipt = deepcopy(reconciled)
                    entry.error_code = ""
                    entry.detail = str(reconciled.get("detail") or "")
                    entry.retryable = False
                    entry.completed_at = completed_at
                    entry.updated_at = completed_at
                    _persist_journal_entry(
                        plan,
                        entry,
                        repository=journal_repository,
                    )
                    items.append(reconciled)
                    continue
            else:
                entry.status = "applying"
                entry.attempt += 1
                entry.expected_result_revision_id = (
                    _stable_operation_revision(
                        plan,
                        operation,
                        prefix="tlpr-cev_",
                    )
                    if domain == "lesson_plan"
                    else _stable_operation_revision(
                        plan,
                        operation,
                        prefix="tlsr-cev_",
                    )
                    if domain == "script"
                    else ""
                )
                if domain == "ppt":
                    lesson = authoring_repository.lesson(
                        course_id,
                        str(payload.get("lesson_unit_id") or ""),
                    )
                    asset = next(
                        (
                            item for item in lesson.get("ppt_assets") or []
                            if isinstance(item, dict)
                            and item.get("role") == "primary"
                            and item.get("engine") == "slide_deck_v6"
                        ),
                        None,
                    )
                    entry.result_receipt = {
                        "previous_binding_id": str(
                            (asset or {}).get("working_v6_revision_id") or ""
                        ),
                    }
                elif action == "rebind_section_references":
                    if domain == "authoring_structure_refs":
                        authoring_state = authoring_repository.load(course_id)
                        entry.previous_revision_id = str(
                            authoring_state.get("revision") or 0
                        )
                    elif domain == "ppt_structure_refs":
                        entry.result_receipt = {
                            "target_registry_ids": _structure_ppt_registry_ids(
                                authoring_repository=authoring_repository,
                                course_id=course_id,
                                payload=payload,
                            ),
                        }
                    elif domain == "question_bank_structure_refs":
                        active_question_bank = question_bank_repository.load_bundle(
                            course_id
                        )
                        entry.previous_revision_id = str(
                            (active_question_bank or {}).get(
                                "bundle_revision_id"
                            )
                            or ""
                        )
                        entry.expected_result_revision_id = (
                            str(_prepare_question_bank_structure_rebind(
                                active=active_question_bank,
                                operation=operation,
                            ).get("bundle_revision_id") or "")
                            if active_question_bank
                            else (
                                "question-bank-none:"
                                f"{payload.get('mapping_revision') or ''}"
                            )
                        )
                entry.error_code = ""
                entry.detail = ""
                entry.retryable = False
                entry.started_at = _now()
                entry.completed_at = None
                entry.updated_at = entry.started_at
                _persist_journal_entry(
                    plan,
                    entry,
                    repository=journal_repository,
                )
            prepared_question_bank: dict[str, Any] | None = None
            try:
                lesson_id = str(payload.get("lesson_unit_id") or "")
                if domain == "lesson_plan":
                    service = TeacherLessonAuthoringService(authoring_repository)
                    lesson = service.resolve_ai_candidate(
                        course_id=course_id,
                        lesson_unit_id=lesson_id,
                        course_data=course_data,
                        candidate_id=str(payload.get("candidate_id") or ""),
                        accept=True,
                        actor=user_id,
                        result_revision_id_override=(
                            entry.expected_result_revision_id
                        ),
                    )
                    receipt["result_revision_id"] = str(lesson.get("working_revision_id") or "")
                elif domain == "script":
                    receipt["result_revision_id"] = _apply_script_candidate(
                        course_data=course_data,
                        user_id=user_id,
                        course_id=course_id,
                        lesson_id=lesson_id,
                        candidate_id=str(payload.get("candidate_id") or ""),
                        repository=authoring_repository,
                        result_revision_id_override=(
                            entry.expected_result_revision_id
                        ),
                    )
                elif domain == "ppt":
                    result_spec_id, result_binding_id, previous_binding_id = _apply_ppt_candidate(
                        course_data=course_data,
                        course_id=course_id,
                        lesson_id=lesson_id,
                        payload=payload,
                        authoring_repository=authoring_repository,
                        representation_repository=representation_repository,
                    )
                    receipt["result_revision_id"] = result_spec_id
                    receipt["result_binding_id"] = result_binding_id
                    receipt["previous_binding_id"] = previous_binding_id
                    receipt["representation_id"] = str(payload.get("representation_id") or "")
                    receipt["synthetic_course_id"] = str(payload.get("synthetic_course_id") or "")
                    receipt["lesson_unit_id"] = lesson_id
                elif domain == "question_bank":
                    prepared_question_bank = _prepare_question_bank_candidate(
                        plan=plan,
                        payload=payload,
                        user_id=user_id,
                        course_id=course_id,
                        repository=question_bank_repository,
                    )
                    entry.expected_result_revision_id = str(
                        prepared_question_bank.get("bundle_revision_id") or ""
                    )
                    entry.updated_at = _now()
                    _persist_journal_entry(
                        plan,
                        entry,
                        repository=journal_repository,
                    )
                    final = question_bank_repository.save_bundle(
                        course_id,
                        prepared_question_bank,
                        activate=False,
                    )
                    previous_id = str(payload.get("previous_revision_id") or "")
                    question_bank_repository.activate_bundle(course_id, final["bundle_revision_id"])
                    try:
                        asyncio.run(document_repository.update_metadata(course_id, {
                            "question_bank_bundle_revision_id": final["bundle_revision_id"],
                            "question_bank_coverage": deepcopy(final.get("coverage") or {}),
                            "question_bank_review_queue": deepcopy(final.get("review_queue") or []),
                            "web_question_enrichment": deepcopy(final.get("web_enrichment") or {}),
                        }))
                    except Exception:
                        if previous_id:
                            question_bank_repository.activate_bundle(course_id, previous_id)
                        raise
                    receipt["result_revision_id"] = str(final["bundle_revision_id"])
                elif domain == "authoring_structure_refs":
                    record = authoring_repository.apply_structure_reference_rebind(
                        course_id,
                        operation_id=operation.operation_id,
                        mapping_revision=str(payload.get("mapping_revision") or ""),
                        reference_migrations=list(
                            payload.get("reference_migrations") or []
                        ),
                        section_tombstones=list(
                            payload.get("section_tombstones") or []
                        ),
                    )
                    receipt.update({
                        "previous_revision_id": str(
                            record.get("previous_repository_revision") or ""
                        ),
                        "result_revision_id": str(
                            record.get("result_repository_revision") or ""
                        ),
                        "mapping_revision": str(
                            payload.get("mapping_revision") or ""
                        ),
                        "affected_section_ids": list(
                            record.get("affected_section_ids") or []
                        ),
                    })
                elif domain == "ppt_structure_refs":
                    registry_ids = list(
                        entry.result_receipt.get("target_registry_ids") or []
                    )
                    affected_section_ids = sorted({
                        str(item.get("source_section_id") or "")
                        for item in _structure_affected_migrations(payload)
                    })
                    registry_receipts: list[dict[str, Any]] = []
                    for registry_id in registry_ids:
                        result = (
                            representation_repository
                            .apply_structure_reference_rebind(
                                str(registry_id),
                                operation_id=operation.operation_id,
                                mapping_revision=str(
                                    payload.get("mapping_revision") or ""
                                ),
                                reference_migrations=list(
                                    payload.get("reference_migrations") or []
                                ),
                                section_tombstones=list(
                                    payload.get("section_tombstones") or []
                                ),
                                affected_section_ids=affected_section_ids,
                            )
                        )
                        registry_receipts.append({
                            "registry_id": str(registry_id),
                            "registry_revision": str(
                                result.get("registry_revision") or ""
                            ),
                        })
                    receipt.update({
                        "result_revision_id": stable_hash(
                            {
                                "operation_id": operation.operation_id,
                                "mapping_revision": payload.get(
                                    "mapping_revision"
                                ),
                                "target_registry_ids": registry_ids,
                            },
                            prefix="ppt-structure-ref-",
                        ),
                        "mapping_revision": str(
                            payload.get("mapping_revision") or ""
                        ),
                        "target_registry_ids": registry_ids,
                        "registries": registry_receipts,
                    })
                elif domain == "question_bank_structure_refs":
                    active_question_bank = question_bank_repository.load_bundle(
                        course_id
                    )
                    previous_id = str(entry.previous_revision_id or "")
                    if active_question_bank:
                        if str(
                            active_question_bank.get("bundle_revision_id") or ""
                        ) != previous_id:
                            raise ValueError(
                                "question_bank_structure_rebind_conflict"
                            )
                        prepared_question_bank = (
                            _prepare_question_bank_structure_rebind(
                                active=active_question_bank,
                                operation=operation,
                            )
                        )
                        entry.expected_result_revision_id = str(
                            prepared_question_bank.get("bundle_revision_id") or ""
                        )
                        entry.updated_at = _now()
                        _persist_journal_entry(
                            plan,
                            entry,
                            repository=journal_repository,
                        )
                        final = question_bank_repository.save_bundle(
                            course_id,
                            prepared_question_bank,
                            activate=False,
                        )
                        question_bank_repository.activate_bundle(
                            course_id,
                            str(final["bundle_revision_id"]),
                            expected_current_revision_id=previous_id,
                        )
                        try:
                            asyncio.run(document_repository.update_metadata(
                                course_id,
                                {
                                    "question_bank_bundle_revision_id": final[
                                        "bundle_revision_id"
                                    ],
                                    "question_bank_coverage": deepcopy(
                                        final.get("coverage") or {}
                                    ),
                                    "question_bank_review_queue": deepcopy(
                                        final.get("review_queue") or []
                                    ),
                                    "web_question_enrichment": deepcopy(
                                        final.get("web_enrichment") or {}
                                    ),
                                },
                            ))
                        except Exception:
                            question_bank_repository.activate_bundle(
                                course_id,
                                previous_id,
                                expected_current_revision_id=str(
                                    final["bundle_revision_id"]
                                ),
                            )
                            raise
                        receipt["result_revision_id"] = str(
                            final["bundle_revision_id"]
                        )
                    else:
                        receipt["result_revision_id"] = str(
                            entry.expected_result_revision_id
                        )
                    receipt.update({
                        "previous_revision_id": previous_id,
                        "mapping_revision": str(
                            payload.get("mapping_revision") or ""
                        ),
                    })
                else:
                    raise ValueError(f"不支持的候选类型：{domain}")
                receipt["status"] = "applied"
                receipt["detail"] = "已写入该资产的正式工作版"
                receipt["retryable"] = False
            except CourseEvolutionJournalPersistenceError:
                raise
            except Exception as error:  # noqa: BLE001 - preserve last-good per asset
                receipt["detail"] = _compact(error, 500) or "应用失败，已保留原版本"
                receipt["error_code"] = str(
                    getattr(error, "code", "") or f"{domain or 'unknown'}_candidate_apply_failed"
                )
                receipt["retryable"] = not any(
                    token in receipt["error_code"]
                    for token in ("conflict", "not_found", "unsupported")
                )
                completed_at = _now()
                entry.status = "failed"
                entry.result_receipt = deepcopy(receipt)
                entry.error_code = receipt["error_code"]
                entry.detail = receipt["detail"]
                entry.retryable = bool(receipt["retryable"])
                entry.completed_at = completed_at
                entry.updated_at = completed_at
                _persist_journal_entry(
                    plan,
                    entry,
                    repository=journal_repository,
                )
            else:
                completed_at = _now()
                entry.status = "applied"
                entry.result_revision_id = str(
                    receipt.get("result_revision_id") or ""
                )
                entry.result_receipt = deepcopy(receipt)
                entry.error_code = ""
                entry.detail = receipt["detail"]
                entry.retryable = False
                entry.completed_at = completed_at
                entry.updated_at = completed_at
                _persist_journal_entry(
                    plan,
                    entry,
                    repository=journal_repository,
                )
            items.append(receipt)
        result = {
            "schema_version": RECEIPT_SCHEMA,
            "status": "applied" if items and all(item["status"] == "applied" for item in items) else "partial",
            "applied_count": sum(item["status"] == "applied" for item in items),
            "failed_count": sum(item["status"] == "failed" for item in items),
            "items": items,
            "updated_at": _now(),
        }
        if result["status"] == "partial" and items:
            record_cross_asset_partial(
                operation_count=len(items),
                failed_count=result["failed_count"],
            )
        return result

    apply.operation_journal_aware = True
    return apply


def build_domain_candidate_undoer(
    *,
    user_id: str,
    course_id: str,
    authoring_repository: TeacherLessonAuthoringRepository,
    representation_repository: TeachingRepresentationRepository,
    question_bank_repository: QuestionBankRepository,
    document_repository: CourseDocumentRepository,
) -> Any:
    def undo(plan: CourseEvolutionPlan) -> dict[str, Any]:
        source_items = list((plan.application_receipt.get("domain_candidates") or {}).get("items") or [])
        previous_undo_items = {
            str(item.get("operation_id") or ""): deepcopy(item)
            for item in (plan.undo_receipt.get("domain_candidates") or {}).get("items") or []
            if isinstance(item, dict) and item.get("status") == "undone"
        }
        items: list[dict[str, Any]] = []
        # Restore the upstream plan before its script, then bind the old script
        # to the proven rollback revision. Preflight protects later teacher edits.
        undo_order = sorted(reversed(source_items), key=lambda item: 0 if item.get("domain") == "lesson_plan" else 1)
        for source in undo_order:
            if source.get("status") != "applied":
                continue
            operation_id = str(source.get("operation_id") or "")
            if operation_id in previous_undo_items:
                items.append(previous_undo_items[operation_id])
                continue
            item = deepcopy(source)
            item["status"] = "failed"
            try:
                domain = str(source.get("domain") or "")
                operation = next(
                    (op for op in plan.operations if op.operation_id == source.get("operation_id")),
                    None,
                )
                payload = operation.payload if operation is not None else {}
                lesson_id = str(payload.get("lesson_unit_id") or source.get("lesson_unit_id") or "")
                previous = str(source.get("previous_revision_id") or "")
                result = str(source.get("result_revision_id") or "")
                if domain == "lesson_plan":
                    paired = next((src for src in source_items if src.get("domain") == "script" and src.get("status") == "applied" and any(op.operation_id == src.get("operation_id") and op.payload.get("lesson_unit_id") == lesson_id for op in plan.operations)), None)
                    if paired and paired.get("operation_id") not in previous_undo_items:
                        live = authoring_repository.lesson(course_id, lesson_id)
                        if str(live.get("working_script_revision_id") or "") != str(paired.get("result_revision_id") or ""):
                            raise ValueError("讲义已有后续修改，本讲教案和讲义均未覆盖；请先处理冲突。")
                    authoring_repository.rollback_plan_revision(
                        course_id,
                        lesson_id,
                        previous,
                        expected_working_revision_id=result,
                        actor=user_id,
                    )
                elif domain == "script":
                    authoring_repository.rollback_script_revision(
                        course_id,
                        lesson_id,
                        previous,
                        expected_working_revision_id=result,
                        actor=user_id,
                    )
                elif domain == "ppt":
                    lesson = authoring_repository.lesson(course_id, lesson_id)
                    asset = next(
                        (
                            value for value in lesson.get("ppt_assets") or []
                            if isinstance(value, dict) and value.get("role") == "primary"
                        ),
                        None,
                    )
                    if not isinstance(asset, dict) or str(asset.get("working_representation_id") or "") != str(payload.get("representation_id") or ""):
                        raise ValueError("PPT 工作稿已变化，不能覆盖")
                    result_binding_id = str(source.get("result_binding_id") or "")
                    previous_binding_id = str(source.get("previous_binding_id") or "")
                    binding = next(
                        (
                            value for value in asset.get("v6_revisions") or []
                            if isinstance(value, dict)
                            and (
                                str(value.get("revision_id") or "") == previous_binding_id
                                if previous_binding_id
                                else str(value.get("spec_id") or "") == previous
                                and str(value.get("revision_id") or "") != result_binding_id
                            )
                        ),
                        None,
                    )
                    if not isinstance(binding, dict):
                        raise ValueError("PPT 原版本不存在")
                    synthetic_course_id = str(
                        binding.get("synthetic_course_id")
                        or payload.get("synthetic_course_id")
                        or source.get("synthetic_course_id")
                        or ""
                    )
                    representation_id = str(
                        binding.get("representation_id")
                        or payload.get("representation_id")
                        or source.get("representation_id")
                        or ""
                    )
                    registry = representation_repository.load(synthetic_course_id)
                    original_registry = registry.model_copy(deep=True)
                    representation = next(
                        (
                            value for value in registry.representations
                            if value.representation_id == representation_id
                        ),
                        None,
                    )
                    previous_spec = next(
                        (value for value in registry.specs if value.spec_id == previous),
                        None,
                    )
                    if representation is None or previous_spec is None:
                        raise ValueError("PPT 表示或原规格已不存在")
                    if str(representation.spec_id or "") != result:
                        raise ValueError("PPT 已被其他修改更新，不能覆盖")
                    previous_content = previous_spec.payload.get("content") or {}
                    representation.spec_id = previous
                    representation.semantic_fingerprint = stable_hash(previous_content, prefix="sem_")
                    representation.render_fingerprint = stable_hash(
                        {"spec_revision": previous_spec.revision, "renderer": "slide_deck_v6"},
                        prefix="rnd_",
                    )
                    representation.revision = stable_hash({
                        "spec_revision": previous_spec.revision,
                        "source_revision_vector": representation.source_revision_vector,
                    }, prefix="rpr_")
                    representation.updated_at = _now()
                    representation_repository.save(registry)
                    try:
                        authoring_repository.restore_v6_ppt_revision(
                            course_id,
                            lesson_id,
                            str(binding.get("revision_id") or ""),
                            expected_working_revision_id=result_binding_id,
                        )
                    except Exception:
                        representation_repository.save(original_registry)
                        raise
                elif domain == "question_bank":
                    active = question_bank_repository.load_bundle(course_id)
                    if not active or str(active.get("bundle_revision_id") or "") != result:
                        raise ValueError("题库已被其他修改更新，不能覆盖")
                    restored = question_bank_repository.load_bundle(course_id, previous)
                    if not restored:
                        raise ValueError("题库原版本不存在")
                    question_bank_repository.activate_bundle(course_id, previous)
                    asyncio.run(document_repository.update_metadata(course_id, {
                        "question_bank_bundle_revision_id": previous,
                        "question_bank_coverage": deepcopy(restored.get("coverage") or {}),
                        "question_bank_review_queue": deepcopy(restored.get("review_queue") or []),
                        "web_question_enrichment": deepcopy(restored.get("web_enrichment") or {}),
                    }))
                elif domain == "authoring_structure_refs":
                    record = authoring_repository.undo_structure_reference_rebind(
                        course_id,
                        operation_id=operation_id,
                        expected_mapping_revision=str(
                            payload.get("mapping_revision") or ""
                        ),
                    )
                    item["result_revision_id"] = str(
                        record.get("undo_repository_revision") or ""
                    )
                elif domain == "ppt_structure_refs":
                    registry_ids = list(
                        source.get("target_registry_ids") or []
                    )
                    restored_registries: list[dict[str, Any]] = []
                    for registry_id in registry_ids:
                        restored_registry = (
                            representation_repository
                            .undo_structure_reference_rebind(
                                str(registry_id),
                                operation_id=operation_id,
                                expected_mapping_revision=str(
                                    payload.get("mapping_revision") or ""
                                ),
                            )
                        )
                        restored_registries.append({
                            "registry_id": str(registry_id),
                            "registry_revision": str(
                                restored_registry.get("registry_revision") or ""
                            ),
                        })
                    item["registries"] = restored_registries
                elif domain == "question_bank_structure_refs":
                    if result.startswith("question-bank-none:"):
                        if question_bank_repository.load_bundle(course_id):
                            raise ValueError(
                                "question_bank_structure_rebind_conflict"
                            )
                    else:
                        active = question_bank_repository.load_bundle(course_id)
                        if (
                            not active
                            or str(active.get("bundle_revision_id") or "")
                            != result
                        ):
                            raise ValueError(
                                "question_bank_structure_rebind_conflict"
                            )
                        restored = question_bank_repository.load_bundle(
                            course_id,
                            previous,
                        )
                        if not restored:
                            raise ValueError("题库原版本不存在")
                        question_bank_repository.activate_bundle(
                            course_id,
                            previous,
                            expected_current_revision_id=result,
                        )
                        try:
                            asyncio.run(document_repository.update_metadata(
                                course_id,
                                {
                                    "question_bank_bundle_revision_id": previous,
                                    "question_bank_coverage": deepcopy(
                                        restored.get("coverage") or {}
                                    ),
                                    "question_bank_review_queue": deepcopy(
                                        restored.get("review_queue") or []
                                    ),
                                    "web_question_enrichment": deepcopy(
                                        restored.get("web_enrichment") or {}
                                    ),
                                },
                            ))
                        except Exception:
                            question_bank_repository.activate_bundle(
                                course_id,
                                result,
                                expected_current_revision_id=previous,
                            )
                            raise
                else:
                    raise ValueError(f"不支持的撤销候选类型：{domain}")
                item["status"] = "undone"
                item["detail"] = "已恢复到本次修改前的版本"
            except Exception as error:  # noqa: BLE001
                item["detail"] = _compact(error, 500) or "撤销失败"
            items.append(item)
        return {
            "schema_version": RECEIPT_SCHEMA,
            "status": "undone" if all(item["status"] == "undone" for item in items) else "partial",
            "undone_count": sum(item["status"] == "undone" for item in items),
            "failed_count": sum(item["status"] == "failed" for item in items),
            "items": items,
            "updated_at": _now(),
        }

    return undo


__all__ = [
    "build_domain_candidate_applier",
    "build_domain_candidate_undoer",
    "generate_teacher_course_change_candidates",
]
