"""Cross-template layout binding contracts for the handout-to-PPT path."""

from copy import deepcopy
import asyncio
import json

import pytest

from backend.tests.test_teacher_script_ppt import TEXT, sample
from teacher_script_ppt import (
    _prepare_page_candidates,
    generate_bundle,
    generation_contract,
    validate_block_pages,
)
from ppt_layout_binding import bind_page_layout


def _block() -> dict:
    return {
        "block_id": "b",
        "title": "执行方式",
        "role": "concept",
        "content": TEXT,
    }


def test_model_contract_exposes_stable_layout_keys_instead_of_versioned_ids():
    template, _, _ = sample()

    contract = generation_contract(template)

    assert contract["page"] == {
        "layout_key": "one of forms",
        "page_goal": "本页实际教学目的",
        "fields": "对应版式表单",
    }
    assert "comparison" in contract["forms"]
    assert all("/" not in key and "@" not in key for key in contract["forms"])


def test_stable_layout_key_binds_to_the_frozen_template_version():
    template, _, page = sample()
    candidate = deepcopy(page)
    candidate["layout_key"] = "comparison"
    candidate.pop("layout_id")

    prepared = _prepare_page_candidates([candidate], _block(), template)

    assert prepared[0]["layout_id"] == template.layout_id("comparison")
    assert "layout_key" not in prepared[0]
    validate_block_pages({**_block(), "ppt_pages": prepared}, template)


def test_old_or_foreign_template_prefix_rebinds_by_stable_layout_key():
    template, _, page = sample()
    candidate = deepcopy(page)
    candidate["layout_id"] = "older-template@1/comparison"

    prepared = _prepare_page_candidates([candidate], _block(), template)

    assert prepared[0]["layout_id"] == template.layout_id("comparison")
    validate_block_pages({**_block(), "ppt_pages": prepared}, template)


def test_unknown_layout_rebinds_only_when_its_fields_identify_one_form():
    template, _, page = sample()
    candidate = deepcopy(page)
    candidate["layout_id"] = "invented-layout-name"

    prepared = _prepare_page_candidates([candidate], _block(), template)

    assert prepared[0]["layout_id"] == template.layout_id("comparison")
    validate_block_pages({**_block(), "ppt_pages": prepared}, template)


def test_unresolved_layout_error_records_supplied_and_allowed_layout_keys():
    template, _, page = sample()
    candidate = deepcopy(page)
    candidate["layout_id"] = "invented-layout-name"
    candidate["fields"] = {
        "title": "讲义要点",
        "notes": "讲解要点",
        "points": [
            {
                "text": "根据任务依赖选择执行方式",
                "sources": [{"block_id": "b", "quote": TEXT}],
            }
        ],
    }

    prepared = _prepare_page_candidates([candidate], _block(), template)

    with pytest.raises(ValueError) as error:
        validate_block_pages({**_block(), "ppt_pages": prepared}, template)
    detail = str(error.value)
    assert "script_ppt_layout_unresolved:b:0" in detail
    assert "supplied=invented-layout-name" in detail
    assert "allowed=" in detail
    assert "bullets" in detail
    assert "summary" in detail


def test_conflicting_stable_key_and_legacy_layout_id_are_rejected():
    template, _, page = sample()
    candidate = deepcopy(page)
    candidate["layout_key"] = "flow"

    with pytest.raises(ValueError, match="script_ppt_layout_identity_conflict"):
        bind_page_layout(candidate, template)


def test_every_frozen_template_layout_has_one_stable_model_key():
    template, _, _ = sample()

    for layout in template.layouts:
        candidate = bind_page_layout(
            {"layout_key": layout.layout_slug, "page_goal": "明确教学目标", "fields": {}},
            template,
        )
        assert candidate["layout_id"] == layout.template_layout_id
        assert "layout_key" not in candidate


def test_joint_generation_persists_exact_layout_id_from_stable_model_key():
    template, contract, page = sample()
    model_page = deepcopy(page)
    model_page["layout_key"] = "comparison"
    model_page.pop("layout_id")

    async def invoke(*_args, **_kwargs):
        return json.dumps({
            "blocks": [{"block_id": "b", "content": TEXT, "pages": [model_page]}]
        }, ensure_ascii=False)

    result = asyncio.run(generate_bundle(
        invoke=invoke,
        contract=contract,
        instructions="",
        template=template,
    ))

    saved = result["blocks"][0]["ppt_pages"][0]
    assert saved["layout_id"] == template.layout_id("comparison")
    assert "layout_key" not in saved
    validate_block_pages(result["blocks"][0], template)


def test_design_course_layout_failure_is_rebound_without_a_model_retry():
    template, contract, page = sample()
    invalid = deepcopy(page)
    invalid["layout_id"] = "design-course-comparison-card"
    calls = []

    async def unexpected(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("a uniquely identified form must bind locally")

    result = asyncio.run(generate_bundle(
        invoke=unexpected,
        contract=contract,
        instructions="",
        template=template,
        seed_blocks={
            "b": {
                **contract["modules"][0],
                "content": TEXT,
                "ppt_pages": [invalid],
                "generation_contract_version": "script_ppt_bundle_v1",
            }
        },
        immutable_handout=True,
    ))

    assert calls == []
    assert result["blocks"][0]["ppt_pages"][0]["layout_id"] == template.layout_id("comparison")
    validate_block_pages(result["blocks"][0], template)
