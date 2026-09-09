import asyncio
import json
from copy import deepcopy

import pytest

from backend.tests.test_teacher_script_ppt import sample, TEXT
from teacher_script_ppt import CONTRACT, generate_bundle, validate_block_pages


def seed_for(contract, content, pages):
    return {**contract["modules"][0], "content": content, "ppt_pages": pages,
            "generation_contract_version": CONTRACT}


@pytest.mark.parametrize("language,body", [
    ("python", "\n".join(f"    print('第 {i} 个步骤')" for i in range(35)) + "\n"),
    ("csharp", "\n".join(f"    var value{i} = {i};" for i in range(40)) + "\n"),
    ("sql", "SELECT " + ", ".join(f"column_{i}" for i in range(200)) + " FROM records;\n"),
], ids=["python", "csharp", "sql-long-line"])
def test_code_pagination_preserves_every_source_character_and_needs_no_model(language, body):
    template, contract, _ = sample()
    quote = f"```{language}\n{body}```"
    page = {"layout_id": template.layout_id("code"), "page_goal": "阅读代码",
            "fields": {"title": "代码示例", "notes": "连续阅读代码", "code": {"sources": [{"block_id": "b", "quote": quote}]}}}

    async def forbidden(*args, **kwargs):
        pytest.fail("valid long code should paginate deterministically")

    result = asyncio.run(generate_bundle(invoke=forbidden, contract=contract, instructions="", template=template,
        seed_blocks={"b": seed_for(contract, quote, [page])}, immutable_handout=True))
    block = result["blocks"][0]
    assert len(block["ppt_pages"]) > 1
    assert not block["ppt_errors"]
    fragments = [p["fields"]["code"]["sources"][0]["quote"] for p in block["ppt_pages"]]
    assert "".join(fragments) == quote
    assert all(fragment in quote for fragment in fragments)
    validate_block_pages(block, template)
    again = asyncio.run(generate_bundle(invoke=forbidden, contract=contract, instructions="", template=template,
        seed_blocks={"b": block}, immutable_handout=True))
    assert again["blocks"][0]["ppt_pages"] == block["ppt_pages"]


@pytest.mark.parametrize("envelope", ["```json\n{}\n```", "\ufeff  {}  ", "~~~json\n{}\n~~~"])
def test_repair_accepts_a_complete_json_envelope(envelope):
    template, contract, page = sample()
    calls = []

    async def invoke(prompt, instructions, **kwargs):
        calls.append(instructions)
        return envelope.format(json.dumps({"pages": [page]}, ensure_ascii=False))

    result = asyncio.run(generate_bundle(invoke=invoke, contract=contract, instructions="只输出完整 Markdown 正文",
        template=template, seed_blocks={"b": seed_for(contract, TEXT, [])}, immutable_handout=True))
    assert len(calls) == 1
    assert "只输出完整 Markdown 正文" not in calls[0]
    assert result["blocks"][0]["ppt_pages"][0]["layout_id"] == page["layout_id"]
    assert not result["blocks"][0]["ppt_errors"]


def test_failed_json_repair_keeps_original_validation_cause():
    template, contract, page = sample()
    page["fields"]["left_subject"]["text"] = "FakeAPI"

    async def invoke(*args, **kwargs):
        return "This is not JSON"

    result = asyncio.run(generate_bundle(invoke=invoke, contract=contract, instructions="", template=template,
        seed_blocks={"b": seed_for(contract, TEXT, [page])}, immutable_handout=True))
    error = result["blocks"][0]["ppt_errors"][0]
    assert "teaching_fact_token_unsupported" in error["validation_error"]
    assert "script_ppt_response_invalid_json" in error["repair_error"]


def test_optional_text_with_only_a_valid_source_is_recovered():
    template, contract, page = sample()
    page["fields"]["condition"].pop("text")
    page["fields"]["condition"]["sources"] = [{"block_id": "b", "quote": "相同任务条件"}]

    async def forbidden(*args, **kwargs):
        pytest.fail("a missing text field with an exact short source can be recovered locally")

    result = asyncio.run(generate_bundle(invoke=forbidden, contract=contract, instructions="", template=template,
        seed_blocks={"b": seed_for(contract, TEXT, [page])}, immutable_handout=True))
    assert not result["blocks"][0]["ppt_errors"]
    validate_block_pages(result["blocks"][0], template)


def test_provider_outage_does_not_fan_out_across_missing_page_groups():
    from ai_base import AIProviderRequestError
    template, contract, _ = sample()
    seed = seed_for(contract, TEXT, [])
    seed["ppt_page_groups"] = [[], [], []]
    calls, saved, waits = [], [], []

    async def invoke(*args, **kwargs):
        calls.append(args)
        raise AIProviderRequestError("provider_unavailable: circuit_breaker_open")

    async def sleep(seconds):
        waits.append(seconds)

    with pytest.raises(AIProviderRequestError):
        asyncio.run(generate_bundle(invoke=invoke, contract=contract, instructions="", template=template,
            seed_blocks={"b": seed}, immutable_handout=True, on_checkpoint=saved.append,
            provider_recovery_sleep=sleep))
    assert len(calls) == 2 and len(waits) == 1
    assert saved[-1]["content"] == TEXT
    assert saved[-1]["ppt_errors"]
    assert not saved[-1]["ppt_pages"]


@pytest.mark.parametrize("prefix", ["", "使用"])
def test_identifier_shorthand_expands_only_to_an_existing_unambiguous_source(prefix):
    template, contract, _ = sample()
    content = "OnTriggerEnter 和 OnTriggerExit 分别处理进入与离开。"
    page = {"layout_id": template.layout_id("bullets"), "page_goal": "区分处理方法",
            "fields": {"title": "处理方法", "notes": "对照原文",
                "points": [{"text": prefix + "OnTriggerEnter/Exit", "sources": [{"block_id": "b", "quote": content}]}]}}

    async def forbidden(*args, **kwargs):
        pytest.fail("unambiguous identifier shorthand can be expanded from the source")

    result = asyncio.run(generate_bundle(invoke=forbidden, contract=contract, instructions="", template=template,
        seed_blocks={"b": seed_for(contract, content, [deepcopy(page)])}, immutable_handout=True))
    assert result["blocks"][0]["ppt_pages"][0]["fields"]["points"][0]["text"] == prefix + "OnTriggerEnter/OnTriggerExit"


@pytest.mark.parametrize("short,qualified", [
    ("fixedDeltaTime", "Time.fixedDeltaTime"),
    ("SetActive", "GameObject.SetActive"),
    ("velocity.magnitude", "Rigidbody.velocity.magnitude"),
    ("MovePosition", "Rigidbody.MovePosition"),
])
def test_member_shorthand_is_grounded_by_its_qualified_source_name(short, qualified):
    template, contract, _ = sample()
    content = f"使用 {qualified} 完成操作。"
    page = {"layout_id": template.layout_id("bullets"), "page_goal": "说明操作",
            "fields": {"title": "操作", "notes": "依据原文",
                "points": [{"text": short, "sources": [{"block_id": "b", "quote": content}]}]}}

    async def forbidden(*args, **kwargs):
        pytest.fail("a unique qualified source identifier should not require a model repair")

    result = asyncio.run(generate_bundle(invoke=forbidden, contract=contract, instructions="", template=template,
        seed_blocks={"b": seed_for(contract, content, [page])}, immutable_handout=True))
    assert result["blocks"][0]["ppt_pages"][0]["fields"]["points"][0]["text"] == short


def test_code_continuation_removes_metadata_identifier_absent_from_its_fragment():
    template, contract, _ = sample()
    quote = "```csharp\nTime.fixedDeltaTime;\n" + "DoWork();\n" * 45 + "```"
    page = {"layout_id": template.layout_id("code"), "page_goal": "读取 fixedDeltaTime",
            "fields": {"title": "fixedDeltaTime 代码", "notes": "连续阅读",
                "code": {"sources": [{"block_id": "b", "quote": quote}]}}}

    async def forbidden(*args, **kwargs):
        pytest.fail("continuation metadata should be grounded deterministically")

    result = asyncio.run(generate_bundle(invoke=forbidden, contract=contract, instructions="", template=template,
        seed_blocks={"b": seed_for(contract, quote, [page])}, immutable_handout=True))
    pages = result["blocks"][0]["ppt_pages"]
    assert len(pages) > 1
    assert "".join(item["fields"]["code"]["sources"][0]["quote"] for item in pages) == quote
    for item in pages:
        validate_block_pages({**result["blocks"][0], "ppt_pages": [item]}, template)


@pytest.mark.parametrize("raw", ['{"pages": [', '{"pages":[]} {"pages":[]}', 'explanation without JSON', '[1,2]'])
def test_response_parser_does_not_invent_or_accept_partial_json(raw):
    from ppt_repair_response import parse_page_response
    with pytest.raises(ValueError, match="script_ppt_response_"):
        parse_page_response(raw)


def test_bad_response_stops_model_fanout_and_keeps_valid_pages_in_a_mixed_group():
    template, contract, good = sample()
    bad = deepcopy(good)
    bad["fields"]["left_subject"]["text"] = "FakeAPI"
    seed = seed_for(contract, TEXT, [good, bad, bad])
    seed["ppt_page_groups"] = [[good, bad, bad]]
    calls = []

    async def invoke(*args, **kwargs):
        calls.append(args)
        return "not JSON"

    result = asyncio.run(generate_bundle(invoke=invoke, contract=contract, instructions="", template=template,
        seed_blocks={"b": seed}, immutable_handout=True))
    assert len(calls) == 2
    assert result["blocks"][0]["ppt_pages"][0] == good
    assert result["blocks"][0]["ppt_errors"][0]["page_index"] == 1


def test_code_metadata_repair_does_not_duplicate_the_program_across_continuations():
    template, contract, _ = sample()
    quote = "```python\n" + "print('example')\n" * 30 + "```"
    page = {"layout_id": template.layout_id("code"), "page_goal": "FakeAPI",
            "fields": {"title": "代码", "notes": "连续阅读", "code": {"sources": [{"block_id": "b", "quote": quote}]}}}
    calls = []

    async def invoke(*args, **kwargs):
        calls.append(args)
        return json.dumps({"pages": [{**page, "page_goal": "阅读代码"}]})

    result = asyncio.run(generate_bundle(invoke=invoke, contract=contract, instructions="", template=template,
        seed_blocks={"b": seed_for(contract, quote, [page])}, immutable_handout=True))
    assert len(calls) == 1
    assert "".join(p["fields"]["code"]["sources"][0]["quote"] for p in result["blocks"][0]["ppt_pages"]) == quote
