"""批次 prompt 的关系契约必须与编译器的丢弃门一致（需求 A1）。

判据不是"prompt 里出现了六个词"，而是"prompt 让模型照抄的样例，本身能过
编译器那道门"。`_compile_relations` 对 `derives` 缺 `derivation_steps`、
`contrasts_with` 缺 `distinction` 的候选是整条丢弃的：样例若不带这两个字段，
模型学到的就是一种必定被丢弃的写法，而丢弃发生在编译期、没有任何提示。
"""

from __future__ import annotations

import json

from course_knowledge_base import RELATION_TYPES, _compile_relations, _normalize_name
from course_prompt_composer import CoursePromptComposer


def _batch_prompt() -> str:
    return CoursePromptComposer().build_teaching_plan_batch_v3_prompt(
        course_title="一次函数",
        positioning="能用一次函数刻画真实情境中的线性变化",
        batch_spec={"batch_id": "batch-1", "section_ids": ["L2-1-2"]},
        batch_sections=[{
            "node_id": "L2-1-2",
            "title": "一次函数的图像与性质",
            "learning_objective": "能够根据图像判断一次函数的变化趋势",
            "allowed_module_ids": ["core_explanation"],
        }],
        knowledge_registry=[{
            "knowledge_key": "K001",
            "name": "一次函数图像",
            "statement": "一次函数图像是一条直线。",
            "owner_node_id": "L2-1-2",
        }],
        section_identities=[{
            "node_id": "L2-1-2",
            "owned_knowledge_keys": ["K001"],
            "reused_knowledge_keys": [],
        }],
        module_catalog=[{"module_id": "core_explanation", "label": "核心教学"}],
        skeleton_revision_id="skeleton-1",
    )


def _example_relations(prompt: str) -> list[dict]:
    """把 JSON Schema 段落里的 knowledge_relations 样例取出来。

    prompt 是 f-string，花括号在输出里已经是单层，所以这里直接按数组边界截取
    并交给 json.loads —— 样例本身必须是合法 JSON，这一点也是断言的一部分。
    """
    start = prompt.index('"knowledge_relations": [')
    body = prompt[start + len('"knowledge_relations": '):]
    depth = 0
    for index, char in enumerate(body):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return json.loads(body[: index + 1])
    raise AssertionError("prompt 里的 knowledge_relations 样例没有闭合")


def test_constraints_name_every_relation_type() -> None:
    """六类关系必须逐个出现在约束里，模型才可能选对类型。"""
    prompt = _batch_prompt()
    constraints = prompt[prompt.index("## 约束"): prompt.index("## JSON Schema")]

    missing = sorted(name for name in RELATION_TYPES if f"`{name}`" not in constraints)

    assert missing == [], f"约束里没有说明这些关系类型：{missing}"


def test_constraints_state_the_two_required_fields() -> None:
    """带必填字段的两类关系必须在约束里点明字段名与缺失后果。"""
    constraints = _batch_prompt()
    constraints = constraints[
        constraints.index("## 约束"): constraints.index("## JSON Schema")
    ]

    assert "derivation_steps" in constraints
    assert "distinction" in constraints
    assert "丢弃" in constraints, "必须让模型知道缺字段会导致整条关系被丢弃"


def test_example_covers_more_than_prerequisite() -> None:
    """样例必须给出多种类型，否则模型只会照抄 prerequisite。"""
    types = {item.get("relation_type") for item in _example_relations(_batch_prompt())}

    assert "prerequisite" in types
    assert "derives" in types
    assert "contrasts_with" in types
    assert len(types) >= 4, f"样例类型过少：{sorted(types)}"
    assert types <= RELATION_TYPES, f"样例用了不存在的类型：{sorted(types - RELATION_TYPES)}"


def test_every_example_relation_survives_the_compiler_gate() -> None:
    """真正的判据：照抄样例的输出不会被 `_compile_relations` 丢弃。"""
    examples = _example_relations(_batch_prompt())
    # 计划层会把 source_key/target_key 换成名字，编译器按名字解析。
    names = {
        key: f"知识点{key}"
        for item in examples
        for key in (item["source_key"], item["target_key"])
    }
    candidates = [
        {
            **{k: v for k, v in item.items() if k not in {"source_key", "target_key"}},
            "source_name": names[item["source_key"]],
            "target_name": names[item["target_key"]],
        }
        for item in examples
    ]
    point_by_name = {
        _normalize_name(name): {"knowledge_id": f"ckp_{key}", "name": name}
        for key, name in names.items()
    }
    invalid: list[dict] = []
    unresolved: list[dict] = []

    compiled = _compile_relations(
        "course-1", candidates, point_by_name, {}, invalid, unresolved,
    )

    assert [item["rejection_reason"] for item in invalid] == []
    assert unresolved == []
    assert len(compiled) == len(examples)
