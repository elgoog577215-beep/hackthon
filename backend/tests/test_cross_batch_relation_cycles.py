"""跨批次关系环：检测并如实上报，绝不自动断边。

环由两条边"拼"出来，任何单层校验都看不见（真机实测，课程 6fac40e7）：

- 骨架 `prerequisite_keys`：K021(L2-3-3) -> K022(L2-4-1)，方向与小节顺序一致；
- 批次 TP-B04 的 `knowledge_relations`：K022 -> K021，方向相反。

骨架自身无环、批次关系自身也无环，**只有合并才成环**。所以检测点必须放在
汇编之后（唯一能看到完整图的位置），而不是批次校验里。

**本模块只诊断，不修复。** 断哪条边会改变课程的知识结构，属于产品判断。
"""

from __future__ import annotations

from course_generation.relation_validation import diagnose_cross_batch_relation_cycles
from course_generation.service import _record_relation_cycle_diagnosis


def _registry(entries: list[tuple[str, str, str, list[str]]]) -> list[dict]:
    return [
        {
            "knowledge_key": key,
            "name": name,
            "statement": "陈述",
            "owner_node_id": owner,
            "prerequisite_keys": list(prereqs),
            "reused_in_node_ids": [],
            "module_ids": ["core_explanation"],
        }
        for key, name, owner, prereqs in entries
    ]


def _skeleton(entries) -> dict:
    return {
        "schema_version": "course_teaching_plan_skeleton_v3",
        "knowledge_registry": _registry(entries),
        "sections": [
            {"node_id": owner, "owned_knowledge_keys": [key], "reused_knowledge_keys": []}
            for key, _name, owner, _p in entries
        ],
        "revision_id": "skeleton_test",
    }


def _batch(batch_id: str, node_id: str, relations: list[tuple[str, str, str]]) -> dict:
    return {
        "batch_id": batch_id,
        "sections": [{
            "node_id": node_id,
            "knowledge_details": [],
            "knowledge_relations": [
                {"relation_type": kind, "source_key": source, "target_key": target}
                for source, target, kind in relations
            ],
        }],
    }


# 真机形状：泰勒近似(L2-3-3) 与 不定积分(L2-4-1)
_REAL_ENTRIES = [
    ("K018", "导数的定义", "L2-3-1", []),
    ("K021", "局部逼近入门：一阶与二阶泰勒近似", "L2-3-3", ["K018"]),
    ("K022", "原函数与不定积分的概念定义", "L2-4-1", ["K021"]),
]
_SECTIONS = [{"node_id": n} for n in ("L2-3-1", "L2-3-2", "L2-3-3", "L2-4-1")]


def test_cycle_that_only_exists_after_merging_is_detected():
    """骨架与批次各自无环，合并后成环 —— 这正是真机上发生的事。"""
    skeleton = _skeleton(_REAL_ENTRIES)
    batches = [_batch("TP-B04", "L2-4-1", [("K022", "K021", "prerequisite")])]

    reports = diagnose_cross_batch_relation_cycles(
        skeleton=skeleton, batches=batches, sections=_SECTIONS,
    )

    assert len(reports) == 1
    report = reports[0]
    assert set(report["cycle_keys"]) == {"K021", "K022"}
    assert report["layers"] == ["batch", "skeleton"]
    assert report["batch_ids"] == ["TP-B04"]


def test_report_names_the_edge_that_contradicts_section_order():
    """报告要指出哪条边方向不对、由谁声明 —— 这是定处理策略需要的信息。"""
    reports = diagnose_cross_batch_relation_cycles(
        skeleton=_skeleton(_REAL_ENTRIES),
        batches=[_batch("TP-B04", "L2-4-1", [("K022", "K021", "prerequisite")])],
        sections=_SECTIONS,
    )
    edges = reports[0]["edges"]

    skeleton_edge = next(
        e for e in edges
        if any(d["layer"] == "skeleton" for d in e["declared_by"])
    )
    batch_edge = next(
        e for e in edges
        if any(d["layer"] == "batch" for d in e["declared_by"])
    )

    # 骨架边 L2-3-3 -> L2-4-1，与小节顺序一致。
    assert skeleton_edge["agrees_with_section_order"] is True
    assert skeleton_edge["source_section"] == "L2-3-3"
    # 批次边 L2-4-1 -> L2-3-3，方向倒了。
    assert batch_edge["agrees_with_section_order"] is False
    assert batch_edge["declared_by"][0]["batch_id"] == "TP-B04"
    assert batch_edge["declared_by"][0]["declared_in"] == "L2-4-1"
    assert reports[0]["verdict"] == "order_contradiction"
    assert reports[0]["order_contradicting_edge_count"] == 1


def test_detection_never_removes_an_edge():
    """只诊断不修复：输入的骨架与批次必须原样不动。"""
    skeleton = _skeleton(_REAL_ENTRIES)
    batches = [_batch("TP-B04", "L2-4-1", [("K022", "K021", "prerequisite")])]
    skeleton_before = repr(skeleton)
    batches_before = repr(batches)

    diagnose_cross_batch_relation_cycles(
        skeleton=skeleton, batches=batches, sections=_SECTIONS,
    )

    assert repr(skeleton) == skeleton_before, "检测不得改动骨架"
    assert repr(batches) == batches_before, "检测不得改动批次"


def test_acyclic_course_reports_nothing():
    """无环课程不得产生噪音。"""
    skeleton = _skeleton(_REAL_ENTRIES)
    # 方向正确的批次边：早 -> 晚
    batches = [_batch("TP-B04", "L2-4-1", [("K018", "K022", "prerequisite")])]

    assert diagnose_cross_batch_relation_cycles(
        skeleton=skeleton, batches=batches, sections=_SECTIONS,
    ) == []


def test_only_prerequisite_edges_form_the_graph():
    """其它关系类型（applies_to 等）不参与前置成环判断。"""
    skeleton = _skeleton(_REAL_ENTRIES)
    batches = [_batch("TP-B04", "L2-4-1", [("K022", "K021", "applies_to")])]

    assert diagnose_cross_batch_relation_cycles(
        skeleton=skeleton, batches=batches, sections=_SECTIONS,
    ) == []


def test_cycle_with_all_edges_plausible_is_flagged_for_human_judgement():
    """两条边方向都合理的环 —— 机器判不了，必须标成待人工判断。

    这类环不能靠"哪条边方向不对"来自动定位，断哪条会改变知识结构。
    """
    entries = [
        ("K001", "概念甲", "L2-1-1", []),
        ("K002", "概念乙", "L2-1-2", ["K001"]),
    ]
    sections = [{"node_id": "L2-1-1"}, {"node_id": "L2-1-2"}]
    # 同节内自环式互指：两条边都不违反"早->晚"（同节 order 相同）
    batches = [_batch("TP-B01", "L2-1-2", [("K002", "K001", "prerequisite")])]
    skeleton = _skeleton(entries)
    for item in skeleton["knowledge_registry"]:
        if item["knowledge_key"] == "K001":
            item["owner_node_id"] = "L2-1-2"
    skeleton["sections"] = [
        {"node_id": "L2-1-2", "owned_knowledge_keys": ["K001", "K002"],
         "reused_knowledge_keys": []},
    ]

    reports = diagnose_cross_batch_relation_cycles(
        skeleton=skeleton, batches=batches, sections=sections,
    )

    assert len(reports) == 1
    assert reports[0]["verdict"] == "all_edges_plausible"
    assert reports[0]["order_contradicting_edge_count"] == 0


def test_multiple_distinct_cycles_are_each_reported_once():
    """真机上有两个环，都要报出来，且不重复。"""
    entries = [
        ("K018", "导数的定义", "L2-3-1", []),
        ("K020", "拉格朗日中值定理", "L2-3-2", ["K018"]),
        ("K021", "泰勒近似", "L2-3-3", ["K018", "K020"]),
        ("K022", "不定积分", "L2-4-1", ["K021"]),
    ]
    batches = [
        _batch("TP-B03", "L2-3-3", [("K021", "K020", "prerequisite")]),
        _batch("TP-B04", "L2-4-1", [("K022", "K021", "prerequisite")]),
    ]

    reports = diagnose_cross_batch_relation_cycles(
        skeleton=_skeleton(entries), batches=batches, sections=_SECTIONS,
    )

    assert len(reports) == 2
    signatures = {frozenset(r["cycle_keys"]) for r in reports}
    assert signatures == {frozenset({"K020", "K021"}), frozenset({"K021", "K022"})}
    assert all(r["verdict"] == "order_contradiction" for r in reports)


# --- 接线：诊断必须真的落进 stage artifact ---------------------------------


def test_diagnosis_is_recorded_on_the_stage_without_blocking():
    """检测是非阻断的：只挂诊断，不改状态、不抛异常。

    知识库编译层已经会因成环判失败，这里再加一道硬门没有增量保护；
    缺的是**诊断**——到编译层时批次早已冻结，追不回是谁声明的。
    """
    stage: dict = {"status": "in_progress"}
    reports = _record_relation_cycle_diagnosis(
        stage,
        skeleton=_skeleton(_REAL_ENTRIES),
        batches=[_batch("TP-B04", "L2-4-1", [("K022", "K021", "prerequisite")])],
        sections=_SECTIONS,
    )

    assert len(reports) == 1
    assert stage["relation_cycle_diagnosis"][0]["verdict"] == "order_contradiction"
    # 非阻断：状态不因为发现环而改变。
    assert stage["status"] == "in_progress"


def test_stale_diagnosis_is_cleared_when_the_cycle_is_gone():
    """上一轮的环诊断不得留在 stage 上误导后续判断。"""
    stage: dict = {"relation_cycle_diagnosis": [{"stale": True}]}
    _record_relation_cycle_diagnosis(
        stage,
        skeleton=_skeleton(_REAL_ENTRIES),
        batches=[_batch("TP-B04", "L2-4-1", [("K018", "K022", "prerequisite")])],
        sections=_SECTIONS,
    )

    assert "relation_cycle_diagnosis" not in stage


def test_diagnosis_failure_never_breaks_generation():
    """诊断本身出错不得连累生成主链路。"""
    stage: dict = {}
    # 畸形输入：batches 不是 list of dict
    reports = _record_relation_cycle_diagnosis(
        stage, skeleton=_skeleton(_REAL_ENTRIES),
        batches=["不是字典"], sections=_SECTIONS,
    )

    assert reports == []
