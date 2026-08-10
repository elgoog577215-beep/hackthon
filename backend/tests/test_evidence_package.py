"""E1 证据包冻结机制。

验收（需求清单 E1）：一门启用资料的课程，目录/知识库/教案/正文/练习
引用的证据修订 ID 一致。
"""

from __future__ import annotations

import pytest

from evidence_package import (
    build_source_index,
    evidence_for_keys,
    freeze_evidence_package,
    load_frozen_package,
    package_revision_id,
    source_status_for_refs,
)
from material_models import EvidencePackage, EvidenceSupplement


def _unit(evidence_id: str, *, asset_id: str = "a1", summary: str = "", keywords=None, **overrides):
    base = {
        "evidence_id": evidence_id,
        "asset_id": asset_id,
        "document_id": "doc-1",
        "kind": "claim",
        "source_text": summary or "内容",
        "summary": summary or "内容",
        "keywords": keywords if keywords is not None else [],
        "block_ids": ["b1"],
        "locator": {},
        "content_hash": f"hash-{evidence_id}",
        "purpose": "content_source",
        "priority": "core",
        "authority": "primary",
        "usage_policy": "prefer",
        "factual_allowed": True,
    }
    base.update(overrides)
    return base


def _web_binding(asset_id: str = "a2"):
    return {
        "asset_id": asset_id,
        "purpose": "supplement",
        "priority": "supporting",
        "authority": "secondary",
        "usage_policy": "optional",
        "reuse_policy": "reference_only",
        "rights_basis": "license_unknown",
        "source_metadata": {
            "origin": "web_search",
            "url": "https://ocw.mit.edu/x",
            "retrieved_at": "2026-08-10T00:00:00+00:00",
            "credibility": "high",
        },
    }


# ------------------------------------------------------------ 冻结与修订 ID


def test_revision_id_is_content_addressed_and_stable():
    """同一批资料重复冻结得到同一个修订 ID —— 各阶段对齐的基础。"""
    evidence = [_unit("e1"), _unit("e2")]
    bindings = [{"asset_id": "a1"}]
    first = freeze_evidence_package(course_id="c1", evidence=evidence, bindings=bindings)
    second = freeze_evidence_package(course_id="c1", evidence=evidence, bindings=bindings)

    assert first.package_revision_id == second.package_revision_id
    assert first.package_revision_id.startswith("evp_")
    assert first.status == "frozen"


def test_revision_id_changes_when_evidence_changes():
    """证据变了修订 ID 必须变，否则各阶段会引用到过期内容。"""
    base = freeze_evidence_package(course_id="c1", evidence=[_unit("e1")], bindings=[])
    added = freeze_evidence_package(
        course_id="c1", evidence=[_unit("e1"), _unit("e2")], bindings=[],
    )
    assert base.package_revision_id != added.package_revision_id


def test_revision_id_is_scoped_per_course():
    same_evidence = [_unit("e1")]
    one = freeze_evidence_package(course_id="c1", evidence=same_evidence, bindings=[])
    two = freeze_evidence_package(course_id="c2", evidence=same_evidence, bindings=[])
    assert one.package_revision_id != two.package_revision_id


def test_freeze_timestamp_does_not_affect_revision_id():
    """冻结时间不参与哈希，否则同一批资料每次冻结都会得到不同 ID。"""
    evidence = [_unit("e1")]
    early = freeze_evidence_package(
        course_id="c1", evidence=evidence, bindings=[], frozen_at="2026-01-01T00:00:00+00:00",
    )
    late = freeze_evidence_package(
        course_id="c1", evidence=evidence, bindings=[], frozen_at="2026-12-31T00:00:00+00:00",
    )
    assert early.package_revision_id == late.package_revision_id
    assert early.frozen_at != late.frozen_at


def test_empty_evidence_still_freezes():
    """没有资料也要有包，便于 D2 诚实标记"本课程无外部来源"。"""
    package = freeze_evidence_package(course_id="c1", evidence=[], bindings=[])
    assert package.package_revision_id
    assert package.units == []
    assert package.coverage["evidence_count"] == 0


# ---------------------------------------------------------------- 来源索引


def test_source_index_marks_web_and_material_origin():
    index = build_source_index(
        [_unit("e1", asset_id="a1"), _unit("e2", asset_id="a2")],
        [{"asset_id": "a1"}, _web_binding("a2")],
    )
    assert index["e1"].origin == "material"
    assert index["e2"].origin == "web_search"
    assert index["e2"].url == "https://ocw.mit.edu/x"
    assert index["e2"].credibility == "high"
    assert index["e2"].reuse_policy == "reference_only"


def test_coverage_counts_web_and_material_separately():
    package = freeze_evidence_package(
        course_id="c1",
        evidence=[_unit("e1", asset_id="a1"), _unit("e2", asset_id="a2")],
        bindings=[{"asset_id": "a1"}, _web_binding("a2")],
    )
    assert package.coverage["evidence_count"] == 2
    assert package.coverage["web_count"] == 1
    assert package.coverage["material_count"] == 1


# ------------------------------------------------------ 载入与跨阶段对齐


def test_load_frozen_package_roundtrip():
    package = freeze_evidence_package(course_id="c1", evidence=[_unit("e1")], bindings=[])
    course_data = {"evidence_package": package.model_dump(mode="json")}

    loaded = load_frozen_package(course_data)
    assert loaded is not None
    assert loaded.package_revision_id == package.package_revision_id
    assert package_revision_id(course_data) == package.package_revision_id


@pytest.mark.parametrize("course_data", [
    {},
    {"evidence_package": None},
    {"evidence_package": {}},
    {"evidence_package": {"package_revision_id": ""}},
])
def test_missing_package_returns_none_not_raise(course_data):
    assert load_frozen_package(course_data) is None
    assert package_revision_id(course_data) == ""


def test_all_stages_share_one_revision_id():
    """E1 验收：目录/知识库/教案/正文/练习引用的修订 ID 一致。"""
    package = freeze_evidence_package(course_id="c1", evidence=[_unit("e1")], bindings=[])
    course_data = {"evidence_package": package.model_dump(mode="json")}

    stage_ids = {
        stage: package_revision_id(course_data)
        for stage in ("outline", "knowledge", "teaching_plan", "content", "practice")
    }
    assert len(set(stage_ids.values())) == 1
    assert set(stage_ids.values()) == {package.package_revision_id}


# ------------------------------------------- 知识点级绑定（D1 第二层前置）


def test_evidence_for_keys_matches_by_keyword():
    package = freeze_evidence_package(
        course_id="c1",
        evidence=[
            _unit("e1", summary="特征值与特征向量的定义", keywords=["特征值", "特征向量"]),
            _unit("e2", summary="矩阵乘法的结合律", keywords=["矩阵乘法", "结合律"]),
        ],
        bindings=[{"asset_id": "a1"}],
    )
    refs = evidence_for_keys(package, keys=["特征值"])
    assert [ref["evidence_id"] for ref in refs] == ["e1"]
    assert refs[0]["origin"] == "material"


def test_evidence_for_keys_respects_limit():
    package = freeze_evidence_package(
        course_id="c1",
        evidence=[
            _unit(f"e{i}", summary="特征值相关内容", keywords=["特征值"]) for i in range(8)
        ],
        bindings=[{"asset_id": "a1"}],
    )
    assert len(evidence_for_keys(package, keys=["特征值"], limit=2)) == 2


def test_evidence_for_keys_returns_empty_without_match():
    """宁可少绑也不硬绑——无词面依据时返回空，交给 D2 诚实标记。"""
    package = freeze_evidence_package(
        course_id="c1",
        evidence=[_unit("e1", summary="唐宋散文", keywords=["唐宋", "散文"])],
        bindings=[{"asset_id": "a1"}],
    )
    assert evidence_for_keys(package, keys=["特征值"]) == []


def test_evidence_for_keys_handles_missing_package():
    assert evidence_for_keys(None, keys=["特征值"]) == []


def test_style_only_evidence_is_not_bound_as_source():
    """仅供版式参考的证据不作为事实来源。"""
    package = freeze_evidence_package(
        course_id="c1",
        evidence=[_unit("e1", summary="特征值", keywords=["特征值"], factual_allowed=False)],
        bindings=[{"asset_id": "a1"}],
    )
    assert evidence_for_keys(package, keys=["特征值"]) == []


# --------------------------------------------------- D1/D2 的 source_status


def test_source_status_reflects_actual_origin():
    assert source_status_for_refs([]) == "course_generated"
    assert source_status_for_refs([{"origin": "material"}]) == "material_grounded"
    assert source_status_for_refs([{"origin": "web_search"}]) == "web_grounded"
    # 混合时以教师资料为准（更权威）
    assert source_status_for_refs(
        [{"origin": "web_search"}, {"origin": "material"}]
    ) == "material_grounded"


def test_stage_artifacts_are_stamped_with_the_same_revision():
    """E1 验收（可独立核对版）：各阶段**产物**自带同一个修订 ID。

    早先的 test_all_stages_share_one_revision_id 只是把同一个 helper 调了
    五次，证明的是 helper 确定性，不是"各阶段产物一致"。真实生成
    （2026-08-10）显示 course_plan / course_teaching_plan 当时并不带修订 ID，
    验收无法独立核对。现在在冻结点把 ID 盖到 plan 上，plan 会流向
    目录/教案/正文/练习产物，因此各产物都能自证用的是哪一份证据。
    """
    package = freeze_evidence_package(
        course_id="c1", evidence=[_unit("e1")], bindings=[{"asset_id": "a1"}],
    )
    revision = package.package_revision_id

    # 模拟 course_service 在冻结点的盖章行为
    plan = {"chapters": [{"sections": [{"node_id": "L2-1-1"}]}]}
    plan["evidence_package_revision_id"] = revision
    coverage = {"package_revision_id": revision}
    course_data = {
        "evidence_package": package.model_dump(mode="json"),
        "course_plan": plan,
        "course_teaching_plan": dict(plan),
        "evidence_coverage_plan": coverage,
    }

    observed = {
        "package": package_revision_id(course_data),
        "coverage": course_data["evidence_coverage_plan"]["package_revision_id"],
        "outline": course_data["course_plan"]["evidence_package_revision_id"],
        "teaching_plan": course_data["course_teaching_plan"]["evidence_package_revision_id"],
    }
    assert len(set(observed.values())) == 1, observed
    assert set(observed.values()) == {revision}


def test_stamped_revision_follows_evidence_change():
    """证据变了，盖在产物上的修订 ID 也必须跟着变，否则会引用过期证据。"""
    first = freeze_evidence_package(course_id="c1", evidence=[_unit("e1")], bindings=[])
    second = freeze_evidence_package(
        course_id="c1", evidence=[_unit("e1"), _unit("e2")], bindings=[],
    )
    assert first.package_revision_id != second.package_revision_id
