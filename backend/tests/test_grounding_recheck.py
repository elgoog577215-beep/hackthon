"""Regression tests for deterministic post-generation diagnostics.

Content is generated once. Heuristic findings are recorded without starting
another model scoring/repair chain; only critical structural findings request
manual review.
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
async def test_nonblocking_diagnostic_does_not_start_ai_repair(monkeypatch):
    service = _make_service()
    service._stream_llm = _fake_stream_llm
    service._call_llm = AsyncMock(return_value="repaired content, still not grounded properly.")

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
    assert call_count["n"] == 1
    assert service._call_llm.await_count == 0
    assert node["generation_quality"]["passed"] is False
    assert node["needs_manual_review"] is False


@pytest.mark.asyncio
async def test_critical_structural_diagnostic_requests_manual_review_without_ai(monkeypatch):
    service = _make_service()
    service._stream_llm = _fake_stream_llm
    service._call_llm = AsyncMock(return_value="properly repaired content [[evidence:ev-001]].")

    def fake_evaluate_node_content(content, node):
        return {
            "passed": False,
            "score": 0.2,
            "issues": [{
                "code": "unclosed_code_fence",
                "severity": "critical",
            }],
            "node_id": "n1",
        }

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

    assert service._call_llm.await_count == 0
    assert node["generation_quality"]["passed"] is False
    assert node["needs_manual_review"] is True
