"""AI teacher answer streaming and note summarization."""

from __future__ import annotations

import json
from typing import Any

from ai_base import (
    AIBase,
    AIProviderRequestError,
    AIProviderUnavailable,
    AIRequestBudgetExceeded,
    AIResponseTruncated,
)
from ai_capacity import ModelCapacityCoolingDown
from ai_teacher_context import format_ai_teacher_context_prompt
from prompts import get_prompt


class AITeacherModelFailure(RuntimeError):
    """One AI-teacher answer failed, with the provider's failure kind preserved.

    `ai_base` already distinguishes auth, quota, rate limit, timeout, budget and
    truncation, and already fails over across configured models before giving
    up. Collapsing all of that into a single opaque error is what made a model
    outage look identical to a bad API key in the UI, so this carries the class
    of failure — plus whatever text the learner already saw — to the SSE layer.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        partial_text: str = "",
    ) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        self.partial_text = partial_text
        super().__init__(f"{code}: {message}")


# Teacher-facing Chinese copy is the server-side audit line; the client
# localizes from `code`.
_FAILURE_COPY: dict[str, tuple[str, bool]] = {
    "model_not_configured": ("AI 老师尚未配置模型，请联系管理员。", False),
    "model_auth_failed": ("AI 模型认证失败，请联系管理员检查密钥。", False),
    "model_quota_exhausted": ("AI 模型额度已用完，请稍后再试或联系管理员。", False),
    "model_request_too_large": ("这次提问的上下文过大，请缩小选区或换个更具体的问题。", False),
    "model_rate_limited": ("AI 模型当前繁忙，请稍后重试。", True),
    "model_timeout": ("AI 模型响应超时，请重试。", True),
    "model_response_truncated": ("AI 回答被长度限制截断，内容不完整。", True),
    "model_unavailable": ("AI 老师暂时不可用，课程和正式学习任务仍可继续使用。", True),
}

_PROVIDER_REASON_CODES = {
    "not_configured": "model_not_configured",
    "authentication_failed": "model_auth_failed",
}


def classify_model_failure(
    error: Exception,
    *,
    partial_text: str = "",
) -> AITeacherModelFailure:
    """Map an `ai_base` provider error onto one stable AI-teacher failure code."""
    code = _failure_code(error)
    message, retryable = _FAILURE_COPY[code]
    return AITeacherModelFailure(
        code,
        message,
        retryable=retryable,
        partial_text=partial_text,
    )


def _delimiter_safe_end(text: str, delimiter: str) -> int:
    """How much of `text` can be released without splitting the delimiter.

    Only a real trailing prefix of the delimiter has to be withheld. The old
    rule held back a fixed `len(delimiter) - 1` characters unconditionally, so
    an answer that never emits `---METADATA---` (the normal case) always lagged
    the model by 13 characters, and a cancel dropped that tail entirely.
    """
    for size in range(min(len(delimiter) - 1, len(text)), 0, -1):
        if text.endswith(delimiter[:size]):
            return len(text) - size
    return len(text)


def _failure_code(error: Exception) -> str:
    if isinstance(error, AITeacherModelFailure):
        return error.code
    if isinstance(error, AIProviderUnavailable):
        return _PROVIDER_REASON_CODES.get(
            str(getattr(error, "reason", "") or ""),
            "model_unavailable",
        )
    if isinstance(error, AIRequestBudgetExceeded):
        return "model_request_too_large"
    if isinstance(error, AIResponseTruncated):
        return "model_response_truncated"
    if isinstance(error, ModelCapacityCoolingDown):
        return "model_rate_limited"
    return _failure_code_from_text(str(error))


def _failure_code_from_text(text: str) -> str:
    """Fall back to the provider's own wording when no typed error survived.

    Providers routinely surface rate limits and quota exhaustion as prose in a
    generic error, and some stream the failure as ordinary answer text. Reuse
    the same markers `ai_base` matches on so both layers agree on the kind.
    """
    lowered = text.lower()
    if "not configured" in lowered:
        return "model_not_configured"
    if any(marker in lowered for marker in (
        "authentication",
        "invalid api key",
        "invalid_api_key",
        "unauthorized",
        "forbidden",
        "permission denied",
        "permission_denied",
    )):
        return "model_auth_failed"
    if any(marker in lowered for marker in (
        "insufficient_quota",
        "insufficient balance",
        "exceeded your current quota",
        "exceeded today's quota",
        "额度",
    )):
        return "model_quota_exhausted"
    if any(marker in lowered for marker in (
        "rate limit",
        "limit_burst_rate",
        "速率限制",
        "429",
        "cooling_down",
    )):
        return "model_rate_limited"
    if any(marker in lowered for marker in ("timed out", "timeout", "超时")):
        return "model_timeout"
    return "model_unavailable"


class AIQAService(AIBase):
    """Model adapter for the unified AI teacher protocol."""

    async def answer_question_stream(
        self,
        question: str,
        *,
        context_package: dict[str, Any],
        **_: Any,
    ):
        system_prompt = format_ai_teacher_context_prompt(context_package)
        web_sources = [
            item
            for item in context_package.get("sources") or []
            if item.get("type") == "web"
        ]
        if web_sources:
            system_prompt += (
                "\n\nWeb citation contract: every fact derived from a web summary "
                "must end with its exact citation marker such as [S1]. "
                "Never cite a source that is not present above and never "
                "claim current information without a cited dated source."
            )
        # Conversation history and the bounded course context are already in
        # the system prompt. Repeating them here wastes context and can make
        # stale turns look more important than the user's current question.
        prompt = f"""用户当前问题：{question}

请严格执行上面的视角、文件范围、回答策略和披露边界。不要假装已经写入笔记、错题、复习任务或课程内容；需要改变系统状态时，只能说明建议动作。"""
        emitted = ""
        try:
            async for chunk in self._stream_llm(
                prompt,
                system_prompt,
                max_attempts=2,
            ):
                normalized = chunk.strip()
                if normalized.startswith("[Error:") or normalized == "AI Service not configured.":
                    # Some providers stream their failure as ordinary text
                    # instead of raising, so classify the text too.
                    raise classify_model_failure(
                        AIProviderRequestError(normalized),
                        partial_text=emitted,
                    )
                emitted += chunk
                yield chunk
        except AITeacherModelFailure:
            raise
        except Exception as exc:
            raise classify_model_failure(exc, partial_text=emitted) from exc

    async def answer_question_events(self, *args: Any, **kwargs: Any):
        """Emit structured SSE blocks without asking the client to parse answer text.

        No `final_answer` is emitted here: the route owns that block because only
        it knows the persisted `message_id`. Emitting one from both layers gave
        clients two competing answers, one of which was never stored.
        """
        delimiter = "---METADATA---"
        full_text = ""
        sent_until = 0
        collecting_metadata = False
        try:
            async for chunk in self.answer_question_stream(*args, **kwargs):
                full_text += chunk
                split_idx = full_text.find(delimiter)
                if split_idx == -1 and not collecting_metadata:
                    safe_end = _delimiter_safe_end(full_text, delimiter)
                    if safe_end > sent_until:
                        yield self._qa_event("answer", {"chunk": full_text[sent_until:safe_end]})
                        sent_until = safe_end
                elif split_idx != -1 and not collecting_metadata:
                    unsent_answer = full_text[sent_until:split_idx]
                    if unsent_answer:
                        yield self._qa_event("answer", {"chunk": unsent_answer})
                    collecting_metadata = True
        except AITeacherModelFailure as failure:
            # Flush whatever the learner already read, then say what went wrong.
            # A failed answer has no trustworthy metadata, so none is emitted —
            # the caller must treat this turn as incomplete.
            answer_end = full_text.find(delimiter)
            visible_end = len(full_text) if answer_end == -1 else answer_end
            if visible_end > sent_until:
                yield self._qa_event("answer", {"chunk": full_text[sent_until:visible_end]})
            yield self._qa_event("error", {
                "code": failure.code,
                "message": failure.message,
                "retryable": failure.retryable,
            })
            return

        if not collecting_metadata and sent_until < len(full_text):
            yield self._qa_event("answer", {"chunk": full_text[sent_until:]})

        _answer, metadata = self._split_answer_metadata(full_text)
        yield self._qa_event("metadata", metadata)

    def _split_answer_metadata(self, text: str) -> tuple[str, dict[str, Any]]:
        split_idx = text.find("---METADATA---")
        if split_idx == -1:
            return text.strip(), {}
        answer = text[:split_idx].strip()
        raw_metadata = text[split_idx + len("---METADATA---"):].strip()
        try:
            metadata = json.loads(raw_metadata)
        except json.JSONDecodeError:
            metadata = {}
        return answer, metadata

    def _qa_event(self, event: str, payload: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def summarize_note(self, content: str) -> str:
        system_prompt = get_prompt("summarize_note").format()
        response = await self._call_llm(
            f"笔记内容：\n{content[:2000]}\n\n请生成标题：",
            system_prompt,
            use_fast_model=True,
        )
        return response if response else (content[:20] + "...")
