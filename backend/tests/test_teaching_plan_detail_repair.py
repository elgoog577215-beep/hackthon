"""按知识点粒度补写：定位缺口、合并补写、不放宽判据。

批次校验是全有全无的：38 个知识点里任何一个漏写 `misconceptions`，整批就判失败、
落本地回退、触发整轮语义重试。实测单点漏写率约 2.9%，于是全课一次通过率只有
(1-0.029)^38 ≈ 33%——这个结构注定发不出版本。

补写域把**修复粒度**从"整批"降到"单个知识点"，但**判据一个字都不放宽**：
补不回来照样判失败。这组测试就是钉住这条边界。
"""

from __future__ import annotations

from course_teaching_plan_v3 import (
    build_knowledge_detail_repair_prompt,
    collect_knowledge_detail_gaps,
    merge_knowledge_detail_repair,
    normalize_teaching_plan_batch_v3,
    validate_teaching_plan_batch_v3,
)

SKELETON = {
    "revision_id": "teaching_skeleton_test",
    "knowledge_registry": [
        {
            "knowledge_key": "K001",
            "name": "线性组合",
            "statement": "向量按标量加权后相加。",
            "owner_node_id": "L2-1-1",
            "module_ids": ["core_explanation"],
        },
        {
            "knowledge_key": "K002",
            "name": "张成空间",
            "statement": "所有线性组合构成的集合。",
            "owner_node_id": "L2-1-1",
            "module_ids": ["core_explanation"],
        },
    ],
    "sections": [
        {
            "node_id": "L2-1-1",
            "owned_knowledge_keys": ["K001", "K002"],
            "reused_knowledge_keys": [],
        },
    ],
}

SECTIONS = [{
    "node_id": "L2-1-1",
    "module_plan": [{"module_id": "core_explanation", "label": "核心教学"}],
}]

SPEC = {"batch_id": "TP-B01", "section_ids": ["L2-1-1"]}


def _detail(key: str, **overrides) -> dict:
    detail = {
        "knowledge_key": key,
        "concept_group": "核心机制",
        "knowledge_type": "concept",
        "capability_points": [{"observable_behavior": f"能写出{key}的表达"}],
        "mastery_criteria": [{
            "observable_performance": "独立完成两组分解",
            "verification_method": "课堂出口题",
        }],
        "misconceptions": [{
            "observable_error_pattern": "把系数当作分量",
            "discrimination": "看系数是否随基改变",
            "repair_strategy": "用几何缩放辨析",
        }],
    }
    detail.update(overrides)
    return detail


def _batch(*details: dict, relations: list | None = None) -> dict:
    return normalize_teaching_plan_batch_v3(
        {
            "sections": [{
                "node_id": "L2-1-1",
                "knowledge_details": list(details),
                "knowledge_relations": relations if relations is not None else [{
                    "source_key": "K001",
                    "target_key": "K002",
                    "relation_type": "prerequisite",
                    "reason": "张成空间建立在线性组合之上",
                }],
                "teaching_modules": [{
                    "module_id": "core_explanation",
                    "teaching_purpose": "讲清核心",
                    "knowledge_keys": ["K001"],
                }],
            }],
        },
        batch_id="TP-B01",
        skeleton_revision_id="teaching_skeleton_test",
    )


def _validate(batch: dict) -> dict:
    return validate_teaching_plan_batch_v3(
        batch, batch_spec=SPEC, skeleton=SKELETON, sections=SECTIONS,
    )


def _gaps(batch: dict) -> list[dict]:
    return collect_knowledge_detail_gaps(batch, batch_spec=SPEC, skeleton=SKELETON)


def test_complete_batch_reports_no_gaps():
    batch = _batch(_detail("K001"), _detail("K002"))

    assert _validate(batch)["passed"] is True
    assert _gaps(batch) == []


def test_single_missing_field_is_located_to_one_knowledge_point():
    """这是本条改动的核心场景：38 个点里 1 个漏写，只补那一个。"""
    batch = _batch(_detail("K001", misconceptions=[]), _detail("K002"))

    report = _validate(batch)
    assert report["passed"] is False
    assert "teaching_batch:missing_misconception" in [
        item["code"] for item in report["blocking_issues"]
    ]

    gaps = _gaps(batch)
    assert len(gaps) == 1
    assert gaps[0]["knowledge_key"] == "K001"
    assert gaps[0]["missing_fields"] == ["misconceptions"]
    # 补写要用到的身份信息来自骨架，不是模型上一次的输出。
    assert gaps[0]["name"] == "线性组合"
    assert gaps[0]["statement"] == "向量按标量加权后相加。"


def test_empty_shell_entries_count_as_missing():
    """给了 mastery_criteria 但没有 verification_method，等于没给。

    这类"空壳"最危险：整批校验会报 empty_mastery，如果补写域认为"字段已存在"
    就不去补，批次会永远卡住。所以两边必须用同一组谓词。
    """
    batch = _batch(
        _detail("K001", mastery_criteria=[{"observable_performance": "做两题"}]),
        _detail("K002"),
    )

    report = _validate(batch)
    assert "teaching_batch:empty_mastery" in [
        item["code"] for item in report["blocking_issues"]
    ]
    gaps = _gaps(batch)
    assert len(gaps) == 1
    assert gaps[0]["missing_fields"] == ["mastery_criteria"]


def test_multiple_fields_and_points_are_all_located():
    """一个批次里多个知识点各缺不同字段时，逐点定位、逐点补。

    用 4 个知识点缺 2 个（50%，正好在阈值内）：真实场景就是零星漏写，
    不是整体跑偏。
    """
    skeleton = {
        "revision_id": "teaching_skeleton_test",
        "knowledge_registry": [
            {
                "knowledge_key": key,
                "name": f"知识{key}",
                "statement": "说明。",
                "owner_node_id": "L2-1-1",
                "module_ids": ["core_explanation"],
            }
            for key in ("K001", "K002", "K003", "K004")
        ],
        "sections": [{
            "node_id": "L2-1-1",
            "owned_knowledge_keys": ["K001", "K002", "K003", "K004"],
            "reused_knowledge_keys": [],
        }],
    }
    batch = normalize_teaching_plan_batch_v3(
        {
            "sections": [{
                "node_id": "L2-1-1",
                "knowledge_details": [
                    _detail("K001", misconceptions=[], capability_points=[]),
                    _detail("K002", mastery_criteria=[]),
                    _detail("K003"),
                    _detail("K004"),
                ],
                "knowledge_relations": [],
                "teaching_modules": [],
            }],
        },
        batch_id="TP-B01",
        skeleton_revision_id="teaching_skeleton_test",
    )

    gaps = collect_knowledge_detail_gaps(batch, batch_spec=SPEC, skeleton=skeleton)
    assert [item["knowledge_key"] for item in gaps] == ["K001", "K002"]
    assert gaps[0]["missing_fields"] == ["capability_points", "misconceptions"]
    assert gaps[1]["missing_fields"] == ["mastery_criteria"]


def test_structural_errors_are_not_treated_as_repairable_gaps():
    """知识键与骨架对不上是结构错误，整批重来，不能靠补字段救。"""
    batch = _batch(_detail("K001"))  # 少了 K002
    assert _validate(batch)["passed"] is False
    assert _gaps(batch) == []

    wrong_section = normalize_teaching_plan_batch_v3(
        {"sections": [{"node_id": "L2-9-9", "knowledge_details": []}]},
        batch_id="TP-B01", skeleton_revision_id="teaching_skeleton_test",
    )
    assert _gaps(wrong_section) == []


def test_relation_failures_are_not_knowledge_detail_gaps():
    """关系类错误不属于**知识点**补写域，它由关系补写域单独处理。"""
    batch = _batch(
        _detail("K001"), _detail("K002"),
        relations=[{
            "source_key": "K001", "target_key": "K002",
            "relation_type": "derives",  # 缺 derivation_steps
            "reason": "推导",
        }],
    )
    report = _validate(batch)
    assert report["passed"] is False
    assert "teaching_batch:relation_missing_required_field" in [
        item["code"] for item in report["blocking_issues"]
    ]
    # 明细字段都齐全，知识点补写域为空；这条缺口归 collect_relation_field_gaps
    assert _gaps(batch) == []


def test_merge_fills_only_the_missing_field_and_passes_validation():
    batch = _batch(_detail("K001", misconceptions=[]), _detail("K002"))
    before = batch["sections"][0]["knowledge_details"][0]["capability_points"]

    merged = merge_knowledge_detail_repair(
        batch, node_id="L2-1-1", knowledge_key="K001",
        repair={"misconceptions": [{
            "observable_error_pattern": "把系数当作分量",
            "discrimination": "看系数是否随基改变",
            "repair_strategy": "用几何缩放辨析",
        }]},
        missing_fields=["misconceptions"],
    )

    assert merged is True
    assert _validate(batch)["passed"] is True
    # 没让补写覆盖模型已经写对的字段
    assert batch["sections"][0]["knowledge_details"][0]["capability_points"] == before


def test_merge_rejects_repairs_that_are_still_empty_shells():
    """补写把判据洗白是最危险的失败模式，必须挡住。"""
    batch = _batch(_detail("K001", mastery_criteria=[]), _detail("K002"))

    merged = merge_knowledge_detail_repair(
        batch, node_id="L2-1-1", knowledge_key="K001",
        # 缺 verification_method —— 补了等于没补
        repair={"mastery_criteria": [{"observable_performance": "做两题"}]},
        missing_fields=["mastery_criteria"],
    )

    assert merged is False
    assert _validate(batch)["passed"] is False


def test_merge_requires_every_missing_field_to_be_filled():
    batch = _batch(_detail("K001", misconceptions=[], capability_points=[]), _detail("K002"))

    merged = merge_knowledge_detail_repair(
        batch, node_id="L2-1-1", knowledge_key="K001",
        repair={"capability_points": [{"observable_behavior": "能写出系数组合"}]},
        missing_fields=["capability_points", "misconceptions"],
    )

    # 只补上一个字段不算成功，批次仍然判失败
    assert merged is False
    assert _validate(batch)["passed"] is False


def test_merge_accepts_alias_shapes_from_the_model():
    """模型常用同义键名。形状漂移由既有的别名修复层处理，补写要能复用它。"""
    batch = _batch(_detail("K001", misconceptions=[]), _detail("K002"))

    merged = merge_knowledge_detail_repair(
        batch, node_id="L2-1-1", knowledge_key="K001",
        repair={"misconceptions": [{
            "error_pattern": "把系数当作分量",
            "why": "看系数是否随基改变",
            "fix": "用几何缩放辨析",
        }]},
        missing_fields=["misconceptions"],
    )

    assert merged is True
    assert _validate(batch)["passed"] is True


def test_repair_prompt_is_small_enough_to_never_truncate():
    """补写提示只带一个知识点，输出结构上不可能撞 max_tokens。

    这正是把「漏写」与「截断」两类失败分开的关键：整批纠正要重发上万字符原文，
    本身就可能再次截断；补写不会。
    """
    gap = {
        "name": "线性组合",
        "statement": "向量按标量加权后相加。",
        "knowledge_type": "concept",
        "conditions": ["向量属于同一向量空间"],
        "boundaries": ["系数来自指定数域"],
        "missing_fields": ["capability_points", "mastery_criteria", "misconceptions"],
    }
    prompt = build_knowledge_detail_repair_prompt(gap)

    assert len(prompt) < 1200
    assert "线性组合" in prompt
    assert "observable_behavior" in prompt
    assert "verification_method" in prompt
    assert "repair_strategy" in prompt


def test_repair_prompt_only_asks_for_the_missing_fields():
    prompt = build_knowledge_detail_repair_prompt({
        "name": "线性组合", "missing_fields": ["misconceptions"],
    })

    assert "observable_error_pattern" in prompt
    assert "observable_behavior" not in prompt
    assert "verification_method" not in prompt


def test_truncated_output_is_not_treated_as_a_repairable_gap():
    """截断是 max_tokens 问题，不是漏写问题，两条路必须分开。

    截断的输出解析不出完整批次，`section_mismatch`/`knowledge_key_mismatch` 会先
    命中，补写域返回空——交回原有的加倍重试路径处理，不会被误当成"缺字段"去补。
    """
    # 模拟截断：只解析出半个批次（缺了 K002）
    partial = normalize_teaching_plan_batch_v3(
        {"sections": [{"node_id": "L2-1-1", "knowledge_details": [_detail("K001")]}]},
        batch_id="TP-B01", skeleton_revision_id="teaching_skeleton_test",
    )
    report = _validate(partial)

    assert report["passed"] is False
    assert "teaching_batch:knowledge_key_mismatch" in [
        item["code"] for item in report["blocking_issues"]
    ]
    assert _gaps(partial) == []


def test_repair_never_relaxes_the_criteria():
    """补写域不能让原本判失败的批次凭空通过。

    这条是整项改动的安全边界：修复粒度变细，判据一个字不放宽。
    """
    batch = _batch(_detail("K001", misconceptions=[]), _detail("K002"))
    assert _validate(batch)["passed"] is False

    # 补写返回垃圾（既不是 dict，也没有目标字段）
    for junk in (None, "", [], {"misconceptions": []}, {"other": "x"}):
        assert merge_knowledge_detail_repair(
            batch, node_id="L2-1-1", knowledge_key="K001",
            repair=junk, missing_fields=["misconceptions"],
        ) is False
        assert _validate(batch)["passed"] is False


def test_wholesale_schema_failure_is_not_repaired_point_by_point():
    """超过一半知识点都缺 = 模型整体跑偏，不是零星漏写。

    这时逐个补写既慢（一批最多 15 个知识点＝15 次串行调用）又多半救不回来，
    应当直接交回整批纠正／本地回退。
    """
    both_missing = _batch(
        _detail("K001", misconceptions=[]),
        _detail("K002", misconceptions=[]),
    )
    assert _validate(both_missing)["passed"] is False
    # 2/2 全缺 > 50% -> 不走补写
    assert _gaps(both_missing) == []

    # 1/2 缺，正好在阈值上 -> 仍然走补写
    one_missing = _batch(_detail("K001", misconceptions=[]), _detail("K002"))
    assert len(_gaps(one_missing)) == 1


# --- 关系必填字段补写 -------------------------------------------------------
# 20 次真实采样里，补完知识点之后剩下的失败 3 次有 2 次是这一条：
# derives 关系少写 derivation_steps，整批被打掉。同样按关系粒度补。

from course_teaching_plan_v3 import (  # noqa: E402
    build_relation_field_repair_prompt,
    collect_relation_field_gaps,
    merge_relation_field_repair,
)


def _relation_batch(**relation_overrides) -> dict:
    relation = {
        "source_key": "K001",
        "target_key": "K002",
        "relation_type": "derives",
        "reason": "张成空间由线性组合推出",
    }
    relation.update(relation_overrides)
    return _batch(_detail("K001"), _detail("K002"), relations=[relation])


def _relation_gaps(batch: dict) -> list[dict]:
    return collect_relation_field_gaps(batch, batch_spec=SPEC, skeleton=SKELETON)


def test_missing_relation_field_is_located_to_one_relation():
    batch = _relation_batch()  # derives 缺 derivation_steps

    assert _validate(batch)["passed"] is False
    gaps = _relation_gaps(batch)
    assert len(gaps) == 1
    assert gaps[0]["missing_fields"] == ["derivation_steps"]
    assert gaps[0]["relation_type"] == "derives"
    # 端点名称来自骨架，补写提示要靠它给上下文
    assert gaps[0]["source_name"] == "线性组合"
    assert gaps[0]["target_name"] == "张成空间"


def test_complete_relation_reports_no_gap():
    batch = _relation_batch(derivation_steps=["从线性组合出发", "取全部系数", "得到张成空间"])
    assert _validate(batch)["passed"] is True
    assert _relation_gaps(batch) == []


def test_relation_repair_fills_field_and_passes_validation():
    batch = _relation_batch()

    merged = merge_relation_field_repair(
        batch, node_id="L2-1-1", relation_index=0,
        repair={"derivation_steps": [
            "从线性组合的定义出发", "取所有可能的系数组合", "得到张成空间",
        ]},
        missing_fields=["derivation_steps"],
    )

    assert merged is True
    assert _validate(batch)["passed"] is True


def test_relation_repair_rejects_empty_content():
    """补不出合格内容照样判失败——判据不放宽。"""
    batch = _relation_batch()

    for junk in (None, {}, {"derivation_steps": []}, {"derivation_steps": ""},
                 {"other": "x"}):
        assert merge_relation_field_repair(
            batch, node_id="L2-1-1", relation_index=0,
            repair=junk, missing_fields=["derivation_steps"],
        ) is False
        assert _validate(batch)["passed"] is False


def test_contrasts_with_requires_distinction():
    batch = _relation_batch(relation_type="contrasts_with", reason="两者常被混同")
    gaps = _relation_gaps(batch)
    assert gaps[0]["missing_fields"] == ["distinction"]

    assert merge_relation_field_repair(
        batch, node_id="L2-1-1", relation_index=0,
        repair={"distinction": "线性组合是运算，张成空间是运算结果的集合"},
        missing_fields=["distinction"],
    ) is True
    assert _validate(batch)["passed"] is True


def test_unknown_relation_endpoints_are_not_repairable():
    """端点不在骨架里是结构问题，补字段没有意义。"""
    batch = _relation_batch(target_key="K999")
    assert _relation_gaps(batch) == []


def test_relation_repair_prompt_is_small():
    prompt = build_relation_field_repair_prompt({
        "relation_type": "derives",
        "source_name": "线性组合", "target_name": "张成空间",
        "source_statement": "向量按标量加权后相加。",
        "target_statement": "所有线性组合构成的集合。",
        "reason": "张成空间由线性组合推出",
        "missing_fields": ["derivation_steps"],
    })

    assert len(prompt) < 900
    assert "derivation_steps" in prompt
    assert "线性组合" in prompt
    assert "distinction" not in prompt
