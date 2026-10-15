import pytest

from slide_source_tokens import _protected_tokens


def test_emphasized_acronym_initial_retains_the_displayed_identifier():
    source = "SCAMPER：**S**ubstitute（替代），**C**ombine（合并），**P**ut to other uses（他用）。"
    assert _protected_tokens("Substitute Combine Put to other uses") <= _protected_tokens(source)
    assert "inventedapi" not in _protected_tokens(source)


@pytest.mark.parametrize("source", ["`**S**ubstitute`", "```python\n**S**ubstitute\n```", "~~~text\n**S**ubstitute\n~~~"])
def test_code_literals_do_not_gain_a_joined_identifier(source):
    assert "substitute" not in _protected_tokens(source)


def test_displayed_identifier_is_accepted_with_the_unchanged_literal_quote():
    from backend.tests.test_teacher_script_ppt import sample
    from teacher_script_ppt import validate_block_pages

    template, contract, _ = sample()
    source = "SCAMPER 的 **S**ubstitute 表示替代现有材料、组件或服务。"
    page = {"layout_id": template.layout_id("bullets"), "page_goal": "理解替代策略", "fields": {
        "title": "替代策略", "notes": "说明英文名称与含义", "points": [{
            "text": "Substitute 表示替代", "sources": [{"block_id": "b", "quote": source}],
        }],
    }}
    block = {**contract["modules"][0], "content": source, "ppt_pages": [page]}
    validate_block_pages(block, template)
    assert block["content"] == source
    assert page["fields"]["points"][0]["sources"][0]["quote"] == source
    page["fields"]["points"][0]["text"] = "InventedApi 表示替代"
    with pytest.raises(ValueError, match="teaching_fact_token_unsupported"):
        validate_block_pages(block, template)


def test_percent_units_are_equivalent_only_inside_delimited_source_math():
    assert "80%" in _protected_tokens(r"完成率 $\ge 80\%$")
    assert "80%" not in _protected_tokens("完成率80，单位未说明")
    assert "90%" not in _protected_tokens(r"完成率 $\ge 80\%$")
    assert "80%" not in _protected_tokens(r"代码 `$\ge 80\%$`")
