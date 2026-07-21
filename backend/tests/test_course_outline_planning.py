from __future__ import annotations

import asyncio
import json
import re
from copy import deepcopy

import pytest

from ai_base import AIBase
from course_generation_workflow import (
    _extract_course_shape_constraints,
    build_course_knowledge_scope_contract,
    build_section_knowledge_scope_slice,
)
from course_outline_planning import (
    CourseOutlinePlanningBudget,
    assemble_course_outline,
    build_outline_batch_specs,
    compile_fallback_outline_batch,
    normalize_outline_skeleton,
    outline_request_fingerprint,
    validate_outline_batch,
    validate_outline_skeleton,
)
from course_service import CourseService


def _outline_skeleton_payload(
    *,
    chapter_count: int,
    sections_per_chapter: int,
) -> str:
    return json.dumps({
        "course_title": "大规模并行课程",
        "positioning": "验证结构化分片、恢复与并行生成",
        "learning_objectives": ["完成一门可检查的大规模课程"],
        "prerequisites": [],
        "chapters": [
            {
                "chapter_number": index,
                "title": f"第 {index} 章",
                "learning_focus": f"完成阶段 {index}",
                "section_count": sections_per_chapter,
            }
            for index in range(1, chapter_count + 1)
        ],
    }, ensure_ascii=False)


def _outline_batch_payload(system_prompt: str) -> str:
    match = re.search(
        r"## 当前批次\n(\{.*?\})\n\n## 当前章已完成",
        system_prompt,
        re.S,
    )
    assert match, system_prompt
    spec = json.loads(match.group(1))
    return json.dumps({
        "sections": [
            {
                "node_id": node_id,
                "title": f"任务 {node_id}",
                "learning_objective": f"独立完成 {node_id}",
                "prerequisite_node_ids": [],
                "assessment": [f"提交 {node_id} 结果"],
                "scope_boundary": f"只负责 {node_id}",
            }
            for node_id in spec["expected_node_ids"]
        ],
    }, ensure_ascii=False)


def test_total_course_size_is_not_an_outline_budget_dimension():
    budget = CourseOutlinePlanningBudget()

    assert budget.choose_mode({"section_count": 6}) == "compact"
    assert budget.choose_mode({"section_count": 120}) == "hierarchical"
    assert not hasattr(budget, "max_sections")
    assert _extract_course_shape_constraints(
        "生成 20 章，共 120 个小节",
    ) == {
        "chapter_count": 20,
        "section_count": 120,
    }


def test_compact_outline_cannot_smuggle_a_large_result_past_the_shard_router():
    service = CourseService()
    response = json.dumps({
        "course_title": "意外大目录",
        "positioning": "应切换到分片链",
        "chapters": [{
            "chapter_number": 1,
            "title": "主线",
            "sections": [
                {
                    "node_id": f"L2-1-{index}",
                    "section_number": f"1.{index}",
                    "title": f"任务 {index}",
                }
                for index in range(1, 8)
            ],
        }],
    }, ensure_ascii=False)

    plan, report = service._validated_compact_course_outline(
        response,
        {"course_shape_constraints": {}},
    )

    assert plan is not None
    assert report["passed"] is False
    assert any(
        issue["code"] == "outline:compact_unit_exceeded"
        for issue in report["issues"]
    )


def test_large_outline_is_split_per_chapter_and_locally_assembled():
    shape = {"chapter_count": 8, "section_count": 48}
    fingerprint = outline_request_fingerprint(
        topic="并行系统",
        audience="undergraduate",
        brief={"course_shape_constraints": shape},
        difficulty_profile={"level": "intermediate"},
    )
    skeleton = normalize_outline_skeleton(
        {
            "course_title": "并行系统",
            "positioning": "验证大课目录分片",
            "learning_objectives": ["完成 48 节递进任务"],
            "prerequisites": [],
            "chapters": [
                {
                    "title": f"并行系统阶段 {index}",
                    "learning_focus": f"完成第 {index} 阶段任务",
                    "section_count": 6,
                }
                for index in range(1, 9)
            ],
        },
        topic="并行系统",
        request_fingerprint=fingerprint,
    )
    report = validate_outline_skeleton(
        skeleton,
        shape_constraints=shape,
        request_fingerprint=fingerprint,
    )
    assert report["passed"]

    specs = build_outline_batch_specs(
        skeleton,
        CourseOutlinePlanningBudget(batch_max_sections=6),
    )
    assert len(specs) == 8
    assert all(spec["section_count"] <= 6 for spec in specs)

    chapter_by_number = {
        item["chapter_number"]: item
        for item in skeleton["chapters"]
    }
    batches = {
        spec["batch_id"]: compile_fallback_outline_batch(
            spec=spec,
            chapter=chapter_by_number[spec["chapter_number"]],
            skeleton_revision_id=skeleton["revision_id"],
        )
        for spec in specs
    }
    assert all(
        validate_outline_batch(
            batches[spec["batch_id"]],
            spec=spec,
            skeleton_revision_id=skeleton["revision_id"],
        )["passed"]
        for spec in specs
    )

    outline = assemble_course_outline(
        skeleton=skeleton,
        batch_specs=specs,
        batches=batches,
    )
    assert len(outline["chapters"]) == 8
    assert sum(
        len(chapter["sections"])
        for chapter in outline["chapters"]
    ) == 48


@pytest.mark.asyncio
async def test_forty_eight_section_outline_uses_parallel_bounded_batches(
    monkeypatch,
):
    service = CourseService(planning_concurrency=4)
    active = 0
    max_active = 0
    payloads: list[tuple[str, str, dict]] = []

    async def fake_call(prompt, system_prompt="", **kwargs):
        nonlocal active, max_active
        payloads.append((prompt, system_prompt, kwargs))
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        if "全课章节骨架 V2" in system_prompt:
            return _outline_skeleton_payload(
                chapter_count=8,
                sections_per_chapter=6,
            )
        if "章节小节目录批次 V2" in system_prompt:
            return _outline_batch_payload(system_prompt)
        raise AssertionError(system_prompt)

    monkeypatch.setattr(service, "_call_llm", fake_call)
    result = await service.build_course_draft(
        course_id="course-outline-48",
        topic="并行系统",
        requirements="生成 8 章，共 48 个小节",
        stop_after_outline=True,
    )

    outline = result["course_outline"]
    assert len(outline["chapters"]) == 8
    assert sum(
        len(chapter["sections"])
        for chapter in outline["chapters"]
    ) == 48
    stage = result["generation_stage_artifacts"]["outline"]
    assert stage["strategy"] == "hierarchical_chapter_batches"
    assert stage["batch_count"] == 8
    assert stage["completed_batch_count"] == 8
    assert stage["fallback_units"] == []
    assert max_active >= 2
    assert max_active <= 4
    assert len(payloads) == 9
    for user_prompt, system_prompt, kwargs in payloads:
        assert len(user_prompt) + len(system_prompt) <= 20_000
        assert AIBase.estimate_request_tokens(
            user_prompt,
            system_prompt,
        ) <= 7_000
        assert kwargs["max_input_chars"] == 20_000
        assert kwargs["max_input_tokens"] == 7_000


@pytest.mark.asyncio
async def test_outline_waits_for_productive_batches_without_whole_course_deadline(
    monkeypatch,
):
    service = CourseService(planning_concurrency=2)
    service._outline_budget = CourseOutlinePlanningBudget(
        compact_max_sections=6,
        batch_max_sections=6,
        batch_timeout_seconds=1,
        total_timeout_seconds=0.02,
    )

    async def fake_call(prompt, system_prompt="", **kwargs):
        if "全课章节骨架 V2" in system_prompt:
            return _outline_skeleton_payload(
                chapter_count=4,
                sections_per_chapter=6,
            )
        if "章节小节目录批次 V2" in system_prompt:
            await asyncio.sleep(0.2)
            return _outline_batch_payload(system_prompt)
        raise AssertionError(system_prompt)

    monkeypatch.setattr(service, "_call_llm", fake_call)
    result = await service.build_course_draft(
        course_id="course-outline-timeout",
        topic="并行系统",
        requirements="生成 4 章，共 24 个小节",
        stop_after_outline=True,
    )

    outline = result["course_outline"]
    assert sum(
        len(chapter["sections"])
        for chapter in outline["chapters"]
    ) == 24
    stage = result["generation_stage_artifacts"]["outline"]
    assert stage["timed_out"] is False
    assert stage["status"] == "completed"
    assert stage["needs_manual_review"] is False
    assert stage["fallback_units"] == []


@pytest.mark.asyncio
async def test_outline_resume_only_requests_missing_chapter_batch(monkeypatch):
    first_service = CourseService(planning_concurrency=3)

    async def first_call(prompt, system_prompt="", **kwargs):
        if "全课章节骨架 V2" in system_prompt:
            return _outline_skeleton_payload(
                chapter_count=3,
                sections_per_chapter=6,
            )
        if "章节小节目录批次 V2" in system_prompt:
            return _outline_batch_payload(system_prompt)
        raise AssertionError(system_prompt)

    monkeypatch.setattr(first_service, "_call_llm", first_call)
    completed = await first_service.build_course_draft(
        course_id="course-outline-resume",
        topic="并行系统",
        requirements="生成 3 章，共 18 个小节",
        stop_after_outline=True,
    )
    checkpoint = deepcopy(completed)
    checkpoint.pop("course_outline", None)
    checkpoint.pop("course_plan", None)
    outline_stage = checkpoint["generation_stage_artifacts"]["outline"]
    outline_stage["batches"].pop("OUT-C002-B001")
    outline_stage["status"] = "in_progress"
    outline_stage["completed_batch_count"] = 2
    outline_stage["completed_section_count"] = 12

    resumed_calls: list[str] = []
    resumed_service = CourseService(planning_concurrency=3)

    async def resumed_call(prompt, system_prompt="", **kwargs):
        resumed_calls.append(system_prompt)
        assert "章节小节目录批次 V2" in system_prompt
        return _outline_batch_payload(system_prompt)

    monkeypatch.setattr(resumed_service, "_call_llm", resumed_call)
    resumed = await resumed_service.build_course_draft(
        course_id="course-outline-resume",
        topic="并行系统",
        requirements="生成 3 章，共 18 个小节",
        existing_course_data=checkpoint,
        stop_after_outline=True,
    )

    assert len(resumed_calls) == 1
    assert "OUT-C002-B001" in resumed_calls[0]
    assert sum(
        len(chapter["sections"])
        for chapter in resumed["course_outline"]["chapters"]
    ) == 18
    assert (
        resumed["generation_stage_artifacts"]["outline"]["status"]
        == "completed"
    )


def test_outline_fingerprint_ignores_ephemeral_brief_id():
    from course_outline_planning import outline_request_fingerprint

    common = {
        "topic": "并行系统",
        "audience": "大学生",
        "difficulty_profile": {"level": "intermediate"},
    }
    first = outline_request_fingerprint(
        **common,
        brief={"brief_id": "brief-first", "goal": "学会并行系统"},
    )
    second = outline_request_fingerprint(
        **common,
        brief={"brief_id": "brief-second", "goal": "学会并行系统"},
    )

    assert first == second


def test_section_scope_payload_stays_linear_and_each_slice_is_bounded():
    def make_plan(section_count: int) -> dict:
        return {
            "course_title": "线性上下文验证",
            "positioning": "验证大课不会重复广播全部前后小节",
            "learning_objectives": ["完成全部递进任务"],
            "prerequisites": [],
            "chapters": [{
                "chapter_number": 1,
                "title": "主线",
                "sections": [
                    {
                        "node_id": f"L2-1-{index}",
                        "section_number": f"1.{index}",
                        "title": f"任务 {index}",
                        "learning_objective": f"完成任务 {index}",
                        "scope_boundary": f"只负责任务 {index}",
                        "prerequisite_node_ids": (
                            [f"L2-1-{index - 1}"] if index > 1 else []
                        ),
                    }
                    for index in range(1, section_count + 1)
                ],
            }],
        }

    contract_50 = build_course_knowledge_scope_contract(make_plan(50))
    contract_100 = build_course_knowledge_scope_contract(make_plan(100))
    size_50 = len(json.dumps(contract_50, ensure_ascii=False))
    size_100 = len(json.dumps(contract_100, ensure_ascii=False))
    assert size_100 < size_50 * 2.2
    assert all(
        "earlier_section_ids" not in item
        and "later_reserved_sections" not in item
        for item in contract_100["section_responsibilities"]
    )

    middle = build_section_knowledge_scope_slice(
        contract_100,
        "L2-1-50",
    )
    assert middle["schema_version"] == (
        "section_knowledge_scope_slice_v2"
    )
    assert len(middle["local_course_path"]) <= 3
