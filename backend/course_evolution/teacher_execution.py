"""Execution adapters for the existing whole-course change plan.

This module deliberately does not introduce another workflow.  It turns the
reviewed migrations already stored on ``CourseEvolutionPlan`` into candidates
owned by the existing lesson-plan, script, PPT and question-bank repositories,
then lets the existing change-set accept/undo endpoints apply those candidates.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
import uuid

from course_document import stable_hash
from .core import (
    CourseEvolutionOperation,
    CourseEvolutionPlan,
    CourseEvolutionRepository,
)
from course_repository import CourseDocumentRepository
from question_bank import (
    QuestionBankRepository,
    review_question_bank_item,
    revise_question_bank_item,
)
from slide_deck_v6 import SlideDeckV6, project_ppt_manuscript_from_deck_v1
from teacher_lesson_authoring import (
    TeacherLessonAuthoringError,
    TeacherLessonAuthoringRepository,
    TeacherLessonAuthoringService,
    lesson_scope,
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


DOMAIN_OPERATION_TYPE = "APPLY_DOMAIN_CANDIDATE"
CANDIDATE_BUNDLE_SCHEMA = "teacher_course_domain_candidates_v1"
RECEIPT_SCHEMA = "teacher_course_domain_receipt_v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact(value: Any, limit: int = 360) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


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
    if not selected:
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
        migration.metadata.pop("operation_id", None)


def _literal_terms(migrations: list[Any]) -> tuple[str, str] | None:
    for migration in migrations:
        value = (migration.metadata or {}).get("literal_replacement") or {}
        before = str(value.get("before") or "")
        after = str(value.get("after") or "")
        if before and after and before != after:
            return before, after
    return None


def _replace_human_text(value: Any, before: str, after: str, *, key: str = "") -> tuple[Any, int]:
    """Replace prose while leaving ids, revisions, URLs and source bindings intact."""
    protected = (
        key.endswith("_id")
        or key.endswith("_ids")
        or "revision" in key
        or key in {"id", "schema_version", "source_refs", "material_asset_ids", "url"}
    )
    if isinstance(value, str):
        if protected or before not in value:
            return value, 0
        return value.replace(before, after), value.count(before)
    if isinstance(value, list):
        result: list[Any] = []
        count = 0
        for item in value:
            replaced, local = _replace_human_text(item, before, after, key=key)
            result.append(replaced)
            count += local
        return result, count
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        count = 0
        for child_key, item in value.items():
            replaced, local = _replace_human_text(item, before, after, key=str(child_key))
            result[child_key] = replaced
            count += local
        return result, count
    return value, 0


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
                item.metadata["after_preview"] = _compact(candidate_plan)
                item.metadata["change_count"] = 1
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
            revision = _revision(lesson.get("script_revisions") or [], base_revision_id)
            if not base_revision_id or not revision:
                raise ValueError("当前课节没有可优化的讲义工作稿")
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
            replacements: dict[str, str] = {}
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
                source_content = str(section.get("content") or "").strip() or teacher_script_blocks_to_markdown(
                    [item for item in section.get("blocks") or [] if isinstance(item, dict)]
                )
                if literal:
                    before, after = literal
                    if before not in source_content:
                        continue
                    replacements[section_id] = source_content.replace(before, after)
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
                    }),
                    user_id=user_id,
                )
                replacement = str(result.get("replacement_text") or "").strip()
                if not replacement:
                    raise ValueError("讲义候选为空")
                replacements[section_id] = replacement
            if not replacements:
                raise ValueError("没有找到可修改的讲义小节")
            first_section_id = next(iter(replacements))
            candidate = repository.save_script_ai_candidate(
                course_id,
                lesson_id,
                base_revision_id=base_revision_id,
                section_node_id=first_section_id,
                instruction=plan.request_text,
                replacement_text=replacements[first_section_id],
                section_replacements=replacements,
                source_lesson_plan_revision_id=str(revision.get("source_lesson_plan_revision_id") or ""),
                material_asset_ids=[],
            )
            for item in items:
                section_id = next((value for value in item.dependency_ids if value in replacements), first_section_id)
                item.metadata["after_preview"] = _compact(replacements[section_id])
                item.metadata["change_count"] = 1
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
        migration.candidate_status = "not_started"
        migration.metadata.pop("candidate_error", None)
        migration.metadata.pop("operation_id", None)
        migration.metadata.pop("after_preview", None)

    operations: list[CourseEvolutionOperation] = []
    actionable = [item for item in migrations if item.candidate_status == "not_started"]
    operations.extend(await _generate_lesson_plan_candidates(
        course_id=course_id,
        plan=plan,
        migrations=actionable,
        repository=authoring_repository,
        course_service=course_service,
    ))
    operations.extend(await _generate_script_candidates(
        course_data=course_data,
        course_id=course_id,
        user_id=user_id,
        plan=plan,
        migrations=actionable,
        repository=authoring_repository,
        course_service=course_service,
    ))
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

    # Exact course-document operations were already compiled during analysis.
    preserved = [
        operation for operation in plan.operations
        if operation.operation_type != DOMAIN_OPERATION_TYPE
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
            if item.operation_type in {"RESEQUENCE_COURSE_PATH", "REBUILD_COURSE_OUTLINE"}
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
    plan.generation_status = "ready" if plan.operations else "failed"
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
        latest_selected = list((target.impact_summary.get("scope_review") or {}).get("selected_migration_ids") or [])
        if set(latest_selected) != set(selected_ids):
            raise ValueError("影响范围已变化，请重新生成候选")
        index = latest.change_sets.index(target)
        latest.change_sets[index] = plan
        latest.updated_at = _now()
        return latest

    return repository.update(user_id, course_id, save_if_scope_unchanged)


def _apply_script_candidate(
    *,
    course_data: dict[str, Any],
    user_id: str,
    course_id: str,
    lesson_id: str,
    candidate_id: str,
    repository: TeacherLessonAuthoringRepository,
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
    if not replacements:
        replacements[str(candidate.get("section_node_id") or "")] = str(candidate.get("replacement_text") or "")
    normalized_sections: list[dict[str, Any]] = []
    for section in base.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("section_node_id") or "")
        candidate_section = deepcopy(section)
        if section_id in replacements:
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
    plan_revision_id = str(lesson.get("confirmed_revision_id") or "")
    script_revision_id = str(lesson.get("working_script_revision_id") or "")
    plan_revision = _revision(lesson.get("revisions") or [], plan_revision_id)
    script_revision = _revision(lesson.get("script_revisions") or [], script_revision_id)
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


def build_domain_candidate_applier(
    *,
    course_data: dict[str, Any],
    user_id: str,
    authoring_repository: TeacherLessonAuthoringRepository,
    representation_repository: TeachingRepresentationRepository,
    question_bank_repository: QuestionBankRepository,
    document_repository: CourseDocumentRepository,
) -> Any:
    course_id = str(course_data.get("course_id") or "")

    def apply(plan: CourseEvolutionPlan, operation_ids: list[str]) -> dict[str, Any]:
        selected = set(operation_ids)
        items: list[dict[str, Any]] = []
        for operation in plan.operations:
            if operation.operation_id not in selected or operation.operation_type != DOMAIN_OPERATION_TYPE:
                continue
            payload = operation.payload or {}
            domain = str(payload.get("domain") or "")
            receipt = {
                "operation_id": operation.operation_id,
                "domain": domain,
                "migration_ids": list(payload.get("migration_ids") or []),
                "unit_ids": list(payload.get("unit_ids") or []),
                "status": "failed",
                "detail": "",
                "previous_revision_id": str(payload.get("previous_revision_id") or payload.get("previous_spec_id") or ""),
                "result_revision_id": "",
            }
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
                    candidate = question_bank_repository.load_bundle(
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
                    final = question_bank_repository.save_bundle(course_id, approved, activate=False)
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
                else:
                    raise ValueError(f"不支持的候选类型：{domain}")
                receipt["status"] = "applied"
                receipt["detail"] = "已写入该资产的正式工作版"
            except Exception as error:  # noqa: BLE001 - preserve last-good per asset
                receipt["detail"] = _compact(error, 500) or "应用失败，已保留原版本"
            items.append(receipt)
        return {
            "schema_version": RECEIPT_SCHEMA,
            "status": "applied" if items and all(item["status"] == "applied" for item in items) else "partial",
            "applied_count": sum(item["status"] == "applied" for item in items),
            "failed_count": sum(item["status"] == "failed" for item in items),
            "items": items,
            "updated_at": _now(),
        }

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
        for source in reversed(source_items):
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
                    authoring_repository.restore_plan_revision(
                        course_id,
                        lesson_id,
                        previous,
                        expected_working_revision_id=result,
                        actor=user_id,
                    )
                elif domain == "script":
                    authoring_repository.restore_script_revision(
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
