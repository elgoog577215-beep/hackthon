"""Intent-scoped context assembly for the AI teacher."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from content_blocks import project_course_content_blocks
from course_knowledge_base import compile_course_knowledge_base, knowledge_binding_for_section
from learner_model import is_model_item_current
from learning_runtime import build_learning_runtime
from practice_attempts import practice_attempt_repository

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
    perspective: str = "learner",
    entrypoint: str = "global",
    context_ref: dict[str, Any] | None = None,
    task_ref: dict[str, Any] | None = None,
    conversation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one immutable package without copying domain state into AI storage."""
    projected_course = project_course_content_blocks(course_data)
    runtime = build_learning_runtime(projected_course, user_id=user_id, node_id=node_id)
    intent = "teacher_design" if perspective == "teacher" else _request_intent(question, entrypoint)
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
        perspective=perspective,
        context_ref=context_ref or {},
    )
    effective_task_ref = deepcopy(task_ref or runtime.get("active_task") or {})
    task = _task_context(
        user_id=user_id,
        course_id=str(projected_course.get("course_id") or ""),
        task_ref=effective_task_ref,
        entrypoint=entrypoint,
    )
    learner_model = (
        {}
        if perspective == "teacher"
        else _learner_model_context(
            runtime.get("learner_model") or {},
            intent=intent,
            node_id=effective_node_id,
        )
    )
    evidence = [] if perspective == "teacher" else _learner_evidence(learner_model, intent=intent)
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
            "perspective": perspective,
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
        "response_strategy": _response_strategy(
            perspective=perspective,
            intent=intent,
            question=question,
            has_course_sources=bool(sources),
            answer_disclosure=(task.get("answer_disclosure") or {}),
        ),
        "conversation": {
            "conversation_id": str((conversation or {}).get("conversation_id") or ""),
            "recent_messages": recent_messages,
        },
        "permissions": {
            "answer": True,
            "explain_runtime_action": perspective != "teacher",
            "allowed_proposals": [] if perspective == "teacher" else [
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
    response_strategy = package.get("response_strategy") or {}

    source_lines = [
        (
            f"- [{item.get('citation_id')}] "
            f"{item.get('title') or 'Web source'}: {item.get('content')}"
            if item.get("type") == "web"
            else (
                f"- [{item.get('source_id')}] "
                f"{item.get('title') or 'Course source'}: {item.get('content')}"
            )
        )
        for item in sources
    ] or ["- No available course sources."]
    evidence_lines = [
        f"- {item.get('type')}（{item.get('status')}）：{item.get('summary')}"
        for item in evidence
    ] or ["- 无与本次请求直接相关的长期证据。"]
    history_lines = [
        f"- {item.get('role')}：{item.get('content')}"
        for item in (conversation.get("recent_messages") or [])
    ] or ["- 新会话。"]

    if request.get("perspective") == "teacher":
        file_scope = ((scene.get("content_anchor") or {}).get("file_scope") or {})
        file_scope_mode = str(file_scope.get("mode") or "all")
        file_scope_label = (
            "全部文件"
            if file_scope_mode == "all"
            else "、".join(file_scope.get("labels") or []) or "未选择文件"
        )
        return f"""你是灵知教师端的通用 AI 助手。你在教师界面中以教师工作视角回答，核心任务是帮助教师理解课程、判断“怎么教”与改进备课；你不代替教师做正式发布决定。

## 当前教师请求
- 问题：{request.get('question')}
- 当前课节：{scene.get('node_name') or '全课程'}
- 文件范围：{file_scope_label}
- 意图：{request.get('intent')}

## 本次回答策略
{json.dumps(response_strategy, ensure_ascii=False, indent=2)}

## 课程结构与版本现场
{json.dumps(scene, ensure_ascii=False, indent=2)}

## 结构化同源知识切片
{json.dumps(knowledge_context, ensure_ascii=False, indent=2)}

## 当前版本课程来源
{chr(10).join(source_lines)}

## 最近对话
{chr(10).join(history_lines)}

## 回答要求
1. 严格限制在“文件范围”内检索课程事实。范围内没有足够来源时，明确写“当前文件范围内证据不足”，再把补充内容标为专业判断；不得悄悄引用范围外文件。
2. 先给结论，再按“本次回答策略”的 answer_order 组织内容。结构分析要覆盖目标、先备关系、重点与断点；课堂设计要覆盖讲解/示范、学生活动、理解检查和备用处理；风险检查要给优先级、依据、影响与动作。
3. 明确区分“课程现状/来源证据”和“教学专业判断”。引用课程事实时使用上面真实 source_id；不得编造稳定块 ID、修订号、知识 ID 或学生数据。
4. 教案、PPT、正文和练习必须引用同一语义真源的稳定块 ID、修订号和依赖关系，不要建议多份脱节的副本。
5. 当底层事实或版本变化时，先说明影响到哪些教案、PPT、正文和练习，再由教师确认是否精确重建。
6. 不得声称已自动修改或发布正式课程；课程正式变更必须先给影响预览，且可确认、可追溯。
7. 教师未要求完整方案时保持紧凑，不为显得全面而机械堆叠模板，也不主动转去代答学生题目。
"""

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

## 本次回答策略
{json.dumps(response_strategy, ensure_ascii=False, indent=2)}

## 回答要求
1. 先直接回应学习者当前问题，再按“本次回答策略”的 answer_order 补充必要内容；不强制添加无关总结、下一步或邀请。
2. explain_content：先给清晰结论与关键机制，例子只在确有帮助时加入；若用户要求“检查理解”，只提出一个可作答的小问题并等待，不同时公布答案。
3. practice_help：在正式任务未允许完整答案时，用递进提示或关键检查点引导，停在学习者可以继续作答的位置；不得泄露标准答案。
4. analyze_attempt：先复述学习者实际思路，再定位最早的推理分叉点，解释原因并给一个下一提示；不得把一次错误升级成稳定薄弱点。
5. learner_review：先说明证据充分度，再陈述有正式依据的优势/待巩固点；证据有限时明确不确定性，不用提问次数或会话措辞代替学习证据。
6. explain_next_action：只解释 LearningRuntime 的 primary_action、原因和当前具体动作，不创建竞争动作。
7. 课程事实优先使用上面的当前版本来源；没有来源时明确说明是在做通用解释。区分课程事实、用户陈述和推断，不伪造知识 ID、来源或已执行动作。
8. 回答正文中不伪造已经执行的系统动作。写动作由独立 ActionProposal 协议处理。
9. 当前课程知识库是本课程知识身份、能力、易错与掌握标准的统一坐标；只允许使用已通过质量门的条目。回答仍须结合当前正文、任务和学习证据，不得忽略真实问题。
10. 当入口为 block 时，回答到当前解释、例子、简化或问题本身为止；不得主动提出下一步、出题、保存或课程改写，也不要在结尾添加“如果你愿意”“需要我可以”等邀请。"""


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
                "citation_id": item.get("citation_id"),
                "url": item.get("url"),
                "domain": item.get("domain"),
                "published_date": item.get("published_date"),
                "retrieved_at": item.get("retrieved_at"),
                "trust_tier": item.get("trust_tier"),
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
    perspective: str,
    context_ref: dict[str, Any],
) -> list[dict[str, Any]]:
    nodes = course.get("nodes") or []
    anchor = context_ref.get("content_anchor") or {}
    file_scope = anchor.get("file_scope") if isinstance(anchor, dict) else {}
    if perspective == "teacher" and isinstance(file_scope, dict):
        mode = str(file_scope.get("mode") or "all")
        selected_node_ids = {
            str(item) for item in file_scope.get("node_ids") or [] if item
        }
        candidate_nodes = [
            node for node in nodes
            if (mode == "all" or str(node.get("node_id") or "") in selected_node_ids)
            and (node.get("content_blocks") or [])
        ]
    else:
        node = _find_node(nodes, node_id)
        candidate_nodes = [node] if node else []
    if not candidate_nodes:
        return []
    requested_revision = str(anchor.get("block_revision_id") or "")
    terms = _terms(f"{question} {selection}")
    ranked: list[tuple[int, int, dict[str, Any], dict[str, Any]]] = []
    sequence = 0
    for node in candidate_nodes:
        for index, block in enumerate(node.get("content_blocks") or []):
            content = str(block.get("content") or "")
            title = str(block.get("title") or "")
            score = 0
            if requested_revision and block.get("block_revision_id") == requested_revision:
                score += 100
            if selection and _normalize(selection) in _normalize(content):
                score += 80
            normalized = _normalize(f"{node.get('node_name') or ''} {title} {content}")
            score += sum(5 for term in terms if term in normalized)
            if index == 0:
                score += 1
            ranked.append((score, -sequence, node, block))
            sequence += 1
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selected = [(item[2], item[3]) for item in ranked[:MAX_SOURCES] if item[0] > 0]
    if not selected:
        selected = [(item[2], item[3]) for item in ranked[:2]]
    return [
        {
            "source_id": str(block.get("block_revision_id") or block.get("block_id") or f"node:{node.get('node_id') or ''}"),
            "type": "course_block",
            "course_version_id": str(course.get("current_course_version_id") or ""),
            "node_id": str(node.get("node_id") or ""),
            "block_id": str(block.get("block_id") or ""),
            "block_revision_id": str(block.get("block_revision_id") or ""),
            "title": str(block.get("title") or node.get("node_name") or ""),
            "content": _clip(str(block.get("content") or ""), 3500),
        }
        for node, block in selected
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


def _response_strategy(
    *,
    perspective: str,
    intent: str,
    question: str,
    has_course_sources: bool,
    answer_disclosure: dict[str, Any],
) -> dict[str, Any]:
    """Select a response shape without creating another assistant endpoint."""
    if perspective == "teacher":
        text = _normalize(question)
        if any(token in text for token in ["风险", "漏洞", "检查", "缺失", "问题"]):
            focus = "teaching_risk_review"
            answer_order = ["priority_finding", "course_evidence", "teaching_impact", "recommended_action"]
        elif any(token in text for token in ["修改", "重写", "更新", "ppt", "正文"]):
            focus = "course_change_analysis"
            answer_order = ["requested_change", "affected_artifacts", "impact_preview", "confirmation_boundary"]
        elif any(token in text for token in ["怎么教", "课堂", "活动", "教案", "备课"]):
            focus = "lesson_design"
            answer_order = ["learning_objective", "teaching_sequence", "classroom_activity", "understanding_check", "fallback"]
        else:
            focus = "course_structure_analysis"
            answer_order = ["conclusion", "course_evidence", "instructional_reasoning", "recommended_action"]
        return {
            "audience": "teacher",
            "focus": focus,
            "answer_order": answer_order,
            "course_evidence_available": has_course_sources,
            "separate_evidence_from_judgment": True,
            "change_requires_confirmation": True,
        }

    strategies = {
        "practice_help": ["brief_hint", "reasoning_checkpoint", "wait_for_learner"],
        "analyze_attempt": ["answer_readback", "first_divergence", "why_it_matters", "next_hint"],
        "learner_review": ["evidence_sufficiency", "current_strength", "current_gap", "single_next_step"],
        "explain_next_action": ["current_action", "runtime_reason", "what_to_do_now"],
        "explain_content": ["direct_answer", "mechanism", "example_if_useful", "understanding_check_if_requested"],
    }
    return {
        "audience": "learner",
        "focus": intent,
        "answer_order": strategies.get(intent, strategies["explain_content"]),
        "course_evidence_available": has_course_sources,
        "full_solution_allowed": bool(answer_disclosure.get("full_solution_allowed")),
        "avoid_stable_diagnosis_without_formal_evidence": True,
    }


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
