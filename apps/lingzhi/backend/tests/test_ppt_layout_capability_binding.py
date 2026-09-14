"""Cross-template layout binding contracts for the handout-to-PPT path."""

from copy import deepcopy

import pytest

from backend.tests.test_teacher_script_ppt import TEXT, sample
from teacher_script_ppt import (
    _prepare_page_candidates,
    generation_contract,
    validate_block_pages,
)


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
