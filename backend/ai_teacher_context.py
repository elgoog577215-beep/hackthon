"""Intent-scoped context assembly for the AI teacher."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from content_blocks import project_course_content_blocks
from course_knowledge_base import compile_course_knowledge_base, knowledge_binding_for_section
from course_knowledge_map import compile_course_knowledge_map, knowledge_ids_for_section
from learner_model import is_model_item_current
from learning_runtime import build_learning_runtime
from practice_attempts import practice_attempt_repository
from subject_knowledge import (
    knowledge_index,
    knowledge_library_slice,
    resolve_subject_library,
)

MAX_SOURCES = 5
MAX_EVIDENCE = 5
MAX_RECENT_MESSAGES = 8


def build_ai_teacher_context(
    course_data: dict[str, Any],
    *,
    user_id: str,
    question: str,
    node_id: str | None = None,
    selection: str = "",
    entrypoint: str = "global",
    context_ref: dict[str, Any] | None = None,
    task_ref: dict[str, Any] | None = None,
    conversation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one immutable package without copying domain state into AI storage."""
    projected_course = project_course_content_blocks(course_data)
    runtime = build_learning_runtime(projected_course, user_id=user_id, node_id=node_id)
    intent = _request_intent(question, entrypoint)
    runtime_context = runtime.get("context") or {}
    effective_node_id = str(
        node_id
        or (context_ref or {}).get("node_id")
        or runtime_context.get("node_id")
        or ""
    )
    scene = _scene(projected_course, runtime, effective_node_id, context_ref or {})
    knowledge_context = _knowledge_context(projected_course, effective_node_id)
    sources = _select_sources(
        projected_course,
        node_id=effective_node_id,
        question=question,
        selection=selection,
        context_ref=context_ref or {},
    )
    effective_task_ref = deepcopy(task_ref or runtime.get("active_task") or {})
    task = _task_context(
        user_id=user_id,
        course_id=str(projected_course.get("course_id") or ""),
        task_ref=effective_task_ref,
        entrypoint=entrypoint,
    )
    learner_model = _learner_model_context(
        runtime.get("learner_model") or {},
        intent=intent,
        node_id=effective_node_id,
    )
    evidence = _learner_evidence(learner_model, intent=intent)
    recent_messages = []
    for message in (conversation or {}).get("messages", [])[-MAX_RECENT_MESSAGES:]:
        recent_messages.append({
            "role": str(message.get("role") or "user"),
            "content": _clip(str(message.get("content") or ""), 2500),
            "message_id": str(message.get("message_id") or ""),
        })

    return {
        "schema_version": "ai_context_package_v3",
        "request": {
            "question": _clip(question, 5000),
            "selection": _clip(selection, 10000),
            "entrypoint": entrypoint,
            "intent": intent,
        },
        "scene": scene,
        "runtime": {
            "runtime_revision_id": runtime.get("runtime_revision_id"),
            "revision_vector": runtime.get("revision_vector") or {},
            "context": runtime_context,
            "active_task": runtime.get("active_task"),
            "primary_action": (runtime.get("continuation") or {}).get("primary_action"),
            "progress_summary": _progress_summary(runtime.get("progress") or {}, effective_node_id),
            "records_summary": runtime.get("records") or {},
            "practice_summary": runtime.get("practice") or {},
            "diagnostic_summary": runtime.get("diagnostic") or {},
            "learner_model_revision_id": (runtime.get("learner_model") or {}).get("model_revision_id"),
        },
        "learner_model": learner_model,
        "knowledge_context": knowledge_context,
        "task": task,
        "sources": sources,
        "learner_evidence": evidence,
        "conversation": {
            "conversation_id": str((conversation or {}).get("conversation_id") or ""),
            "recent_messages": recent_messages,
        },
        "permissions": {
            "answer": True,
            "explain_runtime_action": True,
            "allowed_proposals": [
                "create_note",
                "create_issue",
                "create_review_task",
                "create_bookmark",
                "open_runtime_action",
            ],
            "forbidden_actions": [
                "modify_mastery",
                "modify_learner_profile",
                "confirm_diagnostic",
                "submit_student_answer",
                "overwrite_course_content",
            ],
        },
    }


def format_ai_teacher_context_prompt(package: dict[str, Any]) -> str:
    """Render a bounded prompt while preserving source and inference boundaries."""
    request = package.get("request") or {}
    scene = package.get("scene") or {}
    runtime = package.get("runtime") or {}
    learner_model = package.get("learner_model") or {}
    knowledge_context = package.get("knowledge_context") or {}
    task = package.get("task") or {}
    sources = package.get("sources") or []
    evidence = package.get("learner_evidence") or []
    conversation = package.get("conversation") or {}
    permissions = package.get("permissions") or {}

    source_lines = [
        f"- [{item.get('source_id')}] {item.get('title') or '课程片段'}：{item.get('content')}"
        for item in sources
    ] or ["- 无可用课程片段。"]
    evidence_lines = [
        f"- {item.get('type')}（{item.get('status')}）：{item.get('summary')}"
        for item in evidence
    ] or ["- 无与本次请求直接相关的长期证据。"]
    history_lines = [
        f"- {item.get('role')}：{item.get('content')}"
        for item in (conversation.get("recent_messages") or [])
    ] or ["- 新会话。"]

    return f"""你是灵知课程中的 AI 老师。你负责回答、解释和提出可确认动作，但不拥有学习状态，也不能修改正式课程、掌握结论、画像、诊断结论或替学生提交答案。

## 当前请求
- 入口：{request.get('entrypoint')}
- 意图：{request.get('intent')}
- 问题：{request.get('question')}
- 选区：{request.get('selection') or '无'}

## 版本化学习现场
{json.dumps(scene, ensure_ascii=False, indent=2)}

## LearningRuntime 摘要
{json.dumps(runtime, ensure_ascii=False, indent=2)}

## 本次所需学习者模型
{json.dumps(learner_model, ensure_ascii=False, indent=2)}

## 当前统一知识库切片
{json.dumps(knowledge_context, ensure_ascii=False, indent=2)}

## 正式任务与披露边界
{json.dumps(task, ensure_ascii=False, indent=2)}

## 本次相关课程来源
{chr(10).join(source_lines)}

## 本次相关学习证据
{chr(10).join(evidence_lines)}

## 最近对话
{chr(10).join(history_lines)}

## 权限
{json.dumps(permissions, ensure_ascii=False, indent=2)}

## 回答要求
1. 直接回答当前问题，不强制添加无关的后续问题。
2. 课程事实优先使用上面的当前版本来源；没有来源时明确说明是在做通用解释。
3. 区分事实、用户陈述和推断，不把提问次数、一次错误或会话措辞写成稳定薄弱点。
4. 当前正式任务未允许完整答案时，只能提供方向、关键步骤或允许的量规，不得泄露标准答案。
5. 如果用户询问下一步，只解释 LearningRuntime 的 primary_action，不创建竞争动作。
6. 回答正文中不伪造已经执行的系统动作。写动作由独立 ActionProposal 协议处理。
7. 当前课程知识库是本课程知识身份、能力、易错与掌握标准的统一坐标；只允许使用已通过质量门的条目。回答仍须结合当前正文、任务和学习证据，不得忽略真实问题或伪造知识 ID。
8. 当入口为 block 时，回答到当前解释、例子、简化或问题本身为止；不得主动提出下一步、出题、保存或课程改写，也不要在结尾添加“如果你愿意”“需要我可以”等邀请。"""


def context_public_summary(package: dict[str, Any]) -> dict[str, Any]:
    """Return user-visible provenance without leaking prompt or private evidence."""
    scene = package.get("scene") or {}
    return {
        "schema_version": package.get("schema_version"),
        "runtime_revision_id": (package.get("runtime") or {}).get("runtime_revision_id"),
        "learner_model_revision_id": (package.get("learner_model") or {}).get("model_revision_id"),
        "data_sufficiency": deepcopy((package.get("learner_model") or {}).get("data_sufficiency") or {}),
        "scene": scene,
        "knowledge": {
            "knowledge_library_id": (package.get("knowledge_context") or {}).get("knowledge_library_id"),
            "knowledge_library_version": (package.get("knowledge_context") or {}).get("knowledge_library_version"),
            "course_map_revision_id": (package.get("knowledge_context") or {}).get("course_map_revision_id"),
            "knowledge_ids": [
                item.get("knowledge_id")
                for item in (package.get("knowledge_context") or {}).get("knowledge_nodes") or []
            ],
        },
        "sources": [
            {
                "source_id": item.get("source_id"),
                "type": item.get("type"),
                "title": item.get("title"),
                "node_id": item.get("node_id"),
                "block_revision_id": item.get("block_revision_id"),
            }
            for item in package.get("sources") or []
        ],
        "evidence_types": sorted({str(item.get("type") or "") for item in package.get("learner_evidence") or [] if item.get("type")}),
        "answer_disclosure": (package.get("task") or {}).get("answer_disclosure"),
    }


def _scene(
    course: dict[str, Any],
    runtime: dict[str, Any],
    node_id: str,
    supplied: dict[str, Any],
) -> dict[str, Any]:
    runtime_context = runtime.get("context") or {}
    node = _find_node(course.get("nodes") or [], node_id)
    anchor = supplied.get("content_anchor") if isinstance(supplied.get("content_anchor"), dict) else {}
    return {
        "course_id": str(course.get("course_id") or ""),
        "course_version_id": str(course.get("current_course_version_id") or runtime_context.get("course_version_id") or ""),
        "chapter_id": str(runtime_context.get("chapter_id") or supplied.get("chapter_id") or ""),
        "node_id": node_id,
        "node_name": str((node or {}).get("node_name") or supplied.get("node_name") or ""),
        "objective_id": str(runtime_context.get("objective_id") or supplied.get("objective_id") or ""),
        "objective_revision_id": str(runtime_context.get("objective_revision_id") or supplied.get("objective_revision_id") or ""),
        "content_anchor": deepcopy(anchor),
    }


def _knowledge_context(course: dict[str, Any], node_id: str) -> dict[str, Any]:
    knowledge_base = course.get("course_knowledge_base") or compile_course_knowledge_base(course)
    if knowledge_base.get("lifecycle_status") == "active":
        section_binding = knowledge_binding_for_section(knowledge_base, node_id)
        selected_ids = set(section_binding["course_knowledge_refs"])
        relations = [
            deepcopy(item)
            for item in knowledge_base.get("relations") or []
            if item.get("source_knowledge_id") in selected_ids
            or item.get("target_knowledge_id") in selected_ids
        ][:16]
        context_ids = set(selected_ids)
        for relation in relations:
            context_ids.add(str(relation.get("source_knowledge_id") or ""))
            context_ids.add(str(relation.get("target_knowledge_id") or ""))
        points = {
            str(item.get("knowledge_id") or ""): item
            for item in knowledge_base.get("knowledge_points") or []
        }
        nodes = [{
            "knowledge_id": point_id,
            "name": points[point_id].get("name"),
            "node_type": "knowledge_point",
            "statement": points[point_id].get("statement"),
            "conditions": deepcopy(points[point_id].get("conditions") or []),
            "boundaries": deepcopy(points[point_id].get("boundaries") or []),
            "is_current_section": point_id in selected_ids,
        } for point_id in list(context_ids)[:16] if point_id in points]
        skill_units = [
            deepcopy(item) for item in knowledge_base.get("skill_units") or []
            if item.get("primary_knowledge_id") in context_ids
        ][:12]
        misconceptions = [
            deepcopy(item) for item in knowledge_base.get("misconceptions") or []
            if item.get("primary_knowledge_id") in context_ids
        ][:8]
        mastery_criteria = [
            deepcopy(item) for item in knowledge_base.get("mastery_criteria") or []
            if set(item.get("knowledge_ids") or []) & context_ids
        ][:8]
        return {
            "schema_version": "ai_knowledge_context_v3",
            "knowledge_library_id": knowledge_base.get("knowledge_base_id"),
            "knowledge_library_version": knowledge_base.get("revision_id"),
            "knowledge_library_revision_id": knowledge_base.get("revision_id"),
            "course_map_revision_id": (course.get("course_knowledge_map") or {}).get("revision_id"),
            "node_id": node_id,
            "knowledge_nodes": nodes,
            "relations": relations,
            "skill_units": skill_units,
            "mistake_points": misconceptions,
            "mastery_criteria": mastery_criteria,
            "improvement_points": [],
            "mapping_status": knowledge_base.get("lifecycle_status", "degraded"),
            "usage_policy": {
                "role": "course_runtime_truth",
                "identity_scope": "current_course_only",
                "may_invent_formal_ids": False,
                "reference_catalog_required": False,
            },
        }

    subject_library = resolve_subject_library(course)
    lifecycle_status = str(subject_library.get("lifecycle_status") or "degraded")
    if lifecycle_status in {"accepted", "candidate"} and subject_library.get("nodes"):
        course_map = compile_course_knowledge_map(course, subject_library)
        selected_ids = knowledge_ids_for_section(course_map, node_id)
        by_id = knowledge_index(subject_library)
        nodes = [
            {
                "knowledge_id": knowledge_id,
                "name": by_id[knowledge_id].get("name"),
                "node_type": by_id[knowledge_id].get("node_type"),
                "path_names": deepcopy(by_id[knowledge_id].get("path_names") or []),
                "learning_actions": deepcopy((by_id[knowledge_id].get("learning_actions") or [])[:3]),
            }
            for knowledge_id in selected_ids[:16]
            if knowledge_id in by_id
        ]
        library_slice = knowledge_library_slice(subject_library, selected_ids)
        selected_set = set(selected_ids)
        relations = [
            deepcopy(item)
            for item in subject_library.get("relations") or []
            if item.get("source_knowledge_id") in selected_set
            or item.get("target_knowledge_id") in selected_set
        ][:16]
        return {
            "schema_version": "ai_knowledge_context_v3",
            "knowledge_library_id": subject_library.get("library_id"),
            "knowledge_library_version": subject_library.get("version"),
            "knowledge_library_revision_id": subject_library.get("revision_id"),
            "course_map_revision_id": course_map.get("revision_id"),
            "node_id": node_id,
            "knowledge_nodes": nodes,
            "relations": relations,
            "skill_units": deepcopy((library_slice.get("skill_units") or [])[:8]),
            "mistake_points": deepcopy((library_slice.get("mistake_points") or [])[:8]),
            "mastery_criteria": [],
            "improvement_points": deepcopy((library_slice.get("improvement_points") or [])[:5]),
            "mapping_status": "mapped" if nodes else "unmapped",
            "usage_policy": {
                **deepcopy(library_slice.get("usage_policy") or {}),
                "role": "provisional_reference" if lifecycle_status == "candidate" else "reference_only",
                "identity_scope": "subject_shared",
                "may_invent_formal_ids": False,
            },
        }

    return {
        "schema_version": "ai_knowledge_context_v3",
        "knowledge_library_id": knowledge_base.get("knowledge_base_id"),
        "knowledge_library_version": knowledge_base.get("revision_id"),
        "knowledge_library_revision_id": knowledge_base.get("revision_id"),
        "course_map_revision_id": (course.get("course_knowledge_map") or {}).get("revision_id"),
        "node_id": node_id,
        "knowledge_nodes": [],
        "relations": [],
        "skill_units": [],
        "mistake_points": [],
        "mastery_criteria": [],
        "improvement_points": [],
        "mapping_status": "degraded",
        "usage_policy": {
            "role": "unavailable_until_quality_passed",
            "identity_scope": "current_course_only",
            "may_invent_formal_ids": False,
            "reference_catalog_required": False,
        },
    }


def _select_sources(
    course: dict[str, Any],
    *,
    node_id: str,
    question: str,
    selection: str,
    context_ref: dict[str, Any],
) -> list[dict[str, Any]]:
    node = _find_node(course.get("nodes") or [], node_id)
    if not node:
        return []
    blocks = node.get("content_blocks") or []
    requested_revision = str((context_ref.get("content_anchor") or {}).get("block_revision_id") or "")
    terms = _terms(f"{question} {selection}")
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for index, block in enumerate(blocks):
        content = str(block.get("content") or "")
        title = str(block.get("title") or "")
        score = 0
        if requested_revision and block.get("block_revision_id") == requested_revision:
            score += 100
        if selection and _normalize(selection) in _normalize(content):
            score += 80
        normalized = _normalize(f"{title} {content}")
        score += sum(5 for term in terms if term in normalized)
        if index == 0:
            score += 1
        ranked.append((score, -index, block))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selected = [item[2] for item in ranked[:MAX_SOURCES] if item[0] > 0]
    if not selected and blocks:
        selected = list(blocks[:2])
    return [
        {
            "source_id": str(block.get("block_revision_id") or block.get("block_id") or f"node:{node_id}"),
            "type": "course_block",
            "course_version_id": str(course.get("current_course_version_id") or ""),
            "node_id": node_id,
            "block_id": str(block.get("block_id") or ""),
            "block_revision_id": str(block.get("block_revision_id") or ""),
            "title": str(block.get("title") or node.get("node_name") or ""),
            "content": _clip(str(block.get("content") or ""), 3500),
        }
        for block in selected
    ]


def _task_context(
    *,
    user_id: str,
    course_id: str,
    task_ref: dict[str, Any],
    entrypoint: str,
) -> dict[str, Any]:
    kind = str(task_ref.get("kind") or "")
    object_id = str(task_ref.get("object_id") or "")
    attempt = None
    if object_id and kind in {"practice", "diagnostic", "remediation", "validation"}:
        attempt = next((
            item for item in practice_attempt_repository.list(user_id, course_id)
            if str(item.get("attempt_id") or "") == object_id
        ), None)
    status = str((attempt or {}).get("status") or task_ref.get("status") or "")
    # Disclosure is derived from a server-side attempt, never from client task_ref status.
    submitted = bool(attempt) and status in {"submitted", "grading", "graded", "invalidated", "abandoned"}
    return {
        "task_ref": deepcopy(task_ref),
        "attempt": {
            "attempt_id": str((attempt or {}).get("attempt_id") or ""),
            "status": status,
            "task_revision_id": str((attempt or {}).get("task_revision_id") or task_ref.get("task_revision_id") or ""),
            "task_purpose": str((attempt or {}).get("task_purpose") or ""),
            "support_level": str((attempt or {}).get("support_level") or (attempt or {}).get("evidence_strength") or "independent"),
            "answer_payload": deepcopy((attempt or {}).get("answer_payload") or {}) if entrypoint == "practice" else {},
        } if attempt else {},
        "answer_disclosure": {
            "full_solution_allowed": submitted,
            "reference_answer_in_context": False,
            "reason": "submitted_or_graded" if submitted else "formal_task_not_submitted",
        },
    }


def _learner_model_context(
    model: dict[str, Any],
    *,
    intent: str,
    node_id: str,
) -> dict[str, Any]:
    base = {
        "model_revision_id": model.get("model_revision_id"),
        "observed_at": model.get("observed_at"),
        "data_sufficiency": deepcopy(model.get("data_sufficiency") or {}),
    }
    if intent not in {"learner_review", "analyze_attempt", "practice_help", "explain_next_action"}:
        return base
    current = deepcopy(model.get("current_objective") or {})
    if node_id and str(current.get("node_id") or "") != node_id:
        current = {}
    if current and not is_model_item_current(current):
        current["confidence"] = "insufficient"
        current["support_need"] = {
            "status": "unknown",
            "reason_code": "evidence_expired",
            "confidence": "insufficient",
            "evidence_refs": [],
        }
        current["evidence_refs"] = []
        current["model_evidence_status"] = "expired"
        base["data_sufficiency"] = {
            **base["data_sufficiency"],
            "level": "limited",
            "reason_code": "current_objective_evidence_expired",
        }
    return {
        **base,
        "current_objective": current,
        "current_knowledge_states": deepcopy(model.get("current_knowledge_states") or []),
        "current_skill_states": deepcopy(model.get("current_skill_states") or []),
        "current_mistake_signals": deepcopy(model.get("current_mistake_signals") or []),
        "strengths": deepcopy([
            item for item in model.get("strengths") or [] if is_model_item_current(item)
        ][:3]),
        "needs_attention": deepcopy([
            item for item in model.get("needs_attention") or [] if is_model_item_current(item)
        ][:3]),
    }


def _learner_evidence(
    learner_model: dict[str, Any],
    *,
    intent: str,
) -> list[dict[str, Any]]:
    if intent not in {"learner_review", "analyze_attempt", "practice_help", "explain_next_action"}:
        return []
    evidence: list[dict[str, Any]] = []
    objective = learner_model.get("current_objective") or {}
    for ref in objective.get("evidence_refs") or []:
        evidence.append({
            "type": str(ref.get("type") or "formal_evidence"),
            "status": str(ref.get("status") or "recorded"),
            "source_id": str(ref.get("source_id") or ""),
            "summary": _evidence_summary(ref),
            "strength": str(ref.get("strength") or "unknown"),
            "observed_at": ref.get("observed_at"),
            "confirmed": ref.get("strength") in {"independent", "explicit"},
        })
        if len(evidence) >= MAX_EVIDENCE:
            break
    return evidence[:MAX_EVIDENCE]


def _evidence_summary(ref: dict[str, Any]) -> str:
    evidence_type = str(ref.get("type") or "")
    outcome = str(ref.get("outcome") or "")
    if evidence_type == "practice_attempt":
        return "正式练习已通过。" if outcome == "passed" else "正式练习尚未通过。" if outcome == "not_passed" else "正式练习正在处理。"
    if evidence_type.startswith("learning_record:issue"):
        return "学习者保留了一条当前问题。"
    if evidence_type.startswith("learning_record:review_task"):
        return "学习者保留了一项复习任务。"
    if evidence_type.startswith("learning_record"):
        return "学习者保留了一条正式学习记录。"
    if "node_learning_completed" in evidence_type:
        return "学习者明确完成了当前阅读。"
    if "node_learning_started" in evidence_type:
        return "学习者已经开始当前阅读。"
    return "存在一条与当前目标相关的正式证据。"


def _progress_summary(progress: dict[str, Any], node_id: str) -> dict[str, Any]:
    objectives = progress.get("nodes") or []
    current = next((item for item in objectives if str(item.get("node_id") or "") == node_id), None)
    return deepcopy(current or {})


def _request_intent(question: str, entrypoint: str) -> str:
    text = _normalize(question)
    if entrypoint == "practice":
        return "practice_help"
    if any(token in text for token in ["下一步", "接下来", "现在做什么"]):
        return "explain_next_action"
    if any(token in text for token in ["为什么错", "错在哪", "分析错误"]):
        return "analyze_attempt"
    if any(token in text for token in ["薄弱", "掌握情况", "学习情况", "学习复盘", "学得怎么样", "优势"]):
        return "learner_review"
    if any(token in text for token in ["记成笔记", "保存为笔记", "记下来"]):
        return "create_note_command"
    if any(token in text for token in ["标记为不懂", "创建问题"]):
        return "create_issue_command"
    return "explain_content"


def _find_node(nodes: list[dict[str, Any]], node_id: str) -> dict[str, Any] | None:
    for node in nodes:
        if str(node.get("node_id") or "") == node_id:
            return node
        child = _find_node(node.get("children") or [], node_id)
        if child:
            return child
    return None


def _terms(text: str) -> set[str]:
    ascii_terms = re.findall(r"[a-zA-Z0-9_]{3,}", text.lower())
    chinese = re.findall(r"[\u4e00-\u9fff]{2,8}", text)
    return set(ascii_terms + chinese)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _clip(value: str, limit: int) -> str:
    return value[:limit]


__all__ = [
    "build_ai_teacher_context",
    "context_public_summary",
    "format_ai_teacher_context_prompt",
]
