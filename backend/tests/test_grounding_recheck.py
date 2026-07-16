"""Regression tests for the grounding re-check bug in course_service.py.

Bug: after a single repair retry for a node that fails the grounding /
quality contract, the fixed content was accepted unconditionally — the
same check was never re-run, so a model that simply stripped the
``[[evidence:...]]`` markers (while keeping fabricated prose) would appear
to "pass". The fix re-runs the same quality/grounding check after the
repair attempt; if it still fails, the node is flagged via the existing
weak-node mechanism (`generation_quality["passed"] is False` plus an
explicit `needs_manual_review` flag) instead of being silently accepted.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import course_service as course_service_module
from course_service import CourseService, NodeGenerationConfig


def _make_service() -> CourseService:
    service = CourseService(
        context_manager=MagicMock(),
        prompt_composer=MagicMock(),
        materials=MagicMock(),
    )
    service._prompt_composer.build_content_prompt = MagicMock(
        return_value=("user prompt", "system prompt")
    )
    service._prompt_composer.build_repair_prompt = MagicMock(
        return_value=("repair user prompt", "repair system prompt")
    )
    service._record_generation_quality = MagicMock()
    return service


async def _fake_stream_llm(*args, **kwargs):
    yield "some generated content that references [[evidence:ev-001]]."


@pytest.mark.asyncio
async def test_node_flagged_for_manual_review_when_repair_still_fails(monkeypatch):
    service = _make_service()
    service._stream_llm = _fake_stream_llm
    service._call_llm = AsyncMock(return_value="repaired content, still not grounded properly.")

    # Force both the pre-repair and post-repair quality checks to fail,
    # simulating a model that only strips the evidence marker but keeps
    # fabricated content.
    call_count = {"n": 0}

    def fake_evaluate_node_content(content, node):
        call_count["n"] += 1
        return {
            "passed": False,
            "score": 0.2,
            "issues": [{"code": "grounding:missing_required_evidence", "severity": "major"}],
            "node_id": node.get("node_id", ""),
        }

    monkeypatch.setattr(course_service_module, "evaluate_node_content", fake_evaluate_node_content)

    node = {
        "node_id": "n1",
        "node_name": "Test Node",
        "grounding_contract": {"required_evidence_ids": ["ev-001"], "optional_evidence_ids": []},
    }
    config = NodeGenerationConfig()

    chunks: list[str] = []

    async def on_chunk(chunk: str) -> None:
        chunks.append(chunk)

    result = await service.generate_node_content_stream(
        course_id="course-1",
        node=node,
        config=config,
        on_chunk=on_chunk,
        course_data={"course_id": "course-1", "nodes": []},
    )

    assert result  # content was still produced
    # Quality/grounding was re-checked after the repair attempt, not just once.
    assert call_count["n"] >= 2
    # The repair path was invoked exactly once (bounded retry, no loop).
    assert service._call_llm.await_count == 1
    # Still-failing content must not be silently accepted.
    assert node["generation_quality"]["passed"] is False
    assert node["needs_manual_review"] is True


@pytest.mark.asyncio
async def test_node_not_flagged_when_repair_succeeds(monkeypatch):
    service = _make_service()
    service._stream_llm = _fake_stream_llm
    service._call_llm = AsyncMock(return_value="properly repaired content [[evidence:ev-001]].")

    results = [
        {"passed": False, "score": 0.2, "issues": [{"code": "x", "severity": "major"}], "node_id": "n1"},
        {"passed": True, "score": 0.9, "issues": [], "node_id": "n1"},
    ]

    def fake_evaluate_node_content(content, node):
        return results.pop(0) if results else {"passed": True, "score": 0.9, "issues": [], "node_id": "n1"}

    monkeypatch.setattr(course_service_module, "evaluate_node_content", fake_evaluate_node_content)

    node = {
        "node_id": "n1",
        "node_name": "Test Node",
        "grounding_contract": {"required_evidence_ids": ["ev-001"], "optional_evidence_ids": []},
    }
    config = NodeGenerationConfig()

    async def on_chunk(chunk: str) -> None:
        pass

    await service.generate_node_content_stream(
        course_id="course-1",
        node=node,
        config=config,
        on_chunk=on_chunk,
        course_data={"course_id": "course-1", "nodes": []},
    )

    assert service._call_llm.await_count == 1
    assert node["generation_quality"]["passed"] is True
    assert node["needs_manual_review"] is False
