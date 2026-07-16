"""Load one formal evidence batch and project the current learner model."""

from __future__ import annotations

import asyncio
from typing import Any

from ai_base import AIBase
from change_proposals import change_proposal_repository, create_proposal
from course_repository import CourseDocumentNotFound, CourseDocumentRepository
from diagnostic_service import workflow_view
from learner_context import DEFAULT_USER_ID
from learner_model import build_learner_model, evaluate_evidence_trigger
from learning_continuation import build_learning_continuation
from learning_events import load_learning_events
from learning_progress import build_learning_progress, project_learning_objective_bindings
from learning_records import learning_record_repository
from learning_runtime import build_runtime_revision_vector
from learning_snapshots import learning_snapshot_repository
from practice_attempts import practice_attempt_repository
from storage import storage


def build_current_learner_model(course_data: dict[str, Any], *, user_id: str) -> dict[str, Any]:
    """Build a model from one immutable source batch without persisting it."""
    course = project_learning_objective_bindings(course_data)
    course_id = str(course.get("course_id") or "")
    has_stable_identity = bool(user_id and user_id != DEFAULT_USER_ID)

    if has_stable_identity:
        events = load_learning_events(user_id=user_id, course_id=course_id)
        snapshot = learning_snapshot_repository.load(user_id, course_id)
        records = learning_record_repository.list(user_id, course_id)
        attempts = practice_attempt_repository.list(user_id, course_id)
        workflow = workflow_view(user_id, course_id)
    else:
        events = []
        snapshot = None
        records = []
        attempts = []
        workflow = {}

    progress = build_learning_progress(
        course,
        user_id=user_id,
        events=events,
        attempts=attempts,
    )
    continuation = build_learning_continuation(
        course,
        user_id=user_id,
        progress=progress,
        snapshot=snapshot,
        attempts=attempts,
        workflow=workflow,
        records=records,
        events=events,
    )
    source_revision_vector = build_runtime_revision_vector(
        course=course,
        events=events,
        snapshot=snapshot,
        records=records,
        attempts=attempts,
        workflow=workflow,
        continuation=continuation,
    )
    return build_learner_model(
        course,
        user_id=user_id,
        events=events,
        snapshot=snapshot,
        records=records,
        attempts=attempts,
        workflow=workflow,
        progress=progress,
        source_revision_vector=source_revision_vector,
    )


def build_current_learner_model_for_course(
    course_id: str | None,
    *,
    user_id: str,
) -> dict[str, Any] | None:
    """Load a course and return its model; missing courses have no model."""
    if not course_id:
        return None
    course = storage.load_course(course_id)
    if not course:
        return None
    return build_current_learner_model(course, user_id=user_id)


def _template_supplement_text(block_payload: dict[str, Any], events: list[dict[str, Any]]) -> str:
    """Deterministic fallback generator for the proposed supplementary
    explanation, used whenever a real LLM call (`_llm_supplement_text`) is
    unavailable (no API key, provider failure, already inside a running
    event loop that can't be nested) or returns empty content.

    This concatenates the original block content with a short, clearly-
    labelled "AI supplement" section built from the evidence statements
    themselves. It is intentionally simple and offline so that evidence-
    driven proposals always get *some* fresh, non-blank content even when
    the LLM path can't run.
    """
    content_key = "markdown" if "markdown" in block_payload else ("text" if "text" in block_payload else "content")
    original = str(block_payload.get(content_key) or "")
    statements = [
        str((event.get("evidence") or {}).get("statement") or "").strip()
        for event in events
    ]
    statements = [statement for statement in statements if statement][:3]
    bullet_lines = "\n".join(f"- {statement}" for statement in statements) or "- 学生反馈该节点讲解颗粒度偏粗，需要更详细的解释"
    supplement = (
        "\n\n---\n"
        "**AI 补充说明（根据学习证据自动生成，待确认）**\n\n"
        "以下补充针对学生反馈的理解困难点：\n"
        f"{bullet_lines}\n"
    )
    return original + supplement


async def _llm_supplement_text(block_payload: dict[str, Any], events: list[dict[str, Any]]) -> str | None:
    """Ask the real LLM layer for a supplementary explanation targeted at the
    student's reported comprehension gaps. Returns None (never raises) when
    the provider is unavailable or the call fails, so callers can fall back
    to `_template_supplement_text`.
    """
    content_key = "markdown" if "markdown" in block_payload else ("text" if "text" in block_payload else "content")
    original = str(block_payload.get(content_key) or "")
    statements = [
        str((event.get("evidence") or {}).get("statement") or "").strip()
        for event in events
    ]
    statements = [statement for statement in statements if statement][:3]
    if not statements:
        statements = ["学生反馈该节点讲解颗粒度偏粗，需要更详细的解释"]
    bullet_lines = "\n".join(f"- {statement}" for statement in statements)

    prompt = f"""你正在为一段正式课程正文生成补充讲解，供学生确认后再合并进正文。

## 原正文
{original}

## 学生反馈的理解困难点
{bullet_lines}

## 输出要求
1. 只输出补充讲解本身的 Markdown 正文，不要重复原文，不要输出标题“AI 补充说明”或分隔线（调用方会自行拼接）。
2. 直接针对学生反馈的困难点做更细致、更具体的解释，可以举例，但不要偏离原文术语和结论。
3. 不编造原文中不存在的公式、数据、来源或术语。
4. 保持简洁，控制在 200 字以内。"""

    try:
        client = AIBase()
        response = await client._call_llm(prompt, "你是一位耐心、严谨的学科助教。", enable_thinking=False)
    except Exception:
        return None
    if not response:
        return None
    text = client.clean_response_text(response).strip()
    if not text:
        return None
    return (
        "\n\n---\n"
        "**AI 补充说明（根据学习证据自动生成，待确认）**\n\n"
        f"{text}\n"
    )


def _run_llm_supplement_sync(
    block_payload: dict[str, Any],
    events: list[dict[str, Any]],
) -> str | None:
    """Run `_llm_supplement_text` to completion from synchronous code,
    regardless of whether the calling thread already has a running event
    loop (e.g. inside a FastAPI async request handler). A dedicated worker
    thread gets its own fresh loop via `asyncio.run`, sidestepping the
    "cannot run event loop while another is running" restriction.
    """
    import concurrent.futures

    def _worker() -> str | None:
        return asyncio.run(_llm_supplement_text(block_payload, events))

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_worker).result(timeout=60)
    except Exception:
        return None


def _generate_supplement_payload(
    block_payload: dict[str, Any],
    events: list[dict[str, Any]],
) -> tuple[str, str]:
    """Produce the new block content plus the `generation_method` used
    ("llm" or "template_fallback"). Tries the real LLM call first; falls
    back to the offline template whenever the LLM path is unavailable or
    returns nothing usable.
    """
    content_key = "markdown" if "markdown" in block_payload else ("text" if "text" in block_payload else "content")
    original = str(block_payload.get(content_key) or "")

    llm_supplement = _run_llm_supplement_sync(block_payload, events)
    if llm_supplement:
        return original + llm_supplement, "llm"
    return _template_supplement_text(block_payload, events), "template_fallback"


def evaluate_and_propose_change(
    course_id: str,
    block_id: str,
    *,
    user_id: str,
    request_id: str | None = None,
) -> dict[str, Any] | None:
    """Evaluate one block's evidence and, if the dynamic threshold in
    `learner_model.evaluate_evidence_trigger` is crossed, create a *pending*
    `ChangeProposal` (source="evidence") suggesting a supplementary
    explanation for that block.

    Hard constraint (spec: "AI 变更 MUST 以待确认形式呈现，不得直接写入正式
    课程"): this function's only side effect is `change_proposals.
    create_proposal`. It never calls `CourseCommandService`/`apply_item` and
    never mutates `CourseDocument` or the learner model — the learner model
    stays a deterministic, read-only projection (`ai_writable: False`) with
    or without this function ever running.

    MVP scope note: identification is by `block_id` directly (matching
    `ChangeProposal.target_block_ids`), assuming the caller already resolved
    the relevant `AdaptiveBlock` id. `LearningEvent.node_id` is used as the
    lookup key when loading events, consistent with how the rest of
    `learner_model.py` treats `node_id` as the addressable location of
    evidence; a formal node_id -> block_id projection through
    `course_knowledge_map` is left to that module's own owner.

    Returns the created/loaded proposal dict, or None when there is nothing
    to propose (no evidence, threshold not crossed, or the block no longer
    exists).
    """
    if not course_id or not block_id:
        return None

    events = load_learning_events(
        user_id=user_id,
        course_id=course_id,
        node_id=block_id,
        event_type="learner_self_reported",
    )
    if not events:
        return None

    trigger = evaluate_evidence_trigger(events)
    if not trigger["triggered"]:
        return None

    course_repository = CourseDocumentRepository(storage)
    try:
        document, _is_canonical = course_repository.load_document(course_id)
    except CourseDocumentNotFound:
        return None
    block = next((item for item in document.blocks if item.block_id == block_id), None)
    if block is None:
        return None

    content_key = "markdown" if "markdown" in block.payload else ("text" if "text" in block.payload else "content")
    new_content, generation_method = _generate_supplement_payload(block.payload, events)
    new_payload = dict(block.payload)
    new_payload[content_key] = new_content

    resolved_request_id = request_id or f"evidence-{block_id}-{trigger['reason_code']}-{len(events)}"
    return create_proposal(
        change_proposal_repository,
        course_id,
        request_id=resolved_request_id,
        scope="block",
        target_block_ids=[block_id],
        items=[
            {
                "block_id": block_id,
                "before": dict(block.payload),
                "after": {"payload": new_payload},
                "reason": (
                    f"学习证据触发变更（{trigger['reason_code']}，"
                    f"score={trigger['score']}）：学生对该节点反馈理解困难，"
                    "AI 建议补充更详细的解释。"
                ),
            }
        ],
        source="evidence",
        generation_meta={
            "trigger": trigger,
            "user_id": user_id,
            "evidence_event_ids": [str(event.get("event_id") or "") for event in events],
            "generation_method": generation_method,
            "generation_note": (
                "真实 LLM 生成" if generation_method == "llm"
                else "LLM 不可用，回退为模板生成"
            ),
        },
    )


__all__ = [
    "build_current_learner_model",
    "build_current_learner_model_for_course",
    "evaluate_and_propose_change",
]
