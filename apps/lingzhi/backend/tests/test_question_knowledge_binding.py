"""G4：正式题目直接绑定课程知识库里真实存在的知识点/能力点/易错点。

改动前主生成链路写的"知识点 ID"是 `stable_hash(..., prefix="ck_")` 自造的，而
知识库里知识点的正式 ID 是 `ckp_…`。两者不是一个命名空间，于是题上记着的
绑定在知识库里查不到实体——**不是间接绑定，是悬空绑定**。回答不了"这道题考
哪个知识点"，也做不了知识点级覆盖率。
"""
from __future__ import annotations

from question_knowledge_binding import (
    knowledge_point_coverage,
    resolve_node_knowledge_binding,
)


def _knowledge_base() -> dict:
    """一份最小但结构真实的已编译知识库。

    ID 前缀与 course_knowledge_base 的正式产物一致：知识点 ckp_、能力点 cks_、
    易错点 ckm_、掌握标准 ckmc_。
    """
    return {
        "schema_version": "course_knowledge_base_v1",
        "course_id": "c1",
        "knowledge_points": [
            {
                "knowledge_id": "ckp_energy",
                "name": "能量守恒",
                "section_refs": ["L2-1-1"],
            },
            {
                "knowledge_id": "ckp_first_law",
                "name": "热力学第一定律",
                "section_refs": ["L2-1-1"],
            },
            {
                "knowledge_id": "ckp_entropy",
                "name": "熵",
                "section_refs": ["L2-2-1"],
            },
        ],
        "skill_units": [
            {"skill_id": "cks_apply_first_law", "primary_knowledge_id": "ckp_first_law"},
            {"skill_id": "cks_entropy_sign", "primary_knowledge_id": "ckp_entropy"},
        ],
        "misconceptions": [
            {"misconception_id": "ckm_sign_flip", "primary_knowledge_id": "ckp_first_law"},
            {"misconception_id": "ckm_entropy_direction", "primary_knowledge_id": "ckp_entropy"},
        ],
        "mastery_criteria": [
            {
                "criterion_id": "ckmc_compute_delta_u",
                "knowledge_ids": ["ckp_first_law", "ckp_energy"],
            },
            {"criterion_id": "ckmc_judge_direction", "knowledge_ids": ["ckp_entropy"]},
        ],
    }


def _course() -> dict:
    return {
        "course_id": "c1",
        "course_knowledge_base": _knowledge_base(),
        "nodes": [
            {"node_id": "L2-1-1", "node_level": 2, "node_name": "热力学第一定律"},
            {"node_id": "L2-2-1", "node_level": 2, "node_name": "熵与方向"},
        ],
    }


# --- 解析 -------------------------------------------------------------------


def test_resolves_real_knowledge_ids_for_a_section() -> None:
    binding = resolve_node_knowledge_binding(_course(), "L2-1-1")

    assert binding["resolved"] is True
    assert binding["knowledge_ids"] == ["ckp_energy", "ckp_first_law"]
    # 能力点/易错点经 primary_knowledge_id 归属，只取本节知识点名下的
    assert binding["skill_ids"] == ["cks_apply_first_law"]
    assert binding["misconception_ids"] == ["ckm_sign_flip"]
    # 掌握标准是多对多，与本节知识点有交集即算
    assert binding["mastery_ids"] == ["ckmc_compute_delta_u"]


def test_other_sections_do_not_leak_into_the_binding() -> None:
    binding = resolve_node_knowledge_binding(_course(), "L2-2-1")

    assert binding["knowledge_ids"] == ["ckp_entropy"]
    assert "ckp_first_law" not in binding["knowledge_ids"]
    assert binding["skill_ids"] == ["cks_entropy_sign"]


def test_unresolved_is_distinguishable_from_resolved_empty() -> None:
    """"没解析出来"与"解析出空"必须能区分，后者才是事实。"""
    no_base = resolve_node_knowledge_binding({"course_id": "c1"}, "L2-1-1")
    assert no_base["resolved"] is False
    assert "知识库" in no_base["reason"]

    unknown_section = resolve_node_knowledge_binding(_course(), "L2-9-9")
    assert unknown_section["resolved"] is False
    assert unknown_section["knowledge_ids"] == []
    assert unknown_section["reason"]


def test_missing_node_id_is_reported_not_guessed() -> None:
    binding = resolve_node_knowledge_binding(_course(), "")
    assert binding["resolved"] is False
    assert binding["knowledge_ids"] == []


# --- 知识点级覆盖率（G4 验收物） --------------------------------------------


def test_coverage_counts_questions_per_knowledge_point() -> None:
    items = [
        {"revision_id": "q1", "course_knowledge_refs": ["ckp_first_law"]},
        {"revision_id": "q2", "course_knowledge_refs": ["ckp_first_law", "ckp_energy"]},
    ]
    coverage = knowledge_point_coverage(_course(), items)

    assert coverage["knowledge_point_total"] == 3
    assert coverage["covered_knowledge_point_count"] == 2
    assert coverage["questions_per_knowledge_id"]["ckp_first_law"] == 2
    assert coverage["questions_per_knowledge_id"]["ckp_energy"] == 1
    assert coverage["questions_per_knowledge_id"]["ckp_entropy"] == 0
    assert coverage["uncovered_knowledge_ids"] == ["ckp_entropy"]


def test_coverage_surfaces_dangling_refs_instead_of_ignoring_them() -> None:
    """这正是 G4 之前的病灶：题上写着 ck_…，库里只有 ckp_…。

    两边看起来都"有绑定"，但连不上。静默忽略会让覆盖率显示为 0 而看不出原因，
    所以悬空引用必须单独报出来。
    """
    items = [
        {"revision_id": "q1", "course_knowledge_refs": ["ck_abc123"]},
        {"revision_id": "q2", "course_knowledge_refs": ["ck_abc123", "ckp_energy"]},
    ]
    coverage = knowledge_point_coverage(_course(), items)

    assert coverage["dangling_refs"] == {"ck_abc123": 2}
    assert coverage["questions_per_knowledge_id"]["ckp_energy"] == 1
    # q1 一条真实绑定都没有，必须点名
    assert coverage["items_without_knowledge_binding"] == ["q1"]


def test_coverage_accepts_the_public_concept_ids_projection() -> None:
    """公开题面上这三个字段叫 concept_ids，覆盖率统计要认同一份数据。"""
    coverage = knowledge_point_coverage(
        _course(),
        [{"revision_id": "q1", "concept_ids": ["ckp_entropy"]}],
    )
    assert coverage["questions_per_knowledge_id"]["ckp_entropy"] == 1
    assert coverage["items_without_knowledge_binding"] == []


def test_coverage_without_a_knowledge_base_reports_zero_points() -> None:
    coverage = knowledge_point_coverage({"course_id": "c1"}, [
        {"revision_id": "q1", "course_knowledge_refs": ["ckp_energy"]},
    ])
    assert coverage["knowledge_point_total"] == 0
    assert coverage["dangling_refs"] == {"ckp_energy": 1}


# --- 接到题库主链路 ---------------------------------------------------------


def test_question_bank_items_bind_to_real_knowledge_ids() -> None:
    """主生成链路产出的题必须带真实 ckp_ / cks_ / ckm_ / ckmc_ ID。"""
    from question_bank import (
        _node_knowledge_refs,
        _node_mastery_refs,
        _node_misconception_refs,
        _node_skill_refs,
    )

    course = _course()
    node = course["nodes"][0]

    assert _node_knowledge_refs(course, node) == ["ckp_energy", "ckp_first_law"]
    assert _node_skill_refs(course, node) == ["cks_apply_first_law"]
    assert _node_misconception_refs(course, node) == ["ckm_sign_flip"]
    assert _node_mastery_refs(course, node) == ["ckmc_compute_delta_u"]


def test_question_bank_falls_back_honestly_without_a_knowledge_base() -> None:
    """没有知识库的老课程仍要能出题，退回原有合成 ID，不报错、不留空。"""
    from question_bank import _node_knowledge_refs

    legacy = {"course_id": "c1", "nodes": []}
    node = {"node_id": "L2-1-1", "node_level": 2, "key_points": ["能量守恒"]}

    refs = _node_knowledge_refs(legacy, node)
    assert refs, "没有知识库时不能退化成空绑定"
    assert all(ref.startswith("ck_") for ref in refs), (
        "兜底 ID 必须保持 ck_ 前缀，不得伪装成知识库里的 ckp_"
    )


def test_node_carried_refs_are_still_honoured_when_base_lacks_the_section() -> None:
    """知识库里没有这一节时，仍尊重小节自己带的 refs。"""
    from question_bank import _node_knowledge_refs

    course = _course()
    node = {
        "node_id": "L2-9-9",
        "node_level": 2,
        "course_knowledge_refs": ["ckp_explicitly_pinned"],
    }
    assert _node_knowledge_refs(course, node) == ["ckp_explicitly_pinned"]
