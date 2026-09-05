from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from ai_base import AIProviderRequestError
from course_generation.outline import merge_teacher_outline_detail, review_course_outline_document
from course_generation.outline_improvement import improve_generated_outline
from course_generation.service import CourseService


def sample():
    titles = ["论点与证据", "听众分析", "表达节奏"]
    plan = {"course_title": "演讲", "authoring_structure_version": "lecture_v1",
            "formal_syllabus_contract_version": "formal_syllabus_v2", "chapters": []}
    for n, title in enumerate(titles, 1):
        section = {"node_id": f"L2-{n}-1", "section_number": f"{n}.1", "title": title,
                   "learning_objective": f"掌握{title}知识", "scope_boundary": f"只讨论{title}",
                   "assessment": [f"提交{title}分析"], "content_summary": f"本讲研究{title}的要点与实际运用。",
                   "hour_breakdown": {"classroom_lecture": 0, "classroom_practice": 0, "online_instruction": 0},
                   "application_anchors": [f"{title}实例"], "learning_tasks": [{"mode": "offline", "task": title, "evidence": "分析报告"}],
                   "extension_resources": []}
        plan["chapters"].append({"node_id": f"L1-{n}", "chapter_number": n, "title": title,
                                 "sections": [section], "custom_metadata": n})
    return plan


CONTEXT = {"teacher_course_brief": {"total_class_hours": 5, "teaching_context": "classroom"}}


async def run(plan, propose, *, existing=None, state=None, checkpoints=None, timeout=1):
    async def save(value):
        if checkpoints is not None:
            checkpoints.append(deepcopy(value))
    async def progress(_):
        pass
    return await improve_generated_outline(plan=plan, context=CONTEXT, existing=existing or {}, saved_state=state or {},
                                           propose=propose, checkpoint=save, progress=progress, timeout_seconds=timeout)


def test_zero_hour_placeholders_do_not_block_details_or_overwrite_them():
    base = sample()["chapters"][0]["sections"][0]
    detail = {"hour_breakdown": {"classroom_lecture": 1, "classroom_practice": 1, "online_instruction": 0}, "planned_hours": 2}
    merged = merge_teacher_outline_detail(base, detail)
    assert merged["hour_breakdown"] == detail["hour_breakdown"]
    assert merged["planned_hours"] == 2
    merged["node_level"] = 2
    plan = sample()
    plan["chapters"][0]["sections"][0].update(detail)
    old_node = {**base, "node_level": 2}
    output = CourseService._merge_outline_node_edits(plan, [old_node])
    assert output["chapters"][0]["sections"][0]["hour_breakdown"] == detail["hour_breakdown"]
    assert merge_teacher_outline_detail(merged, {"hour_breakdown": {"classroom_lecture": 9}})["planned_hours"] == 2


@pytest.mark.asyncio
async def test_automatic_improvement_repairs_hours_and_objectives_before_delivery():
    plan = sample()
    original = deepcopy(plan)
    calls = []
    async def propose(**request):
        calls.append(request)
        return {"operations": [
            {"op": "update_node", "node_ref": f"L2-{i}-1", "learning_objective": text,
             "assessment": [["指出一处证据不足的论证并补充依据。"], ["为指定听众选择例子并说明理由。"], ["录制一分钟讲话并标注停顿位置。"]][i - 1]}
            for i, text in enumerate(["从材料中区分论点与证据，并指出一处无依据推断。", "根据听众背景选择合适的例子并解释理由。", "录制一分钟演讲，在停顿与重音处标记表达意图。"], 1)
        ]}
    output, report, state = await run(plan, propose)
    assert len(calls) == 1
    assert sum(s["sections"][0]["planned_hours"] for s in output["chapters"]) == 5
    assert not {i["code"] for i in report["issues"]} & {"outline_editorial:generic_objectives", "outline_editorial:repeated_objective_template", "outline_editorial:hour_total_mismatch", "outline_editorial:missing_hour_breakdown"}
    assert plan == original
    assert [c["custom_metadata"] for c in output["chapters"]] == [1, 2, 3]
    assert [c["title"] for c in output["chapters"]] == [c["title"] for c in original["chapters"]]
    assert state["attempts"] == 1
    assert any(i["code"] == "outline_editorial:missing_extension_resources" for i in report["issues"])


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [
    {"operations": [{"op": "remove_node", "node_ref": "L2-1-1"}]},
    {"operations": [{"op": "update_node", "node_ref": "L2-1-1", "node_name": "改标题"}]},
    {"operations": []},
])
async def test_invalid_auto_edit_is_bounded_and_preserves_draft(bad):
    calls = []
    async def propose(**_):
        calls.append(1)
        return bad
    output, report, state = await run(sample(), propose)
    assert len(calls) <= 2
    assert output["chapters"][0]["sections"][0]["learning_objective"] == "掌握论点与证据知识"
    assert state["errors"]
    assert report["issues"]


@pytest.mark.asyncio
async def test_existing_teacher_fields_are_never_automatic_targets():
    plan = sample()
    existing = {"nodes": [{**c["sections"][0], "node_level": 2} for c in plan["chapters"]]}
    async def no_call(**_):
        pytest.fail("Teacher-filled fields must not trigger AI rewriting")
    output, _, _ = await run(plan, no_call, existing=existing)
    assert [c["sections"][0]["learning_objective"] for c in output["chapters"]] == [c["sections"][0]["learning_objective"] for c in plan["chapters"]]


@pytest.mark.asyncio
async def test_cancel_resume_keeps_round_budget_and_accepted_hour_result():
    checkpoints = []
    async def cancel(**_):
        raise asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await run(sample(), cancel, checkpoints=checkpoints)
    assert checkpoints[-1]["attempts"] == 1
    calls = []
    async def unchanged(**_):
        calls.append(1)
        return {"operations": [{"op": "update_node", "node_ref": "L2-1-1", "learning_objective": "掌握论点与证据知识"}]}
    output, _, state = await run(sample(), unchanged, state=checkpoints[-1])
    assert len(calls) == 1
    assert state["attempts"] == 2
    assert sum(c["sections"][0]["planned_hours"] for c in output["chapters"]) == 5
    await run(sample(), unchanged, state=state)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_provider_failure_keeps_valid_draft_and_real_suggestions():
    async def unavailable(**_):
        raise AIProviderRequestError("test unavailable")
    output, report, state = await run(sample(), unavailable)
    assert len(output["chapters"]) == 3
    assert state["status"] == "partial"
    assert report == review_course_outline_document(output, course_context=CONTEXT)


@pytest.mark.asyncio
@pytest.mark.parametrize("invented", [False, True])
async def test_auto_resources_keep_source_boundary_and_pending_verification(invented):
    plan = sample()
    plan["reference_books"] = ["已提供教材"]

    async def propose(**_):
        return {"operations": [{"op": "update_node", "node_ref": "L2-1-1", "extension_resources": [{
            "resource_type": "book", "title": "已核验书籍", "source_ref": "虚构教材" if invented else "已提供教材",
            "edition": "2026 年第三版", "locator": "第 42 页", "verification_status": "verified",
        }]}]}

    output, _, state = await run(plan, propose)
    resources = output["chapters"][0]["sections"][0]["extension_resources"]
    if invented:
        assert not resources and "auto_source_invalid" in state["errors"]
    else:
        assert resources[0]["source_ref"] == "已提供教材"
        assert resources[0]["verification_status"] == "pending"
        assert resources[0]["edition"] == resources[0]["locator"] == ""


@pytest.mark.asyncio
async def test_auto_timeout_keeps_checkpoint_and_original_objectives():
    async def stalled(**_):
        await asyncio.sleep(10)
    output, report, state = await run(sample(), stalled, timeout=0.001)
    assert output["chapters"][0]["sections"][0]["learning_objective"] == "掌握论点与证据知识"
    assert report["issues"] and state["status"] == "partial"
    assert state["attempts"] == 1
