"""Source-first page generation and generic fact-recovery contracts."""

import asyncio
import json
from copy import deepcopy

import pytest

from backend.tests.test_teacher_script_ppt import TEXT, sample
from teacher_script_ppt import CONTRACT, generate_bundle, validate_block_pages


def _seed(contract: dict, content: str, pages: list[dict]) -> dict:
    return {
        **contract["modules"][0],
        "content": content,
        "ppt_pages": pages,
        "generation_contract_version": CONTRACT,
    }


def _bullet_page(template, content: str, text: str, *, include_sources: bool = True) -> dict:
    point = {"text": text}
    if include_sources:
        point["sources"] = [{"block_id": "b", "quote": content}]
    return {
        "layout_id": template.layout_id("bullets"),
        "page_goal": "说明调研结果",
        "fields": {
            "title": "调研结果",
            "notes": "依据讲义说明调研结果。",
            "points": [point],
        },
    }


def _source_quotes(value) -> list[str]:
    quotes = []
    if isinstance(value, dict):
        choices = value.get("sources")
        if isinstance(choices, list):
            quotes.extend(
                str(choice.get("quote") or "")
                for choice in choices
                if isinstance(choice, dict)
            )
        for key, child in value.items():
            if key != "sources":
                quotes.extend(_source_quotes(child))
    elif isinstance(value, list):
        for child in value:
            quotes.extend(_source_quotes(child))
    return quotes


def _visible_text(value) -> str:
    if isinstance(value, dict):
        return " ".join(
            [str(value.get("text") or ""), str(value.get("heading") or "")]
            + [_visible_text(child) for child in value.values()]
        )
    if isinstance(value, list):
        return " ".join(_visible_text(child) for child in value)
    return ""


def test_missing_sources_for_supported_fact_are_bound_without_model_repair():
    template, contract, _ = sample()
    content = "本轮调研覆盖 65 名参与者，并记录主要需求。"
    page = _bullet_page(template, content, "调研覆盖 65 名参与者", include_sources=False)

    async def forbidden(*_args, **_kwargs):
        pytest.fail("an exact supported fact should bind to its source locally")

    result = asyncio.run(generate_bundle(
        invoke=forbidden,
        contract=contract,
        instructions="",
        template=template,
        seed_blocks={"b": _seed(contract, content, [page])},
        immutable_handout=True,
    ))

    block = result["blocks"][0]
    assert block["ppt_pages"][0]["fields"]["points"][0]["sources"]
    assert "65" in " ".join(_source_quotes(block["ppt_pages"][0]))
    validate_block_pages(block, template)


def test_repeated_invented_fact_falls_back_to_complete_source_grounded_page():
    template, contract, _ = sample()
    content = "访谈覆盖核心用户，并记录主要需求。"
    invalid = _bullet_page(template, content, "访谈覆盖 65 名核心用户")
    calls = []

    async def invoke(_prompt, instructions, **_kwargs):
        calls.append(instructions)
        assert "先选择来源" in instructions
        return json.dumps({"pages": [invalid]}, ensure_ascii=False)

    result = asyncio.run(generate_bundle(
        invoke=invoke,
        contract=contract,
        instructions="",
        template=template,
        seed_blocks={"b": _seed(contract, content, [invalid])},
        immutable_handout=True,
    ))

    block = result["blocks"][0]
    assert len(calls) == 2
    assert block["ppt_recovery_contract_version"] == "ppt_page_recovery_v4"
    assert block["ppt_errors"] == []
    assert "65" not in _visible_text(block["ppt_pages"])
    assert "".join(_source_quotes(block["ppt_pages"])) == content
    assert any(
        "页面事实缺少讲义依据" in page["fields"].get("split_reason", "")
        for page in block["ppt_pages"]
    )
    validate_block_pages(block, template)


def test_fact_fallback_preserves_an_already_valid_page():
    template, contract, _ = sample()
    content = "访谈覆盖核心用户，并记录主要需求。"
    accepted = _bullet_page(template, content, "记录主要需求")
    invalid = _bullet_page(template, content, "访谈覆盖 65 名核心用户")
    seed = _seed(contract, content, [accepted, invalid])
    seed["ppt_page_groups"] = [[accepted], [invalid]]

    async def invoke(*_args, **_kwargs):
        return json.dumps({"pages": [invalid]}, ensure_ascii=False)

    result = asyncio.run(generate_bundle(
        invoke=invoke,
        contract=contract,
        instructions="",
        template=template,
        seed_blocks={"b": seed},
        immutable_handout=True,
    ))

    block = result["blocks"][0]
    assert block["ppt_pages"][0] == accepted
    assert "65" not in _visible_text(block["ppt_pages"][1:])
    assert block["ppt_errors"] == []
    validate_block_pages(block, template)


def test_joint_generation_prompt_requires_sources_before_visible_facts():
    template, contract, page = sample()

    async def invoke(_prompt, instructions, **_kwargs):
        assert "先完成 content，再为每个页面内容项选择连续原文" in instructions
        assert "数字、公式、专有名词和代码标识符" in instructions
        return json.dumps({
            "blocks": [{"block_id": "b", "content": TEXT, "pages": [page]}]
        }, ensure_ascii=False)

    asyncio.run(generate_bundle(
        invoke=invoke,
        contract=contract,
        instructions="",
        template=template,
    ))
