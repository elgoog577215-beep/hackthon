"""AI 知识拆分候选测试（需求：课程知识库必须支持候选式细化）。

核心判据是"AI 不能直接改知识库"：模型只提出建议，落地必须经白名单命令、
质量门和教师确认。因此每条用例都同时断言产出的候选合法、且活动知识库
未被触碰。模型调用被替身接管，测的是我们的契约而不是模型的发挥。
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from content_blocks import set_node_content_blocks
from course_knowledge_base import compile_course_knowledge_base
from course_knowledge_commands import KnowledgeCommandRejected
from course_knowledge_map import compile_course_knowledge_map
from course_knowledge_refinement import (
    MAX_SPLIT_PARTS,
    KnowledgeRefinementService,
    apply_split_to_knowledge_base,
    build_split_prompt,
    normalize_split_proposal,
)


def _knowledge_points() -> list[dict]:
    return [
        {
            "name": "容量耗尽判定",
            "statement": "当元素数量等于当前容量时，下一次插入必须先获得更大的连续存储空间。",
            "knowledge_type": "rule",
            "conditions": ["使用连续存储且不存在可用槽位"],
            "boundaries": ["尚有空闲槽位时不触发扩容"],
            "capability_points": [{
                "name": "判断扩容触发时机",
                "observable_behavior": "给定长度与容量，准确判断下一次插入是否触发扩容",
            }],
            "mastery_criteria": [{
                "name": "扩容触发判断达标",
                "observable_performance": "在不同长度与容量组合中独立判断扩容时机并说明依据",
                "verification_method": "使用至少三个边界案例进行判断并核对结果",
            }],
            "entry_reason": "这是理解动态数组扩容机制的课程入口。",
            "aliases": ["满容量判定"],
            "relations": [{
                "target_name": "动态数组扩容",
                "relation_type": "prerequisite",
                "reason": "必须先识别容量耗尽，才能确定何时执行扩容",
            }],
        },
        {
            "name": "动态数组扩容",
            "statement": "倍增扩容把少数 O(n) 复制成本分摊到一系列插入，使平均单次插入保持常数阶。",
            "knowledge_type": "principle",
            "conditions": ["扩容因子大于 1 且按几何级数增长"],
            "boundaries": ["结论描述摊还成本，不等于每次插入的最坏成本"],
            "capability_points": [{
                "name": "动态数组扩容实现",
                "observable_behavior": "独立实现倍增扩容并用复制次数解释摊还复杂度",
            }],
            "misconceptions": [{
                "name": "把单次复制成本当作每次插入成本",
                "observable_error_pattern": "看到一次扩容需要复制 n 个元素，就断言每次插入都是 O(n)",
                "discrimination": "区分单次操作最坏成本与一系列操作的摊还成本",
                "repair_strategy": "列出连续插入过程中的扩容位置与累计复制次数后重新计算平均成本",
            }],
            "mastery_criteria": [{
                "name": "扩容实现与分析达标",
                "observable_performance": "独立实现倍增扩容，并正确说明最坏成本与摊还成本的区别",
                "verification_method": "运行连续插入测试并提交复杂度推导",
            }],
            "aliases": ["可变长数组"],
        },
    ]


def _course() -> dict:
    course = {
        "course_id": "course-1",
        "course_name": "数据结构",
        "course_purpose": "systematic",
        "nodes": [{
            "node_id": "section-1",
            "node_level": 2,
            "node_name": "线性表与动态数组",
            "learning_objective": "能够实现动态数组扩容并分析摊还复杂度",
            "knowledge_structure": [{
                "concept_group": "动态容量管理",
                "description": "识别扩容触发条件，并解释倍增扩容的摊还成本",
                "knowledge_points": _knowledge_points(),
            }],
            "key_points": ["容量耗尽判定", "动态数组扩容"],
            "content_blocks": [],
            "generation_status": "completed",
            "node_content": (
                "## 容量耗尽判定\n\n根据长度与容量识别扩容触发时机。\n\n"
                "## 动态数组扩容\n\n实现倍增扩容，并区分最坏成本与摊还成本。"
            ),
        }],
    }
    set_node_content_blocks(course["nodes"][0], course["nodes"][0]["node_content"])
    course["course_knowledge_base"] = compile_course_knowledge_base(
        course, course_map=compile_course_knowledge_map(course),
    )
    return course


def _point(course: dict, name: str = "容量耗尽判定") -> dict:
    return next(
        item for item in course["course_knowledge_base"]["knowledge_points"]
        if item["name"] == name
    )


def _split_answer(parts: int = 2) -> dict:
    templates = [
        {"name": "容量耗尽的判定条件", "statement": "元素数量等于容量即为容量耗尽。",
         "conditions": ["连续存储"], "boundaries": ["有空槽不触发"]},
        {"name": "扩容前置检查", "statement": "插入前必须确认是否已达容量上限。",
         "conditions": ["执行插入"], "boundaries": ["不含扩容策略"]},
        {"name": "容量与长度的区分", "statement": "容量是已分配空间，长度是已用元素数。",
         "conditions": ["动态数组"], "boundaries": ["不涉及缩容"]},
    ]
    return {
        "should_split": True,
        "reason": "包含判定条件与扩容动作两个独立命题",
        "parts": templates[:parts],
    }


class _StubService(KnowledgeRefinementService):
    """替身：接管模型调用，测我们的契约而不是模型的发挥。"""

    def __init__(self, answer) -> None:  # noqa: D107 - 不调用父类 __init__（不需要密钥）
        self._answer = answer
        self.prompts: list[str] = []

    async def _call_llm(self, prompt, **_kwargs):
        self.prompts.append(prompt)
        import json

        return json.dumps(self._answer, ensure_ascii=False) if self._answer is not None else None


# --- 提案规范化：模型不得决定身份 ------------------------------------------


def test_ids_are_derived_by_us_not_by_the_model() -> None:
    """稳定 ID 由父节点确定性派生，模型给的 ID 一律不采信。"""
    course = _course()
    point = _point(course)
    answer = _split_answer()
    answer["parts"][0]["knowledge_id"] = "ckp_model_invented"

    proposal = normalize_split_proposal(answer, point=point)

    ids = [part["knowledge_id"] for part in proposal["parts"]]
    assert "ckp_model_invented" not in ids
    assert all(item.startswith("ckp_") for item in ids)
    # 确定性：同样的输入两次得到同样的 ID。
    assert [p["knowledge_id"] for p in normalize_split_proposal(answer, point=point)["parts"]] == ids


def test_identity_map_is_built_from_parent_to_parts() -> None:
    """旧新映射由我们构造，历史作答才能继续解释。"""
    course = _course()
    point = _point(course)

    proposal = normalize_split_proposal(_split_answer(), point=point)

    assert list(proposal["identity_map"]) == [point["knowledge_id"]]
    assert proposal["identity_map"][point["knowledge_id"]] == [
        part["knowledge_id"] for part in proposal["parts"]
    ]


def test_model_saying_no_split_is_respected() -> None:
    """模型判断不需要拆分时不得强行产出候选。"""
    proposal = normalize_split_proposal(
        {"should_split": False, "reason": "只有一个命题"}, point=_point(_course()),
    )

    assert proposal["should_split"] is False
    assert proposal["parts"] == []


@pytest.mark.parametrize("answer,expected", [
    (None, "model_output_unparseable"),
    ({"should_split": True}, "parts_missing"),
    ({"should_split": True, "parts": [{"name": "只有一个", "statement": "x"}]}, "too_few_valid_parts"),
])
def test_malformed_answers_are_rejected_with_reason(answer, expected) -> None:
    """模型输出不可用时说明原因，不静默产出半个候选。"""
    proposal = normalize_split_proposal(answer, point=_point(_course()))

    assert proposal["should_split"] is False
    assert proposal["rejected_reason"] == expected


def test_too_many_parts_is_rejected() -> None:
    """拆得过碎多半是模型在切同一个命题，拒绝。"""
    answer = {"should_split": True, "reason": "x", "parts": [
        {"name": f"节点{i}", "statement": f"命题{i}"} for i in range(MAX_SPLIT_PARTS + 1)
    ]}

    proposal = normalize_split_proposal(answer, point=_point(_course()))

    assert proposal["rejected_reason"] == "too_many_parts"


def test_parts_without_their_own_proposition_are_dropped() -> None:
    """只有名字没有命题的部分不是独立对象。"""
    answer = _split_answer()
    answer["parts"].append({"name": "缺命题的节点", "statement": "   "})

    proposal = normalize_split_proposal(answer, point=_point(_course()))

    assert len(proposal["parts"]) == 2


# --- 应用到知识库：不留孤儿 -------------------------------------------------


def test_split_repoints_dependents_so_the_gate_passes() -> None:
    """拆分必须重指能力点、掌握标准、绑定和关系，否则质量门必拒。"""
    course = _course()
    base = course["course_knowledge_base"]
    point = _point(course)
    proposal = normalize_split_proposal(_split_answer(), point=point)

    proposed = apply_split_to_knowledge_base(base, proposal)

    new_ids = {part["knowledge_id"] for part in proposal["parts"]}
    old_id = point["knowledge_id"]
    # 父节点消失，子节点就位。
    assert old_id not in {item["knowledge_id"] for item in proposed["knowledge_points"]}
    assert new_ids <= {item["knowledge_id"] for item in proposed["knowledge_points"]}
    # 没有任何记录还指向已消失的父 ID。
    for skill in proposed["skill_units"]:
        assert skill["primary_knowledge_id"] != old_id
    for criterion in proposed["mastery_criteria"]:
        assert old_id not in (criterion.get("knowledge_ids") or [])
    for binding in proposed["bindings"]:
        assert old_id not in (binding.get("knowledge_ids") or [])
    for relation in proposed["relations"]:
        assert relation["source_knowledge_id"] != old_id
        assert relation["target_knowledge_id"] != old_id


def test_split_keeps_the_old_name_resolvable() -> None:
    """旧名要留作别名：教案侧按名字寻址知识。"""
    course = _course()
    point = _point(course)
    proposal = normalize_split_proposal(_split_answer(), point=point)

    proposed = apply_split_to_knowledge_base(course["course_knowledge_base"], proposal)

    for part in proposed["knowledge_points"]:
        if part["knowledge_id"] in {item["knowledge_id"] for item in proposal["parts"]}:
            assert point["name"] in part["aliases"]


def test_applying_to_a_missing_point_is_refused() -> None:
    course = _course()
    proposal = normalize_split_proposal(_split_answer(), point=_point(course))
    proposal["knowledge_id"] = "ckp_ghost"

    with pytest.raises(KnowledgeCommandRejected) as error:
        apply_split_to_knowledge_base(course["course_knowledge_base"], proposal)

    assert error.value.code == "knowledge_point_not_found"


# --- 服务：AI 只提候选，绝不写入 --------------------------------------------


async def test_service_produces_a_confirmable_candidate_without_writing() -> None:
    """AI 拆分建议要能通过质量门成为候选，且活动知识库一个字节不变。"""
    course = _course()
    before = deepcopy(course["course_knowledge_base"])
    service = _StubService(_split_answer())

    result = await service.propose_split(course, knowledge_id=_point(course)["knowledge_id"])

    candidate = result["candidate"]
    assert candidate is not None
    assert candidate["confirmable"] is True
    assert candidate["identity_preserved"] is True
    assert candidate["operation"] == "split_knowledge_point"
    assert candidate["blocking_issues"] == []
    # 关键：确认前活动知识库未被触碰。
    assert course["course_knowledge_base"] == before


async def test_service_reports_when_model_declines_to_split() -> None:
    course = _course()
    service = _StubService({"should_split": False, "reason": "只有一个命题"})

    result = await service.propose_split(course, knowledge_id=_point(course)["knowledge_id"])

    assert result["candidate"] is None
    assert result["proposal"]["should_split"] is False
    assert result["proposal"]["reason"] == "只有一个命题"


async def test_service_reports_gate_rejection_instead_of_raising() -> None:
    """候选过不了质量门时要让教师看到"AI 提了但被拒"，而不是抛错。"""
    course = _course()
    answer = _split_answer()
    # 让两个子节点同名 -> 规范化后只剩一个 -> 数量不足。
    answer["parts"][1]["name"] = answer["parts"][0]["name"]
    service = _StubService(answer)

    result = await service.propose_split(course, knowledge_id=_point(course)["knowledge_id"])

    assert result["candidate"] is None
    assert result["proposal"]["rejected_reason"] == "too_few_valid_parts"


async def test_service_refuses_unknown_knowledge_point() -> None:
    course = _course()
    service = _StubService(_split_answer())

    with pytest.raises(KnowledgeCommandRejected) as error:
        await service.propose_split(course, knowledge_id="ckp_ghost")

    assert error.value.code == "knowledge_point_not_found"


def test_prompt_quotes_only_what_the_judgement_needs() -> None:
    """提示词只带判断所需字段，不把整库塞给模型。"""
    point = _point(_course())

    prompt = build_split_prompt(point)

    assert point["name"] in prompt
    assert point["statement"] in prompt
    # 不应泄漏稳定 ID —— 模型没有理由知道它，也不该复制它。
    assert point["knowledge_id"] not in prompt
