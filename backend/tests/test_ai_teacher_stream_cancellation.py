"""Cancelling a streaming answer must not leave half an interaction behind.

Three defects this pins down, all observed against the pre-change code:

1. The learner sees text, presses stop (or navigates away), and the server
   persists *nothing* — the conversation shows only their question, so the
   partial answer they read is unrecoverable and the turn looks like it never
   happened.
2. `answer_question_events` emits its own `final_answer`, and the route emits a
   second one with the message id. A client that takes the first one gets an
   answer block that does not match the persisted message.
3. The answer stream withholds the last `len("---METADATA---") - 1` characters
   waiting for a delimiter that usually never arrives, so the visible answer
   lags the model by a fixed tail and a cancel drops that tail entirely.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from ai_qa_service import AIQAService
from ai_teacher_state import AITeacherRepository
from models import AskQuestionRequest
from routers import assistant as assistant_router


def _events(chunks: list[str]) -> list[tuple[str, dict]]:
    parsed: list[tuple[str, dict]] = []
    for block in "".join(chunks).replace("\r\n", "\n").split("\n\n"):
        name = ""
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].lstrip())
        if not name or not data_lines:
            continue
        try:
            parsed.append((name, json.loads("\n".join(data_lines))))
        except json.JSONDecodeError:
            continue
    return parsed


def _wire(monkeypatch, tmp_path, service) -> AITeacherRepository:
    repository = AITeacherRepository(tmp_path / "ai-teacher")

    async def get_course(course_id: str):
        return {
            "course_id": course_id,
            "course_name": "线性代数",
            "current_course_version_id": "cv-1",
            "nodes": [{
                "node_id": "node-1",
                "node_name": "向量",
                "node_level": 2,
                "node_content": "向量同时具有大小和方向。",
            }],
        }

    monkeypatch.delenv("EVOLUTION_DEMO_MODE", raising=False)
    monkeypatch.setattr(assistant_router, "ai_teacher_repository", repository)
    monkeypatch.setattr(assistant_router, "get_course_or_404", get_course)
    monkeypatch.setattr(
        assistant_router,
        "build_ai_teacher_context",
        lambda *_a, **_k: {"conversation": {"recent_messages": []}},
    )
    monkeypatch.setattr(
        assistant_router,
        "context_public_summary",
        lambda _p: {"scene": {"node_id": "node-1"}, "sources": []},
    )
    monkeypatch.setattr(assistant_router, "record_learning_event", lambda **_p: None)
    monkeypatch.setattr(assistant_router, "record_course_evolution_request", lambda *_a, **_k: None)
    if service is not None:
        monkeypatch.setattr(assistant_router, "ai_service", service)
    return repository


class _StallingService(AIQAService):
    """Streams a little, then hangs — the shape a real cancel interrupts."""

    async def _stream_llm(self, *_a, **_k):
        yield "线性相关的意思是存在一组不全为零的系数"
        await asyncio.sleep(30)
        yield "永远到不了"  # pragma: no cover - cancelled first


class _ChunkyService(AIQAService):
    async def _stream_llm(self, *_a, **_k):
        for piece in "线性相关的意思是存在非零系数组合":
            yield piece


class _BufferedService(AIQAService):
    async def _stream_llm(self, *_a, **_k):
        await asyncio.sleep(0.12)
        yield "本地模型完整回答"

    def stream_delivery_mode(self) -> str:
        return "buffered_fallback"


async def _request(repository_service, question="什么是线性相关？", **extra):
    request = AskQuestionRequest(
        course_id="course-1",
        question=question,
        node_id="node-1",
        node_name="向量",
        **extra,
    )

    class _Request:
        headers = {"X-User-Id": "u1"}

    response = await assistant_router.ask_question_events(request, _Request())
    return response.body_iterator


@pytest.mark.asyncio
async def test_cancelled_answer_persists_what_the_learner_already_read(monkeypatch, tmp_path):
    repository = _wire(monkeypatch, tmp_path, _StallingService())
    stream = await _request(repository)

    seen: list[str] = []
    while True:
        try:
            seen.append(await asyncio.wait_for(stream.__anext__(), timeout=1.0))
        except (asyncio.TimeoutError, StopAsyncIteration):
            break
    await stream.aclose()  # the learner pressed stop / navigated away
    await asyncio.sleep(0)

    streamed = "".join(
        payload.get("chunk", "")
        for name, payload in _events(seen)
        if name == "answer"
    )
    assert streamed, "the learner should have seen some answer text"

    conversation = repository.list_conversations("u1", "course-1")[0]
    assistant = [m for m in conversation["messages"] if m["role"] == "assistant"]
    assert len(assistant) == 1, "a cancelled turn must still leave exactly one assistant message"
    assert assistant[0]["status"] == "failed"
    assert assistant[0]["failure_code"] == "cancelled"
    # What was persisted must be what the learner actually saw — not more.
    assert assistant[0]["content"] == streamed


@pytest.mark.asyncio
async def test_cancelled_answer_records_no_completed_answer_event(monkeypatch, tmp_path):
    recorded: list[dict] = []
    repository = _wire(monkeypatch, tmp_path, _StallingService())
    monkeypatch.setattr(
        assistant_router,
        "record_learning_event",
        lambda **payload: recorded.append(payload),
    )
    stream = await _request(repository)

    while True:
        try:
            await asyncio.wait_for(stream.__anext__(), timeout=1.0)
        except (asyncio.TimeoutError, StopAsyncIteration):
            break
    await stream.aclose()
    await asyncio.sleep(0)

    types = [event["event_type"] for event in recorded]
    assert "assistant_answer_completed" not in types
    assert "assistant_answer_cancelled" in types


@pytest.mark.asyncio
async def test_answer_stream_emits_exactly_one_final_answer(monkeypatch, tmp_path):
    """Two different `final_answer` blocks let a client show an unpersisted answer."""
    repository = _wire(monkeypatch, tmp_path, _ChunkyService())
    stream = await _request(repository)

    blocks = [block async for block in stream]
    events = _events(blocks)

    finals = [payload for name, payload in events if name == "final_answer"]
    assert len(finals) == 1
    conversation = repository.list_conversations("u1", "course-1")[0]
    assistant = [m for m in conversation["messages"] if m["role"] == "assistant"][0]
    assert finals[0]["answer"] == assistant["content"]
    assert finals[0]["message_id"] == assistant["message_id"]


@pytest.mark.asyncio
async def test_buffered_model_gets_immediate_status_and_truthful_heartbeats(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("AI_ASSISTANT_STREAM_HEARTBEAT_SECONDS", "0.05")
    repository = _wire(monkeypatch, tmp_path, _BufferedService())
    stream = await _request(repository)

    first = _events([await stream.__anext__()])
    remaining = _events([block async for block in stream])
    statuses = [payload for name, payload in first + remaining if name == "status"]

    assert first[0][0] == "status"
    assert first[0][1]["stage"] == "accepted"
    assert any(
        item["stage"] == "generating"
        and item["delivery_mode"] == "buffered_fallback"
        and item["elapsed_ms"] >= 50
        for item in statuses
    )
    assert "".join(
        payload.get("chunk", "")
        for name, payload in remaining
        if name == "answer"
    ) == "本地模型完整回答"


@pytest.mark.asyncio
async def test_answer_chunks_are_not_withheld_behind_a_metadata_delimiter(monkeypatch, tmp_path):
    """Everything the model produced must reach the client as `answer` chunks.

    The delimiter guard used to hold back a fixed-length tail forever when the
    model never emitted `---METADATA---`, which is the normal case.
    """
    repository = _wire(monkeypatch, tmp_path, _ChunkyService())
    stream = await _request(repository)

    events = _events([block async for block in stream])
    streamed = "".join(
        payload.get("chunk", "")
        for name, payload in events
        if name == "answer"
    )
    finals = [payload for name, payload in events if name == "final_answer"]

    assert streamed == "线性相关的意思是存在非零系数组合"
    assert finals[0]["answer"] == streamed


@pytest.mark.asyncio
async def test_metadata_block_is_still_stripped_from_the_visible_answer(monkeypatch, tmp_path):
    """The delimiter must keep working when the model does emit it."""

    class _WithMetadata(AIQAService):
        async def _stream_llm(self, *_a, **_k):
            yield "线性相关的意思是存在非零系数组合"
            yield "\n---METADATA---\n"
            yield '{"confidence": "high"}'

    repository = _wire(monkeypatch, tmp_path, _WithMetadata())
    stream = await _request(repository)

    events = _events([block async for block in stream])
    streamed = "".join(
        payload.get("chunk", "")
        for name, payload in events
        if name == "answer"
    )

    assert "METADATA" not in streamed
    assert "confidence" not in streamed
    assert streamed.strip() == "线性相关的意思是存在非零系数组合"


@pytest.mark.asyncio
async def test_cancelling_a_direct_action_does_not_leave_a_dangling_proposal(
    monkeypatch,
    tmp_path,
):
    """A direct "save this as a note" that is cancelled must not stay pending.

    A proposal left in `presented` is a half-action: it survives the cancel and
    can still be confirmed later against context the learner abandoned.
    """
    repository = _wire(monkeypatch, tmp_path, None)
    real_propose = assistant_router.propose_action

    def propose(*args, **kwargs):
        kwargs.setdefault("repository", repository)
        return real_propose(*args, **kwargs)

    def execute(*_args, **_kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(assistant_router, "propose_action", propose)
    monkeypatch.setattr(assistant_router, "execute_proposal", execute)

    stream = await _request(
        repository,
        question="帮我记成笔记",
        selection="向量同时具有大小和方向。",
    )
    with pytest.raises(asyncio.CancelledError):
        async for _ in stream:
            pass
    await stream.aclose()

    leftover = [
        proposal
        for proposal in _all_proposals(repository)
        if proposal["status"] in {"presented", "confirmed", "executing"}
    ]
    assert leftover == [], f"cancelled direct action left {leftover}"


def _all_proposals(repository: AITeacherRepository) -> list[dict]:
    proposals: list[dict] = []
    for path in repository.root.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        proposals.extend(data.get("proposals", []))
    return proposals
