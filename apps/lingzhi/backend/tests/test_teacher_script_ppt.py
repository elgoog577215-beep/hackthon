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
    assert len(result["blocks"][0]["ppt_pages"]) == 1
    validate_block_pages(result["blocks"][0], template)
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
    assert len(calls) == 1
    assert saved[0]["content"] == TEXT
    assert result["blocks"][0]["content"] == TEXT
    assert len(result["blocks"][0]["ppt_pages"]) == 2
    validate_block_pages(result["blocks"][0], template)


def test_frozen_handout_page_repair_resolves_quote_ids_to_portable_literals():
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
    block = result["blocks"][0]
    assert "quote_id" not in json.dumps(block["ppt_pages"], ensure_ascii=False)
    assert not block["ppt_errors"]
    validate_block_pages(block, template)


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


def test_unknown_quote_ids_are_rebound_locally_without_another_model_call():
    template, contract, page = sample()
    invalid = deepcopy(page)

    def replace_sources(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "sources" and isinstance(child, list):
                    value[key] = [{"quote_id": "q_7adad6815373"} for _ in child]
                else:
                    replace_sources(child)
        elif isinstance(value, list):
            for child in value:
                replace_sources(child)

    replace_sources(invalid)

    async def unexpected(*_args, **_kwargs):
        raise AssertionError("unknown quote ids must be repaired deterministically")

    seed = {**contract["modules"][0], "content": TEXT, "ppt_pages": [invalid],
            "generation_contract_version": CONTRACT}
    result = asyncio.run(generate_bundle(invoke=unexpected, contract=contract, instructions="", template=template,
                                         seed_blocks={"b": seed}, immutable_handout=True))

    repaired = result["blocks"][0]
    assert not repaired["ppt_errors"]
    assert "q_7adad6815373" not in json.dumps(repaired["ppt_pages"], ensure_ascii=False)
    validate_block_pages(repaired, template)


def test_overlong_triad_points_are_fitted_locally_without_another_model_call():
    template, contract, _page = sample()

    long_points = [
        "基础组件描述静态场景物体的通用属性，并进一步说明 Transform、MeshRenderer、Collider 等组件之间的职责边界",
        "MonoBehaviour 是 C# 脚本与 Unity 生命周期之间唯一合法的连接载体，需要完整解释 Awake、Start 和 Update",
        "继承 MonoBehaviour 后脚本可以挂载到 GameObject，并在 Inspector 面板中暴露可序列化属性",
    ]
    source_text = "。".join(long_points) + "。"

    def field(text):
        return {"text": text, "sources": [{"block_id": "b", "quote": source_text}]}
    triad = {
        "layout_id": template.layout_id("triad"),
        "page_goal": "解释 Unity 脚本基础",
        "fields": {"title": "Unity 脚本基础", "notes": "说明三个基础关系。", "points": [field(text) for text in long_points]},
    }

    async def unexpected(*_args, **_kwargs):
        raise AssertionError("capacity fitting must not call the model again")

    seed = {**contract["modules"][0], "content": source_text, "ppt_pages": [triad],
            "generation_contract_version": CONTRACT}
    result = asyncio.run(generate_bundle(invoke=unexpected, contract=contract, instructions="", template=template,
                                         seed_blocks={"b": seed}, immutable_handout=True))

    repaired = result["blocks"][0]
    assert not repaired["ppt_errors"]
    assert all(len(point["text"]) <= 32 for point in repaired["ppt_pages"][0]["fields"]["points"])
    validate_block_pages(repaired, template)


def test_source_wrapped_scalar_page_fields_are_unwrapped_without_model_retry():
    template, contract, page = sample()
    wrapped = deepcopy(page)
    source_wrapper = lambda text: {
        "text": text,
        "sources": [{"block_id": "b", "quote": TEXT}],
    }
    wrapped["page_goal"] = source_wrapper("比较执行方式")
    wrapped["fields"]["title"] = source_wrapper("执行方式")
    wrapped["fields"]["notes"] = source_wrapper("根据依赖选择执行方式。")
    wrapped["fields"]["split_reason"] = source_wrapper("保留单页")

    async def unexpected(*_args, **_kwargs):
        raise AssertionError("a source-wrapped scalar title must be repaired locally")

    seed = {**contract["modules"][0], "content": TEXT, "ppt_pages": [wrapped],
            "generation_contract_version": CONTRACT}
    result = asyncio.run(generate_bundle(invoke=unexpected, contract=contract, instructions="", template=template,
                                         seed_blocks={"b": seed}, immutable_handout=True))

    repaired = result["blocks"][0]
    assert repaired["ppt_pages"][0]["page_goal"] == "比较执行方式"
    assert repaired["ppt_pages"][0]["fields"]["title"] == "执行方式"
    assert repaired["ppt_pages"][0]["fields"]["notes"] == "根据依赖选择执行方式。"
    assert repaired["ppt_pages"][0]["fields"]["split_reason"] == "保留单页"
    assert not repaired["ppt_errors"]
    validate_block_pages(repaired, template)


def test_plain_comparison_text_fields_are_source_wrapped_without_model_retry():
    template, contract, page = sample()
    plain = deepcopy(page)
    for key in ("condition", "left_subject", "right_subject"):
        plain["fields"][key] = plain["fields"][key]["text"]
    for row in plain["fields"]["rows"]:
        for key in ("dimension", "left", "right"):
            row[key] = row[key]["text"]

    async def unexpected(*_args, **_kwargs):
        raise AssertionError("plain comparison text fields must be repaired locally")

    seed = {**contract["modules"][0], "content": TEXT, "ppt_pages": [plain],
            "generation_contract_version": CONTRACT}
    result = asyncio.run(generate_bundle(invoke=unexpected, contract=contract, instructions="", template=template,
                                         seed_blocks={"b": seed}, immutable_handout=True))

    repaired = result["blocks"][0]
    assert not repaired["ppt_errors"]
    fields = repaired["ppt_pages"][0]["fields"]
    assert fields["condition"]["text"] == "相同任务条件"
    assert fields["left_subject"]["text"] == "串行"
    assert fields["right_subject"]["text"] == "并行"
    assert fields["rows"][0]["dimension"]["text"] == "执行方式"
    assert all(value["sources"] for value in (
        fields["condition"], fields["left_subject"], fields["right_subject"],
        fields["rows"][0]["dimension"], fields["rows"][0]["left"], fields["rows"][0]["right"],
    ))
    validate_block_pages(repaired, template)


def test_overlong_flow_steps_split_locally_without_losing_content_or_model_retry():
    template, contract, _page = sample()
    step_texts = [
        "串行任务需要按顺序逐项执行，并保持明确的前后依赖关系",
        "并行任务可以同时执行多个任务，但必须确认任务之间相互独立",
        "相同任务条件下应根据任务之间的依赖选择合适的执行方式",
        "独立任务可以采用并行方式同时执行多个相互独立的任务",
        "存在依赖的任务需要按照明确的先后顺序逐项执行",
    ]

    def field(text):
        return {"text": text, "sources": [{"block_id": "b", "quote": TEXT}]}

    flow = {
        "layout_id": template.layout_id("flow"),
        "page_goal": "说明任务执行流程",
        "fields": {
            "title": "任务执行流程",
            "notes": "按依赖关系选择执行方式。",
            "steps": [field(text) for text in step_texts],
        },
    }

    async def unexpected(*_args, **_kwargs):
        raise AssertionError("list capacity fitting must not call the model again")

    seed = {**contract["modules"][0], "content": TEXT, "ppt_pages": [flow],
            "generation_contract_version": CONTRACT}
    result = asyncio.run(generate_bundle(invoke=unexpected, contract=contract, instructions="", template=template,
                                         seed_blocks={"b": seed}, immutable_handout=True))

    repaired = result["blocks"][0]
    assert not repaired["ppt_errors"]
    assert len(repaired["ppt_pages"]) == 2
    repaired_steps = [[step["text"] for step in page["fields"]["steps"]] for page in repaired["ppt_pages"]]
    assert [len(page) for page in repaired_steps] == [3, 3]
    assert all(len(text) <= 28 for page in repaired_steps for text in page)
    assert len(list(dict.fromkeys(text for page in repaired_steps for text in page))) == 5
    assert all(step["sources"][0]["quote"] == TEXT
               for page in repaired["ppt_pages"] for step in page["fields"]["steps"])
    validate_block_pages(repaired, template)


@pytest.mark.parametrize("message", [
    "source_quote_id_unknown:q_7adad6815373",
    "3 validation errors for FixedTriad points.0.text String should have at most 32 characters",
    "teaching_fact_token_unsupported:item-2: unsupported=['gameo']",
    "1 validation error for FixedSection title Input should be a valid string [type=string_type, input_type=dict]",
    "1 validation error for FixedFlow steps List should have at most 4 items after validation, not 5 [type=too_long, input_type=list]",
    "6 validation errors for FixedComparison condition Input should be a valid dictionary or instance of TextUpTo38 [type=model_type, input_type=str]",
])
def test_page_contract_failures_are_reported_as_the_validation_step(message):
    failure = describe_bundle_failure(ValueError(message))
    assert failure["failed_step"] == "sources"
    assert failure["retryable"] is True
    assert failure["technical_detail"] == message


def test_source_only_formula_quote_is_resolved_without_model_retry():
    template, contract, _page = sample()
    source_text = "速度公式为 \\[v=at\\]，其中 a 表示加速度，t 表示时间。"
    formula_page = {
        "layout_id": template.layout_id("formula"),
        "page_goal": "解释速度公式",
        "fields": {
            "title": "速度公式",
            "notes": "解释各符号含义。",
            "formula": {"sources": [{"quote_id": "q_not_in_catalog"}]},
            "explanation": {
                "text": "加速度与时间决定速度变化",
                "sources": [{"block_id": "b", "quote": source_text}],
            },
        },
    }

    async def unexpected(*_args, **_kwargs):
        raise AssertionError("source-only formula references must be repaired locally")

    seed = {**contract["modules"][0], "content": source_text, "ppt_pages": [formula_page],
            "generation_contract_version": CONTRACT}
    result = asyncio.run(generate_bundle(invoke=unexpected, contract=contract, instructions="", template=template,
                                         seed_blocks={"b": seed}, immutable_handout=True))

    block = result["blocks"][0]
    formula_source = block["ppt_pages"][0]["fields"]["formula"]["sources"][0]
    assert formula_source == {"block_id": "b", "quote": "\\[v=at\\]"}
    assert not block["ppt_errors"]
    validate_block_pages(block, template)
