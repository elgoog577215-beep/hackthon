import asyncio
import json
from copy import deepcopy

import pytest

from course_document import stable_hash
from ppt_fixed_templates import compile_fixed_template
from ppt_source_quotes import source_excerpt_catalog
from teacher_script_ppt import CONTRACT, describe_bundle_failure, generate_bundle, validate_block_pages

TEXT = "串行按顺序逐项执行，并行同时执行多个任务。相同任务条件下，应根据任务之间的依赖选择执行方式。独立任务可并行，存在依赖的任务需按先后顺序执行。"


def sample():
    template = compile_fixed_template("qizhi-classroom")
    def field(text):
        return {"text": text, "sources": [{"block_id": "b", "quote": TEXT}]}
    page = {"layout_id": template.layout_id("comparison"), "page_goal": "比较执行方式",
        "fields": {"title": "执行方式", "notes": "根据依赖选择执行方式。", "condition": field("相同任务条件"),
                   "left_subject": field("串行"), "right_subject": field("并行"),
                   "rows": [{"dimension": field("执行方式"), "left": field("逐项执行"), "right": field("同时执行")}],
                   "conclusion": field("根据任务依赖选择")}}
    module = {"block_id": "b", "module_id": "concept", "title": "执行方式", "role": "concept",
              "required": True, "artifact_contract": {}, "target_characters": 0, "max_characters": 0}
    contract = {"section_node_id": "s", "title": "执行方式", "modules": [module]}
    return template, contract, page


def test_joint_response_preserves_markdown_pages_and_hides_page_json_from_stream():
    template, contract, page = sample()
    calls, deltas, saved = [], [], []
    async def invoke(*args, **kwargs):
        calls.append(args)
        raw = json.dumps({"blocks": [{"block_id": "b", "content": TEXT, "pages": [page]}]}, ensure_ascii=False)
        await kwargs["stream_reset"]()
        for offset in range(0, len(raw), 17):
            await kwargs["stream_delta"](raw[offset:offset + 17])
        return raw
    result = asyncio.run(generate_bundle(invoke=invoke, contract=contract, instructions="", template=template,
        on_delta=deltas.append, on_reset=lambda: deltas.clear(), on_checkpoint=saved.append))
    assert len(calls) == 1
    assert result["blocks"][0]["content"] == TEXT
    assert result["blocks"][0]["ppt_pages"] == [page]
    assert result["blocks"][0]["generation_contract_version"] == CONTRACT
    assert "".join(deltas) == "## 执行方式\n" + TEXT
    assert saved[-1]["ppt_errors"] == []


def test_failed_page_repair_receives_fixed_handout_and_preserves_successful_page():
    template, contract, page = sample()
    bad = deepcopy(page)
    bad["fields"]["left_subject"]["sources"][0]["quote"] = "不存在的原文"
    calls, saved = [], []
    async def invoke(prompt, instructions, **kwargs):
        calls.append((prompt, instructions))
        if len(calls) == 1:
            return json.dumps({"blocks": [{"block_id": "b", "content": TEXT, "pages": [page, bad]}]}, ensure_ascii=False)
        assert TEXT in instructions
        assert "只修以下失败页面" in instructions
        assert kwargs["stream_delta"] is None
        return json.dumps({"pages": [page]}, ensure_ascii=False)
    result = asyncio.run(generate_bundle(invoke=invoke, contract=contract, instructions="", template=template, on_checkpoint=saved.append))
    assert len(calls) == 2
    assert saved[0]["content"] == TEXT
    assert result["blocks"][0]["content"] == TEXT
    assert result["blocks"][0]["ppt_pages"] == [page, page]


def test_frozen_handout_page_repair_receives_selectable_literal_quote_ids():
    template, contract, page = sample()
    quote_catalog = source_excerpt_catalog({
        "b": {
            "block_id": "b",
            "block_revision": stable_hash(TEXT, prefix="block_"),
            "full_text": TEXT,
        }
    })
    quote_id = quote_catalog[0]["quote_id"]
    repaired = deepcopy(page)

    def select_quote_ids(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "sources" and isinstance(child, list):
                    value[key] = [{"quote_id": quote_id} for _ in child]
                else:
                    select_quote_ids(child)
        elif isinstance(value, list):
            for child in value:
                select_quote_ids(child)

    select_quote_ids(repaired)

    calls = []

    async def invoke(prompt, instructions, **kwargs):
        calls.append((prompt, instructions))
        return json.dumps({"pages": [repaired]}, ensure_ascii=False)

    seed = {
        **contract["modules"][0],
        "content": TEXT,
        "generation_contract_version": CONTRACT,
    }
    result = asyncio.run(generate_bundle(
        invoke=invoke,
        contract=contract,
        instructions="",
        template=template,
        seed_blocks={"b": seed},
        immutable_handout=True,
    ))

    assert calls[0][0].startswith("修复当前 PPT 页面")
    assert '"literal_source_ranges"' in calls[0][1]
    assert quote_id in calls[0][1]
    assert "sources 只返回 quote_id" in calls[0][1]
    assert result["blocks"][0]["ppt_pages"] == [repaired]
    assert not result["blocks"][0]["ppt_errors"]


def test_source_grounding_failure_names_the_failed_step_and_block():
    failure = describe_bundle_failure(
        ValueError(
            "source_excerpt_mismatch:tsb-fb9d8c62c7fd: "
            "choose a supplied quote_id or copy a literal source quote"
        )
    )

    assert failure == {
        "code": "lesson_ppt_source_grounding_failed",
        "message": "页面引用未能匹配讲义原文，系统没有保存来源不可靠的内容稿。",
        "category": "quality",
        "recovery_action": "retry_original",
        "retryable": True,
        "failed_step": "sources",
        "failed_block_id": "tsb-fb9d8c62c7fd",
        "technical_detail": (
            "source_excerpt_mismatch:tsb-fb9d8c62c7fd: "
            "choose a supplied quote_id or copy a literal source quote"
        ),
    }


def test_page_failure_exhaustion_returns_usable_handout_and_reusable_checkpoint():
    template, contract, page = sample()
    calls, saved = [], []
    async def invoke(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            return json.dumps({"blocks": [{"block_id": "b", "content": TEXT, "pages": []}]})
        raise RuntimeError("provider unavailable")
    result = asyncio.run(generate_bundle(invoke=invoke, contract=contract, instructions="", template=template, on_checkpoint=saved.append))
    assert len(calls) == 3
    assert result["blocks"][0]["content"] == TEXT
    assert result["blocks"][0]["ppt_errors"]
    resumed = []
    async def recover(prompt, instructions, **kwargs):
        resumed.append(prompt)
        return json.dumps({"pages": [page]})
    restored = asyncio.run(generate_bundle(invoke=recover, contract=contract, instructions="", template=template,
        seed_blocks={"b": {**saved[-1], "ppt_repair_attempts": [0]}}))
    assert len(resumed) == 1
    assert restored["blocks"][0]["content"] == TEXT
    assert not restored["blocks"][0]["ppt_errors"]


def test_recovery_does_not_reset_automatic_repair_budget():
    template, contract, _ = sample()
    async def unexpected(*args, **kwargs):
        raise AssertionError("exhausted retries must not invoke the model")
    result = asyncio.run(generate_bundle(invoke=unexpected, contract=contract, instructions="", template=template,
        seed_blocks={"b": {"block_id": "b", "content": TEXT, "ppt_pages": [], "ppt_repair_attempts": [2], "generation_contract_version": CONTRACT}}))
    assert result["blocks"][0]["content"] == TEXT
    assert result["blocks"][0]["ppt_errors"]


def test_malformed_pages_preserve_successful_handout():
    template, contract, page = sample()
    calls = []
    async def invoke(prompt, instructions, **kwargs):
        calls.append(prompt)
        if len(calls) == 1:
            return json.dumps({"blocks": [{"block_id": "b", "content": TEXT, "pages": "bad page"}]})
        return json.dumps({"pages": [page]})
    result = asyncio.run(generate_bundle(invoke=invoke, contract=contract, instructions="", template=template))
    assert len(calls) == 2
    assert result["blocks"][0]["content"] == TEXT
    assert not result["blocks"][0]["ppt_errors"]


def test_page_validation_rejects_fabricated_source():
    template, _, page = sample()
    page["fields"]["left_subject"]["sources"][0]["quote"] = "伪造来源"
    with pytest.raises((ValueError, RuntimeError)):
        validate_block_pages({"block_id": "b", "content": TEXT, "ppt_pages": [page]}, template)
