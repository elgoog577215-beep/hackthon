"""AI teacher answer streaming and note summarization."""

from __future__ import annotations

import json
from typing import Any

from ai_base import AIBase
from ai_teacher_context import format_ai_teacher_context_prompt
from prompts import get_prompt


class AIQAService(AIBase):
    """Model adapter for the unified AI teacher protocol."""

    async def answer_question_stream(
        self,
        question: str,
        *,
        context_package: dict[str, Any],
        **_: Any,
    ):
        recent = ((context_package.get("conversation") or {}).get("recent_messages") or [])
        history_text = "\n".join(
            f"{item.get('role', 'user')}: {item.get('content', '')}"
            for item in recent
        )
        system_prompt = format_ai_teacher_context_prompt(context_package)
        prompt = f"""最近对话：
{history_text or '无'}

用户问题：{question}

请直接回答当前问题。不要假装已经写入笔记、错题或复习任务；需要改变系统状态时，只能说明建议动作。"""
        async for chunk in self._stream_llm(prompt, system_prompt):
            normalized = chunk.strip()
            if normalized.startswith("[Error:") or normalized == "AI Service not configured.":
                raise RuntimeError("AI provider unavailable")
            yield chunk

    async def answer_question_events(self, *args: Any, **kwargs: Any):
        """Emit structured SSE blocks without asking the client to parse answer text."""
        delimiter = "---METADATA---"
        full_text = ""
        sent_until = 0
        collecting_metadata = False
        async for chunk in self.answer_question_stream(*args, **kwargs):
            full_text += chunk
            split_idx = full_text.find(delimiter)
            if split_idx == -1 and not collecting_metadata:
                safe_end = max(0, len(full_text) - len(delimiter) + 1)
                if safe_end > sent_until:
                    yield self._qa_event("answer", {"chunk": full_text[sent_until:safe_end]})
                    sent_until = safe_end
            elif split_idx != -1 and not collecting_metadata:
                unsent_answer = full_text[sent_until:split_idx]
                if unsent_answer:
                    yield self._qa_event("answer", {"chunk": unsent_answer})
                collecting_metadata = True

        if not collecting_metadata and sent_until < len(full_text):
            yield self._qa_event("answer", {"chunk": full_text[sent_until:]})

        answer, metadata = self._split_answer_metadata(full_text)
        yield self._qa_event("final_answer", {"answer": answer})
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
