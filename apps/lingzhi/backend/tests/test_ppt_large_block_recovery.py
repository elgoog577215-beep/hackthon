import asyncio
import json

import pytest

from ai_base import AIProviderRequestError
from backend.tests.test_teacher_script_ppt import sample
from course_generation_budget import TeacherScriptGenerationTimeout
from ppt_page_repair_units import page_repair_source_units, page_repair_unit_block
from teacher_script_ppt import (
    CONTRACT,
    PptPageProviderUnavailable,
    PptPageRepairTimeout,
    _page_repair_prompt,
    completion_seed_blocks,
    describe_bundle_failure,
    generate_bundle,
    validate_block_pages,
)


def large_source() -> str:
    parts = []
    for index in range(4):
        body = "项目操作步骤说明内容，保持输入、处理与结果之间的关系。" * 45
        parts.append(f"### 操作片段 {index + 1}\n\n{body}\n")
    return "\n".join(parts).rstrip()


def seed_for(contract, content):
    return {
        **contract["modules"][0],
        "content": content,
        "ppt_pages": [],
        "generation_contract_version": CONTRACT,
    }


def repair_payload(instructions: str) -> dict:
    return json.loads(instructions[instructions.index('{"block_id"'):])


def valid_page(payload: dict, template) -> dict:
    source = next(
        item for item in payload["literal_source_ranges"]
        if "项目操作步骤说明内容" in item["quote"]
    )
    return {
        "layout_id": template.layout_id("bullets"),
        "page_goal": "说明操作步骤",
        "fields": {
            "title": "操作步骤",
            "notes": "按照讲义依次说明。",
            "points": [{
                "text": "项目操作步骤说明内容",
                "sources": [{"quote_id": source["quote_id"]}],
            }],
        },
    }


def test_large_missing_block_repairs_bounded_source_units_and_keeps_exact_content():
    template, contract, _ = sample()
    content = large_source()
    calls, waits, distinct_units = [], [], []
    failed_once = set()

    async def invoke(_prompt, instructions, **_options):
        payload = repair_payload(instructions)
        unit = payload["repair_unit"]
        calls.append(unit["repair_unit_id"])
        if unit["repair_unit_id"] not in distinct_units:
            distinct_units.append(unit["repair_unit_id"])
        if len(distinct_units) == 2 and unit["repair_unit_id"] not in failed_once:
            failed_once.add(unit["repair_unit_id"])
            raise AIProviderRequestError("provider_unavailable: temporary")
        return json.dumps({"pages": [valid_page(payload, template)]}, ensure_ascii=False)

    async def sleep(seconds):
        waits.append(seconds)

    result = asyncio.run(generate_bundle(
        invoke=invoke,
        contract=contract,
        instructions="",
        template=template,
        seed_blocks={"b": seed_for(contract, content)},
        immutable_handout=True,
        provider_recovery_sleep=sleep,
    ))

    block = result["blocks"][0]
    units = block["ppt_page_repair_units"]
    assert len(units) >= 3
    assert len(block["ppt_pages"]) == len(units)
    assert block["content"] == content
    assert max(unit["source_chars"] for unit in units) <= 2200
    assert calls.count(distinct_units[0]) == 1
    assert calls.count(distinct_units[1]) == 2
    assert waits == [31]
    validate_block_pages(block, template)


def test_resume_skips_source_units_that_already_have_valid_pages():
    template, contract, _ = sample()
    content = large_source()
    saved, first_calls, waits = [], [], []
    failed_unit = ""

    async def first_invoke(_prompt, instructions, **_options):
        nonlocal failed_unit
        payload = repair_payload(instructions)
        unit_id = payload["repair_unit"]["repair_unit_id"]
        first_calls.append(unit_id)
        if len(set(first_calls)) > 1:
            failed_unit = unit_id
            raise AIProviderRequestError("provider_unavailable: temporary")
        return json.dumps({"pages": [valid_page(payload, template)]}, ensure_ascii=False)

    async def sleep(seconds):
        waits.append(seconds)

    with pytest.raises(PptPageProviderUnavailable):
        asyncio.run(generate_bundle(
            invoke=first_invoke,
            contract=contract,
            instructions="",
            template=template,
            seed_blocks={"b": seed_for(contract, content)},
            immutable_handout=True,
            on_checkpoint=saved.append,
            provider_recovery_sleep=sleep,
        ))
    assert failed_unit
    assert waits == [31]
    first_unit = first_calls[0]
    resumed_seed = completion_seed_blocks(
        [seed_for(contract, content)],
        {"b": saved[-1]},
    )["b"]
    resumed_calls = []

    async def resumed_invoke(_prompt, instructions, **_options):
        payload = repair_payload(instructions)
        resumed_calls.append(payload["repair_unit"]["repair_unit_id"])
        return json.dumps({"pages": [valid_page(payload, template)]}, ensure_ascii=False)

    result = asyncio.run(generate_bundle(
        invoke=resumed_invoke,
        contract=contract,
        instructions="",
        template=template,
        seed_blocks={"b": resumed_seed},
        immutable_handout=True,
    ))
    assert first_unit not in resumed_calls
    assert failed_unit in resumed_calls
    assert not result["blocks"][0]["ppt_errors"]


def test_repeated_page_timeout_has_ppt_specific_failure_contract():
    template, contract, _ = sample()

    async def invoke(*_args, **_kwargs):
        raise TeacherScriptGenerationTimeout("讲义模型调用超时，已保留收到的内容。")

    async def sleep(_seconds):
        return None

    with pytest.raises(PptPageRepairTimeout) as captured:
        asyncio.run(generate_bundle(
            invoke=invoke,
            contract=contract,
            instructions="",
            template=template,
            seed_blocks={"b": seed_for(contract, large_source())},
            immutable_handout=True,
            provider_recovery_sleep=sleep,
        ))
    failure = describe_bundle_failure(captured.value)
    assert failure["code"] == "lesson_ppt_page_timeout"
    assert failure["failed_step"] == "pages"
    assert "PPT 页面" in failure["message"]


def test_small_missing_block_stays_one_repair_unit():
    template, contract, _ = sample()
    content = "项目操作步骤说明内容，保持输入、处理与结果之间的关系。"
    calls = []

    async def invoke(_prompt, instructions, **_options):
        payload = repair_payload(instructions)
        calls.append(payload["repair_unit"])
        return json.dumps({"pages": [valid_page(payload, template)]}, ensure_ascii=False)

    result = asyncio.run(generate_bundle(
        invoke=invoke,
        contract=contract,
        instructions="",
        template=template,
        seed_blocks={"b": seed_for(contract, content)},
        immutable_handout=True,
    ))
    assert len(calls) == 1
    assert calls[0]["source_start"] == 0
    assert calls[0]["source_end"] == len(content)
    assert len(result["blocks"][0]["ppt_page_repair_units"]) == 1


def test_source_unit_plan_is_stable_contiguous_and_code_aware():
    content = (
        "操作说明。\n\n```csharp\n"
        + "\n".join(f"var value{i} = {i};" for i in range(240))
        + "\n```\n\n运行结果说明。"
    )
    first = page_repair_source_units("block-1", content)
    second = page_repair_source_units("block-1", content)

    assert first == second
    assert first[0]["source_start"] == 0
    assert first[-1]["source_end"] == len(content)
    assert all(left["source_end"] == right["source_start"] for left, right in zip(first, first[1:]))
    assert "".join(content[item["source_start"]:item["source_end"]] for item in first) == content
    assert len({item["repair_unit_id"] for item in first}) == len(first)
    assert any(item["source_kind"] == "code" for item in first)


def test_code_repair_prompt_bounds_forms_and_literal_source_ranges():
    template, _, _ = sample()
    content = "```csharp\n" + "\n".join(
        f"var value{i} = GetValue(`slot{i}`);" for i in range(120)
    ) + "\n```"
    block = {"block_id": "large-code", "title": "代码示例", "role": "example", "content": content}
    unit = page_repair_source_units(block["block_id"], content)[0]
    repair_block = page_repair_unit_block(block, unit)

    prompt = _page_repair_prompt(
        repair_block,
        [],
        template,
        "script_ppt_pages_missing:large-code",
        repair_unit=unit,
    )
    payload = repair_payload(prompt)

    assert len(payload["forms"]) <= 3
    assert len(payload["literal_source_ranges"]) <= 12
    assert any(item["quote"] == repair_block["content"] for item in payload["literal_source_ranges"])
    assert len(prompt) < 15_000


def test_502_repartitions_only_the_failed_source_unit_before_retry():
    template, contract, _ = sample()
    content = large_source()
    calls, waits = [], []
    failed_range = None

    async def invoke(_prompt, instructions, **_options):
        nonlocal failed_range
        payload = repair_payload(instructions)
        unit = payload["repair_unit"]
        source_range = (unit["source_start"], unit["source_end"])
        calls.append(source_range)
        if failed_range is None and unit["source_start"] > 0 and unit["source_chars"] > 1000:
            failed_range = source_range
            raise AIProviderRequestError("Error code: 502")
        return json.dumps({"pages": [valid_page(payload, template)]}, ensure_ascii=False)

    async def sleep(seconds):
        waits.append(seconds)

    result = asyncio.run(generate_bundle(
        invoke=invoke,
        contract=contract,
        instructions="",
        template=template,
        seed_blocks={"b": seed_for(contract, content)},
        immutable_handout=True,
        provider_recovery_sleep=sleep,
    ))

    assert failed_range is not None
    assert calls.count(failed_range) == 1
    children = [item for item in calls if failed_range[0] <= item[0] and item[1] <= failed_range[1] and item != failed_range]
    assert len(children) >= 2
    assert max(end - start for start, end in children) <= 1000
    assert min(start for start, _end in children) == failed_range[0]
    assert max(end for _start, end in children) == failed_range[1]
    assert waits == [31]
    assert not result["blocks"][0]["ppt_errors"]


def test_repeated_502_uses_complete_grounded_prose_fallback():
    template, contract, _ = sample()
    content = (
        "项目操作步骤说明内容，保持输入、处理与结果之间的关系。\n\n"
        "运行后核对界面状态、存档结果与项目输出，确认每项内容均已保存。"
    )
    calls, waits = [], []

    async def invoke(*_args, **_kwargs):
        calls.append(True)
        raise AIProviderRequestError("Error code: 502")

    async def sleep(seconds):
        waits.append(seconds)

    result = asyncio.run(generate_bundle(
        invoke=invoke,
        contract=contract,
        instructions="",
        template=template,
        seed_blocks={"b": seed_for(contract, content)},
        immutable_handout=True,
        provider_recovery_sleep=sleep,
    ))
    block = result["blocks"][0]
    assert len(calls) == 2
    assert waits == [31]
    assert not block["ppt_errors"]
    quotes = [
        source["quote"]
        for page in block["ppt_pages"]
        for point in page["fields"]["points"]
        for source in point["sources"]
    ]
    assert "".join(quotes) == content
    validate_block_pages(block, template)


def test_missing_code_source_units_compile_without_model_calls():
    template, contract, _ = sample()
    content = "```csharp\n" + "\n".join(
        f"var value{i} = GetValue({i});" for i in range(260)
    ) + "\n```"

    async def forbidden(*_args, **_kwargs):
        pytest.fail("exact code source ranges should compile without a model call")

    result = asyncio.run(generate_bundle(
        invoke=forbidden,
        contract=contract,
        instructions="",
        template=template,
        seed_blocks={"b": seed_for(contract, content)},
        immutable_handout=True,
    ))

    block = result["blocks"][0]
    assert not block["ppt_errors"]
    assert block["ppt_pages"]
    assert "".join(
        page["fields"]["code"]["sources"][0]["quote"]
        for page in block["ppt_pages"]
    ) == content
    validate_block_pages(block, template)
