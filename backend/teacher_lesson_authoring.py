"""Teacher-only lesson plan assets and jobs.

This module deliberately does not write ``CourseDocument``.  It is the
authoring boundary for a teacher lesson (one L1 node plus all direct L2
sections) while the existing learner course-generation pipeline remains
unchanged.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
import uuid
import hashlib
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from course_document import document_from_generation_draft
from course_pedagogy import module_block_role


SCHEMA_VERSION = "teacher_lesson_authoring_v1"
JOB_TYPES = {
    "teacher_lesson_plan_generation",
    "teacher_lesson_ppt_generation",
}


class TeacherLessonAuthoringError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_root() -> Path:
    configured = os.getenv("TEACHER_LESSON_AUTHORING_DIR", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent / "data" / "teacher_lesson_authoring"


def lesson_scope(course_data: dict[str, Any], lesson_unit_id: str) -> dict[str, Any]:
    """Resolve one stable teacher lesson and its direct ordered sections."""
    nodes = [item for item in course_data.get("nodes") or [] if isinstance(item, dict)]
    lesson = next(
        (
            item for item in nodes
            if str(item.get("node_id") or "") == lesson_unit_id
            and int(item.get("node_level") or 0) == 1
        ),
        None,
    )
    if not lesson:
        raise TeacherLessonAuthoringError(
            "lesson_unit_not_found",
            "当前课程中不存在该讲次。",
            details={"lesson_unit_id": lesson_unit_id},
        )
    sections = [
        deepcopy(item) for item in nodes
        if str(item.get("parent_node_id") or "") == lesson_unit_id
    ]
    if not sections:
        raise TeacherLessonAuthoringError(
            "lesson_sections_empty",
            "当前讲次没有可生成教案的小节。",
            details={"lesson_unit_id": lesson_unit_id},
        )
    plan = course_data.get("course_plan") or course_data.get("course_outline") or {}
    chapters = [item for item in plan.get("chapters") or [] if isinstance(item, dict)]
    chapter = next(
        (
            item for item in chapters
            if str(item.get("node_id") or item.get("chapter_id") or "") == lesson_unit_id
        ),
        None,
    )
    if chapter is None:
        section_ids = {str(item.get("node_id") or "") for item in sections}
        chapter = next(
            (
                item for item in chapters
                if section_ids
                and section_ids.issubset({
                    str(section.get("node_id") or "")
                    for section in item.get("sections") or []
                    if isinstance(section, dict)
                })
            ),
            None,
        )
    return {
        "lesson": deepcopy(lesson),
        "sections": sections,
        "chapter": deepcopy(chapter) if isinstance(chapter, dict) else None,
    }


def lesson_plan_ppt_source(
    plan: dict[str, Any],
    *,
    lesson_unit_id: str,
    source_revision_id: str,
) -> dict[str, Any]:
    """Compile the teacher-only source contract for one lesson deck."""
    sections = [
        deepcopy(item)
        for item in plan.get("sections") or []
        if isinstance(item, dict) and item.get("node_id")
    ]
    if not sections:
        raise TeacherLessonAuthoringError(
            "lesson_plan_empty",
            "本讲教案没有可用于生成 PPT 的小节。",
        )
    return {
        "schema_version": "teacher_lesson_ppt_source_v1",
        "lesson_unit_id": lesson_unit_id,
        "source_lesson_plan_revision_id": source_revision_id,
        "title": str(plan.get("lesson_title") or plan.get("course_title") or "本讲课件"),
        "sections": sections,
    }


def teacher_lesson_deck_to_structured_slide_deck(
    deck: dict[str, Any],
    *,
    source_revision_id: str,
) -> dict[str, Any]:
    """Adapt the lightweight teacher deck to the shared editable PPTX renderer."""
    raw_slides = [item for item in deck.get("slides") or [] if isinstance(item, dict)]
    if not raw_slides:
        raise TeacherLessonAuthoringError("lesson_ppt_empty", "本讲 PPT 没有可导出的页面。")
    slides = []
    for index, slide in enumerate(raw_slides):
        body = slide.get("body") or []
        if isinstance(body, str):
            body = [body]
        layout = "cover" if index == 0 else "recap" if index == len(raw_slides) - 1 else "concept"
        slides.append({
            "unit_id": str(slide.get("slide_id") or f"slide-{index + 1}"),
            "position": index,
            "layout": layout,
            "slide_purpose": "teacher_lesson_presentation",
            "title": str(slide.get("title") or f"第 {index + 1} 页"),
            "key_message": str(body[0] if body else slide.get("title") or ""),
            "takeaway": str(body[-1] if body else ""),
            "blocks": [{
                "block_id": f"{slide.get('slide_id') or index}-bullets",
                "type": "bullets",
                "items": [str(item) for item in body if str(item).strip()][:8],
            }],
            "speaker_notes": str(slide.get("speaker_notes") or ""),
        })
    return {
        "schema_version": "slide_deck_v2",
        "title": str(deck.get("title") or "本讲课件"),
        "theme": "qingfeng-classroom",
        "source_document_revision": source_revision_id,
        "slides": slides,
    }


def teacher_lesson_v6_source(
    course_data: dict[str, Any],
    *,
    lesson_unit_id: str,
    plan_revision: dict[str, Any],
) -> tuple[Any, dict[str, Any], str]:
    """Adapt one teacher plan revision to the existing V6 source contracts.

    The returned synthetic course id is stable for one real course + lesson,
    while the CourseDocument revision changes with the teacher plan. Nothing is
    persisted to the learner CourseDocument repository.
    """
    scope = lesson_scope(course_data, lesson_unit_id)
    plan = deepcopy(plan_revision.get("plan") or {})
    plan_sections = {
        str(item.get("node_id") or ""): deepcopy(item)
        for item in plan.get("sections") or []
        if isinstance(item, dict) and item.get("node_id")
    }
    digest = hashlib.sha256(
        f"{course_data.get('course_id')}:{lesson_unit_id}".encode("utf-8")
    ).hexdigest()[:20]
    synthetic_course_id = f"teacher-lesson-{digest}"
    lesson_title = str(scope["lesson"].get("node_name") or "本讲课件")
    lesson_node = deepcopy(scope["lesson"])
    lesson_node.update({
        "node_id": lesson_unit_id,
        "parent_node_id": "root",
        "node_level": 1,
        "node_name": lesson_title,
        "node_content": "",
        "content_blocks": [],
    })
    nodes = [lesson_node]
    for section_index, outline_section in enumerate(scope["sections"], start=1):
        section_id = str(outline_section.get("node_id") or "")
        planned = plan_sections.get(section_id) or {}
        modules = [
            item for item in planned.get("teaching_modules") or []
            if isinstance(item, dict)
        ]
        blocks: list[dict[str, Any]] = []
        for module_index, module in enumerate(modules, start=1):
            module_id = str(module.get("module_id") or "core_explanation")
            role = module_block_role(module_id)
            if role not in {
                "orientation", "prerequisite", "objective", "concept", "reasoning",
                "example", "counterexample", "application", "activity", "feedback",
                "misconception", "checkpoint", "remediation", "summary", "transfer",
            }:
                role = "concept"
            knowledge_names = [
                str(item) for item in module.get("knowledge_names") or []
                if str(item).strip()
            ]
            paragraphs = [
                str(module.get("teaching_purpose") or "").strip(),
                str(module.get("teaching_guidance") or "").strip(),
                f"教师活动：{module.get('teacher_activity')}" if module.get("teacher_activity") else "",
                f"学生活动：{module.get('student_activity')}" if module.get("student_activity") else "",
                f"知识要点：{'、'.join(knowledge_names)}" if knowledge_names else "",
            ]
            blocks.append({
                "block_id": f"{section_id}-teacher-{module_index}",
                "type": role,
                "title": str(module.get("label") or module.get("teaching_purpose") or module_id),
                "content": "\n\n".join(item for item in paragraphs if item),
                "metadata": {
                    "role": role,
                    "module_id": module_id,
                    "module_instance_id": f"{section_id}:{module_id}:{module_index}",
                    "concept_refs": knowledge_names,
                },
            })
        if not blocks:
            key_points = [str(item) for item in planned.get("key_points") or [] if str(item).strip()]
            blocks = [{
                "block_id": f"{section_id}-teacher-concept",
                "type": "concept",
                "title": str(outline_section.get("node_name") or "核心教学"),
                "content": "\n\n".join(filter(None, [
                    str(planned.get("learning_objective") or outline_section.get("learning_objective") or ""),
                    f"知识要点：{'、'.join(key_points)}" if key_points else "",
                ])),
                "metadata": {"role": "concept", "concept_refs": key_points},
            }]
        node = deepcopy(outline_section)
        node.update({
            "node_id": section_id,
            "parent_node_id": lesson_unit_id,
            "node_level": 2,
            "node_name": str(outline_section.get("node_name") or f"第{section_index}节"),
            "learning_objective": str(
                planned.get("learning_objective")
                or outline_section.get("learning_objective")
                or ""
            ),
            "knowledge_structure": deepcopy(
                planned.get("knowledge_structure")
                or outline_section.get("knowledge_structure")
                or []
            ),
            "key_points": deepcopy(planned.get("key_points") or []),
            "content_blocks": blocks,
            "node_content": "\n\n".join(
                f"## {block['title']}\n\n{block['content']}" for block in blocks
            ),
        })
        nodes.append(node)
    synthetic = {
        "course_id": synthetic_course_id,
        "course_name": lesson_title,
        "language": str(course_data.get("language") or "zh-CN"),
        "nodes": nodes,
        "course_teaching_plan": plan,
        "course_knowledge_base": deepcopy(course_data.get("course_knowledge_base") or {}),
        "course_coherence_contract": deepcopy(course_data.get("course_coherence_contract") or {}),
        "generation_request": deepcopy(course_data.get("generation_request") or {}),
        "teacher_lesson_source": {
            "real_course_id": str(course_data.get("course_id") or ""),
            "lesson_unit_id": lesson_unit_id,
            "lesson_plan_revision_id": str(plan_revision.get("revision_id") or ""),
        },
    }
    document = document_from_generation_draft(synthetic)
    return document, synthetic, synthetic_course_id


class TeacherLessonAuthoringRepository:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root is not None else _default_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, course_id: str) -> Path:
        safe = "".join(char for char in course_id if char.isalnum() or char in {"-", "_"})
        if not safe or safe != course_id:
            raise TeacherLessonAuthoringError("invalid_course_id", "课程标识无效。")
        return self.root / f"{safe}.json"

    def _empty(self, course_id: str) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "course_id": course_id,
            "revision": 0,
            "outline_revision_id": "",
            "lessons": {},
            "jobs": {},
            "updated_at": _now(),
        }

    def load(self, course_id: str) -> dict[str, Any]:
        with self._lock:
            path = self._path(course_id)
            if not path.exists():
                return self._empty(course_id)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise TeacherLessonAuthoringError(
                    "authoring_repository_corrupt",
                    "教师讲次资产读取失败。",
                ) from exc
            return data if isinstance(data, dict) else self._empty(course_id)

    def _save(self, value: dict[str, Any]) -> dict[str, Any]:
        course_id = str(value.get("course_id") or "")
        path = self._path(course_id)
        payload = deepcopy(value)
        payload["schema_version"] = SCHEMA_VERSION
        payload["revision"] = int(payload.get("revision") or 0) + 1
        payload["updated_at"] = _now()
        fd, temp_name = tempfile.mkstemp(prefix=f".{course_id}.", suffix=".tmp", dir=str(self.root))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return deepcopy(payload)

    def set_outline(self, course_id: str, outline_revision_id: str) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            previous = str(value.get("outline_revision_id") or "")
            value["outline_revision_id"] = outline_revision_id
            if previous and previous != outline_revision_id:
                for lesson in (value.get("lessons") or {}).values():
                    if isinstance(lesson, dict) and lesson.get("working_revision_id"):
                        lesson["source_state"] = "stale"
            return self._save(value)

    def create_job(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        job_type: str = "teacher_lesson_plan_generation",
        request_id: str = "",
        source_outline_revision_id: str = "",
    ) -> dict[str, Any]:
        if job_type not in JOB_TYPES:
            raise TeacherLessonAuthoringError("unsupported_teacher_job", "不支持的教师讲次任务。")
        with self._lock:
            value = self.load(course_id)
            if request_id:
                existing = next(
                    (
                        job for job in (value.get("jobs") or {}).values()
                        if isinstance(job, dict)
                        and job.get("request_id") == request_id
                        and job.get("lesson_unit_id") == lesson_unit_id
                        and job.get("type") == job_type
                    ),
                    None,
                )
                if existing:
                    return deepcopy(existing)
            job_id = f"tlj-{uuid.uuid4().hex}"
            job = {
                "id": job_id,
                "course_id": course_id,
                "lesson_unit_id": lesson_unit_id,
                "type": job_type,
                "request_id": request_id,
                "source_outline_revision_id": source_outline_revision_id,
                "status": "pending",
                "progress": 0,
                "phase": "queued",
                "message": "等待生成本讲教案",
                "warnings": [],
                "error": None,
                "created_at": _now(),
                "updated_at": _now(),
            }
            value.setdefault("jobs", {})[job_id] = job
            self._save(value)
            return deepcopy(job)

    def update_job(self, course_id: str, job_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            job = (value.get("jobs") or {}).get(job_id)
            if not isinstance(job, dict):
                raise TeacherLessonAuthoringError("teacher_job_not_found", "教师讲次任务不存在。")
            job.update(deepcopy(changes))
            job["updated_at"] = _now()
            value["jobs"][job_id] = job
            self._save(value)
            return deepcopy(job)

    def save_plan_revision(
        self,
        course_id: str,
        lesson_unit_id: str,
        plan: dict[str, Any],
        *,
        source_outline_revision_id: str,
        generation_source: str = "model",
        warnings: list[dict[str, Any]] | None = None,
        actor: str = "teacher",
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = value.setdefault("lessons", {}).setdefault(lesson_unit_id, {
                "lesson_unit_id": lesson_unit_id,
                "working_revision_id": "",
                "confirmed_revision_id": "",
                "source_state": "current",
                "revisions": [],
                "ai_candidates": [],
                "ppt_assets": [],
            })
            revision_id = f"tlpr-{uuid.uuid4().hex}"
            revision = {
                "revision_id": revision_id,
                "lesson_unit_id": lesson_unit_id,
                "source_outline_revision_id": source_outline_revision_id,
                "generation_source": generation_source,
                "status": "needs_ai_review" if warnings else "draft",
                "warnings": deepcopy(warnings or []),
                "plan": deepcopy(plan),
                "actor": actor,
                "created_at": _now(),
            }
            lesson.setdefault("revisions", []).append(revision)
            lesson["working_revision_id"] = revision_id
            lesson["source_state"] = "current"
            for asset in lesson.get("ppt_assets") or []:
                if not isinstance(asset, dict):
                    continue
                source_revision = str(asset.get("source_lesson_plan_revision_id") or "")
                if source_revision and source_revision != revision_id:
                    asset["source_state"] = "stale"
            value["outline_revision_id"] = source_outline_revision_id or value.get("outline_revision_id", "")
            saved = self._save(value)
            return deepcopy(saved["lessons"][lesson_unit_id])

    def save_ppt_revision(
        self,
        course_id: str,
        lesson_unit_id: str,
        deck: dict[str, Any],
        *,
        source_lesson_plan_revision_id: str,
        generation_source: str = "model",
        warnings: list[dict[str, Any]] | None = None,
        actor: str = "teacher",
        asset_role: str = "primary",
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            if not isinstance(lesson, dict):
                raise TeacherLessonAuthoringError("lesson_plan_not_found", "请先生成本讲教案。")
            if lesson.get("working_revision_id") != source_lesson_plan_revision_id:
                raise TeacherLessonAuthoringError(
                    "lesson_plan_revision_conflict",
                    "教案草稿已经变化，请基于最新版本生成 PPT。",
                )
            assets = lesson.setdefault("ppt_assets", [])
            asset = next(
                (
                    item for item in assets
                    if isinstance(item, dict) and item.get("role") == asset_role
                ),
                None,
            )
            if asset is None:
                asset = {
                    "asset_id": f"tlpa-{uuid.uuid4().hex}",
                    "lesson_unit_id": lesson_unit_id,
                    "role": asset_role,
                    "working_revision_id": "",
                    "source_lesson_plan_revision_id": source_lesson_plan_revision_id,
                    "source_state": "current",
                    "revisions": [],
                    "ai_candidates": [],
                }
                assets.append(asset)
            revision_id = f"tlpv-{uuid.uuid4().hex}"
            revision = {
                "revision_id": revision_id,
                "lesson_unit_id": lesson_unit_id,
                "source_lesson_plan_revision_id": source_lesson_plan_revision_id,
                "generation_source": generation_source,
                "status": "needs_ai_review" if warnings else "draft",
                "warnings": deepcopy(warnings or []),
                "deck": deepcopy(deck),
                "actor": actor,
                "created_at": _now(),
            }
            asset.setdefault("revisions", []).append(revision)
            asset["working_revision_id"] = revision_id
            asset["source_lesson_plan_revision_id"] = source_lesson_plan_revision_id
            asset["source_state"] = "current"
            saved = self._save(value)
            saved_lesson = saved["lessons"][lesson_unit_id]
            return deepcopy(next(item for item in saved_lesson["ppt_assets"] if item["asset_id"] == asset["asset_id"]))

    def bind_v6_ppt_revision(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        source_lesson_plan_revision_id: str,
        synthetic_course_id: str,
        representation_id: str,
        spec_id: str,
        candidate_status: str,
    ) -> dict[str, Any]:
        """Register one real V6 representation without copying it into student data."""
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            if not isinstance(lesson, dict):
                raise TeacherLessonAuthoringError("lesson_plan_not_found", "请先生成本讲教案。")
            if lesson.get("working_revision_id") != source_lesson_plan_revision_id:
                raise TeacherLessonAuthoringError(
                    "lesson_plan_revision_conflict",
                    "教案草稿已经变化，V6 结果未登记。",
                )
            assets = lesson.setdefault("ppt_assets", [])
            asset = next(
                (item for item in assets if isinstance(item, dict) and item.get("role") == "primary"),
                None,
            )
            if asset is None:
                asset = {
                    "asset_id": f"tlpa-{uuid.uuid4().hex}",
                    "lesson_unit_id": lesson_unit_id,
                    "role": "primary",
                    "working_revision_id": "",
                    "source_lesson_plan_revision_id": source_lesson_plan_revision_id,
                    "source_state": "current",
                    "revisions": [],
                    "ai_candidates": [],
                }
                assets.append(asset)
            binding = {
                "revision_id": f"tlv6r-{uuid.uuid4().hex}",
                "engine": "slide_deck_v6",
                "synthetic_course_id": synthetic_course_id,
                "representation_id": representation_id,
                "spec_id": spec_id,
                "source_lesson_plan_revision_id": source_lesson_plan_revision_id,
                "candidate_status": candidate_status,
                "created_at": _now(),
            }
            asset.setdefault("v6_revisions", []).append(binding)
            asset["engine"] = "slide_deck_v6"
            asset["working_v6_revision_id"] = binding["revision_id"]
            asset["working_representation_id"] = representation_id
            asset["synthetic_course_id"] = synthetic_course_id
            asset["source_lesson_plan_revision_id"] = source_lesson_plan_revision_id
            asset["source_state"] = "current"
            saved = self._save(value)
            return deepcopy(next(item for item in saved["lessons"][lesson_unit_id]["ppt_assets"] if item["asset_id"] == asset["asset_id"]))

    def save_ppt_ai_candidate(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        asset_id: str,
        base_revision_id: str,
        instruction: str,
        deck: dict[str, Any],
        slide_indexes: list[int] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            asset = next(
                (
                    item for item in (lesson or {}).get("ppt_assets") or []
                    if isinstance(item, dict) and item.get("asset_id") == asset_id
                ),
                None,
            )
            if not isinstance(asset, dict):
                raise TeacherLessonAuthoringError("lesson_ppt_not_found", "本讲还没有可优化的 PPT。")
            if asset.get("working_revision_id") != base_revision_id:
                raise TeacherLessonAuthoringError("lesson_ppt_revision_conflict", "PPT 草稿已经变化，请重新优化。")
            candidate = {
                "candidate_id": f"tlpac-{uuid.uuid4().hex}",
                "asset_id": asset_id,
                "base_revision_id": base_revision_id,
                "instruction": instruction,
                "slide_indexes": list(slide_indexes or []),
                "deck": deepcopy(deck),
                "status": "pending",
                "created_at": _now(),
            }
            asset.setdefault("ai_candidates", []).append(candidate)
            self._save(value)
            return deepcopy(candidate)

    def resolve_ppt_ai_candidate(
        self,
        course_id: str,
        lesson_unit_id: str,
        candidate_id: str,
        *,
        accept: bool,
        actor: str = "teacher",
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            assets = (lesson or {}).get("ppt_assets") or []
            asset = next(
                (
                    item for item in assets
                    if isinstance(item, dict)
                    and any(
                        isinstance(candidate, dict) and candidate.get("candidate_id") == candidate_id
                        for candidate in item.get("ai_candidates") or []
                    )
                ),
                None,
            )
            if not isinstance(asset, dict):
                raise TeacherLessonAuthoringError("lesson_ppt_candidate_not_found", "AI PPT 候选不存在。")
            candidate = next(item for item in asset["ai_candidates"] if item.get("candidate_id") == candidate_id)
            if candidate.get("status") != "pending":
                return deepcopy(asset)
            if asset.get("working_revision_id") != candidate.get("base_revision_id"):
                raise TeacherLessonAuthoringError("lesson_ppt_revision_conflict", "PPT 草稿已经变化，不能覆盖新修改。")
            candidate["status"] = "accepted" if accept else "rejected"
            candidate["resolved_at"] = _now()
            if not accept:
                saved = self._save(value)
                return deepcopy(next(item for item in saved["lessons"][lesson_unit_id]["ppt_assets"] if item["asset_id"] == asset["asset_id"]))
            deck = deepcopy(candidate.get("deck") or {})
            source_revision = str(asset.get("source_lesson_plan_revision_id") or "")
            asset_role = str(asset.get("role") or "primary")
            self._save(value)
        return self.save_ppt_revision(
            course_id,
            lesson_unit_id,
            deck,
            source_lesson_plan_revision_id=source_revision,
            generation_source="ai_optimization",
            actor=actor,
            asset_role=asset_role,
        )

    def get_job(self, course_id: str, job_id: str) -> dict[str, Any]:
        value = self.load(course_id)
        job = (value.get("jobs") or {}).get(job_id)
        if not isinstance(job, dict):
            raise TeacherLessonAuthoringError("teacher_job_not_found", "教师讲次任务不存在。")
        return deepcopy(job)

    def lesson(self, course_id: str, lesson_unit_id: str) -> dict[str, Any]:
        value = self.load(course_id)
        lesson = (value.get("lessons") or {}).get(lesson_unit_id)
        if not isinstance(lesson, dict):
            return {
                "lesson_unit_id": lesson_unit_id,
                "working_revision_id": "",
                "confirmed_revision_id": "",
                "source_state": "current",
                "revisions": [],
                "ai_candidates": [],
                "ppt_assets": [],
            }
        return deepcopy(lesson)

    def confirm_plan_revision(
        self,
        course_id: str,
        lesson_unit_id: str,
        revision_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            if not isinstance(lesson, dict):
                raise TeacherLessonAuthoringError("lesson_plan_not_found", "本讲还没有可确认的教案。")
            revision = next(
                (
                    item for item in lesson.get("revisions") or []
                    if isinstance(item, dict) and item.get("revision_id") == revision_id
                ),
                None,
            )
            if revision is None:
                raise TeacherLessonAuthoringError("lesson_plan_revision_not_found", "教案修订不存在。")
            lesson["confirmed_revision_id"] = revision_id
            revision["status"] = "confirmed"
            revision["confirmed_at"] = _now()
            saved = self._save(value)
            return deepcopy(saved["lessons"][lesson_unit_id])

    def save_ai_candidate(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        base_revision_id: str,
        instruction: str,
        plan: dict[str, Any],
        section_node_id: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            if not isinstance(lesson, dict):
                raise TeacherLessonAuthoringError("lesson_plan_not_found", "本讲还没有可优化的教案。")
            if lesson.get("working_revision_id") != base_revision_id:
                raise TeacherLessonAuthoringError("lesson_plan_revision_conflict", "教案草稿已经变化，请重新生成 AI 候选。")
            candidate = {
                "candidate_id": f"tlpc-{uuid.uuid4().hex}",
                "lesson_unit_id": lesson_unit_id,
                "base_revision_id": base_revision_id,
                "instruction": instruction,
                "section_node_id": section_node_id,
                "plan": deepcopy(plan),
                "status": "pending",
                "created_at": _now(),
            }
            lesson.setdefault("ai_candidates", []).append(candidate)
            self._save(value)
            return deepcopy(candidate)

    def resolve_ai_candidate(
        self,
        course_id: str,
        lesson_unit_id: str,
        candidate_id: str,
        *,
        accept: bool,
        actor: str = "teacher",
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            if not isinstance(lesson, dict):
                raise TeacherLessonAuthoringError("lesson_plan_not_found", "本讲还没有可优化的教案。")
            candidate = next(
                (
                    item for item in lesson.get("ai_candidates") or []
                    if isinstance(item, dict) and item.get("candidate_id") == candidate_id
                ),
                None,
            )
            if candidate is None:
                raise TeacherLessonAuthoringError("lesson_plan_candidate_not_found", "AI 教案候选不存在。")
            if candidate.get("status") != "pending":
                return deepcopy(lesson)
            if lesson.get("working_revision_id") != candidate.get("base_revision_id"):
                raise TeacherLessonAuthoringError("lesson_plan_revision_conflict", "教案草稿已经变化，不能覆盖新修改。")
            candidate["status"] = "accepted" if accept else "rejected"
            candidate["resolved_at"] = _now()
            if not accept:
                saved = self._save(value)
                return deepcopy(saved["lessons"][lesson_unit_id])
            source_outline_revision_id = str(value.get("outline_revision_id") or "")
            plan = deepcopy(candidate.get("plan") or {})
            self._save(value)
        return self.save_plan_revision(
            course_id,
            lesson_unit_id,
            plan,
            source_outline_revision_id=source_outline_revision_id,
            generation_source="ai_optimization",
            actor=actor,
        )

    def view(self, course_id: str) -> dict[str, Any]:
        return self.load(course_id)


Planner = Callable[[dict[str, Any], str, Callable[..., Awaitable[None]]], Awaitable[dict[str, Any]]]


class TeacherLessonAuthoringService:
    def __init__(self, repository: TeacherLessonAuthoringRepository):
        self.repository = repository

    async def run_plan_job(
        self,
        *,
        course_id: str,
        lesson_unit_id: str,
        job_id: str,
        course_data: dict[str, Any],
        planner: Planner,
    ) -> dict[str, Any]:
        self.repository.update_job(
            course_id,
            job_id,
            status="running",
            phase="lesson_plan_generation",
            progress=5,
            message="正在生成本讲全部小节教案",
        )

        async def on_progress(phase: str, progress: int, message: str) -> None:
            self.repository.update_job(
                course_id,
                job_id,
                phase=phase,
                progress=max(5, min(95, int(progress))),
                message=message,
            )

        try:
            result = await planner(course_data, lesson_unit_id, on_progress)
            plan = result.get("plan") if isinstance(result, dict) else None
            if not isinstance(plan, dict) or not plan.get("sections"):
                raise TeacherLessonAuthoringError(
                    "lesson_plan_empty",
                    "本讲教案生成结果为空。",
                )
            warnings = list(result.get("warnings") or [])
            generation_source = str(result.get("generation_source") or ("deterministic_local_fallback" if warnings else "model"))
            outline_revision = str(
                result.get("source_outline_revision_id")
                or self.repository.get_job(course_id, job_id).get("source_outline_revision_id")
                or ""
            )
            lesson = self.repository.save_plan_revision(
                course_id,
                lesson_unit_id,
                plan,
                source_outline_revision_id=outline_revision,
                generation_source=generation_source,
                warnings=warnings,
            )
            status = "completed_with_warnings" if warnings else "completed"
            return self.repository.update_job(
                course_id,
                job_id,
                status=status,
                phase="lesson_plan_ready",
                progress=100,
                message="本讲教案已生成" if not warnings else "本讲基础教案已生成，建议继续 AI 优化",
                warnings=warnings,
                result_revision_id=lesson.get("working_revision_id"),
                error=None,
            )
        except Exception as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            code = exc.code if isinstance(exc, TeacherLessonAuthoringError) else "lesson_plan_generation_failed"
            return self.repository.update_job(
                course_id,
                job_id,
                status="failed",
                phase="lesson_plan_failed",
                message="本讲教案生成失败",
                error={"code": code, "message": str(exc), "retryable": True},
            )

    async def run_ppt_job(
        self,
        *,
        course_id: str,
        lesson_unit_id: str,
        job_id: str,
        source_revision_id: str,
        source: dict[str, Any],
        generator: Callable[[dict[str, Any], Callable[..., Awaitable[None]]], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        self.repository.update_job(
            course_id,
            job_id,
            status="running",
            phase="lesson_ppt_generation",
            progress=5,
            message="正在生成本讲 PPT",
        )

        async def on_progress(phase: str, progress: int, message: str) -> None:
            self.repository.update_job(
                course_id,
                job_id,
                phase=phase,
                progress=max(5, min(95, int(progress))),
                message=message,
            )

        try:
            result = await generator(source, on_progress)
            deck = result.get("deck") if isinstance(result, dict) else None
            if not isinstance(deck, dict) or not deck.get("slides"):
                raise TeacherLessonAuthoringError("lesson_ppt_empty", "本讲 PPT 生成结果为空。")
            warnings = list(result.get("warnings") or [])
            asset = self.repository.save_ppt_revision(
                course_id,
                lesson_unit_id,
                deck,
                source_lesson_plan_revision_id=source_revision_id,
                generation_source=str(result.get("generation_source") or "model"),
                warnings=warnings,
            )
            status = "completed_with_warnings" if warnings else "completed"
            return self.repository.update_job(
                course_id,
                job_id,
                status=status,
                phase="lesson_ppt_ready",
                progress=100,
                message="本讲 PPT 已生成" if not warnings else "本讲基础 PPT 已生成，建议继续 AI 优化",
                warnings=warnings,
                result_revision_id=asset.get("working_revision_id"),
                result_asset_id=asset.get("asset_id"),
                error=None,
            )
        except Exception as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            code = exc.code if isinstance(exc, TeacherLessonAuthoringError) else "lesson_ppt_generation_failed"
            return self.repository.update_job(
                course_id,
                job_id,
                status="failed",
                phase="lesson_ppt_failed",
                message="本讲 PPT 生成失败",
                error={"code": code, "message": str(exc), "retryable": True},
            )
