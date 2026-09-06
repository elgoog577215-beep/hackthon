"""全课教案装配：重试批次不得抹掉已经成功的小节内容（数据损坏级）。

**缺陷来源**：`assemble_course_teaching_plan_v3` 用

    details_by_id = {node_id: item for batch in batches for item in batch.sections}

按 `node_id` 收集各批次小节，**后写覆盖前写**。NOTES 3.12 实测到
`L2-2-3` 的模型输出序列是 `[3, 0, 1]`（先给 3 条关系、纠正轮给 0 条、
再给 1 条）。那次最后一轮是 1 条所以侥幸无事，**若最后一轮为 0，
前面那批内容会被整段抹掉**。

**这是丢数据，不是丢质量**：没有任何报错、没有留痕，教师看到的是一节
凭空少了知识点与关系，而生成链路报告"成功"。

**修法的边界**：不做并集，也不做"取最多的一次"——那两种都要先定
"重试后以哪次为准"的产品语义（同一小节两轮都有内容时，后一轮可能是模型
**故意**删掉了不成立的关系，并集会把它救回来）。这里只堵死无歧义的那种：
**空的一轮不许覆盖非空的一轮**。一轮什么都没返回是失败，不是删除意图。
"""

from __future__ import annotations

from course_teaching_plan_v3 import assemble_course_teaching_plan_v3

SKELETON = {
    "revision_id": "skeleton-1",
    "knowledge_registry": [
        {"knowledge_key": "K001", "name": "交流电", "statement": "周期性变化的电流。"},
        {"knowledge_key": "K002", "name": "有效值", "statement": "按热效应等效的直流值。"},
    ],
    "sections": [{
        "node_id": "L2-1-1",
        "owned_knowledge_keys": ["K001", "K002"],
        "reused_knowledge_keys": [],
    }],
}


def _batch(batch_id: str, *, details: list[dict], relations: list[dict]):
    return {
        "batch_id": batch_id,
        "sections": [{
            "node_id": "L2-1-1",
            "knowledge_details": details,
            "knowledge_relations": relations,
            "teaching_modules": [],
        }],
    }


def _rich():
    return _batch(
        "b1",
        details=[
            {"knowledge_key": "K001", "concept_group": "交流电基础"},
            {"knowledge_key": "K002", "concept_group": "交流电基础"},
        ],
        relations=[
            {"source_key": "K001", "target_key": "K002",
             "relation_type": "prerequisite", "reason": "先懂交流电才能定义有效值"},
            {"source_key": "K002", "target_key": "K001",
             "relation_type": "derives", "reason": "有效值由交流电波形推出",
             "derivation_steps": ["取一个周期", "算焦耳热", "令其与直流相等"]},
            {"source_key": "K001", "target_key": "K002",
             "relation_type": "contrasts_with", "reason": "峰值与有效值常被混同",
             "distinction": "峰值是瞬时最大，有效值按热效应等效"},
        ],
    )


def _empty():
    return _batch("b2", details=[], relations=[])


def _relations(assembled) -> list[dict]:
    return assembled["sections"][0]["knowledge_relations"]


def _point_names(assembled) -> list[str]:
    return [
        point["name"]
        for group in assembled["sections"][0]["knowledge_structure"]
        for point in group["knowledge_points"]
    ]


def test_empty_retry_does_not_erase_a_successful_section() -> None:
    """空的重试批次排在后面时，前一批的知识点与关系必须原样保留。

    这是 NOTES 3.12 记的那条数据损坏缺陷的最小复现：修复前这里拿到的是
    0 个知识点、0 条关系。
    """
    assembled = assemble_course_teaching_plan_v3(
        skeleton=SKELETON,
        batches=[_rich(), _empty()],
        outline_revision_id="outline-1",
    )

    assert _point_names(assembled) == ["交流电", "有效值"]
    assert len(_relations(assembled)) == 3


def test_order_does_not_matter_for_an_empty_batch() -> None:
    """空批次排在前面时结果一致——保留的判据是"有没有内容"，不是"第几个"。"""
    assembled = assemble_course_teaching_plan_v3(
        skeleton=SKELETON,
        batches=[_empty(), _rich()],
        outline_revision_id="outline-1",
    )

    assert _point_names(assembled) == ["交流电", "有效值"]
    assert len(_relations(assembled)) == 3


def test_a_later_non_empty_retry_still_wins() -> None:
    """两轮都有内容时仍然后写覆盖前写——不改既有语义，只堵空覆盖。

    这条很重要：纠正轮**故意**删掉不成立的关系是正常行为，不能用并集
    把它救回来，否则校验层刚拒绝的关系会从装配层绕回知识网。
    """
    corrected = _batch(
        "b2",
        details=[{"knowledge_key": "K001", "concept_group": "交流电基础"}],
        relations=[{
            "source_key": "K001", "target_key": "K002",
            "relation_type": "prerequisite", "reason": "纠正后只保留这一条",
        }],
    )

    assembled = assemble_course_teaching_plan_v3(
        skeleton=SKELETON,
        batches=[_rich(), corrected],
        outline_revision_id="outline-1",
    )

    assert _point_names(assembled) == ["交流电"]
    assert len(_relations(assembled)) == 1
    assert _relations(assembled)[0]["reason"] == "纠正后只保留这一条"


def test_a_section_with_only_relations_is_not_treated_as_empty() -> None:
    """判据要看整节有没有内容，不能只看知识点。

    一节可以只贡献关系（本节不引入新知识、只把已学知识连起来）。
    若判据写成"没有 knowledge_details 就算空"，这种小节会被误判成失败轮。
    """
    relations_only = _batch(
        "b2",
        details=[],
        relations=[{
            "source_key": "K001", "target_key": "K002",
            "relation_type": "applies_to", "reason": "只连关系不引入新知识",
        }],
    )

    assembled = assemble_course_teaching_plan_v3(
        skeleton=SKELETON,
        batches=[_rich(), relations_only],
        outline_revision_id="outline-1",
    )

    assert len(_relations(assembled)) == 1
    assert _relations(assembled)[0]["relation_type"] == "applies_to"
