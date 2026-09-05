"""D1-2 知识点级来源绑定（G-2）。

**要解决的问题**：改之前知识点的 `source_refs` 只有小节级 `evidence_refs`
一个来源（`course_knowledge_base.py` 的 `_section_evidence_refs`）。那是
"这一节允许引用哪些证据"，粒度是小节：同一节里每个知识点拿到的是同一串 ID。
后果有两个方向，都不如实——

- 小节挂了资料：该节所有知识点都被记成"有依据"，但没有任何一条能回答
  "这个知识点的依据是哪一块"。落地率虚高。
- 小节没挂资料：知识点级来源恒为空，落地率恒为 0。

**改法**：走 `evidence_package.evidence_for_keys()` 的既有契约，按知识点自己
的名字与别名到冻结包里取匹配证据，写进 `source_bindings`（带 origin/url/
credibility 的明细）并合并进 `source_refs`。

**为什么用名字与别名、不用 statement**：`_match_score` 是词面包含判断，
`statement` 是整句话，拿它当键几乎所有证据都会命中，绑定就失去了"这一块讲的
正是这个知识点"的含义。宁可少绑也不制造看不出依据的绑定。
"""

from __future__ import annotations

from course_knowledge_base import (
    build_course_knowledge_library_view,
    compile_course_knowledge_base,
)
from evidence_package import freeze_evidence_package


def _unit(evidence_id: str, *, asset_id: str, summary: str, keywords: list[str]):
    return {
        "evidence_id": evidence_id,
        "asset_id": asset_id,
        "document_id": "doc-1",
        "kind": "claim",
        "source_text": summary,
        "summary": summary,
        "keywords": keywords,
        "block_ids": ["b1"],
        "locator": {},
        "content_hash": f"hash-{evidence_id}",
        "purpose": "content_source",
        "priority": "core",
        "authority": "primary",
        "usage_policy": "prefer",
        "factual_allowed": True,
    }


def _web_binding(asset_id: str):
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


def _course(*, with_package: bool, web_asset: bool = False):
    """一门两知识点的课：只有"交流电"能在证据里找到词面依据，"变压器"找不到。

    刻意留一个匹配不上的知识点：落地率必须是可区分的中间值，全绑或全不绑都
    无法证明绑定真的按知识点走。
    """
    course = {
        "course_id": "c1",
        "nodes": [{
            "node_id": "L2-1-1",
            "node_level": 2,
            "node_type": "section",
            "node_name": "交流电基础",
            "title": "交流电基础",
            "knowledge_structure": [{
                "concept_group": "电流随时间的变化",
                "knowledge_points": [
                    {
                        "name": "交流电",
                        "statement": "大小和方向都随时间做周期性变化的电流。",
                        "knowledge_type": "definition",
                        "aliases": ["AC"],
                    },
                    {
                        "name": "变压器",
                        "statement": "利用互感改变交变电压的器件。",
                        "knowledge_type": "principle",
                    },
                ],
            }],
        }],
    }
    if not with_package:
        return course
    asset_id = "a2" if web_asset else "a1"
    bindings = [_web_binding(asset_id)] if web_asset else [{"asset_id": asset_id}]
    package = freeze_evidence_package(
        course_id="c1",
        evidence=[_unit(
            "e1",
            asset_id=asset_id,
            summary="交流电的大小和方向随时间周期性变化。",
            keywords=["交流电"],
        )],
        bindings=bindings,
    )
    course["evidence_package"] = package.model_dump(mode="json")
    if web_asset:
        course["material_bindings"] = bindings
        course["evidence_catalog"] = [{"evidence_id": "e1", "asset_id": asset_id}]
    return course


def _points(course):
    return {
        str(item.get("name")): item
        for item in compile_course_knowledge_base(course).get("knowledge_points") or []
    }


def test_without_a_frozen_package_binding_stays_empty() -> None:
    """没有冻结包时不许凭空造来源——D2 诚实标记的下限。"""
    points = _points(_course(with_package=False))

    assert points, "用例本身要能编译出知识点"
    for point in points.values():
        assert point["source_bindings"] == []


def test_matching_knowledge_point_binds_its_own_evidence() -> None:
    """命中的知识点拿到自己的证据，明细带得出 origin 与 evidence_id。"""
    points = _points(_course(with_package=True))

    bound = points["交流电"]["source_bindings"]
    assert [item["evidence_id"] for item in bound] == ["e1"]
    assert bound[0]["origin"] == "material"
    # 合并进 source_refs，`_source_status` 才看得见。
    assert "e1" in points["交流电"]["source_refs"]


def test_unmatched_knowledge_point_reports_no_source() -> None:
    """匹配不上的知识点必须留空，不能继承同节其他知识点的证据。

    这一条是整个改动的要害：小节级继承正是它要修的东西，如果"变压器"也拿到
    `e1`，落地率就又回到了小节粒度。
    """
    points = _points(_course(with_package=True))

    assert points["变压器"]["source_bindings"] == []
    assert "e1" not in points["变压器"]["source_refs"]


def test_landing_rate_uses_knowledge_point_count_as_denominator() -> None:
    """落地率的分母是知识点总数，且与逐点明细算的是同一件事。"""
    course = _course(with_package=True)
    knowledge_base = compile_course_knowledge_base(course)
    view = build_course_knowledge_library_view(
        knowledge_base, {}, {}, course_data=course,
    )
    grounding = view["source_grounding"]

    assert grounding["knowledge_point_count"] == 2
    assert grounding["point_bound_count"] == 1
    assert grounding["point_binding_ratio"] == 0.5


def test_web_only_binding_is_not_reported_as_material() -> None:
    """只能追到联网的知识点必须报 `web_grounded`。

    逐点绑定直接来自冻结包的 `source_index`，不经过 `material_bindings`，
    所以 `_web_evidence_ids` 必须同时看知识点自带的 `origin`——否则一条
    license_unknown 的网页会被报成"教师上传资料依据"。
    """
    course = _course(with_package=True, web_asset=True)
    knowledge_base = compile_course_knowledge_base(course)
    view = build_course_knowledge_library_view(
        knowledge_base, {}, {}, course_data=course,
    )

    projected = {
        str(item.get("name")): item
        for item in view.get("nodes") or []
        if item.get("node_type") == "knowledge_point"
    }
    assert projected["交流电"]["source_status"] == "web_grounded"
    assert view["source_grounding"]["material_grounded_count"] == 0
    assert view["source_grounding"]["web_grounded_count"] == 1


def test_reused_knowledge_point_keeps_its_binding() -> None:
    """同一知识点在第二小节被复用时，绑定不能丢。

    复用走的是 `point_by_name` 那条分支，它只合并 `source_refs` 等字段、
    不重算绑定。绑定是按名字算的，所以首次算出的结果对复用同样成立——
    这条测试钉住"复用分支不会把它清空"。
    """
    course = _course(with_package=True)
    second = {
        "node_id": "L2-1-2",
        "node_level": 2,
        "node_type": "section",
        "node_name": "交流电的应用",
        "title": "交流电的应用",
        "knowledge_structure": [{
            "concept_group": "交流电的应用",
            "knowledge_points": [{
                "name": "交流电",
                "statement": "大小和方向都随时间做周期性变化的电流。",
                "knowledge_type": "definition",
                "aliases": ["AC"],
            }],
        }],
    }
    course["nodes"].append(second)
    points = _points(course)

    reused = points["交流电"]
    assert [item["evidence_id"] for item in reused["source_bindings"]] == ["e1"]
    assert sorted(reused["section_refs"]) == ["L2-1-1", "L2-1-2"]


def test_view_carries_binding_detail_for_the_graph() -> None:
    """前端图谱要在节点上显示"依据是哪一份"，读模型必须带明细而不只是状态。"""
    course = _course(with_package=True)
    knowledge_base = compile_course_knowledge_base(course)
    view = build_course_knowledge_library_view(
        knowledge_base, {}, {}, course_data=course,
    )

    projected = {
        str(item.get("name")): item
        for item in view.get("nodes") or []
        if item.get("node_type") == "knowledge_point"
    }
    assert projected["交流电"]["source_bindings"][0]["evidence_id"] == "e1"
    assert projected["变压器"]["source_bindings"] == []
