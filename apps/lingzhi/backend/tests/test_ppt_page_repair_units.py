from ppt_page_repair_units import full_page_repair_unit, page_repair_source_units


def test_mixed_lecture_does_not_turn_explanation_into_code_pages():
    text = "# 二叉树\n\n树是层级结构。\n\n```python\ndef height(node):\n    return 0\n```\n\n高度按边数计算。\n"
    assert full_page_repair_unit("lecture", text)["source_kind"] == "mixed"
    long_text = text * 40
    units = page_repair_source_units("lecture", long_text)
    assert "".join(long_text[u["source_start"]:u["source_end"]] for u in units) == long_text
    assert all(u["source_kind"] == "mixed" for u in units)


def test_only_fenced_code_uses_deterministic_code_pagination():
    assert full_page_repair_unit("code", "```python\nx = 1\n```\n")["source_kind"] == "code"
    assert full_page_repair_unit("code", "~~~\nx = 1\n~~~")["source_kind"] == "code"
    assert full_page_repair_unit("text", "解释内联 `code` 和字符串 ``` 的含义。")["source_kind"] == "prose"
    assert full_page_repair_unit("text", "```\nx = 1\n```\n后续说明")["source_kind"] == "mixed"
