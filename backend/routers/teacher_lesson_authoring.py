from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from dependencies import (
    get_teacher_lesson_authoring_repository,
    require_task_manager,
)
from learner_context import resolve_user_id
from lesson_arrangement import (
    LESSON_TYPES,
    normalize_lesson_arrangement,
    recommend_lesson_arrangement,
    validate_lesson_arrangement,
)
from material_storage import MaterialStorageError, material_repository
from material_parser import parse_document_path, parse_material_asset
from task_manager import TaskManager
from teacher_lesson_authoring import (
    LESSON_PLAN_PIPELINE_VERSION,
    TeacherLessonAuthoringError,
    TeacherLessonAuthoringRepository,
    TeacherLessonAuthoringService,
    build_uploaded_ppt_review_report,
    extract_uploaded_pptx_evidence,
    extract_uploaded_pptx_review,
    lesson_scope,
    teacher_lesson_deck_to_structured_slide_deck,
    teacher_lesson_script_revision,
    teacher_lesson_v6_source,
)
from question_bank import question_bank_repository
from teacher_script import (
    compile_teacher_script_module_contract,
    normalize_teacher_script_section,
    validate_teacher_script_section,
)
from teacher_course_space import teacher_course_space_repository
from teacher_lesson_source import compile_original_lesson_plan_evidence
from slide_deck_renderer import export_structured_slide_deck
from representation_compiler import export_slide_deck_pptx
from representation_edits import (
    classify_representation_edit,
    representation_edit_impact,
)
from slide_deck_v6_orchestrator import (
    SlideDeckV6CandidateRepository,
    SlideDeckV6Orchestrator,
    V6BuildError,
)
from slide_ai_planning_v6 import (
    build_ai_base_story_planner_v6,
    build_ai_base_visual_planner_v2,
)
from teaching_representations import (
    TeachingRepresentationSpec,
    teaching_representation_repository,
)
from template_layout_contract import compile_builtin_template_layout_contract_v1
from course_document import (
    CourseDocument,
    course_view_from_document,
    refresh_document_revision,
    stable_hash,
)
from slide_deck_v6 import SlideDeckV6, compile_ppt_manuscript_v1


router = APIRouter(prefix="/teacher", tags=["teacher-lesson-authoring"])
_background_jobs: set[asyncio.Task] = set()


class GenerateLessonPlanRequest(BaseModel):
    request_id: str = Field(default="", max_length=160)
    resume_job_id: str = Field(default="", max_length=160)
    source_package_id: str = Field(default="", max_length=160)
    source_asset_id: str = Field(default="", max_length=160)
    requirements: str = Field(default="", max_length=4000)
    material_asset_ids: list[str] = Field(default_factory=list, max_length=24)


class ConfirmLessonArrangementRequest(BaseModel):
    lesson_type: str
    blocks: list[dict[str, Any]] = Field(min_length=1, max_length=32)


class SaveLessonPlanDraftRequest(BaseModel):
    plan: dict[str, Any]
    source_outline_revision_id: str = ""


class ConfirmLessonPlanRequest(BaseModel):
    revision_id: str


class ConfirmLessonScriptRequest(BaseModel):
    revision_id: str


class GenerateLessonScriptRequest(BaseModel):
    request_id: str = Field(default="", max_length=160)
    resume_job_id: str = Field(default="", max_length=160)
    requirements: str = Field(default="", max_length=4000)
    material_asset_ids: list[str] = Field(default_factory=list, max_length=24)


class SaveLessonScriptDraftRequest(BaseModel):
    base_revision_id: str = ""
    sections: list[dict[str, Any]]


class RewriteLessonScriptRequest(BaseModel):
    base_revision_id: str
    section_node_id: str
    instruction: str = Field(min_length=1, max_length=2000)
    material_asset_ids: list[str] = Field(default_factory=list, max_length=24)


class ResolveLessonScriptCandidateRequest(BaseModel):
    accept: bool


class CreateLessonPlanCandidateRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)
    section_node_id: str = ""
    base_revision_id: str
    material_asset_ids: list[str] = Field(default_factory=list, max_length=24)


class ResolveLessonPlanCandidateRequest(BaseModel):
    accept: bool


class TeacherLessonV6BuildRequest(BaseModel):
    mode: str = "teaching"
    theme: str = "qizhi-classroom"
    force_rebuild: bool = False


class ConfirmTeacherLessonPptManuscriptRequest(BaseModel):
    manuscript_revision: str = Field(min_length=1, max_length=200)


class TeacherLessonRepresentationEditRequest(BaseModel):
    unit_id: str
    field: str
    before: Any = None
    after: Any = None
    semantic_intent: bool = False


class TeacherLessonApplyRepresentationEditRequest(TeacherLessonRepresentationEditRequest):
    decision: str = "representation_only"


class CreateTeacherLessonV6CandidateRequest(BaseModel):
    page_id: str = Field(min_length=1, max_length=200)
    instruction: str = Field(min_length=1, max_length=2000)
    base_spec_id: str = Field(min_length=1, max_length=200)
    base_spec_revision: str = Field(min_length=1, max_length=200)


class ResolveTeacherLessonV6CandidateRequest(BaseModel):
    accept: bool


class CreateImportedPptReviewRequest(BaseModel):
    package_id: str = Field(min_length=1, max_length=200)
    asset_id: str = Field(min_length=1, max_length=200)


class UpdateImportedPptSlideRequest(BaseModel):
    base_revision_id: str = Field(min_length=1, max_length=200)
    blocks: list[dict[str, Any]] = Field(default_factory=list, max_length=80)


class CreateImportedPptCandidateRequest(BaseModel):
    base_revision_id: str = Field(min_length=1, max_length=200)
    slide_id: str = Field(min_length=1, max_length=240)
    instruction: str = Field(min_length=1, max_length=2000)


class ResolveImportedPptCandidateRequest(BaseModel):
    accept: bool


class ConfirmImportedPptReviewRequest(BaseModel):
    revision_id: str = Field(min_length=1, max_length=200)


def _raise(exc: TeacherLessonAuthoringError) -> None:
    status = 404 if exc.code.endswith("not_found") else 409
    raise HTTPException(
        status_code=status,
        detail={"code": exc.code, "message": str(exc), **exc.details},
    ) from exc


_V6_KEY_REGION_SLOTS = (
    "interpretation",
    "conclusion",
    "takeaway",
    "body",
    "content",
    "task",
    "steps",
    "items",
)


def _v6_page_expression(page: dict[str, Any]) -> dict[str, str]:
    regions = [item for item in page.get("regions") or [] if isinstance(item, dict)]
    subtitle_region = next(
        (item for item in regions if str(item.get("slot_id") or "") == "subtitle"),
        None,
    )
    key_region = next(
        (
            item
            for slot_id in _V6_KEY_REGION_SLOTS
            for item in regions
            if str(item.get("slot_id") or "") == slot_id
        ),
        next(
            (
                item
                for item in regions
                if str(item.get("slot_id") or "") not in {"eyebrow", "subtitle"}
                and str(item.get("content") or "").strip()
            ),
            None,
        ),
    )
    return {
        "page_id": str(page.get("page_id") or ""),
        "title": str(page.get("title") or "").strip(),
        "subtitle": str((subtitle_region or {}).get("content") or "").strip(),
        "key_message": str((key_region or {}).get("content") or "").strip(),
        "subtitle_region_id": str((subtitle_region or {}).get("region_id") or ""),
        "key_region_id": str((key_region or {}).get("region_id") or ""),
    }


def _apply_v6_page_expression(
    page: dict[str, Any],
    *,
    field: str,
    value: Any,
    target_region_id: str = "",
) -> None:
    if field == "title":
        page["title"] = str(value or "").strip()
        return
    expression = _v6_page_expression(page)
    if field == "subtitle":
        region_id = target_region_id or expression["subtitle_region_id"]
    elif field == "key_message":
        region_id = target_region_id or expression["key_region_id"]
    else:
        raise ValueError(f"v6_expression_field_unsupported:{field}")
    if not region_id:
        raise ValueError(f"v6_expression_region_missing:{field}")
    region = next(
        (
            item
            for item in page.get("regions") or []
            if isinstance(item, dict) and str(item.get("region_id") or "") == region_id
        ),
        None,
    )
    if region is None:
        raise ValueError(f"v6_expression_region_missing:{field}")
    region["content"] = str(value or "").strip()


def _refresh_v6_ppt_manuscript(
    content: dict[str, Any],
    *,
    course_view: dict[str, Any],
    source_lesson_plan_revision_id: str,
) -> dict[str, Any]:
    """页面文案变化后同步重建文书投影，避免最终 PPT 出现第二内容源。"""
    deck = SlideDeckV6.model_validate({
        key: content[key]
        for key in SlideDeckV6.model_fields
        if key in content
    })
    teacher_source = dict(course_view.get("teacher_lesson_source") or {})
    previous = (
        dict(content.get("ppt_manuscript") or {})
        if isinstance(content.get("ppt_manuscript"), dict)
        else {}
    )
    manuscript = compile_ppt_manuscript_v1(
        deck,
        source_lesson_plan_revision_id=source_lesson_plan_revision_id,
        source_script_revision_id=str(teacher_source.get("script_revision_id") or ""),
        material_bindings=list(
            teacher_source.get("material_bindings")
            or previous.get("material_bindings")
            or []
        ),
        page_material_evidence_ids={
            str(page.get("page_id") or ""): list(
                page.get("source_material_evidence_ids") or []
            )
            for page in previous.get("pages") or []
            if isinstance(page, dict) and str(page.get("page_id") or "")
        },
    )
    content["ppt_manuscript"] = manuscript.model_dump(mode="json")
    return content["ppt_manuscript"]


def _has_teaching_structure(source: Any) -> bool:
    if not isinstance(source, dict):
        return False
    if any(isinstance(item, dict) for item in source.get("nodes") or []):
        return True
    document = source.get("course_document")
    if not isinstance(document, dict):
        return False
    return bool(document.get("sections") or document.get("blocks"))


def _matches_course_shell(source: Any, course_id: str) -> bool:
    if not isinstance(source, dict):
        return False
    if str(source.get("course_id") or "") == course_id:
        return True
    document = source.get("course_document")
    return (
        isinstance(document, dict)
        and str(document.get("course_id") or "") == course_id
    )


def _source_course(
    tm: TaskManager,
    course_id: str,
    *,
    allow_empty: bool = False,
) -> dict[str, Any]:
    raw = tm.storage.load_course(course_id) if tm.storage else None
    source = raw if _has_teaching_structure(raw) else None
    if not isinstance(source, dict):
        workspace = tm.get_generation_workspace_course(course_id)
        source = workspace if _has_teaching_structure(workspace) else None
    if not isinstance(source, dict):
        preview = tm.get_generation_preview(course_id)
        source = preview if _has_teaching_structure(preview) else None
    if not isinstance(source, dict) and allow_empty and _matches_course_shell(raw, course_id):
        source = raw
    if not isinstance(source, dict):
        raise TeacherLessonAuthoringError("course_not_found", "课程不存在或没有可用大纲。")
    if not source.get("nodes") and isinstance(source.get("course_document"), dict):
        source = course_view_from_document(source, source["course_document"])
    return deepcopy(source)


def _canonical_outline_revision(source: dict[str, Any]) -> str:
    """Return the revision consumed by the V3 teaching-plan engine.

    ``blueprint_revision_id`` identifies a broader course snapshot, while the
    knowledge-scope revision is the exact frozen outline contract used by the
    lesson planner.  Every read, generation, edit and confirmation must use the
    latter when available or a freshly generated plan becomes stale on reload.
    """
    return str(
        (source.get("course_knowledge_scope_contract") or {}).get("revision_id")
        or (source.get("course_teaching_plan") or {}).get("source_outline_revision_id")
        or source.get("blueprint_revision_id")
        or ""
    )


def _course_material_evidence(
    course_id: str,
    actor: str,
    material_asset_ids: list[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Load only evidence from explicitly selected, course-owned materials."""
    selected_ids = list(dict.fromkeys(
        str(value or "").strip()
        for value in material_asset_ids
        if str(value or "").strip()
    ))
    if not selected_ids:
        return [], []

    allowed_material_ids: set[str] = set()
    for summary in teacher_course_space_repository.list_owned(actor, course_id):
        try:
            package = teacher_course_space_repository.load_owned(
                str(summary.get("package_id") or ""), actor
            )
        except (FileNotFoundError, MaterialStorageError):
            continue
        allowed_material_ids.update(
            str(item.get("material_asset_id") or "")
            for item in package.get("assets") or []
            if str(item.get("material_asset_id") or "")
        )
    unknown_material_ids = sorted(set(selected_ids) - allowed_material_ids)
    if unknown_material_ids:
        raise TeacherLessonAuthoringError(
            "lesson_material_source_not_found",
            "部分已选资料不属于当前课程。",
            details={"material_asset_ids": unknown_material_ids},
        )

    evidence: list[dict[str, Any]] = []
    for material_asset_id in selected_ids:
        for item in material_repository.load_evidence(material_asset_id):
            if not isinstance(item, dict):
                continue
            evidence.append({
                **item,
                "asset_id": material_asset_id,
                "source_kind": "course_material",
            })
    return selected_ids, evidence


def _ppt_material_bundle(
    course_id: str,
    actor: str,
    lesson_unit_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve the PPT stage's frozen, teacher-owned material relationships."""
    target_id = f"ppt-v6:{lesson_unit_id}"
    bindings: list[dict[str, Any]] = []
    seen_material_ids: set[str] = set()
    for summary in teacher_course_space_repository.list_owned(actor, course_id):
        try:
            package = teacher_course_space_repository.load_owned(
                str(summary.get("package_id") or ""), actor
            )
        except (FileNotFoundError, MaterialStorageError):
            continue
        for relationship in teacher_course_space_repository.relationships_for_target(
            package, target_id
        ):
            material_asset_id = str(
                relationship.get("material_asset_id") or ""
            )
            if not material_asset_id or material_asset_id in seen_material_ids:
                continue
            seen_material_ids.add(material_asset_id)
            bindings.append({
                "material_asset_id": material_asset_id,
                "source_asset_id": str(
                    relationship.get("source_asset_id") or ""
                ),
                "source_label": str(
                    relationship.get("source_label") or material_asset_id
                ),
                "role": (
                    "primary"
                    if relationship.get("role") == "primary"
                    else "reference"
                ),
            })
    material_ids, evidence = _course_material_evidence(
        course_id,
        actor,
        [item["material_asset_id"] for item in bindings],
    )
    binding_by_material = {
        item["material_asset_id"]: item for item in bindings
    }
    normalized_evidence: list[dict[str, Any]] = []
    for index, item in enumerate(evidence):
        material_asset_id = str(item.get("asset_id") or "")
        binding = binding_by_material.get(material_asset_id) or {}
        evidence_id = str(
            item.get("evidence_id")
            or item.get("unit_id")
            or stable_hash(
                {
                    "material_asset_id": material_asset_id,
                    "index": index,
                    "text": str(
                        item.get("summary")
                        or item.get("source_text")
                        or item.get("text")
                        or item.get("content")
                        or ""
                    ),
                },
                prefix="pptev_",
            )
        )
        normalized_evidence.append({
            **item,
            "evidence_id": evidence_id,
            "asset_id": material_asset_id,
            "source_label": str(binding.get("source_label") or material_asset_id),
            "source_role": str(binding.get("role") or "reference"),
        })
    if set(material_ids) != set(binding_by_material):
        raise TeacherLessonAuthoringError(
            "lesson_material_source_not_found",
            "部分 PPT 资料来源无法读取。",
        )
    return bindings, normalized_evidence


def _ppt_reference_terms(value: str) -> set[str]:
    text = str(value or "").lower()
    terms = set(re.findall(r"[a-z][a-z0-9_+-]{1,30}", text))
    for group in re.findall(r"[\u4e00-\u9fff]{2,20}", text):
        terms.add(group)
        terms.update(
            group[index:index + width]
            for width in (2, 3, 4)
            for index in range(max(0, len(group) - width + 1))
        )
    return terms


def _attach_ppt_reference_evidence(
    document: CourseDocument,
    evidence: list[dict[str, Any]],
) -> CourseDocument:
    """Bind relevant selected evidence to confirmed script blocks without rewriting them."""
    if not evidence:
        return document
    evidence_terms = {
        str(item.get("evidence_id") or ""): _ppt_reference_terms(" ".join([
            " ".join(str(value) for value in item.get("keywords") or []),
            str(item.get("summary") or ""),
            str(item.get("source_text") or item.get("text") or item.get("content") or ""),
        ]))
        for item in evidence
        if str(item.get("evidence_id") or "")
    }
    section_titles = {
        section.section_id: section.title for section in document.sections
    }
    changed = False
    for block in document.blocks:
        block_query = " ".join([
            str((block.payload or {}).get("title") or ""),
            json.dumps(block.payload or {}, ensure_ascii=False),
        ])
        query_terms = _ppt_reference_terms(
            block_query or section_titles.get(block.section_id, "")
        )
        ranked = sorted(
            (
                (evidence_id, len(query_terms & terms))
                for evidence_id, terms in evidence_terms.items()
            ),
            key=lambda pair: (-pair[1], pair[0]),
        )
        selected = [evidence_id for evidence_id, score in ranked if score > 0][:4]
        if selected != block.evidence_refs:
            block.evidence_refs = selected
            changed = True
    return refresh_document_revision(document) if changed else document


def _prompt_material_evidence(
    evidence: list[dict[str, Any]],
    *,
    character_budget: int = 12000,
) -> list[dict[str, str]]:
    """Keep selected evidence useful while bounding one model request."""
    result: list[dict[str, str]] = []
    remaining = character_budget
    for item in evidence:
        raw_text = str(item.get("text") or item.get("content") or "").strip()
        if not raw_text or remaining <= 0:
            continue
        text = raw_text[:remaining]
        remaining -= len(text)
        result.append({
            "asset_id": str(item.get("asset_id") or ""),
            "unit_id": str(item.get("unit_id") or item.get("evidence_id") or ""),
            "text": text,
        })
    return result


def _lesson_projection(
    source: dict[str, Any],
    repository: TeacherLessonAuthoringRepository,
) -> list[dict[str, Any]]:
    course_id = str(source.get("course_id") or "")
    assets = repository.view(course_id).get("lessons") or {}
    nodes = [item for item in source.get("nodes") or [] if isinstance(item, dict)]
    lessons = [
        item for item in nodes
        if int(item.get("node_level") or 0) == 1
        and str(item.get("parent_node_id") or "").lower() in {"", "root"}
    ]
    result = []
    for index, lesson in enumerate(lessons, start=1):
        lesson_id = str(lesson.get("node_id") or "")
        sections = [
            item for item in nodes
            if str(item.get("parent_node_id") or "") == lesson_id
        ]
        asset = assets.get(lesson_id) if isinstance(assets, dict) else None
        plan_asset = deepcopy(asset) if isinstance(asset, dict) else {
            "lesson_unit_id": lesson_id,
            "arrangement": {
                "working_revision_id": "",
                "confirmed_revision_id": "",
                "source_state": "current",
                "revisions": [],
            },
            "working_revision_id": "",
            "confirmed_revision_id": "",
            "source_state": "current",
            "revisions": [],
            "working_script_revision_id": "",
            "script_revisions": [],
            "script_confirmation": {},
            "ppt_assets": [],
        }
        arrangement_state = plan_asset.get("arrangement") or {}
        arrangement_revision_id = str(arrangement_state.get("working_revision_id") or "")
        arrangement_revision = next(
            (
                item for item in arrangement_state.get("revisions") or []
                if isinstance(item, dict) and item.get("revision_id") == arrangement_revision_id
            ),
            None,
        )
        arrangement = deepcopy(arrangement_revision) if isinstance(arrangement_revision, dict) else recommend_lesson_arrangement(
            source,
            lesson_id,
            source_outline_revision_id=_canonical_outline_revision(source),
        )
        arrangement["confirmed"] = bool(
            arrangement_revision_id
            and arrangement_state.get("confirmed_revision_id") == arrangement_revision_id
            and arrangement_state.get("source_state", "current") == "current"
        )
        arrangement["source_state"] = str(arrangement_state.get("source_state") or "current")
        working_script_revision_id = str(plan_asset.get("working_script_revision_id") or "")
        script_revision = next(
            (
                item for item in plan_asset.get("script_revisions") or []
                if isinstance(item, dict) and item.get("revision_id") == working_script_revision_id
            ),
            None,
        )
        legacy_script_sections = [
            {
                "section_node_id": str(section.get("node_id") or ""),
                "title": str(section.get("node_name") or ""),
                "content": str(section.get("node_content") or ""),
            }
            for section in sections
        ]
        script_sections = deepcopy(
            script_revision.get("sections")
            if isinstance(script_revision, dict)
            else legacy_script_sections
        )
        current_script_revision = str(
            (script_revision or {}).get("revision_id")
            or teacher_lesson_script_revision(source, lesson_id)
        )
        script_confirmation = plan_asset.get("script_confirmation") or {}
        for ppt_asset in plan_asset.get("ppt_assets") or []:
            if not isinstance(ppt_asset, dict):
                continue
            source_script_revision = str(ppt_asset.get("source_script_revision_id") or "")
            if (
                ppt_asset.get("engine") == "slide_deck_v6"
                and source_script_revision != current_script_revision
            ):
                ppt_asset["source_state"] = "stale"
        script_source_state = (
            "current"
            if not isinstance(script_revision, dict)
            or script_revision.get("source_lesson_plan_revision_id")
            == plan_asset.get("confirmed_revision_id")
            else "stale"
        )
        script_ready = script_source_state == "current" and bool(script_sections) and all(
            str(section.get("content") or "").strip()
            for section in script_sections
        )
        script_confirmed = bool(
            script_ready
            and script_confirmation.get("confirmed_revision_id") == current_script_revision
            and script_confirmation.get("source_lesson_plan_revision_id")
            == plan_asset.get("confirmed_revision_id")
            and script_confirmation.get("source_state", "current") == "current"
        )
        result.append({
            "lesson_unit_id": lesson_id,
            "number": index,
            "title": str(lesson.get("node_name") or f"第{index}讲"),
            "duration_minutes": int(
                lesson.get("duration_minutes")
                or (source.get("teacher_course_brief") or {}).get("lesson_duration_minutes")
                or 45
            ),
            "sections": [
                {
                    "section_node_id": str(section.get("node_id") or ""),
                    "title": str(section.get("node_name") or ""),
                }
                for section in sections
            ],
            "arrangement": arrangement,
            "script": {
                "current_revision_id": current_script_revision,
                "confirmed_revision_id": str(
                    script_confirmation.get("confirmed_revision_id") or ""
                ),
                "source_lesson_plan_revision_id": str(
                    (script_revision or {}).get("source_lesson_plan_revision_id")
                    or script_confirmation.get("source_lesson_plan_revision_id")
                    or ""
                ),
                "source_state": script_source_state,
                "ready": script_ready,
                "confirmed": script_confirmed,
                "confirmed_at": str(script_confirmation.get("confirmed_at") or ""),
                "sections": script_sections,
                "ai_candidate": next(
                    (
                        deepcopy(candidate)
                        for candidate in reversed(plan_asset.get("script_ai_candidates") or [])
                        if isinstance(candidate, dict)
                        and candidate.get("status") == "pending"
                        and candidate.get("base_revision_id") == current_script_revision
                    ),
                    None,
                ),
            },
            "plan": plan_asset,
        })
    return result


def _plan_revision(
    repository: TeacherLessonAuthoringRepository,
    course_id: str,
    lesson_unit_id: str,
    revision_id: str,
) -> dict[str, Any]:
    lesson = repository.lesson(course_id, lesson_unit_id)
    revision = next(
        (
            item for item in lesson.get("revisions") or []
            if isinstance(item, dict) and item.get("revision_id") == revision_id
        ),
        None,
    )
    if not isinstance(revision, dict):
        raise TeacherLessonAuthoringError("lesson_plan_revision_not_found", "教案修订不存在。")
    return revision


def _script_revision(
    repository: TeacherLessonAuthoringRepository,
    course_id: str,
    lesson_unit_id: str,
    revision_id: str,
) -> dict[str, Any]:
    lesson = repository.lesson(course_id, lesson_unit_id)
    revision = next(
        (
            item for item in lesson.get("script_revisions") or []
            if isinstance(item, dict) and item.get("revision_id") == revision_id
        ),
        None,
    )
    if not isinstance(revision, dict):
        raise TeacherLessonAuthoringError(
            "lesson_script_revision_not_found",
            "讲稿修订不存在。",
        )
    return revision


def _imported_ppt_review_context(
    source: dict[str, Any],
    repository: TeacherLessonAuthoringRepository,
    course_id: str,
    lesson_unit_id: str,
    *,
    actor: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    """Compile the exact upstream revisions used by one imported-deck review."""
    scoped = lesson_scope(source, lesson_unit_id)
    lesson = repository.lesson(course_id, lesson_unit_id)
    sources: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    revisions = {
        "outline": _canonical_outline_revision(source),
        "plan": str(lesson.get("confirmed_revision_id") or ""),
        "script": "",
        "question_bank": "",
    }

    if revisions["outline"]:
        sources.append({
            "kind": "outline",
            "label": "课程大纲",
            "revision_id": revisions["outline"],
            "status": "current",
        })
    for section in scoped["sections"]:
        units.append({
            "kind": "outline",
            "label": str(section.get("node_name") or "未命名小节"),
            "revision_id": revisions["outline"],
            "text": "\n".join(filter(None, [
                str(section.get("node_name") or ""),
                str(section.get("learning_objective") or ""),
                str(section.get("node_content") or "")[:1600],
            ])),
        })

    if revisions["plan"]:
        plan_revision = _plan_revision(repository, course_id, lesson_unit_id, revisions["plan"])
        sources.append({
            "kind": "lesson_plan",
            "label": "已确认教案",
            "revision_id": revisions["plan"],
            "status": "confirmed",
        })
        for section in (plan_revision.get("plan") or {}).get("sections") or []:
            if not isinstance(section, dict):
                continue
            units.append({
                "kind": "lesson_plan",
                "label": str(section.get("title") or section.get("node_name") or section.get("node_id") or "教案小节"),
                "revision_id": revisions["plan"],
                "text": json.dumps(section, ensure_ascii=False)[:4000],
            })

    confirmation = lesson.get("script_confirmation") or {}
    confirmed_script = str(confirmation.get("confirmed_revision_id") or "")
    if confirmed_script and confirmation.get("source_state", "current") == "current":
        script_revision = _script_revision(repository, course_id, lesson_unit_id, confirmed_script)
        revisions["script"] = confirmed_script
        sources.append({
            "kind": "script",
            "label": "已确认讲稿",
            "revision_id": confirmed_script,
            "status": "confirmed",
        })
        for section in script_revision.get("sections") or []:
            if not isinstance(section, dict):
                continue
            units.append({
                "kind": "script",
                "label": str(section.get("title") or section.get("section_node_id") or "讲稿小节"),
                "revision_id": confirmed_script,
                "text": str(section.get("content") or "") or json.dumps(section.get("blocks") or [], ensure_ascii=False),
            })

    bundle = question_bank_repository.load_bundle(course_id)
    if isinstance(bundle, dict):
        section_ids = {str(item.get("node_id") or "") for item in scoped["sections"]}
        items = [
            item for item in bundle.get("items") or []
            if isinstance(item, dict)
            and (
                str(item.get("node_id") or "") in section_ids
                or section_ids.intersection(str(value or "") for value in item.get("node_ids") or [])
            )
        ]
        if items:
            revisions["question_bank"] = str(bundle.get("bundle_revision_id") or "")
            sources.append({
                "kind": "question_bank",
                "label": f"题库（{len(items)} 题）",
                "revision_id": revisions["question_bank"],
                "status": "current",
            })
            units.append({
                "kind": "question_bank",
                "label": "题库考查内容",
                "revision_id": revisions["question_bank"],
                "text": "\n".join(
                    str(item.get("stem") or item.get("prompt") or item.get("question") or "")
                    for item in items[:30]
                ),
            })
    if actor:
        material_bindings, material_evidence = _ppt_material_bundle(
            course_id, actor, lesson_unit_id
        )
        for binding in material_bindings:
            role = str(binding.get("role") or "reference")
            sources.append({
                "kind": "primary_material" if role == "primary" else "reference_material",
                "label": (
                    f"主参考：{binding['source_label']}"
                    if role == "primary"
                    else f"参考：{binding['source_label']}"
                ),
                "revision_id": stable_hash(binding, prefix="pptref_"),
                "status": "current",
            })
        for item in material_evidence[:48]:
            text = str(
                item.get("summary")
                or item.get("source_text")
                or item.get("text")
                or item.get("content")
                or ""
            ).strip()
            if not text:
                continue
            units.append({
                "kind": "reference_material",
                "label": str(item.get("source_label") or "PPT 参考资料"),
                "revision_id": str(item.get("evidence_id") or ""),
                "text": text[:2400],
            })
    return sources, units, revisions


def _updated_imported_ppt_slides(
    review: dict[str, Any],
    slide_id: str,
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    slides = deepcopy(review.get("slides") or [])
    slide = next((item for item in slides if item.get("slide_id") == slide_id), None)
    if not isinstance(slide, dict):
        raise TeacherLessonAuthoringError("uploaded_ppt_slide_not_found", "PPT 页面不存在。")
    existing = {
        str(item.get("block_id") or ""): item
        for item in slide.get("blocks") or []
        if isinstance(item, dict)
    }
    for patch in blocks:
        block_id = str(patch.get("block_id") or "")
        block = existing.get(block_id)
        if not isinstance(block, dict) or not block.get("editable"):
            raise TeacherLessonAuthoringError("uploaded_ppt_block_not_editable", "该文字块不支持在线编辑。")
        text = str(patch.get("text") or "").strip()
        if len(text) > 6000:
            raise TeacherLessonAuthoringError("uploaded_ppt_block_too_long", "单个 PPT 文字块不能超过 6000 字符。")
        block["text"] = text
    title_block = next((item for item in existing.values() if item.get("kind") == "title"), None)
    slide["title"] = str((title_block or {}).get("text") or "")
    slide["content_hash"] = stable_hash(slide.get("blocks") or [])[:24]
    return slides


def _ppt_asset_revision(
    repository: TeacherLessonAuthoringRepository,
    course_id: str,
    lesson_unit_id: str,
    asset_id: str,
    revision_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    lesson = repository.lesson(course_id, lesson_unit_id)
    asset = next(
        (
            item for item in lesson.get("ppt_assets") or []
            if isinstance(item, dict) and item.get("asset_id") == asset_id
        ),
        None,
    )
    if not isinstance(asset, dict):
        raise TeacherLessonAuthoringError("lesson_ppt_not_found", "本讲 PPT 不存在。")
    revision = next(
        (
            item for item in asset.get("revisions") or []
            if isinstance(item, dict) and item.get("revision_id") == revision_id
        ),
        None,
    )
    if not isinstance(revision, dict):
        raise TeacherLessonAuthoringError("lesson_ppt_revision_not_found", "PPT 修订不存在。")
    return asset, revision


def _teacher_v6_source(
    tm: TaskManager,
    repository: TeacherLessonAuthoringRepository,
    course_id: str,
    lesson_unit_id: str,
):
    source = _source_course(tm, course_id)
    lesson = repository.lesson(course_id, lesson_unit_id)
    revision_id = str(lesson.get("confirmed_revision_id") or "")
    if not revision_id:
        raise TeacherLessonAuthoringError(
            "lesson_plan_not_confirmed",
            "请先确认本讲教案，再进入 PPT 工作台。",
        )
    current_script_revision = str(lesson.get("working_script_revision_id") or "")
    script_confirmation = lesson.get("script_confirmation") or {}
    if not (
        script_confirmation.get("confirmed_revision_id") == current_script_revision
        and script_confirmation.get("source_lesson_plan_revision_id") == revision_id
        and script_confirmation.get("source_state", "current") == "current"
    ):
        raise TeacherLessonAuthoringError(
            "lesson_script_not_confirmed",
            "请先确认本讲讲稿，再进入 PPT 工作台。",
        )
    revision = _plan_revision(repository, course_id, lesson_unit_id, revision_id)
    script_revision = _script_revision(
        repository,
        course_id,
        lesson_unit_id,
        current_script_revision,
    )
    document, course_view, synthetic_id = teacher_lesson_v6_source(
        source,
        lesson_unit_id=lesson_unit_id,
        plan_revision=revision,
        script_revision=script_revision,
    )
    return document, course_view, synthetic_id, lesson, revision


def _teacher_v6_registry_payload(synthetic_id: str) -> dict[str, Any]:
    registry = teaching_representation_repository.load(synthetic_id)
    payload = registry.model_dump(mode="json")
    payload["slide_deck_target_schema"] = "slide_deck_v6"
    payload["slide_deck_v6_eligible"] = True
    slide_representations = [
        item for item in registry.representations
        if item.representation_type == "slide_deck" and item.status != "archived"
    ]
    selected = slide_representations[0] if slide_representations else None
    spec = next(
        (item for item in registry.specs if selected and item.spec_id == selected.spec_id),
        None,
    )
    content = (spec.payload.get("content") if spec else None) or {}
    payload.update({
        "slide_deck_target_schema": "slide_deck_v6",
        "slide_deck_candidate_schema": str(content.get("schema_version") or ""),
        "slide_deck_published_schema": str(content.get("schema_version") or ""),
        "slide_deck_candidate_status": str(content.get("candidate_status") or content.get("status") or ""),
    })
    return payload


@router.get("/courses/{course_id}/lesson-authoring")
async def get_lesson_authoring_view(
    course_id: str,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        source = _source_course(tm, course_id, allow_empty=True)
        outline_revision = _canonical_outline_revision(source)
        if outline_revision:
            repository.set_outline(course_id, outline_revision)
        jobs = repository.view(course_id).get("jobs") or {}
        for job_id, job in list(jobs.items()):
            if str((job or {}).get("status") or "") in {"pending", "running"}:
                repository.expire_stale_job(course_id, str(job_id))
        return {
            "schema_version": "teacher_lesson_authoring_view_v1",
            "pipeline_version": LESSON_PLAN_PIPELINE_VERSION,
            "plan_schema_version": "course_teaching_plan_v3",
            "course_id": course_id,
            "outline_revision_id": outline_revision,
            "lessons": _lesson_projection(source, repository),
            "jobs": list((repository.view(course_id).get("jobs") or {}).values()),
        }
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.put("/courses/{course_id}/lessons/{lesson_unit_id}/arrangement/confirm")
async def confirm_lesson_arrangement(
    course_id: str,
    lesson_unit_id: str,
    body: ConfirmLessonArrangementRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        source = _source_course(tm, course_id)
        scope = lesson_scope(source, lesson_unit_id)
        outline_revision = _canonical_outline_revision(source)
        repository.set_outline(course_id, outline_revision)
        arrangement = normalize_lesson_arrangement(
            body.model_dump(mode="json"),
            lesson_unit_id=lesson_unit_id,
            source_outline_revision_id=outline_revision,
        )
        issues = validate_lesson_arrangement(
            arrangement,
            expected_section_ids=[str(item.get("node_id") or "") for item in scope["sections"]],
        )
        if issues:
            raise TeacherLessonAuthoringError(
                "lesson_arrangement_invalid",
                issues[0]["message"],
                details={"blocking_issues": issues},
            )
        actor = resolve_user_id(request.headers.get("X-User-Id"))
        repository.save_arrangement_revision(
            course_id,
            lesson_unit_id,
            arrangement,
            source_outline_revision_id=outline_revision,
            actor=actor,
            confirm=True,
        )
        lesson = next(
            item for item in _lesson_projection(source, repository)
            if item["lesson_unit_id"] == lesson_unit_id
        )
        return {"lesson": lesson, "lesson_types": LESSON_TYPES}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-import/reviews")
async def create_imported_ppt_review(
    course_id: str,
    lesson_unit_id: str,
    body: CreateImportedPptReviewRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(get_teacher_lesson_authoring_repository),
):
    try:
        actor = resolve_user_id(request.headers.get("X-User-Id"))
        package = teacher_course_space_repository.load_owned(body.package_id, actor)
        if str(package.get("course_id") or "") != course_id:
            raise TeacherLessonAuthoringError("uploaded_ppt_course_mismatch", "上传的 PPT 不属于当前课程。")
        asset, path = teacher_course_space_repository.source_file(package, body.asset_id)
        parsed = await run_in_threadpool(
            extract_uploaded_pptx_review,
            path,
            asset_id=body.asset_id,
            filename=str(asset.get("filename") or path.name),
        )
        source = _source_course(tm, course_id)
        sources, units, revisions = _imported_ppt_review_context(
            source,
            repository,
            course_id,
            lesson_unit_id,
            actor=actor,
        )
        report = build_uploaded_ppt_review_report(
            parsed["slides"], sources=sources, reference_units=units
        )
        review = repository.save_imported_ppt_review(
            course_id,
            lesson_unit_id,
            package_id=body.package_id,
            source_asset_id=body.asset_id,
            source_filename=parsed["source_filename"],
            slides=parsed["slides"],
            report=report,
            source_outline_revision_id=revisions["outline"],
            source_lesson_plan_revision_id=revisions["plan"],
            source_script_revision_id=revisions["script"],
            actor=actor,
        )
        return {"review": review}
    except (FileNotFoundError, MaterialStorageError) as exc:
        _raise(TeacherLessonAuthoringError("uploaded_ppt_asset_not_found", "上传的 PPT 原文件不存在。"))
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.get("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-import/reviews/current")
async def get_current_imported_ppt_review(
    course_id: str,
    lesson_unit_id: str,
    repository: TeacherLessonAuthoringRepository = Depends(get_teacher_lesson_authoring_repository),
):
    return {"review": repository.current_imported_ppt_review(course_id, lesson_unit_id)}


@router.patch("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-import/reviews/{review_id}/slides/{slide_id}")
async def update_imported_ppt_slide(
    course_id: str,
    lesson_unit_id: str,
    review_id: str,
    slide_id: str,
    body: UpdateImportedPptSlideRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(get_teacher_lesson_authoring_repository),
):
    try:
        review = repository.current_imported_ppt_review(course_id, lesson_unit_id)
        if not isinstance(review, dict) or review.get("review_id") != review_id:
            raise TeacherLessonAuthoringError("uploaded_ppt_review_not_found", "PPT 审阅记录不存在。")
        slides = _updated_imported_ppt_slides(review, slide_id, body.blocks)
        source = _source_course(tm, course_id)
        sources, units, _revisions = _imported_ppt_review_context(
            source,
            repository,
            course_id,
            lesson_unit_id,
            actor=resolve_user_id(request.headers.get("X-User-Id")),
        )
        report = build_uploaded_ppt_review_report(slides, sources=sources, reference_units=units)
        updated = repository.replace_imported_ppt_review(
            course_id,
            lesson_unit_id,
            review_id=review_id,
            base_revision_id=body.base_revision_id,
            slides=slides,
            report=report,
            actor=resolve_user_id(request.headers.get("X-User-Id")),
        )
        return {"review": updated}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-import/reviews/{review_id}/ai-candidates")
async def create_imported_ppt_ai_candidate(
    course_id: str,
    lesson_unit_id: str,
    review_id: str,
    body: CreateImportedPptCandidateRequest,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(get_teacher_lesson_authoring_repository),
):
    try:
        review = repository.current_imported_ppt_review(course_id, lesson_unit_id)
        if not isinstance(review, dict) or review.get("review_id") != review_id:
            raise TeacherLessonAuthoringError("uploaded_ppt_review_not_found", "PPT 审阅记录不存在。")
        if review.get("revision_id") != body.base_revision_id:
            raise TeacherLessonAuthoringError("uploaded_ppt_revision_conflict", "PPT 工作稿已更新，请重新生成 AI 候选。")
        slide = next((item for item in review.get("slides") or [] if item.get("slide_id") == body.slide_id), None)
        if not isinstance(slide, dict):
            raise TeacherLessonAuthoringError("uploaded_ppt_slide_not_found", "PPT 页面不存在。")
        blocks = [item for item in slide.get("blocks") or [] if isinstance(item, dict)]
        title_block = next((item for item in blocks if item.get("kind") == "title" and item.get("editable")), None)
        body_block = next((item for item in blocks if item.get("kind") != "title" and item.get("editable")), None)
        page = {
            "page_id": body.slide_id,
            "title": str((title_block or {}).get("text") or slide.get("title") or "未命名页面"),
            "regions": ([{
                "region_id": str((body_block or {}).get("block_id") or "body"),
                "slot_id": "body",
                "content": str((body_block or {}).get("text") or ""),
            }] if body_block else []),
            "speaker_notes": "",
            "source_block_ids": [str(item.get("block_id") or "") for item in blocks],
        }
        optimized = await tm.course_service.optimize_teacher_lesson_v6_page(
            page=page,
            instruction=body.instruction,
        )
        proposed_blocks = deepcopy(blocks)
        proposed_by_id = {str(item.get("block_id") or ""): item for item in proposed_blocks}
        if title_block:
            proposed_by_id[str(title_block.get("block_id") or "")]["text"] = str(optimized["page"].get("title") or title_block.get("text") or "")
        if body_block and optimized["page"].get("key_message"):
            proposed_by_id[str(body_block.get("block_id") or "")]["text"] = str(optimized["page"]["key_message"])
        candidate = repository.save_imported_ppt_ai_candidate(
            course_id,
            lesson_unit_id,
            review_id=review_id,
            base_revision_id=body.base_revision_id,
            slide_id=body.slide_id,
            instruction=body.instruction.strip(),
            proposed_blocks=proposed_blocks,
        )
        return {"candidate": candidate}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-import/reviews/{review_id}/ai-candidates/{candidate_id}/resolve")
async def resolve_imported_ppt_ai_candidate(
    course_id: str,
    lesson_unit_id: str,
    review_id: str,
    candidate_id: str,
    body: ResolveImportedPptCandidateRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(get_teacher_lesson_authoring_repository),
):
    try:
        review = repository.current_imported_ppt_review(course_id, lesson_unit_id)
        candidate = next((item for item in (review or {}).get("ai_candidates") or [] if isinstance(item, dict) and item.get("candidate_id") == candidate_id), None)
        if not isinstance(review, dict) or review.get("review_id") != review_id or not isinstance(candidate, dict):
            raise TeacherLessonAuthoringError("uploaded_ppt_candidate_not_found", "AI PPT 修改候选不存在。")
        if candidate.get("status") != "pending":
            return {"review": review}
        if body.accept:
            editable = [item for item in candidate.get("proposed_blocks") or [] if isinstance(item, dict) and item.get("editable")]
            slides = _updated_imported_ppt_slides(review, str(candidate.get("slide_id") or ""), editable)
            source = _source_course(tm, course_id)
            sources, units, _revisions = _imported_ppt_review_context(
                source,
                repository,
                course_id,
                lesson_unit_id,
                actor=resolve_user_id(request.headers.get("X-User-Id")),
            )
            report = build_uploaded_ppt_review_report(slides, sources=sources, reference_units=units)
            repository.replace_imported_ppt_review(
                course_id,
                lesson_unit_id,
                review_id=review_id,
                base_revision_id=str(candidate.get("base_revision_id") or ""),
                slides=slides,
                report=report,
                actor=resolve_user_id(request.headers.get("X-User-Id")),
            )
        repository.mark_imported_ppt_ai_candidate(
            course_id,
            lesson_unit_id,
            review_id=review_id,
            candidate_id=candidate_id,
            status="accepted" if body.accept else "rejected",
        )
        return {"review": repository.current_imported_ppt_review(course_id, lesson_unit_id)}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-import/reviews/{review_id}/confirm")
async def confirm_imported_ppt_review(
    course_id: str,
    lesson_unit_id: str,
    review_id: str,
    body: ConfirmImportedPptReviewRequest,
    repository: TeacherLessonAuthoringRepository = Depends(get_teacher_lesson_authoring_repository),
):
    try:
        return {"review": repository.confirm_imported_ppt_review(
            course_id,
            lesson_unit_id,
            review_id=review_id,
            revision_id=body.revision_id,
        )}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.get("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-import/reviews/{review_id}/export.pptx")
async def export_imported_ppt_review(
    course_id: str,
    lesson_unit_id: str,
    review_id: str,
    request: Request,
    repository: TeacherLessonAuthoringRepository = Depends(get_teacher_lesson_authoring_repository),
):
    try:
        review = repository.current_imported_ppt_review(course_id, lesson_unit_id)
        if not isinstance(review, dict) or review.get("review_id") != review_id:
            raise TeacherLessonAuthoringError("uploaded_ppt_review_not_found", "PPT 审阅记录不存在。")
        actor = resolve_user_id(request.headers.get("X-User-Id"))
        package = teacher_course_space_repository.load_owned(str(review.get("package_id") or ""), actor)
        asset, source_path = teacher_course_space_repository.source_file(package, str(review.get("source_asset_id") or ""))
        export_dir = repository.root / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        output = export_dir / f"imported-{uuid.uuid4().hex}.pptx"

        def render() -> None:
            from pptx import Presentation

            presentation = Presentation(source_path)
            for slide_state in review.get("slides") or []:
                slide_index = int(slide_state.get("slide_number") or 0) - 1
                if slide_index < 0 or slide_index >= len(presentation.slides):
                    continue
                slide = presentation.slides[slide_index]
                for block in slide_state.get("blocks") or []:
                    shape_index = int(block.get("shape_index") or 0)
                    if not block.get("editable") or shape_index >= len(slide.shapes):
                        continue
                    shape = slide.shapes[shape_index]
                    if getattr(shape, "has_text_frame", False):
                        shape.text = str(block.get("text") or "")
            presentation.save(output)

        await run_in_threadpool(render)
        filename = f"{str(asset.get('filename') or 'PPT').rsplit('.', 1)[0]}-已审阅.pptx"
        return FileResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=filename,
        )
    except (FileNotFoundError, MaterialStorageError) as exc:
        _raise(TeacherLessonAuthoringError("uploaded_ppt_asset_not_found", "上传的 PPT 原文件不存在。"))
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.get("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6/source")
async def get_teacher_lesson_v6_source(
    course_id: str,
    lesson_unit_id: str,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        document, _course_view, _synthetic_id, _lesson, _revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
        return {
            "schema_version": "course_document_envelope_v1",
            "course_id": course_id,
            "course_name": document.title,
            "source_format": "canonical",
            "document": document.model_dump(mode="json"),
            "migration": {"required": False},
        }
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.get("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6")
async def get_teacher_lesson_v6_registry(
    course_id: str,
    lesson_unit_id: str,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        _document, _course_view, synthetic_id, lesson, _revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
        return {"registry": _teacher_v6_registry_payload(synthetic_id)}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.get("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6/{representation_id}/spec")
async def get_teacher_lesson_v6_spec(
    course_id: str,
    lesson_unit_id: str,
    representation_id: str,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        _document, _course_view, synthetic_id, lesson, _revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
        registry = teaching_representation_repository.load(synthetic_id)
        representation = next(
            (item for item in registry.representations if item.representation_id == representation_id),
            None,
        )
        if representation is None:
            raise TeacherLessonAuthoringError("lesson_ppt_not_found", "本讲 V6 PPT 不存在。")
        spec = next((item for item in registry.specs if item.spec_id == representation.spec_id), None)
        if spec is None:
            raise TeacherLessonAuthoringError("lesson_ppt_revision_not_found", "本讲 V6 PPT 规格不存在。")
        manuscript = (spec.payload.get("content") or {}).get("ppt_manuscript") or {}
        asset = next(
            (
                item
                for item in lesson.get("ppt_assets") or []
                if isinstance(item, dict)
                and item.get("working_representation_id") == representation_id
            ),
            {},
        )
        return {
            "representation": representation.model_dump(mode="json"),
            "spec": spec.model_dump(mode="json"),
            "ai_candidate": repository.pending_v6_ppt_ai_candidate(
                course_id,
                lesson_unit_id,
                representation_id=representation_id,
                spec_id=spec.spec_id,
                spec_revision=spec.revision,
            ),
            "ppt_manuscript_state": {
                "revision": str(manuscript.get("manuscript_revision") or ""),
                "status": str(asset.get("ppt_manuscript_status") or "draft"),
                "source_state": str(asset.get("source_state") or "current"),
                "confirmable": bool(
                    manuscript.get("manuscript_revision")
                    and asset.get("source_state") == "current"
                ),
            },
        }
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post(
    "/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6/"
    "{representation_id}/manuscript/confirm"
)
async def confirm_teacher_lesson_v6_manuscript(
    course_id: str,
    lesson_unit_id: str,
    representation_id: str,
    body: ConfirmTeacherLessonPptManuscriptRequest,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        _document, _course_view, synthetic_id, lesson, _revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
        registry = teaching_representation_repository.load(synthetic_id)
        representation = next(
            (
                item
                for item in registry.representations
                if item.representation_id == representation_id
            ),
            None,
        )
        spec = next(
            (
                item
                for item in registry.specs
                if representation and item.spec_id == representation.spec_id
            ),
            None,
        )
        manuscript = (
            (spec.payload.get("content") or {}).get("ppt_manuscript")
            if spec
            else None
        )
        if not isinstance(manuscript, dict):
            raise TeacherLessonAuthoringError(
                "lesson_ppt_manuscript_not_found", "当前 PPT 没有可确认的文书。"
            )
        if manuscript.get("manuscript_revision") != body.manuscript_revision:
            raise TeacherLessonAuthoringError(
                "lesson_ppt_manuscript_revision_conflict",
                "PPT 文书已更新，请刷新后再确认。",
            )
        asset = repository.confirm_v6_ppt_manuscript(
            course_id,
            lesson_unit_id,
            representation_id=representation_id,
            manuscript_revision=body.manuscript_revision,
        )
        return {
            "ppt_manuscript_state": {
                "revision": body.manuscript_revision,
                "status": asset.get("ppt_manuscript_status"),
                "source_state": asset.get("source_state"),
                "confirmable": True,
            }
        }
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post(
    "/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6/{representation_id}/ai-candidates"
)
async def create_teacher_lesson_v6_ai_candidate(
    course_id: str,
    lesson_unit_id: str,
    representation_id: str,
    body: CreateTeacherLessonV6CandidateRequest,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        _document, _course_view, synthetic_id, _lesson, _revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
        registry = teaching_representation_repository.load(synthetic_id)
        representation = next(
            (item for item in registry.representations if item.representation_id == representation_id),
            None,
        )
        spec = next(
            (item for item in registry.specs if representation and item.spec_id == representation.spec_id),
            None,
        )
        if representation is None or spec is None:
            raise TeacherLessonAuthoringError("lesson_ppt_not_found", "本讲 V6 PPT 不存在。")
        if spec.spec_id != body.base_spec_id or spec.revision != body.base_spec_revision:
            raise TeacherLessonAuthoringError(
                "lesson_ppt_revision_conflict", "PPT 已经变化，请基于当前页面重新优化。"
            )
        content = spec.payload.get("content") or {}
        pages = content.get("pages") if isinstance(content.get("pages"), list) else []
        page = next(
            (item for item in pages if str(item.get("page_id") or "") == body.page_id),
            None,
        )
        if not isinstance(page, dict):
            raise TeacherLessonAuthoringError("lesson_ppt_page_not_found", "当前 PPT 页面不存在。")
        optimized = await tm.course_service.optimize_teacher_lesson_v6_page(
            page=page,
            instruction=body.instruction,
        )
        candidate = repository.save_v6_ppt_ai_candidate(
            course_id,
            lesson_unit_id,
            representation_id=representation_id,
            base_spec_id=spec.spec_id,
            base_spec_revision=spec.revision,
            page_id=body.page_id,
            instruction=body.instruction.strip(),
            candidate_page=optimized["page"],
            changed_fields=list(optimized.get("changed_fields") or []),
        )
        return {"candidate": candidate}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post(
    "/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6/{representation_id}/ai-candidates/{candidate_id}/resolve"
)
async def resolve_teacher_lesson_v6_ai_candidate(
    course_id: str,
    lesson_unit_id: str,
    representation_id: str,
    candidate_id: str,
    body: ResolveTeacherLessonV6CandidateRequest,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        _document, course_view, synthetic_id, _lesson, plan_revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
        registry = teaching_representation_repository.load(synthetic_id)
        representation = next(
            (item for item in registry.representations if item.representation_id == representation_id),
            None,
        )
        spec = next(
            (item for item in registry.specs if representation and item.spec_id == representation.spec_id),
            None,
        )
        candidate = repository.pending_v6_ppt_ai_candidate(
            course_id,
            lesson_unit_id,
            representation_id=representation_id,
            spec_id=str(spec.spec_id if spec else ""),
            spec_revision=str(spec.revision if spec else ""),
        )
        if not isinstance(candidate, dict) or candidate.get("candidate_id") != candidate_id:
            raise TeacherLessonAuthoringError(
                "lesson_ppt_candidate_not_found", "AI PPT 候选不存在或已过期。"
            )
        if not body.accept:
            resolved = repository.mark_v6_ppt_ai_candidate(
                course_id, lesson_unit_id, candidate_id, status="rejected"
            )
            return {"candidate": resolved, "status": "rejected"}
        if representation is None or spec is None:
            raise TeacherLessonAuthoringError("lesson_ppt_not_found", "本讲 V6 PPT 不存在。")
        payload = deepcopy(spec.payload)
        content = payload.get("content") or {}
        pages = content.get("pages") if isinstance(content.get("pages"), list) else []
        page = next(
            (item for item in pages if str(item.get("page_id") or "") == candidate.get("page_id")),
            None,
        )
        if not isinstance(page, dict):
            raise TeacherLessonAuthoringError("lesson_ppt_page_not_found", "当前 PPT 页面不存在。")
        candidate_page = candidate.get("candidate_page") or {}
        for field in candidate.get("changed_fields") or []:
            if field in {"title", "subtitle", "key_message"}:
                _apply_v6_page_expression(
                    page,
                    field=field,
                    value=deepcopy(candidate_page.get(field)),
                    target_region_id=str(candidate_page.get(f"{field}_region_id") or ""),
                )
        manuscript = _refresh_v6_ppt_manuscript(
            content,
            course_view=course_view,
            source_lesson_plan_revision_id=str(plan_revision.get("revision_id") or ""),
        )
        now = datetime.now(timezone.utc).isoformat()
        spec_revision = stable_hash(payload, prefix="tsr_")
        edited_spec = TeachingRepresentationSpec(
            spec_id=stable_hash({
                "course_id": spec.course_id,
                "representation_type": spec.representation_type,
                "source_bindings": [item.model_dump(mode="json") for item in spec.source_bindings],
                "payload": payload,
            }, prefix="trs_"),
            course_id=spec.course_id,
            representation_type=spec.representation_type,
            source_bindings=spec.source_bindings,
            unit_bindings=spec.unit_bindings,
            payload=payload,
            revision=spec_revision,
            created_at=now,
            updated_at=now,
        )
        teaching_representation_repository.register_spec(edited_spec)
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
        updated_registry = teaching_representation_repository.register_representation(
            edited_representation
        )
        repository.bind_v6_ppt_revision(
            course_id,
            lesson_unit_id,
            source_lesson_plan_revision_id=str(plan_revision.get("revision_id") or ""),
            source_script_revision_id=str(
                (course_view.get("teacher_lesson_source") or {}).get("script_revision_id") or ""
            ),
            synthetic_course_id=synthetic_id,
            representation_id=edited_representation.representation_id,
            spec_id=edited_spec.spec_id,
            candidate_status=str(content.get("status") or content.get("candidate_status") or "v6_ready"),
            ppt_manuscript_revision=str(manuscript.get("manuscript_revision") or ""),
            ppt_manuscript_status="draft",
        )
        resolved = repository.mark_v6_ppt_ai_candidate(
            course_id,
            lesson_unit_id,
            candidate_id,
            status="accepted",
            result_spec_id=edited_spec.spec_id,
        )
        return {
            "candidate": resolved,
            "status": "accepted",
            "registry": updated_registry.model_dump(mode="json"),
            "spec": edited_spec.model_dump(mode="json"),
        }
    except TeacherLessonAuthoringError as exc:
        _raise(exc)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "teacher_v6_edit_quality_blocked", "message": str(exc)},
        ) from exc


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6/build/stream")
async def build_teacher_lesson_v6(
    course_id: str,
    lesson_unit_id: str,
    body: TeacherLessonV6BuildRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        document, course_view, synthetic_id, lesson, revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
        actor = resolve_user_id(request.headers.get("X-User-Id"))
        material_bindings, material_evidence = _ppt_material_bundle(
            course_id, actor, lesson_unit_id
        )
        document = _attach_ppt_reference_evidence(document, material_evidence)
        teacher_source = dict(course_view.get("teacher_lesson_source") or {})
        teacher_source["material_bindings"] = material_bindings
        course_view["teacher_lesson_source"] = teacher_source
        course_view["evidence_catalog"] = material_evidence
    except TeacherLessonAuthoringError as exc:
        _raise(exc)
    source_plan_revision = str(revision.get("revision_id") or lesson.get("confirmed_revision_id") or "")
    source_script_revision = str(
        (course_view.get("teacher_lesson_source") or {}).get("script_revision_id") or ""
    )
    source_material_revision = stable_hash(
        material_bindings, prefix="pptrefs_"
    )
    task_id = f"teacher-v6-{uuid.uuid4().hex}"
    template = compile_builtin_template_layout_contract_v1(body.theme)
    orchestrator = SlideDeckV6Orchestrator(
        representation_repository=teaching_representation_repository,
        candidate_repository=SlideDeckV6CandidateRepository(repository.root / "v6_candidates"),
        progress_root=repository.root / "v6_progress",
    )
    story_planner = build_ai_base_story_planner_v6()
    visual_planner = build_ai_base_visual_planner_v2()

    async def event_stream():
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        sequence = 0

        async def progress(payload: dict[str, object]) -> None:
            await queue.put({
                "event": "slide_build_progress_v2",
                "progress": int(payload.get("percent") or 0),
                "stage": str(payload.get("stage") or "building"),
                "message": (
                    f"正在结合已确认讲稿与 {len(material_bindings)} 份资料编译 PPT 文书"
                    if material_bindings
                    else "正在从已确认讲稿编译 PPT 文书与页面表达"
                ),
                "slide_build_progress_v2": deepcopy(payload),
                "target_schema": "slide_deck_v6",
            })

        def source_revision_provider() -> str:
            current = repository.lesson(course_id, lesson_unit_id)
            confirmation = current.get("script_confirmation") or {}
            try:
                current_bindings, _current_evidence = _ppt_material_bundle(
                    course_id, actor, lesson_unit_id
                )
                materials_current = (
                    stable_hash(current_bindings, prefix="pptrefs_")
                    == source_material_revision
                )
            except TeacherLessonAuthoringError:
                materials_current = False
            return (
                str(document.document_revision or "")
                if current.get("confirmed_revision_id") == source_plan_revision
                and current.get("working_script_revision_id") == source_script_revision
                and confirmation.get("confirmed_revision_id") == source_script_revision
                and confirmation.get("source_state", "current") == "current"
                and materials_current
                else ""
            )

        async def run() -> None:
            try:
                result = await orchestrator.build(
                    task_id=task_id,
                    document=document,
                    course_data=course_view,
                    mode=body.mode,
                    theme=body.theme,
                    story_planner=story_planner,
                    visual_planner=visual_planner,
                    source_revision_provider=source_revision_provider,
                    template_contract=template,
                    template_digest_provider=lambda: template.template_digest,
                    publish_result=True,
                    progress_callback=progress,
                )
                repository.bind_v6_ppt_revision(
                    course_id,
                    lesson_unit_id,
                    source_lesson_plan_revision_id=source_plan_revision,
                    source_script_revision_id=source_script_revision,
                    synthetic_course_id=synthetic_id,
                    representation_id=str(result.get("representation_id") or ""),
                    spec_id=str(result.get("spec_id") or ""),
                    candidate_status=str(result.get("candidate_status") or result.get("status") or ""),
                    ppt_manuscript_revision=str(
                        result.get("ppt_manuscript_revision") or ""
                    ),
                    ppt_manuscript_status="draft",
                )
                await queue.put({
                    "event": "build_complete",
                    "progress": 100,
                    "stage": "complete",
                    "target_schema": "slide_deck_v6",
                    "quality": result.get("quality") or {},
                    "build": result,
                    "registry": _teacher_v6_registry_payload(synthetic_id),
                })
            except V6BuildError as exc:
                failure = exc.failure.model_dump(mode="json")
                await queue.put({
                    "event": "build_failed",
                    "progress": 100,
                    "stage": failure.get("stage") or "failed",
                    **failure,
                })
            except Exception as exc:
                await queue.put({
                    "event": "build_failed",
                    "progress": 100,
                    "stage": "failed",
                    "code": "teacher_lesson_v6_failed",
                    "message": str(exc),
                    "retryable": True,
                })
            finally:
                await queue.put(None)

        worker = asyncio.create_task(run())
        while True:
            payload = await queue.get()
            if payload is None:
                break
            sequence += 1
            name = str(payload.get("event") or "message")
            yield f"id: {sequence}\nevent: {name}\ndata: {json.dumps({**payload, 'sequence': sequence}, ensure_ascii=False)}\n\n"
        await worker

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6/{representation_id}/export.pptx")
async def export_teacher_lesson_v6(
    course_id: str,
    lesson_unit_id: str,
    representation_id: str,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        _document, _course_view, synthetic_id, lesson, _revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
        registry = teaching_representation_repository.load(synthetic_id)
        representation = next(
            (item for item in registry.representations if item.representation_id == representation_id),
            None,
        )
        spec = next(
            (item for item in registry.specs if representation and item.spec_id == representation.spec_id),
            None,
        )
        if representation is None or spec is None:
            raise TeacherLessonAuthoringError("lesson_ppt_not_found", "本讲 V6 PPT 不存在。")
        manuscript = (spec.payload.get("content") or {}).get("ppt_manuscript")
        if isinstance(manuscript, dict):
            asset = next(
                (
                    item
                    for item in lesson.get("ppt_assets") or []
                    if isinstance(item, dict)
                    and item.get("working_representation_id") == representation_id
                ),
                {},
            )
            if (
                asset.get("ppt_manuscript_status") != "confirmed"
                or asset.get("ppt_manuscript_revision")
                != manuscript.get("manuscript_revision")
            ):
                raise TeacherLessonAuthoringError(
                    "lesson_ppt_manuscript_not_confirmed",
                    "请先确认 PPT 文书，再导出正式 PPTX。",
                )
        output = repository.root / "exports" / f"{synthetic_id}-{representation_id}-{spec.revision}.pptx"
        output.parent.mkdir(parents=True, exist_ok=True)
        await run_in_threadpool(export_slide_deck_pptx, spec, output, theme="qizhi-classroom")
        return FileResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=f"{lesson_unit_id}-V6课堂课件.pptx",
        )
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6/{representation_id}/edits/preview")
async def preview_teacher_lesson_v6_edit(
    course_id: str,
    lesson_unit_id: str,
    representation_id: str,
    body: TeacherLessonRepresentationEditRequest,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        _document, _course_view, synthetic_id, _lesson, _revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
        registry = teaching_representation_repository.load(synthetic_id)
        representation = next((item for item in registry.representations if item.representation_id == representation_id), None)
        spec = next((item for item in registry.specs if representation and item.spec_id == representation.spec_id), None)
        if representation is None or spec is None:
            raise TeacherLessonAuthoringError("lesson_ppt_not_found", "本讲 V6 PPT 不存在。")
        classification = classify_representation_edit(
            field=body.field,
            before=body.before,
            after=body.after,
            semantic_intent=body.semantic_intent,
        )
        impact = representation_edit_impact(
            registry,
            spec,
            unit_id=body.unit_id,
            field=body.field,
            semantic_change=classification.get("semantic_change"),
        )
        return {"status": "preview", **classification, "impact": impact}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6/{representation_id}/edits/apply")
async def apply_teacher_lesson_v6_edit(
    course_id: str,
    lesson_unit_id: str,
    representation_id: str,
    body: TeacherLessonApplyRepresentationEditRequest,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    if body.decision != "representation_only":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "teacher_semantic_edit_requires_lesson_plan",
                "message": "语义修改请回到本讲教案；PPT 工作台只保存表达层修改。",
            },
        )
    try:
        _document, _course_view, synthetic_id, _lesson, _revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
        registry = teaching_representation_repository.load(synthetic_id)
        representation = next((item for item in registry.representations if item.representation_id == representation_id), None)
        spec = next((item for item in registry.specs if representation and item.spec_id == representation.spec_id), None)
        if representation is None or spec is None:
            raise TeacherLessonAuthoringError("lesson_ppt_not_found", "本讲 V6 PPT 不存在。")
        payload = deepcopy(spec.payload)
        content = payload.get("content") or {}
        pages = content.get("pages") if isinstance(content.get("pages"), list) else None
        if pages is None or content.get("schema_version") != "slide_deck_v6":
            raise HTTPException(
                status_code=422,
                detail={"code": "teacher_v6_edit_unsupported", "message": "当前 V6 规格不支持页面编辑。"},
            )
        page = next(
            (item for item in pages if str(item.get("page_id") or "") == body.unit_id),
            None,
        )
        if page is None:
            raise HTTPException(status_code=404, detail="V6 page not found")
        if body.field not in {"title", "subtitle", "key_message"}:
            raise HTTPException(
                status_code=422,
                detail={"code": "teacher_v6_edit_field_unsupported", "message": "当前字段请通过原 V6 专用编辑器处理。"},
            )
        _apply_v6_page_expression(
            page,
            field=body.field,
            value=deepcopy(body.after),
        )
        manuscript = _refresh_v6_ppt_manuscript(
            content,
            course_view=_course_view,
            source_lesson_plan_revision_id=str(_revision.get("revision_id") or ""),
        )
        now = datetime.now(timezone.utc).isoformat()
        spec_revision = stable_hash(payload, prefix="tsr_")
        edited_spec = TeachingRepresentationSpec(
            spec_id=stable_hash({
                "course_id": spec.course_id,
                "representation_type": spec.representation_type,
                "source_bindings": [item.model_dump(mode="json") for item in spec.source_bindings],
                "payload": payload,
            }, prefix="trs_"),
            course_id=spec.course_id,
            representation_type=spec.representation_type,
            source_bindings=spec.source_bindings,
            unit_bindings=spec.unit_bindings,
            payload=payload,
            revision=spec_revision,
            created_at=now,
            updated_at=now,
        )
        teaching_representation_repository.register_spec(edited_spec)
        edited_representation = representation.model_copy(deep=True)
        edited_representation.spec_id = edited_spec.spec_id
        edited_representation.semantic_fingerprint = stable_hash(content, prefix="sem_")
        edited_representation.render_fingerprint = stable_hash({
            "spec_revision": spec_revision,
            "renderer": "slide_deck_v6",
        }, prefix="rnd_")
        edited_representation.revision = stable_hash({
            "spec_revision": spec_revision,
            "source_revision_vector": edited_representation.source_revision_vector,
        }, prefix="rpr_")
        edited_representation.updated_at = now
        updated = teaching_representation_repository.register_representation(edited_representation)
        repository.bind_v6_ppt_revision(
            course_id,
            lesson_unit_id,
            source_lesson_plan_revision_id=str(_revision.get("revision_id") or ""),
            source_script_revision_id=str(
                (_course_view.get("teacher_lesson_source") or {}).get("script_revision_id") or ""
            ),
            synthetic_course_id=synthetic_id,
            representation_id=edited_representation.representation_id,
            spec_id=edited_spec.spec_id,
            candidate_status=str(content.get("status") or content.get("candidate_status") or "v6_ready"),
            ppt_manuscript_revision=str(manuscript.get("manuscript_revision") or ""),
            ppt_manuscript_status="draft",
        )
        return {"status": "applied_to_representation", "registry": updated.model_dump(mode="json")}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "teacher_v6_edit_quality_blocked", "message": str(exc)},
        ) from exc


@router.get("/courses/{course_id}/knowledge-evidence")
async def get_lesson_knowledge_evidence(
    course_id: str,
    lesson_unit_id: str = "",
    tm: TaskManager = Depends(require_task_manager),
):
    try:
        source = _source_course(tm, course_id)
        nodes = [item for item in source.get("nodes") or [] if isinstance(item, dict)]
        if lesson_unit_id:
            scope = lesson_scope(source, lesson_unit_id)
            section_ids = {str(item.get("node_id") or "") for item in scope["sections"]}
            nodes = [item for item in nodes if str(item.get("node_id") or "") in section_ids]
        points: list[dict[str, Any]] = []
        for node in nodes:
            for group in node.get("knowledge_structure") or []:
                if not isinstance(group, dict):
                    continue
                for point in group.get("knowledge_points") or []:
                    if not isinstance(point, dict):
                        continue
                    sources = point.get("source_refs") or point.get("evidence_refs") or []
                    if isinstance(sources, str):
                        sources = [sources]
                    points.append({
                        "section_node_id": str(node.get("node_id") or ""),
                        "section_title": str(node.get("node_name") or ""),
                        "name": str(point.get("name") or ""),
                        "statement": str(point.get("statement") or point.get("description") or ""),
                        "sources": [str(item) for item in sources if str(item).strip()],
                        "conflict": bool(point.get("conflict") or point.get("needs_manual_review")),
                    })
        return {
            "schema_version": "teacher_lesson_knowledge_evidence_v1",
            "course_id": course_id,
            "lesson_unit_id": lesson_unit_id,
            "points": points,
            "conflict_count": sum(1 for item in points if item["conflict"]),
        }
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/plan/generate", status_code=202)
async def generate_lesson_plan(
    course_id: str,
    lesson_unit_id: str,
    body: GenerateLessonPlanRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        source = _source_course(tm, course_id)
        scope = lesson_scope(source, lesson_unit_id)
        source_evidence: list[dict[str, Any]] = []
        source_filename = ""
        primary_source_kind = ""
        primary_material_asset_id = ""
        actor = resolve_user_id(request.headers.get("X-User-Id"))
        if bool(body.source_package_id) != bool(body.source_asset_id):
            raise TeacherLessonAuthoringError(
                "lesson_primary_source_incomplete",
                "主来源信息不完整。",
            )
        if body.source_package_id and body.source_asset_id:
            try:
                package = teacher_course_space_repository.load_owned(
                    body.source_package_id,
                    actor,
                )
                source_asset, source_path = teacher_course_space_repository.source_file(
                    package,
                    body.source_asset_id,
                )
            except (FileNotFoundError, MaterialStorageError) as exc:
                raise TeacherLessonAuthoringError(
                    "lesson_primary_source_not_found",
                    "主来源不存在或无权访问。",
                ) from exc
            if str(package.get("course_id") or "") != course_id:
                raise TeacherLessonAuthoringError(
                    "lesson_primary_source_course_mismatch",
                    "主来源不属于当前课程。",
                )
            source_filename = str(source_asset.get("filename") or "")
            extension = str(
                source_asset.get("extension") or source_path.suffix or ""
            ).lower()
            if not extension.startswith(".") and extension:
                extension = f".{extension}"
            if extension == ".pptx":
                primary_source_kind = "uploaded_ppt"
                source_evidence = await run_in_threadpool(
                    extract_uploaded_pptx_evidence,
                    source_path,
                    asset_id=body.source_asset_id,
                )
            elif extension in {".docx", ".pdf", ".md", ".markdown", ".txt"}:
                primary_source_kind = "uploaded_lesson_plan"
                primary_material_asset_id = str(
                    source_asset.get("material_asset_id") or ""
                )
                try:
                    material = (
                        material_repository.get_asset(primary_material_asset_id)
                        if primary_material_asset_id
                        else None
                    )
                    document = (
                        await parse_material_asset(material_repository, material)
                        if material is not None
                        else await parse_document_path(
                            source_path,
                            asset_id=body.source_asset_id,
                            filename=source_filename or source_path.name,
                        )
                    )
                except Exception as exc:
                    raise TeacherLessonAuthoringError(
                        "lesson_primary_source_parse_failed",
                        "原教案解析失败，请检查文件后重试。",
                    ) from exc
                if document.parse_status not in {"parsed", "degraded"} or not document.blocks:
                    raise TeacherLessonAuthoringError(
                        "lesson_primary_source_parse_failed",
                        "原教案没有提取到可用于生成的内容。",
                    )
                source_evidence = compile_original_lesson_plan_evidence(
                    document,
                    asset_id=(primary_material_asset_id or body.source_asset_id),
                    filename=source_filename or source_path.name,
                    sections=scope["sections"],
                )
            else:
                raise TeacherLessonAuthoringError(
                    "lesson_primary_source_unsupported",
                    "主来源暂时支持 DOCX、PDF、Markdown、TXT 或 PPTX。",
                )
        selected_material_ids, selected_evidence = _course_material_evidence(
            course_id, actor, body.material_asset_ids
        )
        source_evidence.extend(selected_evidence)
        outline_revision = _canonical_outline_revision(source)
        repository.set_outline(course_id, outline_revision)
        arrangement = repository.confirmed_arrangement(course_id, lesson_unit_id)
        if not arrangement:
            raise TeacherLessonAuthoringError(
                "lesson_arrangement_not_confirmed",
                "请先确认本讲课型与教学块，再生成教案。",
            )
        input_fingerprint = stable_hash({
            "lesson_unit_id": lesson_unit_id,
            "source_outline_revision_id": outline_revision,
            "source_package_id": body.source_package_id,
            "source_asset_id": body.source_asset_id,
            "requirements": body.requirements.strip(),
            "material_asset_ids": sorted(selected_material_ids),
            "arrangement": arrangement,
        }, prefix="teacher-lesson-plan-input")
        resume_checkpoint: dict[str, Any] = {}
        if body.resume_job_id:
            previous = repository.get_job(course_id, body.resume_job_id)
            if (
                previous.get("lesson_unit_id") == lesson_unit_id
                and previous.get("type") == "teacher_lesson_plan_generation"
                and previous.get("input_fingerprint") == input_fingerprint
            ):
                resume_checkpoint = deepcopy(previous.get("checkpoint") or {})
        job = repository.create_job(
            course_id,
            lesson_unit_id,
            request_id=body.request_id,
            source_outline_revision_id=outline_revision,
        )
        job = repository.update_job(
            course_id,
            str(job["id"]),
            input_fingerprint=input_fingerprint,
            resume_from_job_id=(body.resume_job_id if resume_checkpoint else ""),
            requirements=body.requirements,
            material_asset_ids=selected_material_ids,
        )
        if source_evidence:
            job_source_kind = (
                "mixed_course_sources"
                if body.source_asset_id and selected_material_ids
                else primary_source_kind
                if body.source_asset_id
                else "course_materials"
            )
            job = repository.update_job(
                course_id,
                str(job["id"]),
                source_asset_id=(body.source_asset_id or selected_material_ids[0]),
                source_package_id=body.source_package_id,
                source_filename=(
                    source_filename
                    or f"{len(selected_material_ids)} 份课程资料"
                ),
                source_kind=job_source_kind,
                source_material_asset_id=primary_material_asset_id,
            )
        if job.get("status") in {"running", "completed", "completed_with_warnings"}:
            return {"job": job}

        service = TeacherLessonAuthoringService(repository)

        async def planner(
            course: dict[str, Any],
            lesson_id: str,
            on_progress,
        ) -> dict[str, Any]:
            scoped_course = deepcopy(course)
            normalized_requirements = body.requirements.strip()
            if normalized_requirements:
                scoped_course["requirements"] = normalized_requirements
                scoped_course.setdefault("metadata", {}).setdefault(
                    "teacher_lesson_requirements", {}
                )[lesson_id] = normalized_requirements
                for plan_key in ("course_plan", "course_outline"):
                    scoped_plan = scoped_course.get(plan_key)
                    if not isinstance(scoped_plan, dict):
                        continue
                    for chapter in scoped_plan.get("chapters") or []:
                        if not isinstance(chapter, dict):
                            continue
                        chapter_id = str(
                            chapter.get("node_id")
                            or chapter.get("chapter_id")
                            or ""
                        )
                        if chapter_id != lesson_id:
                            continue
                        chapter["teacher_requirements"] = normalized_requirements
                        for section in chapter.get("sections") or []:
                            if isinstance(section, dict):
                                section["teacher_requirements"] = normalized_requirements
            return await tm.course_service.prepare_teacher_lesson_plan(
                course_data=scoped_course,
                lesson_unit_id=lesson_id,
                on_phase=on_progress,
                source_evidence=source_evidence,
                lesson_arrangement=arrangement,
                resume_checkpoint=resume_checkpoint,
                on_checkpoint=lambda checkpoint: repository.update_job(
                    course_id,
                    str(job["id"]),
                    checkpoint=checkpoint,
                ),
            )

        async def run() -> None:
            await service.run_plan_job(
                course_id=course_id,
                lesson_unit_id=lesson_unit_id,
                job_id=str(job["id"]),
                course_data=source,
                planner=planner,
            )

        task = asyncio.create_task(run())
        _background_jobs.add(task)
        task.add_done_callback(_background_jobs.discard)
        return {"job": {**job, "actor": actor}}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.get("/courses/{course_id}/lesson-jobs/{job_id}")
async def get_lesson_job(
    course_id: str,
    job_id: str,
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        job = await run_in_threadpool(repository.get_job, course_id, job_id)
        if str(job.get("status") or "") in {"pending", "running"}:
            job = await run_in_threadpool(
                repository.expire_stale_job,
                course_id,
                job_id,
            )
        return {"job": job}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.delete("/courses/{course_id}/lesson-jobs/{job_id}")
async def cancel_lesson_job(
    course_id: str,
    job_id: str,
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        job = await run_in_threadpool(repository.cancel_job, course_id, job_id)
        return {"job": job}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.get("/courses/{course_id}/lesson-jobs/{job_id}/stream")
async def stream_lesson_job(
    course_id: str,
    job_id: str,
    request: Request,
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    """Stream the durable lesson-plan candidate while final save stays atomic."""
    try:
        await run_in_threadpool(repository.get_job, course_id, job_id)
    except TeacherLessonAuthoringError as exc:
        _raise(exc)

    async def event_stream():
        last_sequence = -1
        last_updated_at = ""
        while True:
            if await request.is_disconnected():
                return
            try:
                job = await run_in_threadpool(
                    repository.get_job,
                    course_id,
                    job_id,
                )
                if str(job.get("status") or "") in {"pending", "running"}:
                    job = await run_in_threadpool(
                        repository.expire_stale_job,
                        course_id,
                        job_id,
                    )
            except TeacherLessonAuthoringError:
                payload = {
                    "event": "error",
                    "job_id": job_id,
                    "message": "本讲生成任务不存在或已被清理。",
                }
                yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                return
            sequence = int(job.get("stream_sequence") or 0)
            updated_at = str(job.get("updated_at") or "")
            status = str(job.get("status") or "")
            terminal = status in {
                "completed",
                "completed_with_warnings",
                "failed",
                "cancelled",
            }
            if sequence > last_sequence or updated_at != last_updated_at:
                last_sequence = sequence
                last_updated_at = updated_at
                script_job = str(job.get("type") or "") == "teacher_lesson_script_generation"
                event = (
                    "lesson_script_complete"
                    if script_job and status in {"completed", "completed_with_warnings"}
                    else "lesson_script_cancelled"
                    if script_job and status == "cancelled"
                    else "lesson_script_failed"
                    if script_job and status == "failed"
                    else "lesson_script_stream"
                    if script_job
                    else "lesson_plan_complete"
                    if status in {"completed", "completed_with_warnings"}
                    else "lesson_plan_cancelled"
                    if status == "cancelled"
                    else "lesson_plan_failed"
                    if status == "failed"
                    else "lesson_plan_stream"
                )
                payload = {
                    "event": event,
                    "job": {
                        "id": job_id,
                        "schema_version": str(job.get("schema_version") or ""),
                        "course_id": course_id,
                        "lesson_unit_id": str(job.get("lesson_unit_id") or ""),
                        "type": str(job.get("type") or ""),
                        "status": status,
                        "phase": str(job.get("phase") or ""),
                        "progress": int(job.get("progress") or 0),
                        "message": str(job.get("message") or ""),
                        "warnings": deepcopy(job.get("warnings") or []),
                        "error": deepcopy(job.get("error")),
                        "result_revision_id": str(job.get("result_revision_id") or ""),
                        "stream_sequence": sequence,
                        "stream_batches": deepcopy(job.get("stream_batches") or {}),
                        "stream_complete": bool(job.get("stream_complete")),
                        "checkpoint": deepcopy(job.get("checkpoint") or {}),
                        "cancel_requested": bool(job.get("cancel_requested")),
                        "retryable": bool(job.get("retryable")),
                        "heartbeat_at": str(job.get("heartbeat_at") or ""),
                        "requirements": str(job.get("requirements") or ""),
                        "total_blocks": int(job.get("total_blocks") or 0),
                        "completed_blocks": int(job.get("completed_blocks") or 0),
                        "current_block_id": str(job.get("current_block_id") or ""),
                        "current_block_title": str(job.get("current_block_title") or ""),
                        "block_states": deepcopy(job.get("block_states") or {}),
                        "result_sections": deepcopy(job.get("result_sections") or []),
                        "updated_at": updated_at,
                    },
                }
                yield (
                    f"id: {sequence}\n"
                    f"event: {event}\n"
                    f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                )
            if terminal:
                return
            await asyncio.sleep(0.35)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.patch("/courses/{course_id}/lessons/{lesson_unit_id}/plan/draft")
async def save_lesson_plan_draft(
    course_id: str,
    lesson_unit_id: str,
    body: SaveLessonPlanDraftRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        source = _source_course(tm, course_id)
        canonical_outline_revision = _canonical_outline_revision(source)
        if canonical_outline_revision:
            repository.set_outline(course_id, canonical_outline_revision)
        lesson = TeacherLessonAuthoringService(repository).save_plan_draft(
            course_id=course_id,
            lesson_unit_id=lesson_unit_id,
            course_data=source,
            plan=body.plan,
            source_outline_revision_id=body.source_outline_revision_id,
            actor=resolve_user_id(request.headers.get("X-User-Id")),
        )
        return {"lesson": lesson}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/plan/confirm")
async def confirm_lesson_plan(
    course_id: str,
    lesson_unit_id: str,
    body: ConfirmLessonPlanRequest,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        source = _source_course(tm, course_id)
        canonical_outline_revision = _canonical_outline_revision(source)
        if canonical_outline_revision:
            repository.set_outline(course_id, canonical_outline_revision)
        return {
            "lesson": TeacherLessonAuthoringService(repository).confirm_plan(
                course_id=course_id,
                lesson_unit_id=lesson_unit_id,
                course_data=source,
                revision_id=body.revision_id,
            )
        }
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/script/confirm")
async def confirm_lesson_script(
    course_id: str,
    lesson_unit_id: str,
    body: ConfirmLessonScriptRequest,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        source = _source_course(tm, course_id)
        lesson = repository.lesson(course_id, lesson_unit_id)
        current_revision = str(lesson.get("working_script_revision_id") or "")
        if not current_revision:
            scope = lesson_scope(source, lesson_unit_id)
            legacy_sections = [
                {
                    "section_node_id": str(section.get("node_id") or ""),
                    "title": str(section.get("node_name") or ""),
                    "content": str(section.get("node_content") or ""),
                }
                for section in scope["sections"]
            ]
            if legacy_sections and all(item["content"].strip() for item in legacy_sections):
                migrated = repository.save_script_revision(
                    course_id,
                    lesson_unit_id,
                    legacy_sections,
                    source_lesson_plan_revision_id=str(lesson.get("confirmed_revision_id") or ""),
                    generation_source="legacy_course_content",
                )
                current_revision = str(migrated.get("working_script_revision_id") or "")
        if body.revision_id != current_revision:
            raise TeacherLessonAuthoringError(
                "lesson_script_revision_conflict",
                "讲稿内容已经变化，请基于当前版本重新确认。",
                details={"current_revision_id": current_revision},
            )
        repository.confirm_script_revision(
            course_id,
            lesson_unit_id,
            current_revision,
        )
        lesson = next(
            item for item in _lesson_projection(source, repository)
            if item["lesson_unit_id"] == lesson_unit_id
        )
        return {"lesson": lesson}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post(
    "/courses/{course_id}/lessons/{lesson_unit_id}/script/generate",
    status_code=202,
)
async def generate_lesson_script(
    course_id: str,
    lesson_unit_id: str,
    body: GenerateLessonScriptRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        source = _source_course(tm, course_id)
        scope = lesson_scope(source, lesson_unit_id)
        lesson = repository.lesson(course_id, lesson_unit_id)
        plan_revision_id = str(lesson.get("confirmed_revision_id") or "")
        if not plan_revision_id:
            raise TeacherLessonAuthoringError(
                "lesson_plan_not_confirmed",
                "请先确认本讲教案，再生成讲稿。",
            )
        plan_revision = _plan_revision(
            repository, course_id, lesson_unit_id, plan_revision_id
        )
        plan_sections = {
            str(item.get("node_id") or ""): item
            for item in (plan_revision.get("plan") or {}).get("sections") or []
            if isinstance(item, dict) and item.get("node_id")
        }
        actor = resolve_user_id(request.headers.get("X-User-Id"))
        selected_material_ids, source_evidence = _course_material_evidence(
            course_id, actor, body.material_asset_ids
        )
        prompt_evidence = _prompt_material_evidence(source_evidence)
        register = getattr(tm.course_service, "register_course_generation_metadata", None)
        if callable(register):
            register(course_id, source)
        input_fingerprint = stable_hash({
            "lesson_unit_id": lesson_unit_id,
            "source_lesson_plan_revision_id": plan_revision_id,
            "requirements": body.requirements.strip(),
            "material_asset_ids": selected_material_ids,
        }, prefix="teacher-script-input")
        seed_sections: list[dict[str, Any]] = []
        if body.resume_job_id:
            previous = repository.get_job(course_id, body.resume_job_id)
            if (
                previous.get("lesson_unit_id") == lesson_unit_id
                and previous.get("type") == "teacher_lesson_script_generation"
                and previous.get("input_fingerprint") == input_fingerprint
                and previous.get("source_lesson_plan_revision_id") == plan_revision_id
            ):
                seed_sections = [
                    deepcopy(item)
                    for item in previous.get("result_sections") or []
                    if isinstance(item, dict)
                ]

        job = repository.create_job(
            course_id,
            lesson_unit_id,
            job_type="teacher_lesson_script_generation",
            request_id=body.request_id,
            source_outline_revision_id=_canonical_outline_revision(source),
        )
        job = repository.update_job(
            course_id,
            str(job["id"]),
            source_lesson_plan_revision_id=plan_revision_id,
            input_fingerprint=input_fingerprint,
            requirements=body.requirements,
            material_asset_ids=selected_material_ids,
            actor=actor,
        )
        if job.get("status") in {"running", "completed", "completed_with_warnings"}:
            return {"job": job}

        lesson_title = str(scope["lesson"].get("node_name") or "")
        lesson_section_titles = [
            str(item.get("node_name") or "") for item in scope["sections"]
        ]

        async def generate_block(
            outline_section: dict[str, Any],
            confirmed_plan: dict[str, Any],
            module: dict[str, Any],
            completed_blocks: list[dict[str, Any]],
        ) -> str:
            module_id = str(module.get("module_id") or "")
            single_outline = deepcopy(outline_section)
            single_outline["module_plan"] = [{
                **deepcopy(module),
                "label": str(module.get("title") or module_id),
            }]
            single_plan = deepcopy(confirmed_plan)
            single_plan["teaching_modules"] = [{
                **deepcopy(module),
                "label": str(module.get("title") or module_id),
            }]
            try:
                generated = await asyncio.wait_for(
                    tm.course_service.generate_teacher_script_section(
                    course_id=course_id,
                    outline_section=single_outline,
                    confirmed_plan_section=single_plan,
                    lesson_context={
                        "lesson_title": lesson_title,
                        "lesson_sections": lesson_section_titles,
                        "current_block": {
                            "block_id": module.get("block_id"),
                            "module_id": module_id,
                            "title": module.get("title"),
                            "role": module.get("role"),
                        },
                        "previous_script_blocks": [
                            {
                                "title": item.get("title"),
                                # Only a short tail is needed for transition
                                # and de-duplication. Passing several complete
                                # blocks makes the next lightweight block copy
                                # the earlier textbook-like exposition.
                                "content": str(item.get("content") or "")[-320:],
                            }
                            for item in completed_blocks[-3:]
                        ],
                        "material_asset_ids": selected_material_ids,
                        "selected_material_evidence": prompt_evidence,
                    },
                    requirements=body.requirements,
                    user_id=actor,
                    ),
                    timeout=150,
                )
            except asyncio.TimeoutError as exc:
                raise TeacherLessonAuthoringError(
                    "lesson_script_block_timeout",
                    f"“{module.get('title') or module_id}”生成超时，已保留前面完成的教学块。",
                ) from exc
            blocks = [
                item for item in generated.get("blocks") or [] if isinstance(item, dict)
            ]
            content = str((blocks[0] if blocks else {}).get("content") or "").strip()
            if not content:
                raise TeacherLessonAuthoringError(
                    "lesson_script_block_empty",
                    f"{module.get('title') or module_id} 没有生成有效内容，请重试。",
                )
            return content

        async def run() -> None:
            try:
                await TeacherLessonAuthoringService(repository).run_script_job(
                    course_id=course_id,
                    lesson_unit_id=lesson_unit_id,
                    job_id=str(job["id"]),
                    source_plan_revision_id=plan_revision_id,
                    outline_sections=scope["sections"],
                    plan_sections=plan_sections,
                    generator=generate_block,
                    seed_sections=seed_sections,
                    requirements=body.requirements,
                    material_asset_ids=selected_material_ids,
                    actor=actor,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                current = repository.get_job(course_id, str(job["id"]))
                if current.get("status") not in {
                    "completed", "completed_with_warnings", "failed",
                }:
                    repository.update_job(
                        course_id,
                        str(job["id"]),
                        status="failed",
                        phase="lesson_script_failed",
                        message="本讲讲稿生成失败",
                        stream_sequence=int(current.get("stream_sequence") or 0) + 1,
                        stream_complete=True,
                        error={
                            "code": "lesson_script_generation_failed",
                            "message": str(exc),
                            "retryable": True,
                        },
                    )

        task = asyncio.create_task(run())
        _background_jobs.add(task)
        task.add_done_callback(_background_jobs.discard)
        return {"job": job}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.put("/courses/{course_id}/lessons/{lesson_unit_id}/script/draft")
async def save_lesson_script_draft(
    course_id: str,
    lesson_unit_id: str,
    body: SaveLessonScriptDraftRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        source = _source_course(tm, course_id)
        scope = lesson_scope(source, lesson_unit_id)
        lesson = repository.lesson(course_id, lesson_unit_id)
        current_revision = str(lesson.get("working_script_revision_id") or "")
        if body.base_revision_id != current_revision:
            raise TeacherLessonAuthoringError(
                "lesson_script_revision_conflict",
                "讲稿工作稿已经变化，请重新载入后再保存。",
            )
        # The first teacher-authored draft has no model revision to build on.
        # Treat an empty base id as the explicit empty working state so a
        # teacher can take over after generation fails (or write from scratch)
        # without creating a parallel persistence path.
        base_revision = (
            _script_revision(
                repository, course_id, lesson_unit_id, body.base_revision_id
            )
            if body.base_revision_id
            else {}
        )
        base_sections = {
            str(item.get("section_node_id") or ""): item
            for item in base_revision.get("sections") or []
            if isinstance(item, dict) and item.get("section_node_id")
        }
        expected_ids = [str(item.get("node_id") or "") for item in scope["sections"]]
        actual_ids = [str(item.get("section_node_id") or "") for item in body.sections]
        if actual_ids != expected_ids:
            raise TeacherLessonAuthoringError(
                "lesson_script_scope_conflict",
                "讲稿小节与当前大纲不一致，请重新载入。",
            )
        plan_revision_id = str(lesson.get("confirmed_revision_id") or "")
        plan_revision = _plan_revision(
            repository, course_id, lesson_unit_id, plan_revision_id
        )
        plan_sections = {
            str(item.get("node_id") or ""): item
            for item in (plan_revision.get("plan") or {}).get("sections") or []
            if isinstance(item, dict) and item.get("node_id")
        }
        outline_sections = {
            str(item.get("node_id") or ""): item for item in scope["sections"]
        }
        normalized_sections = []
        for item in body.sections:
            section_id = str(item.get("section_node_id") or "")
            if not item.get("blocks") and not (
                base_sections.get(section_id) or {}
            ).get("blocks"):
                normalized_sections.append(normalize_teacher_script_section(item))
                continue
            contract = compile_teacher_script_module_contract(
                outline_sections.get(section_id) or {},
                plan_sections.get(section_id) or {},
            )
            normalized = normalize_teacher_script_section(item, contract)
            normalized["quality_report"] = validate_teacher_script_section(
                normalized,
                contract,
            )
            normalized_sections.append(normalized)
        repository.save_script_revision(
            course_id,
            lesson_unit_id,
            normalized_sections,
            source_lesson_plan_revision_id=plan_revision_id,
            generation_source="teacher_edit",
            requirements=str(base_revision.get("requirements") or ""),
            material_asset_ids=list(base_revision.get("material_asset_ids") or []),
            actor=resolve_user_id(request.headers.get("X-User-Id")),
        )
        projected = next(
            item for item in _lesson_projection(source, repository)
            if item["lesson_unit_id"] == lesson_unit_id
        )
        return {"lesson": projected}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/script/rewrite-candidate")
async def rewrite_lesson_script_candidate(
    course_id: str,
    lesson_unit_id: str,
    body: RewriteLessonScriptRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        source = _source_course(tm, course_id)
        scope = lesson_scope(source, lesson_unit_id)
        lesson = repository.lesson(course_id, lesson_unit_id)
        if lesson.get("working_script_revision_id") != body.base_revision_id:
            raise TeacherLessonAuthoringError(
                "lesson_script_revision_conflict",
                "讲稿工作稿已经变化，请重新载入后再优化。",
            )
        revision = _script_revision(
            repository, course_id, lesson_unit_id, body.base_revision_id
        )
        section = next(
            (
                item for item in revision.get("sections") or []
                if item.get("section_node_id") == body.section_node_id
            ),
            None,
        )
        outline_section = next(
            (
                item for item in scope["sections"]
                if item.get("node_id") == body.section_node_id
            ),
            None,
        )
        if not isinstance(section, dict) or not isinstance(outline_section, dict):
            raise TeacherLessonAuthoringError(
                "lesson_script_section_not_found",
                "当前讲稿小节不存在。",
            )
        selected_material_ids, source_evidence = _course_material_evidence(
            course_id,
            resolve_user_id(request.headers.get("X-User-Id")),
            body.material_asset_ids,
        )
        plan_revision = _plan_revision(
            repository,
            course_id,
            lesson_unit_id,
            str(revision.get("source_lesson_plan_revision_id") or ""),
        )
        plan_section = next(
            (
                item for item in (plan_revision.get("plan") or {}).get("sections") or []
                if isinstance(item, dict) and item.get("node_id") == body.section_node_id
            ),
            {},
        )
        script_headings = [
            str(item.get("title") or "").strip()
            for item in section.get("blocks") or []
            if isinstance(item, dict) and str(item.get("title") or "").strip()
        ]
        result = await tm.course_service.rewrite_selection(
            course_id=course_id,
            node=outline_section,
            selected_text=str(section.get("content") or ""),
            node_content=str(section.get("content") or ""),
            heading_path=[str(section.get("title") or "")],
            user_requirement="\n".join(filter(None, [
                body.instruction.strip(),
                "保持已确认教案结构和事实边界；涉及高风险事实而选定资料无法支持时标注“需核验”，不得给出无依据的绝对结论。",
                (
                    "完整保留并仅使用这些二级标题，顺序和名称均不得改变："
                    + "、".join(f"## {title}" for title in script_headings)
                ) if script_headings else "",
            ])),
            action_type="rewrite",
            course_context=json.dumps({
                "lesson_sections": [
                    str(item.get("title") or "") for item in revision.get("sections") or []
                ],
                "confirmed_lesson_plan": plan_section,
                "teacher_requirements": str(revision.get("requirements") or ""),
                "material_asset_ids": selected_material_ids,
                "selected_material_evidence": _prompt_material_evidence(source_evidence),
            }, ensure_ascii=False),
            user_id=resolve_user_id(request.headers.get("X-User-Id")),
        )
        replacement_text = str(result.get("replacement_text") or "").strip()
        if not replacement_text:
            raise TeacherLessonAuthoringError(
                "lesson_script_candidate_empty",
                "AI 没有生成可审阅的讲稿修改。",
            )
        candidate = repository.save_script_ai_candidate(
            course_id,
            lesson_unit_id,
            base_revision_id=body.base_revision_id,
            section_node_id=body.section_node_id,
            instruction=body.instruction.strip(),
            replacement_text=replacement_text,
            source_lesson_plan_revision_id=str(
                revision.get("source_lesson_plan_revision_id") or ""
            ),
            material_asset_ids=selected_material_ids,
        )
        return {"candidate": candidate}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post(
    "/courses/{course_id}/lessons/{lesson_unit_id}/script/ai-candidates/{candidate_id}/resolve"
)
async def resolve_lesson_script_candidate(
    course_id: str,
    lesson_unit_id: str,
    candidate_id: str,
    body: ResolveLessonScriptCandidateRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        source = _source_course(tm, course_id)
        scope = lesson_scope(source, lesson_unit_id)
        lesson = repository.lesson(course_id, lesson_unit_id)
        candidate = repository.script_ai_candidate(
            course_id, lesson_unit_id, candidate_id
        )
        if candidate.get("status") != "pending":
            projected = next(
                item for item in _lesson_projection(source, repository)
                if item["lesson_unit_id"] == lesson_unit_id
            )
            return {"lesson": projected, "candidate": candidate}
        base_revision_id = str(candidate.get("base_revision_id") or "")
        if lesson.get("working_script_revision_id") != base_revision_id:
            raise TeacherLessonAuthoringError(
                "lesson_script_revision_conflict",
                "讲稿工作稿已经变化，不能覆盖新修改。",
            )
        if not body.accept:
            resolved = repository.mark_script_ai_candidate(
                course_id,
                lesson_unit_id,
                candidate_id,
                status="rejected",
            )
            projected = next(
                item for item in _lesson_projection(source, repository)
                if item["lesson_unit_id"] == lesson_unit_id
            )
            return {"lesson": projected, "candidate": resolved}

        base_revision = _script_revision(
            repository, course_id, lesson_unit_id, base_revision_id
        )
        plan_revision_id = str(candidate.get("source_lesson_plan_revision_id") or "")
        plan_revision = _plan_revision(
            repository, course_id, lesson_unit_id, plan_revision_id
        )
        plan_sections = {
            str(item.get("node_id") or ""): item
            for item in (plan_revision.get("plan") or {}).get("sections") or []
            if isinstance(item, dict) and item.get("node_id")
        }
        outline_sections = {
            str(item.get("node_id") or ""): item for item in scope["sections"]
        }
        target_section_id = str(candidate.get("section_node_id") or "")
        normalized_sections: list[dict[str, Any]] = []
        for section in base_revision.get("sections") or []:
            if not isinstance(section, dict):
                continue
            section_id = str(section.get("section_node_id") or "")
            candidate_section = deepcopy(section)
            if section_id == target_section_id:
                candidate_section.pop("blocks", None)
                candidate_section["content"] = str(
                    candidate.get("replacement_text") or ""
                ).strip()
            contract = compile_teacher_script_module_contract(
                outline_sections.get(section_id) or {},
                plan_sections.get(section_id) or {},
            )
            normalized = normalize_teacher_script_section(
                candidate_section,
                contract,
            )
            normalized["quality_report"] = validate_teacher_script_section(
                normalized,
                contract,
            )
            normalized_sections.append(normalized)
        saved = repository.save_script_revision(
            course_id,
            lesson_unit_id,
            normalized_sections,
            source_lesson_plan_revision_id=plan_revision_id,
            generation_source="ai_optimization",
            requirements=str(base_revision.get("requirements") or ""),
            material_asset_ids=list(
                candidate.get("material_asset_ids")
                or base_revision.get("material_asset_ids")
                or []
            ),
            actor=resolve_user_id(request.headers.get("X-User-Id")),
            expected_working_revision_id=base_revision_id,
        )
        accepted_revision_id = str(saved.get("working_script_revision_id") or "")
        resolved = repository.mark_script_ai_candidate(
            course_id,
            lesson_unit_id,
            candidate_id,
            status="accepted",
            result_revision_id=accepted_revision_id,
        )
        projected = next(
            item for item in _lesson_projection(source, repository)
            if item["lesson_unit_id"] == lesson_unit_id
        )
        return {"lesson": projected, "candidate": resolved}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/plan/ai-candidates")
async def create_lesson_plan_candidate(
    course_id: str,
    lesson_unit_id: str,
    body: CreateLessonPlanCandidateRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        actor = resolve_user_id(request.headers.get("X-User-Id"))
        selected_material_ids, source_evidence = _course_material_evidence(
            course_id,
            actor,
            body.material_asset_ids,
        )
        lesson = repository.lesson(course_id, lesson_unit_id)
        if lesson.get("working_revision_id") != body.base_revision_id:
            raise TeacherLessonAuthoringError("lesson_plan_revision_conflict", "教案草稿已经变化，请重新打开后再优化。")
        revision = next(
            (
                item for item in lesson.get("revisions") or []
                if item.get("revision_id") == body.base_revision_id
            ),
            None,
        )
        if not isinstance(revision, dict):
            raise TeacherLessonAuthoringError("lesson_plan_revision_not_found", "教案草稿不存在。")
        optimized = await tm.course_service.optimize_teacher_lesson_plan(
            plan=deepcopy(revision.get("plan") or {}),
            instruction=body.instruction,
            section_node_id=body.section_node_id,
            material_evidence=_prompt_material_evidence(source_evidence),
        )
        candidate = repository.save_ai_candidate(
            course_id,
            lesson_unit_id,
            base_revision_id=body.base_revision_id,
            instruction=body.instruction,
            section_node_id=body.section_node_id,
            plan=optimized["plan"],
            material_asset_ids=selected_material_ids,
        )
        return {"candidate": candidate}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/plan/ai-candidates/{candidate_id}/resolve")
async def resolve_lesson_plan_candidate(
    course_id: str,
    lesson_unit_id: str,
    candidate_id: str,
    body: ResolveLessonPlanCandidateRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        source = _source_course(tm, course_id)
        canonical_outline_revision = _canonical_outline_revision(source)
        if canonical_outline_revision:
            repository.set_outline(course_id, canonical_outline_revision)
        lesson = TeacherLessonAuthoringService(repository).resolve_ai_candidate(
            course_id=course_id,
            lesson_unit_id=lesson_unit_id,
            course_data=source,
            candidate_id=candidate_id,
            accept=body.accept,
            actor=resolve_user_id(request.headers.get("X-User-Id")),
        )
        return {"lesson": lesson}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.get("/courses/{course_id}/lessons/{lesson_unit_id}/ppt/export.pptx")
async def export_lesson_ppt(
    course_id: str,
    lesson_unit_id: str,
    asset_id: str,
    revision_id: str,
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        _asset, revision = _ppt_asset_revision(
            repository,
            course_id,
            lesson_unit_id,
            asset_id,
            revision_id,
        )
        structured = teacher_lesson_deck_to_structured_slide_deck(
            deepcopy(revision.get("deck") or {}),
            source_revision_id=str(revision.get("source_lesson_plan_revision_id") or ""),
        )
        export_dir = repository.root / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        output = export_dir / f"{course_id}-{lesson_unit_id}-{revision_id}.pptx"
        await run_in_threadpool(
            export_structured_slide_deck,
            structured,
            output,
            require_quality=False,
            theme="qingfeng-classroom",
        )
        return FileResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=f"{lesson_unit_id}-课堂课件.pptx",
        )
    except TeacherLessonAuthoringError as exc:
        _raise(exc)
