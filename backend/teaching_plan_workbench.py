"""Structured draft, review and revision workflow for course teaching plans.

The workbench intentionally stores its state in the canonical course envelope.
It therefore reuses the course lock, atomic persistence, command receipts and
revision listeners instead of creating a second teaching-plan repository.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import inspect
import os
import re
from typing import Any
from uuid import uuid4

from course_document import CourseDocument, stable_hash
from course_generation_workflow import (
    apply_course_teaching_plan,
    build_course_knowledge_scope_contract,
    compile_course_teaching_plan_modules,
    validate_course_teaching_plan,
)
from course_repository import CourseDocumentConflict, CourseDocumentRepository
from course_revisions import revision_vector_for_course
from course_teaching_plan_v3 import promote_course_teaching_plan_v3
from course_teaching_plan_projection import project_course_teaching_plan
from downstream_rebuild import execute_rebuild, rebuild_summary
from teaching_plan_impact import (
    build_downstream_state,
    build_impact_report,
)


WORKBENCH_SCHEMA = "teaching_plan_workbench_v1"
DRAFT_SCHEMA = "teaching_plan_draft_v1"
REVISION_SCHEMA = "teaching_plan_revision_v1"
CHANGE_SET_SCHEMA = "teaching_plan_change_set_v1"
AI_CANDIDATE_SCHEMA = "teaching_plan_ai_candidate_v1"


def _feature_enabled() -> bool:
    return os.getenv("TEACHING_PLAN_WORKBENCH_ENABLED", "true").strip().lower() not in {
        "0", "false", "off", "no",
    }


class TeachingPlanWorkbenchError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _draft_ttl_hours() -> int:
    """Draft lifetime in hours; 0 disables expiry."""
    raw = os.getenv("TEACHING_PLAN_DRAFT_TTL_HOURS", "72").strip()
    try:
        value = int(raw)
    except ValueError:
        return 72
    return max(value, 0)


def _draft_expires_at(created_at: str) -> str | None:
    hours = _draft_ttl_hours()
    if not hours:
        return None
    try:
        started = datetime.fromisoformat(created_at)
    except ValueError:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return (started + timedelta(hours=hours)).isoformat()


def _is_expired(draft: dict[str, Any]) -> bool:
    expires_at = _text(draft.get("expires_at"))
    if not expires_at:
        return False
    try:
        deadline = datetime.fromisoformat(expires_at)
    except ValueError:
        return False
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= deadline


def _draft_status(draft: dict[str, Any], current_plan_revision: str) -> str:
    """Draft lifecycle state derived from expiry and the current official plan.

    A draft never silently overwrites a newer official revision: once the plan
    it was based on is superseded it becomes ``stale`` and must be rebased.
    """
    if _is_expired(draft):
        return "expired"
    if (
        current_plan_revision
        and _text(draft.get("base_plan_revision_id")) != current_plan_revision
    ):
        return "stale"
    return "active"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _strings(value: Any, *, maximum: int = 16) -> list[str]:
    if not isinstance(value, list):
        raise TeachingPlanWorkbenchError(
            "teaching_plan_invalid_value",
            "该字段需要一组文本值",
        )
    items = list(dict.fromkeys(
        item
        for raw in value
        if (item := _text(raw))
    ))
    if len(items) > maximum:
        raise TeachingPlanWorkbenchError(
            "teaching_plan_value_too_long",
            f"该字段最多保留 {maximum} 项",
        )
    return items


def _value_hash(value: Any) -> str:
    return stable_hash(value, prefix="tpv_")


def _new_id(prefix: str) -> str:
    return f"{prefix}{uuid4().hex}"


def _state(raw: dict[str, Any], *, create: bool = False) -> dict[str, Any]:
    value = raw.get("teaching_plan_workbench")
    if isinstance(value, dict):
        value.setdefault("schema_version", WORKBENCH_SCHEMA)
        value.setdefault("drafts", {})
        value.setdefault("revisions", [])
        value.setdefault("change_sets", [])
        value.setdefault("ai_candidates", [])
        value.setdefault("downstream", {})
        return value
    if not create:
        return {
            "schema_version": WORKBENCH_SCHEMA,
            "drafts": {},
            "revisions": [],
            "change_sets": [],
            "ai_candidates": [],
            "downstream": {},
        }
    value = {
        "schema_version": WORKBENCH_SCHEMA,
        "drafts": {},
        "revisions": [],
        "change_sets": [],
        "ai_candidates": [],
        "downstream": {},
    }
    raw["teaching_plan_workbench"] = value
    return value


def _source_snapshot(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "course_plan": deepcopy(raw.get("course_plan") or {}),
        "generation_request": deepcopy(raw.get("generation_request") or {}),
        "subject_pedagogy_profile": deepcopy(
            raw.get("subject_pedagogy_profile") or {},
        ),
        "course_teaching_plan": deepcopy(raw.get("course_teaching_plan") or {}),
    }


def _source_revision(snapshot: dict[str, Any]) -> str:
    plan = deepcopy(snapshot.get("course_teaching_plan") or {})
    if not isinstance(plan, dict) or not plan.get("sections"):
        return ""
    plan.pop("revision_id", None)
    return stable_hash(
        {
            "course_plan": snapshot.get("course_plan") or {},
            "generation_request": snapshot.get("generation_request") or {},
            "subject_pedagogy_profile": (
                snapshot.get("subject_pedagogy_profile") or {}
            ),
            "course_teaching_plan": plan,
        },
        prefix="tpr_",
    )


def _current_plan_revision(raw: dict[str, Any]) -> str:
    plan = raw.get("course_teaching_plan")
    if not isinstance(plan, dict) or not plan.get("sections"):
        return ""
    return _text(plan.get("revision_id")) or _source_revision(_source_snapshot(raw))


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


def _plan_section(snapshot: dict[str, Any], section_id: str) -> dict[str, Any]:
    plan = snapshot.get("course_teaching_plan")
    if not isinstance(plan, dict):
        raise TeachingPlanWorkbenchError(
            "teaching_plan_missing",
            "当前课程还没有可编辑的结构化教案",
        )
    section = next(
        (
            item
            for item in plan.get("sections") or []
            if isinstance(item, dict) and _text(item.get("node_id")) == section_id
        ),
        None,
    )
    if section is None:
        raise TeachingPlanWorkbenchError(
            "teaching_plan_path_not_found",
            "教案小节不存在或已被目录修改",
            details={"section_id": section_id},
        )
    return section


def _classroom(snapshot: dict[str, Any], *, create: bool = False) -> dict[str, Any]:
    plan = snapshot.get("course_teaching_plan")
    if not isinstance(plan, dict):
        raise TeachingPlanWorkbenchError(
            "teaching_plan_missing",
            "当前课程还没有可编辑的结构化教案",
        )
    classroom = plan.get("classroom")
    if isinstance(classroom, dict):
        return classroom
    if not create:
        return {}
    classroom = {}
    plan["classroom"] = classroom
    return classroom


def _classroom_value(snapshot: dict[str, Any], field: str, default: Any = "") -> Any:
    classroom = _classroom(snapshot)
    if field in classroom:
        return classroom[field]
    request = snapshot.get("generation_request")
    teacher_brief = request.get("teacher_course_brief") if isinstance(request, dict) else {}
    if isinstance(teacher_brief, dict) and field in teacher_brief:
        return teacher_brief[field]
    return default


def _outline_section(snapshot: dict[str, Any], section_id: str) -> dict[str, Any]:
    section = next(
        (
            item
            for item in _course_sections(snapshot)
            if _text(item.get("node_id")) == section_id
        ),
        None,
    )
    if section is None:
        raise TeachingPlanWorkbenchError(
            "teaching_plan_path_not_found",
            "目录小节不存在或已被目录修改",
            details={"section_id": section_id},
        )
    return section


def _module(snapshot: dict[str, Any], section_id: str, module_id: str) -> dict[str, Any]:
    section = _plan_section(snapshot, section_id)
    module = next(
        (
            item
            for item in section.get("teaching_modules") or []
            if isinstance(item, dict) and _text(item.get("module_id")) == module_id
        ),
        None,
    )
    if module is None:
        raise TeachingPlanWorkbenchError(
            "teaching_plan_path_not_found",
            "教学环节不存在或已被课程模板调整",
            details={"section_id": section_id, "module_id": module_id},
        )
    return module


def _knowledge_point(
    snapshot: dict[str, Any],
    section_id: str,
    knowledge_name: str,
) -> dict[str, Any]:
    section = _plan_section(snapshot, section_id)
    normalized_name = "".join(knowledge_name.lower().split())
    for group in section.get("knowledge_structure") or []:
        if not isinstance(group, dict):
            continue
        for point in group.get("knowledge_points") or []:
            if not isinstance(point, dict):
                continue
            actual = "".join(_text(point.get("name")).lower().split())
            if actual == normalized_name:
                return point
    raise TeachingPlanWorkbenchError(
        "teaching_plan_path_not_found",
        "知识点不存在或已被其他修订改变",
        details={"section_id": section_id, "knowledge_name": knowledge_name},
    )


_OVERALL_FIELDS = {
    "overall/positioning",
    "overall/target_audience",
    "overall/learning_objectives",
    "overall/prerequisites",
    "overall/teaching_strategy/rationale",
    "overall/academic_term",
    "overall/total_class_hours",
    "overall/lesson_duration_minutes",
    "overall/teaching_context",
    "overall/class_size",
    "overall/class_profile",
    "overall/teaching_preparation",
    "overall/course_assessment_plan",
}
_TEXT_LIMIT = 2000
_CLASSROOM_TEXT_FIELDS = {"academic_term", "class_profile"}
_CLASSROOM_LIST_FIELDS = {"teaching_preparation", "course_assessment_plan"}
_SECTION_CLASSROOM_LIST_FIELDS = {
    "key_difficulties",
    "teacher_activities",
    "student_activities",
    "resource_refs",
    "in_class_checks",
    "homework",
    "teaching_notes",
}

# 知识语义字段（contracts.md §2.4）。稳定知识 ID、来源绑定与编译状态
# 不在其中——它们由课程知识库维护，只读。
_KNOWLEDGE_TEXT_FIELDS = {"statement", "capability"}
# 7.3：知识绑定缺失时仍可编辑的描述性字段。statement 是「这个知识点讲什么」，
# conditions 是适用前提，二者不参与下游语义编译，改了不会因编译而丢失。
_KNOWLEDGE_DESCRIPTIVE_FIELDS = {"statement", "conditions"}
_KNOWLEDGE_LIST_FIELDS = {"conditions", "boundaries", "counterexamples"}
# 结构化条目：教师编辑的是每条的主字段文本，verification_method、
# discrimination 等兄弟键必须原样保留，不能被整条覆盖掉。
_KNOWLEDGE_DETAIL_FIELDS = {
    "misconceptions": "observable_error_pattern",
    "mastery_criteria": "observable_performance",
}


def _module_plan(snapshot: dict[str, Any], section_id: str) -> list[dict[str, Any]]:
    """学科模板为该小节提供的课程块合同（module_plan）。"""
    return [
        item
        for item in _outline_section(snapshot, section_id).get("module_plan") or []
        if isinstance(item, dict) and _text(item.get("module_id"))
    ]


def _write_module_order(
    snapshot: dict[str, Any],
    section_id: str,
    value: Any,
) -> list[str]:
    """按 module_id 有序列表重写小节的教学环节。

    一条路径同时表达新增、删除、替换与排序：给出的顺序就是结果顺序。
    module_id 保持稳定——已有环节按 id 原样搬运，不重建内容；新增的环节
    从模板取 label 与 output_contract 作为初始教学职责。

    模板合同在这里就地校验，不留到应用时才报错：教师删掉一个必需环节，
    应该当场知道，而不是写了一串草稿之后才被质量门挡下。
    """
    order = _strings(value, maximum=16)
    plan_by_id = {_text(item.get("module_id")): item for item in _module_plan(snapshot, section_id)}
    section = _plan_section(snapshot, section_id)
    existing = {
        _text(module.get("module_id")): module
        for module in section.get("teaching_modules") or []
        if isinstance(module, dict) and _text(module.get("module_id"))
    }

    if unknown := [item for item in order if item not in plan_by_id]:
        raise TeachingPlanWorkbenchError(
            "teaching_plan_invalid_value",
            "教学环节必须来自学科模板提供的课程块。",
            details={"section_id": section_id, "unknown_module_ids": unknown},
        )
    required = [
        _text(item.get("module_id"))
        for item in _module_plan(snapshot, section_id)
        if item.get("required")
    ]
    if missing := [item for item in required if item not in order]:
        raise TeachingPlanWorkbenchError(
            "teaching_plan_quality_blocked",
            "不能删除学科模板规定的必需教学环节。",
            details={"section_id": section_id, "missing_required_module_ids": missing},
        )
    if not order:
        raise TeachingPlanWorkbenchError(
            "teaching_plan_invalid_value",
            "小节至少保留一个教学环节。",
            details={"section_id": section_id},
        )

    rebuilt: list[dict[str, Any]] = []
    for module_id in order:
        if module_id in existing:
            rebuilt.append(existing[module_id])
            continue
        template = plan_by_id[module_id]
        rebuilt.append({
            "module_id": module_id,
            "teaching_purpose": _text(template.get("output_contract"))
            or _text(template.get("label"))
            or "待补充教学职责",
            "teaching_guidance": _text(template.get("prompt_instruction")),
            "knowledge_names": [],
        })
    section["teaching_modules"] = rebuilt
    return order


def _detail_texts(entries: Any, primary_field: str) -> list[str]:
    """把结构化条目投影成教师看到的主字段文本列表。"""
    texts: list[str] = []
    for entry in entries or []:
        if isinstance(entry, dict):
            text = _text(entry.get(primary_field))
        else:
            text = _text(entry)
        if text:
            texts.append(text)
    return texts


def _merge_detail_texts(
    existing: Any,
    texts: list[str],
    primary_field: str,
) -> list[dict[str, Any]]:
    """按位置回填主字段，保留原条目的其他键；多出的条目新建。

    教师改的是「易错表现」「掌握标准」这句话本身，配套的验证方法、
    纠偏策略不该因为改了一句话就被抹掉。
    """
    previous = [item for item in (existing or []) if isinstance(item, dict)]
    merged: list[dict[str, Any]] = []
    for index, text in enumerate(texts):
        entry = deepcopy(previous[index]) if index < len(previous) else {}
        entry[primary_field] = text
        merged.append(entry)
    return merged


def field_permission(path: str) -> dict[str, str]:
    normalized = path.strip("/")
    if any(token in normalized for token in (
        "knowledge_id", "revision_id", "binding_id", "source_revision",
        "module_id", "node_id",
    )):
        return {
            "state": "readonly",
            "reason": "该字段由课程、知识库或来源修订自动维护。",
        }
    if normalized in _OVERALL_FIELDS:
        if normalized in {
            "overall/total_class_hours",
            "overall/lesson_duration_minutes",
            "overall/teaching_context",
        }:
            return {
                "state": "requires_impact_review",
                "reason": "课堂时间或场景变化会影响教案执行与下游教学表达。",
            }
        return {"state": "editable", "reason": "可先保存为教案草稿。"}
    if re.fullmatch(r"sections/[^/]+/learning_objective", normalized):
        return {
            "state": "requires_impact_review",
            "reason": "小节目标变化会影响正文、练习与 PPT。",
        }
    if re.fullmatch(r"sections/[^/]+/key_points", normalized):
        return {
            "state": "requires_impact_review",
            "reason": "知识范围变化会影响绑定与下游教学表达。",
        }
    if re.fullmatch(
        r"sections/[^/]+/(planned_minutes|key_difficulties|teacher_activities|student_activities|resource_refs|in_class_checks|homework|teaching_notes)",
        normalized,
    ):
        return {
            "state": "requires_impact_review",
            "reason": "课堂执行字段变化需要检查该小节的教学表达与课时安排。",
        }
    if re.fullmatch(r"sections/[^/]+/teaching_modules", normalized):
        return {
            "state": "requires_impact_review",
            "reason": "教学环节的增删与排序会改变本节的教学结构与派生表达。",
        }
    if re.fullmatch(
        r"sections/[^/]+/teaching_modules/[^/]+/(teaching_purpose|teaching_guidance|planned_minutes|teacher_activity|student_activity)",
        normalized,
    ):
        return {
            "state": "requires_impact_review",
            "reason": "教学环节变化会影响当前小节的派生表达。",
        }
    if re.fullmatch(
        r"sections/[^/]+/knowledge/[^/]+/(statement|capability|conditions|boundaries|counterexamples|misconceptions|mastery_criteria)",
        normalized,
    ):
        return {
            "state": "requires_impact_review",
            "reason": "知识语义变化需要完成绑定与下游影响检查。",
        }
    if "chapter" in normalized or "outline" in normalized:
        return {
            "state": "readonly",
            "reason": "章节增删与排序请在目录编辑器中完成。",
            "redirect": "redirect_to_outline_edit",
        }
    return {"state": "readonly", "reason": "该字段暂不支持直接编辑。"}


# 目录真源拥有的结构操作：章节/小节的增删、排序与改标题。
# 这些路径即使落在 sections/ 命名空间下也不归教案命令管——
# 教案只描述「怎么教」，目录决定「有哪些节、什么顺序」。
_OUTLINE_OWNED_SUFFIXES = (
    "position",
    "order",
    "title",
    "node_name",
    "parent_section_id",
    "parent_node_id",
    "level",
)


def outline_redirect_reason(path: str) -> str:
    """结构操作要走目录真源时的用户可见理由；不命中返回空串。"""
    normalized = path.strip("/")
    if "chapter" in normalized or "outline" in normalized:
        return "章节增删与排序请在目录编辑器中完成。"
    parts = normalized.split("/")
    if len(parts) >= 3 and parts[0] == "sections" and parts[-1] in _OUTLINE_OWNED_SUFFIXES:
        return "小节的标题、层级与排序请在目录编辑器中完成。"
    return ""


def _read_path(snapshot: dict[str, Any], path: str) -> Any:
    parts = path.strip("/").split("/")
    if parts == ["overall", "positioning"]:
        return (snapshot.get("course_plan") or {}).get("positioning", "")
    if parts == ["overall", "target_audience"]:
        request = snapshot.get("generation_request") or {}
        return request.get("target_audience", "")
    if parts == ["overall", "learning_objectives"]:
        return (snapshot.get("course_plan") or {}).get("learning_objectives", [])
    if parts == ["overall", "prerequisites"]:
        return (snapshot.get("course_plan") or {}).get("prerequisites", [])
    if parts == ["overall", "teaching_strategy", "rationale"]:
        return (snapshot.get("subject_pedagogy_profile") or {}).get("rationale", "")
    if len(parts) == 2 and parts[0] == "overall" and parts[1] in _CLASSROOM_TEXT_FIELDS | _CLASSROOM_LIST_FIELDS | {
        "total_class_hours", "lesson_duration_minutes", "teaching_context", "class_size",
    }:
        default = [] if parts[1] in _CLASSROOM_LIST_FIELDS else ""
        return _classroom_value(snapshot, parts[1], default)
    if len(parts) == 3 and parts[0] == "sections" and parts[2] == "learning_objective":
        return _outline_section(snapshot, parts[1]).get("learning_objective", "")
    if len(parts) == 3 and parts[0] == "sections" and parts[2] == "key_points":
        return _plan_section(snapshot, parts[1]).get("key_points", [])
    if len(parts) == 3 and parts[0] == "sections" and parts[2] == "planned_minutes":
        return _plan_section(snapshot, parts[1]).get("planned_minutes")
    if len(parts) == 3 and parts[0] == "sections" and parts[2] in _SECTION_CLASSROOM_LIST_FIELDS:
        return _plan_section(snapshot, parts[1]).get(parts[2], [])
    if len(parts) == 3 and parts[0] == "sections" and parts[2] == "teaching_modules":
        return [
            _text(module.get("module_id"))
            for module in _plan_section(snapshot, parts[1]).get("teaching_modules") or []
            if isinstance(module, dict) and _text(module.get("module_id"))
        ]
    if len(parts) == 5 and parts[0] == "sections" and parts[2] == "teaching_modules":
        if parts[4] in {"teaching_purpose", "teaching_guidance", "teacher_activity", "student_activity"}:
            return _module(snapshot, parts[1], parts[3]).get(parts[4], "")
        if parts[4] == "planned_minutes":
            return _module(snapshot, parts[1], parts[3]).get(parts[4])
    if len(parts) == 5 and parts[0] == "sections" and parts[2] == "knowledge":
        if parts[4] in _KNOWLEDGE_TEXT_FIELDS:
            return _knowledge_point(snapshot, parts[1], parts[3]).get(parts[4], "")
        if parts[4] in _KNOWLEDGE_LIST_FIELDS:
            point = _knowledge_point(snapshot, parts[1], parts[3])
            return list(point.get(parts[4]) or [])
        if (primary := _KNOWLEDGE_DETAIL_FIELDS.get(parts[4])) is not None:
            point = _knowledge_point(snapshot, parts[1], parts[3])
            return _detail_texts(point.get(parts[4]), primary)
    raise TeachingPlanWorkbenchError(
        "teaching_plan_path_not_found",
        "教案字段不存在",
        details={"path": path},
    )


def _write_path(snapshot: dict[str, Any], path: str, value: Any) -> Any:
    permission = field_permission(path)
    if permission["state"] == "readonly":
        raise TeachingPlanWorkbenchError(
            "teaching_plan_readonly_field",
            permission["reason"],
            details={"path": path},
        )
    parts = path.strip("/").split("/")
    if parts == ["overall", "positioning"]:
        text = _text(value)
        if not text or len(text) > _TEXT_LIMIT:
            raise TeachingPlanWorkbenchError("teaching_plan_invalid_value", "课程定位不能为空且不能过长")
        snapshot.setdefault("course_plan", {})["positioning"] = text
        return text
    if parts == ["overall", "target_audience"]:
        text = _text(value)
        if not text or len(text) > 500:
            raise TeachingPlanWorkbenchError("teaching_plan_invalid_value", "教学对象不能为空且不能过长")
        snapshot.setdefault("generation_request", {})["target_audience"] = text
        snapshot["generation_request"].setdefault("teacher_course_brief", {})["target_audience"] = text
        return text
    if parts == ["overall", "learning_objectives"]:
        values = _strings(value, maximum=8)
        if not values:
            raise TeachingPlanWorkbenchError("teaching_plan_invalid_value", "总体目标至少保留一项")
        snapshot.setdefault("course_plan", {})["learning_objectives"] = values
        return values
    if parts == ["overall", "prerequisites"]:
        values = _strings(value, maximum=12)
        snapshot.setdefault("course_plan", {})["prerequisites"] = values
        return values
    if parts == ["overall", "teaching_strategy", "rationale"]:
        text = _text(value)
        if not text or len(text) > _TEXT_LIMIT:
            raise TeachingPlanWorkbenchError("teaching_plan_invalid_value", "教学策略说明不能为空且不能过长")
        snapshot.setdefault("subject_pedagogy_profile", {})["rationale"] = text
        return text
    if len(parts) == 2 and parts[0] == "overall" and parts[1] in _CLASSROOM_TEXT_FIELDS:
        text = _text(value)
        maximum = 100 if parts[1] == "academic_term" else _TEXT_LIMIT
        if len(text) > maximum:
            raise TeachingPlanWorkbenchError("teaching_plan_invalid_value", "课堂字段内容过长")
        _classroom(snapshot, create=True)[parts[1]] = text
        return text
    if len(parts) == 2 and parts[0] == "overall" and parts[1] in _CLASSROOM_LIST_FIELDS:
        values = _strings(value, maximum=12)
        _classroom(snapshot, create=True)[parts[1]] = values
        return values
    if parts == ["overall", "teaching_context"]:
        context = _text(value)
        if context not in {"classroom", "online", "blended", "self_study"}:
            raise TeachingPlanWorkbenchError("teaching_plan_invalid_value", "教学场景不合法")
        _classroom(snapshot, create=True)["teaching_context"] = context
        return context
    if len(parts) == 2 and parts[0] == "overall" and parts[1] in {
        "total_class_hours", "lesson_duration_minutes", "class_size",
    }:
        if parts[1] == "class_size" and value is None:
            _classroom(snapshot, create=True).pop("class_size", None)
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            raise TeachingPlanWorkbenchError("teaching_plan_invalid_value", "课堂人数与课时必须为整数")
        lower, upper = (1, 1000) if parts[1] != "lesson_duration_minutes" else (20, 240)
        if value < lower or value > upper:
            raise TeachingPlanWorkbenchError("teaching_plan_invalid_value", "课堂人数或课时超出允许范围")
        _classroom(snapshot, create=True)[parts[1]] = value
        return value
    if len(parts) == 3 and parts[0] == "sections" and parts[2] == "learning_objective":
        text = _text(value)
        if not text or len(text) > _TEXT_LIMIT:
            raise TeachingPlanWorkbenchError("teaching_plan_invalid_value", "小节目标不能为空且不能过长")
        _outline_section(snapshot, parts[1])["learning_objective"] = text
        return text
    if len(parts) == 3 and parts[0] == "sections" and parts[2] == "key_points":
        values = _strings(value, maximum=16)
        if not values:
            raise TeachingPlanWorkbenchError("teaching_plan_invalid_value", "小节至少保留一个知识要点")
        _plan_section(snapshot, parts[1])["key_points"] = values
        return values
    if len(parts) == 3 and parts[0] == "sections" and parts[2] == "planned_minutes":
        if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > 240:
            raise TeachingPlanWorkbenchError("teaching_plan_invalid_value", "小节计划时长必须在 1 到 240 分钟之间")
        _plan_section(snapshot, parts[1])["planned_minutes"] = value
        return value
    if len(parts) == 3 and parts[0] == "sections" and parts[2] in _SECTION_CLASSROOM_LIST_FIELDS:
        values = _strings(value, maximum=30 if parts[2] == "resource_refs" else 16)
        _plan_section(snapshot, parts[1])[parts[2]] = values
        return values
    if len(parts) == 3 and parts[0] == "sections" and parts[2] == "teaching_modules":
        return _write_module_order(snapshot, parts[1], value)
    if len(parts) == 5 and parts[0] == "sections" and parts[2] == "teaching_modules":
        if parts[4] in {"teaching_purpose", "teaching_guidance", "teacher_activity", "student_activity"}:
            text = _text(value)
            if not text or len(text) > _TEXT_LIMIT:
                raise TeachingPlanWorkbenchError("teaching_plan_invalid_value", "教学环节说明不能为空且不能过长")
            _module(snapshot, parts[1], parts[3])[parts[4]] = text
            return text
        if parts[4] == "planned_minutes":
            if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > 240:
                raise TeachingPlanWorkbenchError("teaching_plan_invalid_value", "教学环节时长必须在 1 到 240 分钟之间")
            _module(snapshot, parts[1], parts[3])[parts[4]] = value
            return value
    if len(parts) == 5 and parts[0] == "sections" and parts[2] == "knowledge":
        # 7.3：写入侧同样把关。只在 UI 隐藏不够——API 仍可被直接调用，
        # 那样绕过限制写进去的结构字段会在编译后被覆盖，改动静默丢失。
        if parts[4] not in _KNOWLEDGE_DESCRIPTIVE_FIELDS:
            point = _knowledge_point(snapshot, parts[1], parts[3])
            if not _text(point.get("knowledge_id")):
                raise TeachingPlanWorkbenchError(
                    "teaching_plan_knowledge_binding_required",
                    "该知识点尚未完成知识库编译；补全绑定后才能编辑能力、掌握标准与边界。",
                    details={"section_id": parts[1], "knowledge_name": parts[3]},
                )
        if parts[4] in _KNOWLEDGE_TEXT_FIELDS:
            text = _text(value)
            if not text or len(text) > _TEXT_LIMIT:
                raise TeachingPlanWorkbenchError("teaching_plan_invalid_value", "知识说明不能为空且不能过长")
            _knowledge_point(snapshot, parts[1], parts[3])[parts[4]] = text
            return text
        if parts[4] in _KNOWLEDGE_LIST_FIELDS:
            values = _strings(value, maximum=12)
            _knowledge_point(snapshot, parts[1], parts[3])[parts[4]] = values
            return values
        if (primary := _KNOWLEDGE_DETAIL_FIELDS.get(parts[4])) is not None:
            texts = _strings(value, maximum=12)
            point = _knowledge_point(snapshot, parts[1], parts[3])
            point[parts[4]] = _merge_detail_texts(point.get(parts[4]), texts, primary)
            return texts
    raise TeachingPlanWorkbenchError(
        "teaching_plan_path_not_found",
        "教案字段不存在",
        details={"path": path},
    )


def _validate(snapshot: dict[str, Any]) -> dict[str, Any]:
    plan = snapshot.get("course_teaching_plan")
    if not isinstance(plan, dict) or not plan.get("sections"):
        return {
            "schema_version": "teaching_plan_workbench_validation_v1",
            "status": "blocked",
            "passed": False,
            "issues": [{
                "code": "teaching_plan_missing",
                "message": "当前课程没有可编辑的结构化教案。",
                "blocking": True,
            }],
        }
    report = validate_course_teaching_plan(
        plan,
        sections=_course_sections(snapshot),
        expected_outline_revision_id=_text(plan.get("source_outline_revision_id")) or None,
    )
    issues = list(report.get("issues") or [])
    classroom = _classroom(snapshot)
    total_hours = classroom.get("total_class_hours")
    planned_minutes = [
        value
        for section in plan.get("sections") or []
        if isinstance(section, dict)
        if isinstance((value := section.get("planned_minutes")), int) and not isinstance(value, bool)
    ]
    blocking = False
    if isinstance(total_hours, int) and not isinstance(total_hours, bool) and planned_minutes:
        planned_total = sum(planned_minutes)
        capacity = total_hours * 60
        if planned_total > capacity:
            issues.append({
                "code": "teaching_plan_class_hours_exceeded",
                "message": "各小节计划时长超过课程总课时。",
                "blocking": True,
            })
            blocking = True
        elif planned_total != capacity:
            issues.append({
                "code": "teaching_plan_class_hours_incomplete",
                "message": "各小节计划时长尚未与课程总课时对齐。",
                "blocking": False,
            })
    return {
        **report,
        "passed": bool(report.get("passed")) and not blocking,
        "issues": issues,
        "schema_version": "teaching_plan_workbench_validation_v1",
        "status": "blocked" if not report.get("passed") or blocking else (
            "warning" if issues else "valid"
        ),
    }


def _impact(
    operations: list[dict[str, Any]],
    snapshot: dict[str, Any],
    *,
    course_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministic impact report; see teaching_plan_impact for the rules."""
    return build_impact_report(operations, snapshot, course_data=course_data)


def _diff_between(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    operations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    entries = deepcopy(operations or [])
    if not entries:
        fields = [
            "overall/positioning",
            "overall/target_audience",
            "overall/learning_objectives",
            "overall/prerequisites",
            "overall/teaching_strategy/rationale",
            "overall/academic_term",
            "overall/total_class_hours",
            "overall/lesson_duration_minutes",
            "overall/teaching_context",
            "overall/class_size",
            "overall/class_profile",
            "overall/teaching_preparation",
            "overall/course_assessment_plan",
        ]
        before_sections = {item.get("node_id") for item in _course_sections(before)}
        after_sections = {item.get("node_id") for item in _course_sections(after)}
        for section_id in sorted(str(item) for item in before_sections & after_sections if item):
            fields.extend([
                f"sections/{section_id}/learning_objective",
                f"sections/{section_id}/key_points",
                f"sections/{section_id}/planned_minutes",
                *[
                    f"sections/{section_id}/{field}"
                    for field in sorted(_SECTION_CLASSROOM_LIST_FIELDS)
                ],
            ])
        for path in fields:
            try:
                left = _read_path(before, path)
                right = _read_path(after, path)
            except TeachingPlanWorkbenchError:
                continue
            if left != right:
                entries.append({
                    "operation_id": _value_hash({"path": path, "before": left, "after": right}),
                    "path": path,
                    "before": left,
                    "after": right,
                    "source": "restore",
                })
    return {"schema_version": "teaching_plan_diff_v1", "operations": entries}


def _baseline_revision(
    raw: dict[str, Any],
    state: dict[str, Any],
    *,
    created_by: str = "generation",
) -> None:
    revisions = state.setdefault("revisions", [])
    if not isinstance(revisions, list):
        revisions = []
        state["revisions"] = revisions
    current_id = _current_plan_revision(raw)
    if not current_id or any(item.get("revision_id") == current_id for item in revisions):
        return
    source = _source_snapshot(raw)
    revisions.append({
        "schema_version": REVISION_SCHEMA,
        "revision_id": current_id,
        "revision_number": max([int(item.get("revision_number") or 0) for item in revisions] or [0]) + 1,
        "parent_revision_id": "",
        "source_revision_vector": revision_vector_for_course(
            CourseDocument.model_validate(raw["course_document"]), raw,
        ).model_dump(mode="json"),
        "snapshot": source,
        "change_set_id": "",
        "quality_report": _validate(source),
        "created_by": created_by,
        "created_at": _now(),
    })


def _initializable_sections(raw: dict[str, Any]) -> list[dict[str, Any]]:
    plan = raw.get("course_plan")
    if not isinstance(plan, dict):
        return []
    return [
        deepcopy(section)
        for chapter in plan.get("chapters") or []
        if isinstance(chapter, dict)
        for section in chapter.get("sections") or []
        if isinstance(section, dict) and _text(section.get("node_id"))
    ]


def _compile_initial_teaching_plan(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = raw.get("course_plan")
    sections = _initializable_sections(raw)
    if not isinstance(plan, dict) or not sections:
        raise TeachingPlanWorkbenchError(
            "teaching_plan_initialization_unavailable",
            "当前课程缺少可用于建立教案基线的结构化目录。",
        )
    scope = build_course_knowledge_scope_contract(plan)
    outline_revision_id = _text(scope.get("revision_id"))
    compiled = compile_course_teaching_plan_modules(
        {"sections": sections},
        sections=sections,
    )
    official = promote_course_teaching_plan_v3(
        compiled,
        outline_revision_id=outline_revision_id,
    )
    official = compile_course_teaching_plan_modules(official, sections=sections)
    report = validate_course_teaching_plan(
        official,
        sections=sections,
        expected_outline_revision_id=outline_revision_id or None,
    )
    if not report.get("passed"):
        raise TeachingPlanWorkbenchError(
            "teaching_plan_initialization_blocked",
            "当前目录还不能建立可编辑教案，请先修复目录中的结构问题。",
            details={"validation": report},
        )
    return official, report


def _public_draft(
    draft: dict[str, Any] | None,
    current_plan_revision: str = "",
) -> dict[str, Any] | None:
    if not isinstance(draft, dict):
        return None
    public = {
        key: deepcopy(value)
        for key, value in draft.items()
        if key != "snapshot"
    }
    public["status"] = _draft_status(draft, current_plan_revision)
    return public


def _section_module_options(snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """每节的候选教学环节：模板给了哪些、哪些必需、当前是否已选。

    教师要能增删环节，前端就得知道「候选集是什么」。这份数据来自目录侧的
    `module_plan`（学科模板合同），不是教案自己编的——教案只能在模板给定的
    集合里选，必需环节不能删（校验在 `_write_module_order`）。
    """
    options: dict[str, list[dict[str, Any]]] = {}
    for section in _course_sections(snapshot):
        section_id = _text(section.get("node_id"))
        if not section_id:
            continue
        try:
            selected = {
                _text(module.get("module_id"))
                for module in _plan_section(snapshot, section_id).get("teaching_modules") or []
                if isinstance(module, dict)
            }
        except TeachingPlanWorkbenchError:
            selected = set()
        entries = []
        for item in _module_plan(snapshot, section_id):
            module_id = _text(item.get("module_id"))
            entries.append({
                "module_id": module_id,
                "label": _text(item.get("label")) or module_id,
                "required": bool(item.get("required")),
                "selected": module_id in selected,
                "output_contract": _text(item.get("output_contract")),
            })
        if entries:
            options[section_id] = entries
    return options


def _editable_fields(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    fields = []
    for path in sorted(_OVERALL_FIELDS):
        fields.append({"path": path, **field_permission(path)})
    for section in _course_sections(snapshot):
        section_id = _text(section.get("node_id"))
        if not section_id:
            continue
        for suffix in ("learning_objective", "key_points"):
            path = f"sections/{section_id}/{suffix}"
            fields.append({"path": path, **field_permission(path)})
        for suffix in ("planned_minutes", *sorted(_SECTION_CLASSROOM_LIST_FIELDS)):
            path = f"sections/{section_id}/{suffix}"
            fields.append({"path": path, **field_permission(path)})
        try:
            teaching_section = _plan_section(snapshot, section_id)
        except TeachingPlanWorkbenchError:
            continue
        # 环节的增删与排序：一条路径承载整组顺序，module_id 保持稳定。
        order_path = f"sections/{section_id}/teaching_modules"
        fields.append({"path": order_path, **field_permission(order_path)})
        for module in teaching_section.get("teaching_modules") or []:
            module_id = _text((module or {}).get("module_id"))
            if not module_id:
                continue
            for suffix in (
                "teaching_purpose",
                "teaching_guidance",
                "planned_minutes",
                "teacher_activity",
                "student_activity",
            ):
                path = f"sections/{section_id}/teaching_modules/{module_id}/{suffix}"
                fields.append({"path": path, **field_permission(path)})
        for group in teaching_section.get("knowledge_structure") or []:
            if not isinstance(group, dict):
                continue
            for point in group.get("knowledge_points") or []:
                name = _text((point or {}).get("name"))
                if not name:
                    continue
                # 7.3 缺知识绑定时限制编辑：知识点还没编译出稳定
                # knowledge_id 时，只开放描述性字段，结构性字段（能力、
                # 掌握标准、易错、边界）转只读并说明补全要求。
                # 理由：这些字段是知识库编译与下游绑定的输入，在身份未定
                # 之前改它们，改动无处落脚，编译后还会被覆盖。
                bound = bool(_text((point or {}).get("knowledge_id")))
                for suffix in (
                    "statement",
                    "capability",
                    "conditions",
                    "boundaries",
                    "counterexamples",
                    "misconceptions",
                    "mastery_criteria",
                ):
                    path = f"sections/{section_id}/knowledge/{name}/{suffix}"
                    permission = dict(field_permission(path))
                    if not bound and suffix not in _KNOWLEDGE_DESCRIPTIVE_FIELDS:
                        permission = {
                            "state": "readonly",
                            "reason": "该知识点尚未完成知识库编译；补全绑定后才能编辑能力、掌握标准与边界。",
                            "requires": "knowledge_binding",
                        }
                    fields.append({"path": path, **permission})
    readable_fields = []
    for field in fields:
        try:
            field["value_hash"] = _value_hash(_read_path(snapshot, field["path"]))
        except TeachingPlanWorkbenchError:
            continue
        readable_fields.append(field)
    return readable_fields


def _candidate_prompt(
    snapshot: dict[str, Any],
    *,
    paths: list[str],
    instruction: str,
) -> str:
    fields = []
    for path in paths:
        fields.append({"path": path, "current_value": _read_path(snapshot, path)})
    return f"""你正在为教师生成一份可审阅的课程教案修改候选，而不是直接修改正式课程。

## 教师意图
{instruction}

## 当前可修改字段
{fields}

## 严格约束
1. 只能修改以上 path，不能增删章节、课程块、知识 ID、模块 ID、修订号或知识绑定。
2. 目标是提升教学清晰度、可教性和可评价性；不得编造事实、来源、题目、年份或外部数据。
3. 数组字段必须是短文本数组，不要返回 Markdown。
4. 课时、人数和时长字段必须返回合法整数；教学场景只能是 classroom、online、blended 或 self_study。
5. 每个字段至多一项操作；没有必要修改的字段不要输出。
6. 这只是候选，教师之后会逐项审阅和确认。

只输出一个 JSON 对象：
{{
  "rationale": "为什么这样建议",
  "operations": [
    {{"path": "以上某一个路径", "after": "修改后内容或字符串数组", "reason": "教学理由"}}
  ]
}}"""


def _normalize_ai_operations(
    snapshot: dict[str, Any],
    *,
    paths: list[str],
    response: dict[str, Any],
) -> list[dict[str, Any]]:
    requested = set(paths)
    raw_operations = response.get("operations") if isinstance(response, dict) else None
    if not isinstance(raw_operations, list) or not raw_operations:
        raise TeachingPlanWorkbenchError(
            "teaching_plan_ai_empty_candidate",
            "AI 没有返回可应用的教案候选。",
        )
    working = deepcopy(snapshot)
    operations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_operations:
        if not isinstance(item, dict):
            continue
        path = _text(item.get("path")).strip("/")
        if not path or path not in requested or path in seen:
            continue
        permission = field_permission(path)
        if permission["state"] == "readonly":
            continue
        before = _read_path(working, path)
        after = _write_path(working, path, item.get("after"))
        if before == after:
            continue
        operations.append({
            "operation_id": _new_id("tpao_"),
            "path": path,
            "before": before,
            "after": after,
            "source": "ai",
            "reason": _text(item.get("reason")),
            "permission": permission["state"],
            "updated_at": _now(),
        })
        seen.add(path)
    if not operations:
        raise TeachingPlanWorkbenchError(
            "teaching_plan_ai_empty_candidate",
            "AI 候选没有形成可保存的字段修改。",
        )
    return operations


def _realign_plan_section_ids(
    course_plan: dict[str, Any],
    teaching_plan: dict[str, Any],
) -> None:
    """让教案小节的 node_id 跟随目录归一化后的正式 ID。

    apply_course_teaching_plan 内部会走 normalize_course_plan_contract，
    把目录小节重编为 L2-<章>-<节>。教案自己的 sections[].node_id 不在那条
    链路上，于是应用之后两边会分叉：目录是 L2-1-1，教案还是 section-1。

    分叉的后果是安静的——_plan_section 找不到小节，_editable_fields 直接
    跳过整节，于是第二轮编辑时该节的教学环节与知识字段**从工作台消失**，
    不报任何错。需求 5 的「二次编辑」正好踩在这上面。

    目录是结构真源，所以按位置对齐、以目录为准；两边小节数不一致时不猜，
    保持原样交给结构校验去报。
    """
    outline_ids = [
        _text(section.get("node_id"))
        for chapter in course_plan.get("chapters") or []
        if isinstance(chapter, dict)
        for section in chapter.get("sections") or []
        if isinstance(section, dict)
    ]
    plan_sections = [
        section for section in teaching_plan.get("sections") or []
        if isinstance(section, dict)
    ]
    if len(outline_ids) != len(plan_sections):
        return
    renamed = {
        _text(section.get("node_id")): outline_id
        for section, outline_id in zip(plan_sections, outline_ids)
        if _text(section.get("node_id")) and _text(section.get("node_id")) != outline_id
    }
    if not renamed:
        return
    for section, outline_id in zip(plan_sections, outline_ids):
        if outline_id:
            section["node_id"] = outline_id
    # 知识关系与复用引用里的小节归属同样要跟着改名，否则会指向不存在的节。
    for section in plan_sections:
        for relation in section.get("knowledge_relations") or []:
            if not isinstance(relation, dict):
                continue
            for key in ("owner_node_id", "source_node_id", "target_node_id"):
                if (current := _text(relation.get(key))) in renamed:
                    relation[key] = renamed[current]


class TeachingPlanWorkbenchService:
    def __init__(
        self,
        repository: CourseDocumentRepository,
        *,
        candidate_generator: Any | None = None,
        feature_enabled: bool | None = None,
        representation_repository: Any | None = None,
    ) -> None:
        self.repository = repository
        self.candidate_generator = candidate_generator
        self.feature_enabled = _feature_enabled() if feature_enabled is None else feature_enabled
        # Read-only: the impact analysis inspects the representation registry to
        # report downstream source state; rebuilds stay with their own pipelines.
        self.representation_repository = representation_repository

    def representation_registry(self, course_id: str) -> Any | None:
        if self.representation_repository is None:
            return None
        try:
            return self.representation_repository.load(course_id)
        except Exception:
            # A missing or unreadable registry must never block teaching-plan
            # analysis; downstream state simply falls back to the course data.
            return None

    def _require_feature_enabled(self) -> None:
        if not self.feature_enabled:
            raise TeachingPlanWorkbenchError(
                "teaching_plan_workbench_disabled",
                "教案工作台当前未启用，只能查看正式教案。",
            )

    def view(self, course_id: str, *, actor: str) -> dict[str, Any]:
        raw = self.repository.load_raw(course_id)
        snapshot = _source_snapshot(raw)
        state = _state(raw)
        current_revision = _current_plan_revision(raw)
        is_canonical = self.repository.is_canonical(raw)
        can_initialize = bool(
            is_canonical
            and self.feature_enabled
            and not current_revision
            and _initializable_sections(raw)
        )
        draft = (state.get("drafts") or {}).get(actor)
        if isinstance(draft, dict) and isinstance(draft.get("snapshot"), dict):
            snapshot = deepcopy(draft["snapshot"])
        revisions = [
            {
                key: deepcopy(value)
                for key, value in item.items()
                if key != "snapshot"
            }
            for item in state.get("revisions") or []
            if isinstance(item, dict)
        ]
        return {
            "schema_version": WORKBENCH_SCHEMA,
            "course_id": course_id,
            "actor": actor,
            "enabled": self.feature_enabled,
            "available": bool(current_revision and is_canonical and self.feature_enabled),
            "can_initialize": can_initialize,
            "read_only_reason": (
                "" if current_revision and is_canonical and self.feature_enabled
                else "教案工作台当前未启用，只能查看正式教案。" if not self.feature_enabled
                else "当前课程可以从已发布目录建立可编辑教案基线。" if can_initialize
                else "当前课程尚未迁移为可修订的结构化课程；现可阅读，迁移后可编辑。"
            ),
            "current_plan_revision_id": current_revision,
            "course_document_revision": _text(raw.get("course_document_revision")),
            "revision_vector": revision_vector_for_course(
                CourseDocument.model_validate(raw["course_document"]), raw,
            ).model_dump(mode="json") if is_canonical else {},
            "teaching_plan": project_course_teaching_plan(raw),
            "draft": _public_draft(draft, current_revision),
            "revisions": sorted(revisions, key=lambda item: int(item.get("revision_number") or 0), reverse=True),
            "change_sets": [{
                key: deepcopy(value)
                for key, value in item.items()
                if key not in {"snapshot", "base_snapshot"}
            } for item in state.get("change_sets") or [] if isinstance(item, dict)],
            "ai_candidates": [
                deepcopy(item)
                for item in state.get("ai_candidates") or []
                if isinstance(item, dict) and item.get("actor") == actor
            ],
            "downstream": deepcopy(state.get("downstream") or {}),
            "editable_fields": (
                _editable_fields(snapshot)
                if current_revision and is_canonical
                else []
            ),
            # 学科模板为每节提供的候选教学环节：前端据此渲染「可以加哪些环节、
            # 哪些是必需的不能删」。没有它，UI 只能显示已有环节，教师无从新增。
            "section_module_options": _section_module_options(snapshot) if is_canonical else {},
        }

    async def initialize_baseline(
        self,
        course_id: str,
        *,
        actor: str,
        idempotency_key: str,
        base_course_document_revision: str,
    ) -> dict[str, Any]:
        self._require_feature_enabled()
        raw = self.repository.load_raw(course_id)
        command_id = f"teaching-plan-initialize:{actor}:{idempotency_key}"
        existing_receipt = self.repository.receipt_for_command(course_id, command_id)
        if existing_receipt:
            return {
                "workbench": self.view(course_id, actor=actor),
                "receipt": existing_receipt,
            }
        if not self.repository.is_canonical(raw):
            raise TeachingPlanWorkbenchError(
                "teaching_plan_readonly_legacy",
                "当前课程需要先迁移为结构化课程。",
            )
        current_revision = _current_plan_revision(raw)
        if current_revision:
            return {
                "workbench": self.view(course_id, actor=actor),
                "receipt": {},
            }
        document_revision = _text(raw.get("course_document_revision"))
        if base_course_document_revision and base_course_document_revision != document_revision:
            raise TeachingPlanWorkbenchError(
                "course_document_base_conflict",
                "课程正文已更新，请重新载入后再建立教案基线。",
                details={"current_course_document_revision": document_revision},
            )
        official, report = _compile_initial_teaching_plan(raw)

        def mutation(working: dict[str, Any]) -> None:
            if _current_plan_revision(working):
                raise TeachingPlanWorkbenchError(
                    "teaching_plan_base_conflict",
                    "正式教案已由其他操作建立，请重新载入。",
                    details={
                        "current_plan_revision_id": _current_plan_revision(working),
                    },
                )
            working["course_teaching_plan"] = deepcopy(official)
            working["course_plan"] = apply_course_teaching_plan(
                deepcopy(working.get("course_plan") or {}),
                official,
            )
            working.setdefault("generation_stage_artifacts", {})[
                "course_teaching_plan"
            ] = {
                "status": "completed",
                "semantic_status": "deterministic_baseline",
                "schema_version": official.get("schema_version"),
                "revision_id": official.get("revision_id"),
                "source_outline_revision_id": official.get(
                    "source_outline_revision_id",
                ),
                "validation_report": deepcopy(report),
                "strategy": "explicit_course_plan_upgrade",
                "model_call_count": 0,
            }
            working["teaching_plan_migration"] = {
                "schema_version": "teaching_plan_migration_v1",
                "source": "published_course_plan",
                "revision_id": official.get("revision_id"),
                "actor": actor,
                "created_at": _now(),
            }
            state = _state(working, create=True)
            _baseline_revision(working, state, created_by="migration")

        receipt = await self.repository.apply_metadata_command(
            course_id,
            expected_document_revision=document_revision,
            operation={
                "command_id": command_id,
                "operation": "initialize_teaching_plan_baseline",
                "reason": "从已发布课程目录显式建立可编辑教案基线",
                "actor": actor,
            },
            mutation=mutation,
        )
        return {
            "workbench": self.view(course_id, actor=actor),
            "receipt": receipt,
        }

    async def create_draft(
        self,
        course_id: str,
        *,
        actor: str,
        idempotency_key: str,
        base_plan_revision_id: str,
        base_course_document_revision: str,
    ) -> dict[str, Any]:
        self._require_feature_enabled()
        raw = self.repository.load_raw(course_id)
        if not self.repository.is_canonical(raw):
            raise TeachingPlanWorkbenchError(
                "teaching_plan_readonly_legacy",
                "当前课程尚未迁移为可修订的结构化课程。",
            )
        current_plan_revision = _current_plan_revision(raw)
        if not current_plan_revision:
            raise TeachingPlanWorkbenchError("teaching_plan_missing", "当前课程没有可编辑的结构化教案")
        if base_plan_revision_id and base_plan_revision_id != current_plan_revision:
            raise TeachingPlanWorkbenchError(
                "teaching_plan_base_conflict",
                "正式教案已更新，请重新载入后再编辑。",
                details={"current_plan_revision_id": current_plan_revision},
            )
        document_revision = _text(raw.get("course_document_revision"))
        if base_course_document_revision and base_course_document_revision != document_revision:
            raise TeachingPlanWorkbenchError(
                "course_document_base_conflict",
                "课程正文已更新，请重新载入教案工作台。",
                details={"current_course_document_revision": document_revision},
            )

        def mutation(working: dict[str, Any]) -> None:
            state = _state(working, create=True)
            _baseline_revision(working, state)
            existing = (state.get("drafts") or {}).get(actor)
            if (
                isinstance(existing, dict)
                and existing.get("base_plan_revision_id") == current_plan_revision
                and not _is_expired(existing)
            ):
                return
            created_at = _now()
            state["drafts"][actor] = {
                "schema_version": DRAFT_SCHEMA,
                "draft_id": _new_id("tpd_"),
                "course_id": course_id,
                "actor": actor,
                "base_plan_revision_id": current_plan_revision,
                "base_course_document_revision": document_revision,
                "snapshot": _source_snapshot(working),
                "operations": [],
                "changed_paths": [],
                "validation": _validate(_source_snapshot(working)),
                "created_at": created_at,
                "updated_at": created_at,
                "expires_at": _draft_expires_at(created_at),
            }

        await self.repository.apply_metadata_command(
            course_id,
            expected_document_revision=document_revision,
            operation={
                "command_id": f"teaching-plan-draft:{actor}:{idempotency_key}",
                "operation": "create_teaching_plan_draft",
                "reason": "创建教案结构化草稿",
                "actor": actor,
            },
            mutation=mutation,
        )
        return self.view(course_id, actor=actor)

    async def patch_draft(
        self,
        course_id: str,
        *,
        actor: str,
        draft_id: str,
        path: str,
        value: Any,
        expected_value_hash: str,
        base_plan_revision_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_feature_enabled()
        raw = self.repository.load_raw(course_id)
        document_revision = _text(raw.get("course_document_revision"))
        current_plan_revision = _current_plan_revision(raw)
        path = path.strip("/")

        def mutation(working: dict[str, Any]) -> None:
            state = _state(working, create=True)
            draft = (state.get("drafts") or {}).get(actor)
            if not isinstance(draft, dict) or draft.get("draft_id") != draft_id:
                raise TeachingPlanWorkbenchError("teaching_plan_draft_not_found", "教案草稿不存在或已被放弃。")
            if _is_expired(draft):
                raise TeachingPlanWorkbenchError(
                    "teaching_plan_draft_expired",
                    "教案草稿已过期，请重新创建草稿后再编辑。",
                    details={"expires_at": _text(draft.get("expires_at"))},
                )
            if draft.get("base_plan_revision_id") != current_plan_revision or (
                base_plan_revision_id and base_plan_revision_id != current_plan_revision
            ):
                raise TeachingPlanWorkbenchError(
                    "teaching_plan_base_conflict",
                    "正式教案已更新，当前草稿不能继续直接保存。",
                    details={"current_plan_revision_id": current_plan_revision},
                )
            snapshot = deepcopy(draft.get("snapshot") or {})
            permission = field_permission(path)
            # 结构操作先于只读兜底判定：目录真源拥有章节/小节的增删、排序与
            # 标题，教案命令不得绕过它。这里必须回目录修订，前端才能跳转。
            if redirect_reason := outline_redirect_reason(path):
                raise TeachingPlanWorkbenchError(
                    "redirect_to_outline_edit",
                    redirect_reason,
                    details={
                        "path": path,
                        "course_id": course_id,
                        # 教案侧看到的目录修订（course_document_revision，cdr_…）。
                        # 注意它与目录编辑器自己的 blueprint_revision_id（bp_…）
                        # 不是同一个标识：前端跳过去后应重新读 GET /blueprint
                        # 取当前蓝图修订，不要把这里的值当作蓝图修订回传，
                        # 否则会被 blueprint_base_conflict 挡下。
                        "outline_revision_id": document_revision,
                        "outline_editor": {
                            "endpoint": f"/api/courses/{course_id}/blueprint",
                            "revision_field": "current_blueprint_revision_id",
                        },
                    },
                )
            if permission["state"] == "readonly":
                raise TeachingPlanWorkbenchError(
                    "teaching_plan_readonly_field",
                    permission["reason"],
                    details={"path": path},
                )
            before = _read_path(snapshot, path)
            if expected_value_hash and _value_hash(before) != expected_value_hash:
                raise TeachingPlanWorkbenchError(
                    "teaching_plan_field_conflict",
                    "该字段已在草稿中变化，请重新读取后再保存。",
                    details={"path": path, "current_value": before, "current_value_hash": _value_hash(before)},
                )
            after = _write_path(snapshot, path, value)
            if before == after:
                return
            existing_operation = next(
                (
                    item for item in draft.get("operations") or []
                    if isinstance(item, dict) and item.get("path") == path
                ),
                None,
            )
            official_before = (
                deepcopy(existing_operation.get("before"))
                if isinstance(existing_operation, dict)
                else _read_path(_source_snapshot(working), path)
            )
            operation = {
                "operation_id": _new_id("tpo_"),
                "path": path,
                "before": official_before,
                "after": after,
                "source": "manual",
                "permission": field_permission(path)["state"],
                "updated_at": _now(),
            }
            operations = [
                item for item in draft.get("operations") or []
                if isinstance(item, dict) and item.get("path") != path
            ]
            if official_before != after:
                operations.append(operation)
            draft["snapshot"] = snapshot
            draft["operations"] = operations
            draft["changed_paths"] = [item.get("path") for item in operations]
            draft["validation"] = _validate(snapshot)
            draft["updated_at"] = _now()
            for change_set in state.get("change_sets") or []:
                if (
                    isinstance(change_set, dict)
                    and change_set.get("draft_id") == draft_id
                    and change_set.get("status") in {"ready", "blocked", "stale"}
                ):
                    change_set["status"] = "superseded"
                    change_set["superseded_at"] = _now()
            for candidate in state.get("ai_candidates") or []:
                if (
                    isinstance(candidate, dict)
                    and candidate.get("draft_id") == draft_id
                    and candidate.get("status") == "ready"
                ):
                    candidate["status"] = "stale"
                    candidate["stale_at"] = _now()

        await self.repository.apply_metadata_command(
            course_id,
            expected_document_revision=document_revision,
            operation={
                "command_id": f"teaching-plan-patch:{actor}:{idempotency_key}",
                "operation": "patch_teaching_plan_draft",
                "reason": f"编辑教案字段 {path}",
                "actor": actor,
            },
            mutation=mutation,
        )
        return self.view(course_id, actor=actor)

    async def _generate_ai_candidate(
        self,
        *,
        snapshot: dict[str, Any],
        paths: list[str],
        instruction: str,
    ) -> dict[str, Any]:
        if self.candidate_generator is not None:
            generated = self.candidate_generator(
                snapshot=deepcopy(snapshot),
                paths=list(paths),
                instruction=instruction,
            )
            if inspect.isawaitable(generated):
                generated = await generated
            if isinstance(generated, dict):
                return generated
            raise TeachingPlanWorkbenchError(
                "teaching_plan_ai_invalid_candidate",
                "AI 候选服务返回了无效结果。",
            )

        from course_service import get_course_service

        service = get_course_service()
        response = await service._call_llm(
            "请生成一份可审阅的结构化教案修改候选。",
            _candidate_prompt(snapshot, paths=paths, instruction=instruction),
            use_fast_model=True,
            retry_count=1,
            enable_thinking=False,
            raise_on_failure=False,
        )
        parsed = service._extract_json(str(response or ""))
        if not isinstance(parsed, dict):
            raise TeachingPlanWorkbenchError(
                "teaching_plan_ai_invalid_candidate",
                "AI 没有返回可解析的结构化教案候选。",
            )
        return parsed

    async def create_ai_candidate(
        self,
        course_id: str,
        *,
        actor: str,
        draft_id: str,
        paths: list[str],
        instruction: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_feature_enabled()
        raw = self.repository.load_raw(course_id)
        document_revision = _text(raw.get("course_document_revision"))
        state = _state(raw)
        draft = (state.get("drafts") or {}).get(actor)
        if not isinstance(draft, dict) or draft.get("draft_id") != draft_id:
            raise TeachingPlanWorkbenchError("teaching_plan_draft_not_found", "教案草稿不存在或已被放弃。")
        allowed = {
            item["path"]
            for item in _editable_fields(deepcopy(draft.get("snapshot") or {}))
            if item.get("state") != "readonly"
        }
        normalized_paths = list(dict.fromkeys(
            _text(path).strip("/") for path in paths if _text(path).strip("/")
        ))
        if not normalized_paths or any(path not in allowed for path in normalized_paths):
            raise TeachingPlanWorkbenchError(
                "teaching_plan_ai_invalid_target",
                "请只选择当前草稿中允许 AI 建议的教案字段。",
            )
        normalized_instruction = _text(instruction)
        if not normalized_instruction:
            raise TeachingPlanWorkbenchError("teaching_plan_ai_invalid_instruction", "请说明希望 AI 怎样优化教案。")
        base_snapshot = deepcopy(draft.get("snapshot") or {})
        response = await self._generate_ai_candidate(
            snapshot=base_snapshot,
            paths=normalized_paths,
            instruction=normalized_instruction,
        )
        operations = _normalize_ai_operations(
            base_snapshot,
            paths=normalized_paths,
            response=response,
        )
        candidate_snapshot = deepcopy(base_snapshot)
        for operation in operations:
            _write_path(candidate_snapshot, operation["path"], operation["after"])
        validation = _validate(candidate_snapshot)
        impact = _impact(operations, candidate_snapshot, course_data=raw)
        if not validation.get("passed") or impact.get("blocking"):
            raise TeachingPlanWorkbenchError(
                "teaching_plan_ai_quality_blocked",
                "AI 候选没有通过结构校验或影响分析。",
                details={"validation": validation, "impact_report": impact},
            )

        def mutation(working: dict[str, Any]) -> None:
            working_state = _state(working, create=True)
            current_draft = (working_state.get("drafts") or {}).get(actor)
            if not isinstance(current_draft, dict) or current_draft.get("draft_id") != draft_id:
                raise TeachingPlanWorkbenchError("teaching_plan_draft_not_found", "教案草稿不存在或已被放弃。")
            if current_draft.get("base_plan_revision_id") != draft.get("base_plan_revision_id") or (
                stable_hash(current_draft.get("snapshot") or {}, prefix="tpds_")
                != stable_hash(base_snapshot, prefix="tpds_")
            ):
                raise TeachingPlanWorkbenchError(
                    "teaching_plan_ai_stale",
                    "草稿已更新，请基于最新草稿重新生成 AI 候选。",
                )
            working_state["ai_candidates"].append({
                "schema_version": AI_CANDIDATE_SCHEMA,
                "candidate_id": _new_id("tpac_"),
                "course_id": course_id,
                "actor": actor,
                "draft_id": draft_id,
                "base_plan_revision_id": draft.get("base_plan_revision_id"),
                "base_draft_snapshot_hash": stable_hash(base_snapshot, prefix="tpds_"),
                "instruction": normalized_instruction,
                "rationale": _text(response.get("rationale")),
                "operations": operations,
                "validation": validation,
                "impact_report": impact,
                "status": "ready",
                "created_at": _now(),
            })

        await self.repository.apply_metadata_command(
            course_id,
            expected_document_revision=document_revision,
            operation={
                "command_id": f"teaching-plan-ai-candidate:{actor}:{idempotency_key}",
                "operation": "create_teaching_plan_ai_candidate",
                "reason": "生成可审阅的 AI 教案候选",
                "actor": actor,
            },
            mutation=mutation,
        )
        return self.view(course_id, actor=actor)

    async def accept_ai_candidate(
        self,
        course_id: str,
        *,
        actor: str,
        candidate_id: str,
        operation_ids: list[str],
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_feature_enabled()
        raw = self.repository.load_raw(course_id)
        document_revision = _text(raw.get("course_document_revision"))

        def mutation(working: dict[str, Any]) -> None:
            state = _state(working, create=True)
            candidate = next(
                (item for item in state.get("ai_candidates") or []
                 if isinstance(item, dict) and item.get("candidate_id") == candidate_id and item.get("actor") == actor),
                None,
            )
            if candidate is None:
                raise TeachingPlanWorkbenchError("teaching_plan_ai_candidate_not_found", "AI 教案候选不存在。")
            if candidate.get("status") != "ready":
                raise TeachingPlanWorkbenchError("teaching_plan_ai_candidate_not_ready", "该 AI 候选已失效或已处理。")
            draft = (state.get("drafts") or {}).get(actor)
            if not isinstance(draft, dict) or draft.get("draft_id") != candidate.get("draft_id"):
                raise TeachingPlanWorkbenchError("teaching_plan_ai_stale", "AI 候选对应的草稿已不存在。")
            if stable_hash(draft.get("snapshot") or {}, prefix="tpds_") != candidate.get("base_draft_snapshot_hash"):
                candidate["status"] = "stale"
                raise TeachingPlanWorkbenchError("teaching_plan_ai_stale", "草稿已更新，请重新生成 AI 候选。")
            requested = set(operation_ids or [])
            available = [item for item in candidate.get("operations") or [] if isinstance(item, dict)]
            selected = [item for item in available if not requested or item.get("operation_id") in requested]
            if not selected:
                raise TeachingPlanWorkbenchError("teaching_plan_ai_no_selection", "请至少选择一项 AI 建议。")
            snapshot = deepcopy(draft.get("snapshot") or {})
            official_snapshot = _source_snapshot(working)
            merged = [item for item in draft.get("operations") or [] if isinstance(item, dict)]
            for operation in selected:
                path = _text(operation.get("path"))
                before = _read_path(snapshot, path)
                if before != operation.get("before"):
                    candidate["status"] = "stale"
                    raise TeachingPlanWorkbenchError("teaching_plan_ai_stale", "草稿字段已变化，请重新生成 AI 候选。")
                after = _write_path(snapshot, path, operation.get("after"))
                existing_operation = next(
                    (item for item in merged if item.get("path") == path),
                    None,
                )
                official_before = (
                    deepcopy(existing_operation.get("before"))
                    if isinstance(existing_operation, dict)
                    else _read_path(official_snapshot, path)
                )
                merged = [item for item in merged if item.get("path") != path]
                if official_before != after:
                    merged.append({
                        **operation,
                        "before": official_before,
                        "after": after,
                        "accepted_at": _now(),
                    })
            draft["snapshot"] = snapshot
            draft["operations"] = merged
            draft["changed_paths"] = [item.get("path") for item in merged]
            draft["validation"] = _validate(snapshot)
            draft["updated_at"] = _now()
            candidate["status"] = "accepted"
            candidate["accepted_operation_ids"] = [item.get("operation_id") for item in selected]
            candidate["accepted_at"] = _now()
            for change_set in state.get("change_sets") or []:
                if (
                    isinstance(change_set, dict)
                    and change_set.get("draft_id") == draft.get("draft_id")
                    and change_set.get("status") in {"ready", "blocked", "stale"}
                ):
                    change_set["status"] = "superseded"
                    change_set["superseded_at"] = _now()

        await self.repository.apply_metadata_command(
            course_id,
            expected_document_revision=document_revision,
            operation={
                "command_id": f"teaching-plan-ai-accept:{actor}:{idempotency_key}",
                "operation": "accept_teaching_plan_ai_candidate",
                "reason": "教师接受 AI 教案候选",
                "actor": actor,
            },
            mutation=mutation,
        )
        return self.view(course_id, actor=actor)

    async def reject_ai_candidate(
        self,
        course_id: str,
        *,
        actor: str,
        candidate_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_feature_enabled()
        raw = self.repository.load_raw(course_id)
        document_revision = _text(raw.get("course_document_revision"))

        def mutation(working: dict[str, Any]) -> None:
            candidate = next(
                (item for item in _state(working, create=True).get("ai_candidates") or []
                 if isinstance(item, dict) and item.get("candidate_id") == candidate_id and item.get("actor") == actor),
                None,
            )
            if candidate is None:
                raise TeachingPlanWorkbenchError("teaching_plan_ai_candidate_not_found", "AI 教案候选不存在。")
            if candidate.get("status") == "accepted":
                raise TeachingPlanWorkbenchError("teaching_plan_ai_candidate_accepted", "已接受的 AI 候选不能直接拒绝。")
            candidate["status"] = "rejected"
            candidate["rejected_at"] = _now()

        await self.repository.apply_metadata_command(
            course_id,
            expected_document_revision=document_revision,
            operation={
                "command_id": f"teaching-plan-ai-reject:{actor}:{idempotency_key}",
                "operation": "reject_teaching_plan_ai_candidate",
                "reason": "教师拒绝 AI 教案候选",
                "actor": actor,
            },
            mutation=mutation,
        )
        return self.view(course_id, actor=actor)

    async def discard_draft(
        self,
        course_id: str,
        *,
        actor: str,
        draft_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_feature_enabled()
        raw = self.repository.load_raw(course_id)
        document_revision = _text(raw.get("course_document_revision"))

        def mutation(working: dict[str, Any]) -> None:
            state = _state(working, create=True)
            drafts = state.get("drafts") or {}
            draft = drafts.get(actor)
            if not isinstance(draft, dict) or draft.get("draft_id") != draft_id:
                raise TeachingPlanWorkbenchError(
                    "teaching_plan_draft_not_found",
                    "教案草稿不存在或已经放弃。",
                )
            drafts.pop(actor, None)
            for change_set in state.get("change_sets") or []:
                if (
                    isinstance(change_set, dict)
                    and change_set.get("draft_id") == draft_id
                    and change_set.get("status") in {"draft", "ready", "blocked", "stale", "superseded"}
                ):
                    change_set["status"] = "rejected"
                    change_set["rejected_at"] = _now()
                    change_set["rejection_reason"] = "draft_discarded"

        await self.repository.apply_metadata_command(
            course_id,
            expected_document_revision=document_revision,
            operation={
                "command_id": f"teaching-plan-discard:{actor}:{idempotency_key}",
                "operation": "discard_teaching_plan_draft",
                "reason": "教师放弃教案草稿",
                "actor": actor,
            },
            mutation=mutation,
        )
        return self.view(course_id, actor=actor)

    def review_draft(self, course_id: str, *, actor: str, draft_id: str) -> dict[str, Any]:
        raw = self.repository.load_raw(course_id)
        draft = (_state(raw).get("drafts") or {}).get(actor)
        if not isinstance(draft, dict) or draft.get("draft_id") != draft_id:
            raise TeachingPlanWorkbenchError("teaching_plan_draft_not_found", "教案草稿不存在或已被放弃。")
        current = _source_snapshot(raw)
        current_plan_revision = _current_plan_revision(raw)
        snapshot = deepcopy(draft.get("snapshot") or {})
        operations = deepcopy(draft.get("operations") or [])
        validation = _validate(snapshot)
        status = _draft_status(draft, current_plan_revision)
        return {
            "draft_id": draft_id,
            "base_plan_revision_id": draft.get("base_plan_revision_id"),
            "current_plan_revision_id": current_plan_revision,
            "status": status,
            "expires_at": _text(draft.get("expires_at")) or None,
            "diff": _diff_between(current, snapshot, operations=operations),
            "impact_report": _impact(operations, snapshot, course_data=raw),
            "validation": validation,
        }

    async def create_change_set(
        self,
        course_id: str,
        *,
        actor: str,
        draft_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_feature_enabled()
        raw = self.repository.load_raw(course_id)
        document_revision = _text(raw.get("course_document_revision"))
        current = _source_snapshot(raw)
        current_plan_revision = _current_plan_revision(raw)

        def mutation(working: dict[str, Any]) -> None:
            state = _state(working, create=True)
            draft = (state.get("drafts") or {}).get(actor)
            if not isinstance(draft, dict) or draft.get("draft_id") != draft_id:
                raise TeachingPlanWorkbenchError("teaching_plan_draft_not_found", "教案草稿不存在或已被放弃。")
            status = _draft_status(draft, current_plan_revision)
            if status == "expired":
                raise TeachingPlanWorkbenchError(
                    "teaching_plan_draft_expired",
                    "教案草稿已过期，请重新创建草稿后再审阅。",
                    details={"expires_at": _text(draft.get("expires_at"))},
                )
            if status == "stale":
                raise TeachingPlanWorkbenchError(
                    "teaching_plan_base_conflict",
                    "正式教案已更新，请基于当前修订重新编辑后再审阅。",
                    details={
                        "current_plan_revision_id": current_plan_revision,
                        "draft_base_plan_revision_id": _text(draft.get("base_plan_revision_id")),
                    },
                )
            existing = next(
                (
                    item for item in state.get("change_sets") or []
                    if isinstance(item, dict)
                    and item.get("draft_id") == draft_id
                    and item.get("status") in {"draft", "ready", "blocked"}
                ),
                None,
            )
            if existing is not None:
                return
            snapshot = deepcopy(draft.get("snapshot") or {})
            operations = deepcopy(draft.get("operations") or [])
            if not operations:
                raise TeachingPlanWorkbenchError(
                    "teaching_plan_no_changes",
                    "草稿没有修改，不能创建正式变更集。",
                )
            validation = _validate(snapshot)
            impact = _impact(operations, snapshot, course_data=working)
            status = "blocked" if not validation.get("passed") or impact.get("blocking") else "ready"
            state["change_sets"].append({
                "schema_version": CHANGE_SET_SCHEMA,
                "change_set_id": _new_id("tpc_"),
                "course_id": course_id,
                "actor": actor,
                "draft_id": draft_id,
                "base_plan_revision_id": draft.get("base_plan_revision_id"),
                "base_course_document_revision": draft.get("base_course_document_revision"),
                "operations": operations,
                "diff": _diff_between(current, snapshot, operations=operations),
                "impact_report": impact,
                "validation": validation,
                "status": status,
                "snapshot": snapshot,
                "created_at": _now(),
            })

        await self.repository.apply_metadata_command(
            course_id,
            expected_document_revision=document_revision,
            operation={
                "command_id": f"teaching-plan-change-set:{actor}:{idempotency_key}",
                "operation": "review_teaching_plan_change_set",
                "reason": "生成教案差异与影响审阅",
                "actor": actor,
            },
            mutation=mutation,
        )
        return self.view(course_id, actor=actor)

    async def apply_change_set(
        self,
        course_id: str,
        *,
        actor: str,
        change_set_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_feature_enabled()
        raw = self.repository.load_raw(course_id)
        document_revision = _text(raw.get("course_document_revision"))
        current_plan_revision = _current_plan_revision(raw)

        def mutation(working: dict[str, Any]) -> None:
            state = _state(working, create=True)
            change_set = next(
                (
                    item for item in state.get("change_sets") or []
                    if isinstance(item, dict) and item.get("change_set_id") == change_set_id
                ),
                None,
            )
            if change_set is None:
                raise TeachingPlanWorkbenchError("teaching_plan_change_set_not_found", "教案变更集不存在。")
            if change_set.get("status") == "applied":
                return
            if change_set.get("status") != "ready":
                raise TeachingPlanWorkbenchError(
                    "teaching_plan_change_set_not_ready",
                    "该变更集尚未通过结构校验或已经失效。",
                    details={"status": change_set.get("status")},
                )
            if not change_set.get("operations"):
                raise TeachingPlanWorkbenchError(
                    "teaching_plan_no_changes",
                    "空变更集不能应用为新的正式修订。",
                )
            if change_set.get("base_plan_revision_id") != current_plan_revision:
                change_set["status"] = "stale"
                raise TeachingPlanWorkbenchError(
                    "teaching_plan_base_conflict",
                    "正式教案已更新，请重新生成差异与影响审阅。",
                    details={"current_plan_revision_id": current_plan_revision},
                )
            if change_set.get("base_course_document_revision") != document_revision:
                change_set["status"] = "stale"
                raise TeachingPlanWorkbenchError(
                    "course_document_base_conflict",
                    "课程正文已更新，请重新生成差异与影响审阅。",
                    details={"current_course_document_revision": document_revision},
                )
            snapshot = deepcopy(change_set.get("snapshot") or {})
            validation = _validate(snapshot)
            impact = _impact(
                change_set.get("operations") or [], snapshot, course_data=working,
            )
            if not validation.get("passed") or impact.get("blocking"):
                change_set["status"] = "blocked"
                change_set["validation"] = validation
                change_set["impact_report"] = impact
                raise TeachingPlanWorkbenchError(
                    "teaching_plan_quality_blocked",
                    "教案结构或影响分析未通过，不能应用正式修订。",
                    details={"validation": validation, "impact_report": impact},
                )

            source_plan = deepcopy(snapshot.get("course_teaching_plan") or {})
            source_plan["revision_id"] = _source_revision(snapshot)
            snapshot["course_teaching_plan"] = source_plan
            working["course_plan"] = deepcopy(snapshot.get("course_plan") or {})
            working["generation_request"] = deepcopy(snapshot.get("generation_request") or {})
            working["subject_pedagogy_profile"] = deepcopy(snapshot.get("subject_pedagogy_profile") or {})
            working["course_teaching_plan"] = source_plan
            if isinstance(working.get("course_plan"), dict):
                working["course_plan"] = apply_course_teaching_plan(
                    working["course_plan"], source_plan,
                )
                _realign_plan_section_ids(working["course_plan"], source_plan)
            stage = (working.setdefault("generation_stage_artifacts", {})
                     .setdefault("course_teaching_plan", {}))
            stage["revision_id"] = source_plan["revision_id"]
            stage.setdefault("status", "completed")
            revision_number = max(
                [int(item.get("revision_number") or 0) for item in state.get("revisions") or []] or [0],
            ) + 1
            state["revisions"].append({
                "schema_version": REVISION_SCHEMA,
                "revision_id": source_plan["revision_id"],
                "revision_number": revision_number,
                "parent_revision_id": current_plan_revision,
                "source_revision_vector": revision_vector_for_course(
                    CourseDocument.model_validate(working["course_document"]), working,
                ).model_dump(mode="json"),
                "snapshot": snapshot,
                "change_set_id": change_set_id,
                "quality_report": validation,
                "created_by": actor,
                "created_at": _now(),
            })
            change_set["status"] = "applied"
            change_set["applied_revision_id"] = source_plan["revision_id"]
            change_set["applied_at"] = _now()
            change_set["validation"] = validation
            change_set["impact_report"] = impact
            state["downstream"] = build_downstream_state(
                impact,
                plan_revision_id=source_plan["revision_id"],
                course_data=working,
                registry=self.representation_registry(course_id),
                previous=state.get("downstream"),
            )
            drafts = state.get("drafts") or {}
            if (draft := drafts.get(actor)) and draft.get("draft_id") == change_set.get("draft_id"):
                drafts.pop(actor, None)

        receipt = await self.repository.apply_metadata_command(
            course_id,
            expected_document_revision=document_revision,
            operation={
                "command_id": f"teaching-plan-apply:{actor}:{idempotency_key}",
                "operation": "apply_teaching_plan_change_set",
                "reason": "教师确认应用教案变更",
                "actor": actor,
            },
            mutation=mutation,
        )
        view = self.view(course_id, actor=actor)
        return {"receipt": receipt, "workbench": view}

    async def reject_change_set(
        self,
        course_id: str,
        *,
        actor: str,
        change_set_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_feature_enabled()
        raw = self.repository.load_raw(course_id)
        document_revision = _text(raw.get("course_document_revision"))

        def mutation(working: dict[str, Any]) -> None:
            state = _state(working, create=True)
            change_set = next(
                (
                    item for item in state.get("change_sets") or []
                    if isinstance(item, dict) and item.get("change_set_id") == change_set_id
                ),
                None,
            )
            if change_set is None:
                raise TeachingPlanWorkbenchError("teaching_plan_change_set_not_found", "教案变更集不存在。")
            if change_set.get("status") == "applied":
                raise TeachingPlanWorkbenchError("teaching_plan_change_set_applied", "已应用的变更集请通过历史修订恢复。")
            change_set["status"] = "rejected"
            change_set["rejected_at"] = _now()

        await self.repository.apply_metadata_command(
            course_id,
            expected_document_revision=document_revision,
            operation={
                "command_id": f"teaching-plan-reject:{actor}:{idempotency_key}",
                "operation": "reject_teaching_plan_change_set",
                "reason": "教师放弃教案变更",
                "actor": actor,
            },
            mutation=mutation,
        )
        return self.view(course_id, actor=actor)

    async def restore_revision(
        self,
        course_id: str,
        *,
        actor: str,
        revision_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_feature_enabled()
        raw = self.repository.load_raw(course_id)
        document_revision = _text(raw.get("course_document_revision"))
        current_plan_revision = _current_plan_revision(raw)

        def mutation(working: dict[str, Any]) -> None:
            state = _state(working, create=True)
            if state.get("drafts", {}).get(actor):
                raise TeachingPlanWorkbenchError(
                    "teaching_plan_draft_active",
                    "请先审阅或放弃当前草稿后，再恢复历史修订。",
                )
            target = next(
                (
                    item for item in state.get("revisions") or []
                    if isinstance(item, dict) and item.get("revision_id") == revision_id
                ),
                None,
            )
            if target is None:
                raise TeachingPlanWorkbenchError("teaching_plan_revision_not_found", "历史教案修订不存在。")
            snapshot = deepcopy(target.get("snapshot") or {})
            operations = _diff_between(_source_snapshot(working), snapshot)["operations"]
            validation = _validate(snapshot)
            impact = _impact(operations, snapshot, course_data=working)
            if not validation.get("passed") or impact.get("blocking"):
                raise TeachingPlanWorkbenchError("teaching_plan_quality_blocked", "该历史版本不能通过当前质量门。")
            source_plan = deepcopy(snapshot.get("course_teaching_plan") or {})
            source_plan["revision_id"] = stable_hash(
                {
                    "content_revision": _source_revision(snapshot),
                    "parent_revision_id": current_plan_revision,
                    "restored_from_revision_id": revision_id,
                },
                prefix="tpr_",
            )
            snapshot["course_teaching_plan"] = source_plan
            working["course_plan"] = apply_course_teaching_plan(
                deepcopy(snapshot.get("course_plan") or {}), source_plan,
            )
            _realign_plan_section_ids(working["course_plan"], source_plan)
            working["generation_request"] = deepcopy(snapshot.get("generation_request") or {})
            working["subject_pedagogy_profile"] = deepcopy(snapshot.get("subject_pedagogy_profile") or {})
            working["course_teaching_plan"] = source_plan
            stage = (working.setdefault("generation_stage_artifacts", {})
                     .setdefault("course_teaching_plan", {}))
            stage["revision_id"] = source_plan["revision_id"]
            stage.setdefault("status", "completed")
            revision_number = max(
                [int(item.get("revision_number") or 0) for item in state.get("revisions") or []] or [0],
            ) + 1
            state["revisions"].append({
                "schema_version": REVISION_SCHEMA,
                "revision_id": source_plan["revision_id"],
                "revision_number": revision_number,
                "parent_revision_id": current_plan_revision,
                "source_revision_vector": revision_vector_for_course(
                    CourseDocument.model_validate(working["course_document"]), working,
                ).model_dump(mode="json"),
                "snapshot": snapshot,
                "change_set_id": "",
                "restored_from_revision_id": revision_id,
                "quality_report": validation,
                "created_by": actor,
                "created_at": _now(),
            })
            state["downstream"] = build_downstream_state(
                impact,
                plan_revision_id=source_plan["revision_id"],
                course_data=working,
                registry=self.representation_registry(course_id),
                previous=state.get("downstream"),
            )

        receipt = await self.repository.apply_metadata_command(
            course_id,
            expected_document_revision=document_revision,
            operation={
                "command_id": f"teaching-plan-restore:{actor}:{idempotency_key}",
                "operation": "restore_teaching_plan_revision",
                "reason": f"恢复历史教案修订 {revision_id}",
                "actor": actor,
            },
            mutation=mutation,
        )
        return {"receipt": receipt, "workbench": self.view(course_id, actor=actor)}

    async def rebuild_downstream(
        self,
        course_id: str,
        *,
        actor: str,
        idempotency_key: str,
        only_types: list[str] | None = None,
        only_ids: list[str] | None = None,
        candidate_only: bool = True,
    ) -> dict[str, Any]:
        """按当前下游状态执行定向重建，并把逐对象回执写回课程。

        这是 6.2–6.6 的执行入口。真正的重建仍由既有管线完成——本方法只负责
        「按影响报告挑对象、调用对应管线、把结果折回下游状态」。教案侧与
        知识侧共用 `downstream_rebuild.execute_rebuild`，不建平行重建机制。

        默认 `candidate_only=True`：生成重建候选等教师确认，而不是直接覆盖
        正式产物。教师确认这一步归既有的候选流程管。
        """
        self._require_feature_enabled()
        raw = self.repository.load_raw(course_id)
        document_revision = _text(raw.get("course_document_revision"))
        state = _state(raw)
        downstream = state.get("downstream") or {}
        if not (downstream.get("items") or []):
            raise TeachingPlanWorkbenchError(
                "teaching_plan_no_downstream_work",
                "当前没有待重建的下游对象。",
            )

        runners = self._rebuild_runners(
            course_id, raw, actor=actor,
            source_revision=_text(downstream.get("source_plan_revision_id")),
        )
        result = execute_rebuild(
            downstream,
            runners=runners,
            only_types=only_types,
            only_ids=only_ids,
            candidate_only=candidate_only,
        )

        def mutation(working: dict[str, Any]) -> None:
            working_state = _state(working, create=True)
            working_state["downstream"] = result["downstream"]
            working_state["rebuild_receipts"] = result["receipts"]

        await self.repository.apply_metadata_command(
            course_id,
            expected_document_revision=document_revision,
            operation={
                "command_id": f"teaching-plan-rebuild:{actor}:{idempotency_key}",
                "operation": "rebuild_teaching_plan_downstream",
                "actor": actor,
                "summary": rebuild_summary(result),
            },
            mutation=mutation,
        )
        return {
            "receipts": result["receipts"],
            "counts": result["counts"],
            "summary": rebuild_summary(result),
            "workbench": self.view(course_id, actor=actor),
        }

    def _rebuild_runners(
        self,
        course_id: str,
        raw: dict[str, Any],
        *,
        actor: str = "",
        source_revision: str = "",
    ) -> dict[str, Any]:
        """把既有重建管线包成执行器认识的形状。

        刻意不在这里实现任何重建逻辑：
        - 表达走 representation_compiler 的 shadow-then-publish
          （失败时旧产物留在 stale 状态继续可读）；
        - 正文走与知识侧**同一个** `build_content_runner`，产出候选即止
          （`BlockRegenerationService` 只在 apply 时才写正文）。两侧共用一份
          实现，否则同一个正文块因教案改动和因知识改动重建会走出两套失败
          语义、两份「最后可用产物」记录；
        - 练习登记为按小节定向的出题作业，由既有异步管线接手；
        - 知识目前没有可直接调用的定向重建入口，明确返回失败原因，不假装成功。
        """
        def representation(entry: dict[str, Any]) -> dict[str, Any]:
            if self.representation_repository is None:
                return {"status": "failed", "error": "表达注册表不可用"}
            try:
                from course_document import CourseDocument
                from representation_compiler import rebuild_core_representations_safely

                document = CourseDocument.model_validate(raw["course_document"])
                outcome = rebuild_core_representations_safely(
                    document, raw, self.representation_repository,
                )
                revision = _text((outcome or {}).get("registry_revision"))
                return {"status": "succeeded", "revision": revision}
            except Exception as error:  # noqa: BLE001
                return {"status": "failed", "error": str(error)}

        def practice(entry: dict[str, Any]) -> dict[str, Any]:
            """练习重建：登记按小节定向的重建作业，不在这里同步出题。

            出题是 10 阶段的异步作业（有自己的作业仓库与断点恢复），
            在教案的应用请求里同步跑会让教师等几分钟、且失败无法恢复。
            所以这里只把「哪一节要重建」登记成作业，回执记为候选，
            由既有的出题管线接手——这与 6.2「定向重建候选」的语义一致。
            """
            section_id = _text(entry.get("section_id")) or _text(entry.get("id"))
            if not section_id:
                return {"status": "failed", "error": "无法确定练习所属小节"}
            try:
                from question_bank_jobs import question_bank_rebuild_job_repository

                job, created = question_bank_rebuild_job_repository.create_job(
                    course_id,
                    request_id=f"teaching-plan-rebuild:{source_revision}:{section_id}",
                    scope="nodes",
                    node_ids=[section_id],
                    mode="incremental",
                    actor_id=actor,
                )
                return {
                    "status": "candidate_ready",
                    "revision": _text(job.get("job_id")),
                }
            except Exception as error:  # noqa: BLE001
                return {"status": "failed", "error": str(error)}

        def unsupported(entry: dict[str, Any]) -> dict[str, Any]:
            return {
                "status": "failed",
                "error": f"{entry['type']} 目前没有可用于定向重建的管线入口",
            }

        from course_downstream_rebuild import (
            PLAN_CONTENT_INSTRUCTION,
            build_content_runner,
        )
        from block_regeneration import block_regeneration_candidate_repository

        course_content = build_content_runner(
            raw,
            course_repository=self.repository,
            block_repository=block_regeneration_candidate_repository,
            actor=actor or "system",
            request_id=source_revision,
            request_prefix="teaching-plan-rebuild",
            instruction=PLAN_CONTENT_INSTRUCTION,
        )

        return {
            "representation": representation,
            "course_content": course_content,
            "practice": practice,
            "knowledge": unsupported,
        }

    def revision_diff(self, course_id: str, *, left: str, right: str) -> dict[str, Any]:
        raw = self.repository.load_raw(course_id)
        revisions = _state(raw).get("revisions") or []
        by_id = {item.get("revision_id"): item for item in revisions if isinstance(item, dict)}
        if left not in by_id or right not in by_id:
            raise TeachingPlanWorkbenchError("teaching_plan_revision_not_found", "指定的历史教案修订不存在。")
        return {
            "left_revision_id": left,
            "right_revision_id": right,
            "diff": _diff_between(by_id[left].get("snapshot") or {}, by_id[right].get("snapshot") or {}),
        }


__all__ = [
    "TeachingPlanWorkbenchError",
    "TeachingPlanWorkbenchService",
    "field_permission",
]
