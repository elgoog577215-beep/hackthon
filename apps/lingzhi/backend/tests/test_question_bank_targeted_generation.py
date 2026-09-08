from __future__ import annotations

import asyncio
from copy import deepcopy
from types import SimpleNamespace

from assessment_orchestrator import (
    UniversalAssessmentModel,
    _apply_targeted_repair_candidate,
)
from routers.question_bank import (
    _item_practice_levels_by_node,
    _settled_chapter_contracts,
)


def test_item_scope_resolves_only_the_selected_question_slot() -> None:
    bundle = {
        "items": [
            {
                "revision_id": "revision-concept",
                "node_id": "node-1",
                "practice_levels": ["concept_check"],
            },
            {
                "revision_id": "revision-objective",
                "node_id": "node-1",
                "practice_levels": ["objective_practice"],
            },
        ],
    }

    assert _item_practice_levels_by_node(
        bundle,
        revision_ids=["revision-objective"],
    ) == {"node-1": ["objective_practice"]}


def test_partial_chapter_keeps_only_individually_settled_contracts() -> None:
    event = {
        "passed": False,
        "settled_practice_levels": [
            "concept_check",
            "objective_practice",
        ],
        "contracts": {
            "concept_check": {"prompt": "概念题"},
            "objective_practice": {"prompt": "应用题"},
            "mastery_check": {"prompt": "失败题"},
        },
        "audit_items": [
            {"practice_level": "concept_check", "final_decision": "publish"},
            {"practice_level": "objective_practice", "final_decision": "publish"},
            {"practice_level": "mastery_check", "final_decision": "discard"},
        ],
    }

    contracts, audit_items = _settled_chapter_contracts(event)

    assert set(contracts) == {"concept_check", "objective_practice"}
    assert {
        item["practice_level"] for item in audit_items
    } == {"concept_check", "objective_practice"}


def test_worked_solution_repair_restores_unrelated_model_changes() -> None:
    original = {
        "question_spec": {
            "stimulus": {"rendered_text": "保持不变的公开题面材料。"},
            "task": {"rendered_text": "保持不变的作答要求。"},
            "options": [],
        },
        "solution": {
            "canonical_answer": "42",
            "solution_graph": {"steps": []},
            "worked_solution": {"summary": "不完整"},
        },
    }
    model_repair = deepcopy(original)
    model_repair["question_spec"]["stimulus"]["rendered_text"] = "越界修改题面"
    model_repair["solution"]["canonical_answer"] = "99"
    model_repair["solution"]["worked_solution"] = {
        "summary": "完整解析",
        "steps": ["代入并计算"],
        "final_answer": "42",
        "checks": ["回代成立"],
    }

    repaired, audit = _apply_targeted_repair_candidate(
        original,
        model_repair,
        issue_codes=["WORKED_SOLUTION_INCOMPLETE"],
    )

    assert repaired["question_spec"] == original["question_spec"]
    assert repaired["solution"]["canonical_answer"] == "42"
    assert repaired["solution"]["worked_solution"]["summary"] == "完整解析"
    assert audit["changed_paths"] == ["solution.worked_solution"]
    assert "question_spec.stimulus" in audit["restored_paths"]
    assert "solution.canonical_answer" in audit["restored_paths"]


def test_assessment_timeout_starts_inside_provider_after_capacity_wait() -> None:
    captured: dict = {}

    class CapacityWaitingModel:
        async def _call_llm(self, _prompt: str, **kwargs):
            captured.update(kwargs)
            await asyncio.sleep(0.02)
            return "{}"

    policy = SimpleNamespace(
        max_provider_attempts=None,
        physical_call_telemetry=[],
        timeout_seconds=0.001,
        stage="generate",
    )

    result = asyncio.run(
        UniversalAssessmentModel._assessment_llm_call(
            CapacityWaitingModel(),
            policy,
            "测试容量排队",
        )
    )

    assert result == "{}"
    assert captured["wait_for_capacity"] is True
    assert captured["request_timeout_seconds"] == 0.001
