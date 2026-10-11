"""Exercise the real preflight gate, without network requests or course writes."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from ai_base import AIBase
from backend.tests.test_knowledge_first import svc, initialize, start, tree_response
from course_knowledge_context import knowledge_context_prompt


@pytest.mark.asyncio
async def test_tree_prompt_fits_real_input_gate_without_dropping_material(svc):
    svc.storage.update_course_data("c-pilot", lambda raw: {**raw,
        "generation_request": {"requirements": "理解计算机系统中的类型转换与控制流，能够说明判断依据与适用条件。" * 25}})
    initialize(svc)
    job = start(svc, "tree", "real-budget-gate")
    frozen = deepcopy(job["request_snapshot"]["knowledge_generation_context"])
    wire_calls = []
    async def call(prompt, **kwargs):
        AIBase.validate_request_budget(prompt, kwargs["system_prompt"], kwargs["max_input_tokens"])
        wire_calls.append(1)
        for unit in frozen["evidence_package"]["units"]:
            assert json.dumps(unit["source_text"], ensure_ascii=False) in prompt
        return json.dumps(tree_response(), ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart="test", client=None)
    await svc.run("c-pilot", job["id"])
    saved = svc.authoring.load("c-pilot")["jobs"][job["id"]]
    assert saved["status"] == "completed", saved.get("error")
    assert wire_calls == [1]
    assert saved["request_snapshot"]["knowledge_generation_context"] == frozen


def test_compaction_keeps_parse_gaps_and_source_versions_in_full_snapshot(svc):
    initialize(svc)
    context = start(svc, "tree", "inventory")["request_snapshot"]["knowledge_generation_context"]
    context["material_coverage"]["inventory"].append({"asset_id": "bad", "parse_status": "failed"})
    context["material_coverage"]["incomplete_assets"] = ["bad"]
    before = deepcopy(context)
    compact = knowledge_context_prompt(context, compact_evidence=True)
    assert "inventory" not in compact["material_coverage"]
    assert compact["material_coverage"]["inventory_count"] == 50
    assert compact["material_coverage"]["inventory_issues"] == [{"asset_id": "bad", "parse_status": "failed"}]
    assert compact["material_coverage"]["incomplete_assets"] == ["bad"]
    assert compact["evidence_package"]["package_revision_id"] == context["evidence_package"]["package_revision_id"]
    assert context == before


@pytest.mark.asyncio
async def test_real_oversize_fails_once_with_actionable_error(svc, monkeypatch):
    monkeypatch.setenv("COURSE_TEACHING_PLAN_MAX_INPUT_TOKENS", "2000")
    initialize(svc)
    job = start(svc, "tree", "too-large")
    attempts, wire_calls = [], []
    async def call(prompt, **kwargs):
        attempts.append(1)
        AIBase.validate_request_budget(prompt, kwargs["system_prompt"], kwargs["max_input_tokens"])
        wire_calls.append(1)
        return json.dumps(tree_response())
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart="test", client=None)
    await svc.run("c-pilot", job["id"])
    saved = svc.authoring.load("c-pilot")["jobs"][job["id"]]
    assert saved["status"] == "failed"
    assert saved["error"]["code"] == "AIRequestBudgetExceeded"
    assert "输入" in saved["error"]["message"]
    assert saved["error"]["retryable"] is False
    assert saved["error"]["model_request_sent"] is False
    assert attempts == [1] and not wire_calls
    assert not saved.get("partial_text")
