"""跨批次关系环：检测并如实上报，绝不自动断边。

环由两条边"拼"出来，任何单层校验都看不见（真机实测，课程 6fac40e7）：

- 骨架 `prerequisite_keys`：K021(L2-3-3) -> K022(L2-4-1)，方向与小节顺序一致；
- 批次 TP-B04 的 `knowledge_relations`：K022 -> K021，方向相反。

骨架自身无环、批次关系自身也无环，**只有合并才成环**。所以检测点必须放在
汇编之后（唯一能看到完整图的位置），而不是批次校验里。

`course_teaching_plan_v3.py:505-510` 只限制关系"能不能引用"某个键（K021 属更早
小节，引用合法），**不检查 prerequisite 的方向**；而骨架侧 `:354-373` 的
`future_prerequisite` 是管方向的。两边规则不对称，缝就在这里。

**本模块只诊断，不修复。** 断哪条边会改变课程的知识结构，属于产品判断。
"""

from __future__ import annotations

from course_generation.service import (
    _record_relation_cycle_diagnosis,
    diagnose_cross_batch_relation_cycles,
    enforce_batch_prerequisite_direction,
)


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


# --- 对称化：批次侧也检查 prerequisite 方向（源头拦截） ---------------------
#
# 骨架侧 `teaching_skeleton:future_prerequisite` 一直在管方向，批次侧不管——
# 环就是从这条缝里长出来的。堵在源头比汇编后断边好：断边必然有损。


def test_reversed_prerequisite_across_sections_is_blocked():
    """批次不得声明「更晚小节的知识是更早知识的前置」。"""
    report = enforce_batch_prerequisite_direction(
        {"passed": True, "blocking_issues": [], "issues": []},
        batch=_batch("TP-B04", "L2-4-1", [("K022", "K021", "prerequisite")]),
        skeleton=_skeleton(_REAL_ENTRIES),
        sections=_SECTIONS,
    )

    assert report["passed"] is False
    codes = {i["code"] for i in report["blocking_issues"]}
    assert "teaching_batch:reversed_prerequisite" in codes


def test_message_names_the_later_key_as_the_offender():
    """报错文案必须说对是谁太晚——写反了会把模型引向错误的修法。

    我第一版把 source/target 写反了，文案说「L2-3-2 属于更晚的」，
    而真相是 source(L2-3-3) 才是更晚的那个。真机数据把它逼了出来。
    """
    report = enforce_batch_prerequisite_direction(
        {"passed": True, "blocking_issues": [], "issues": []},
        batch=_batch("TP-B04", "L2-4-1", [("K022", "K021", "prerequisite")]),
        skeleton=_skeleton(_REAL_ENTRIES),
        sections=_SECTIONS,
    )
    message = report["blocking_issues"][0]["message"]

    # K022 属 L2-4-1（更晚），它才是不该当前置的那个。
    assert "「原函数与不定积分的概念定义」属于更晚的 L2-4-1" in message
    # 依赖方是 L2-4-1 之前的 K021。
    assert "L2-3-3" in message


def test_forward_prerequisite_passes():
    """方向正确的前置不得被误伤。"""
    report = enforce_batch_prerequisite_direction(
        {"passed": True, "blocking_issues": [], "issues": []},
        batch=_batch("TP-B04", "L2-4-1", [("K021", "K022", "prerequisite")]),
        skeleton=_skeleton(_REAL_ENTRIES),
        sections=_SECTIONS,
    )

    assert report["passed"] is True
    assert report["blocking_issues"] == []


def test_same_section_ordering_follows_registry_order():
    """同一小节内按注册表顺序判定，与骨架侧规则一致。"""
    entries = [
        ("K001", "先讲的知识", "L2-1-1", []),
        ("K002", "后讲的知识", "L2-1-1", ["K001"]),
    ]
    sections = [{"node_id": "L2-1-1"}]
    skeleton = _skeleton(entries)
    skeleton["sections"] = [{
        "node_id": "L2-1-1",
        "owned_knowledge_keys": ["K001", "K002"],
        "reused_knowledge_keys": [],
    }]

    # K002 在注册表里更靠后，不能作为 K001 的前置。
    bad = enforce_batch_prerequisite_direction(
        {"passed": True, "blocking_issues": [], "issues": []},
        batch=_batch("TP-B01", "L2-1-1", [("K002", "K001", "prerequisite")]),
        skeleton=skeleton, sections=sections,
    )
    assert bad["passed"] is False
    assert "本节的知识顺序" in bad["blocking_issues"][0]["message"]

    # 反过来是合法的。
    good = enforce_batch_prerequisite_direction(
        {"passed": True, "blocking_issues": [], "issues": []},
        batch=_batch("TP-B01", "L2-1-1", [("K001", "K002", "prerequisite")]),
        skeleton=skeleton, sections=sections,
    )
    assert good["passed"] is True


def test_only_prerequisite_direction_is_enforced():
    """其它关系类型没有方向约束，不得被这条规则波及。"""
    report = enforce_batch_prerequisite_direction(
        {"passed": True, "blocking_issues": [], "issues": []},
        batch=_batch("TP-B04", "L2-4-1", [("K022", "K021", "applies_to")]),
        skeleton=_skeleton(_REAL_ENTRIES),
        sections=_SECTIONS,
    )

    assert report["passed"] is True


def test_existing_issues_are_preserved_and_input_not_mutated():
    """增补不得覆盖既有 issue，也不得就地改调用方的报告。"""
    original = {
        "passed": False,
        "blocking_issues": [{"code": "teaching_batch:section_mismatch"}],
        "issues": [{"code": "teaching_batch:section_mismatch"}],
    }
    snapshot = repr(original)

    report = enforce_batch_prerequisite_direction(
        original,
        batch=_batch("TP-B04", "L2-4-1", [("K022", "K021", "prerequisite")]),
        skeleton=_skeleton(_REAL_ENTRIES),
        sections=_SECTIONS,
    )

    codes = {i["code"] for i in report["blocking_issues"]}
    assert codes == {
        "teaching_batch:section_mismatch",
        "teaching_batch:reversed_prerequisite",
    }
    assert repr(original) == snapshot, "不得就地修改入参报告"


def test_unknown_endpoints_are_left_to_the_batch_validator():
    """未知知识键已有专门的 issue，这里不重复报。"""
    report = enforce_batch_prerequisite_direction(
        {"passed": True, "blocking_issues": [], "issues": []},
        batch=_batch("TP-B04", "L2-4-1", [("K999", "K021", "prerequisite")]),
        skeleton=_skeleton(_REAL_ENTRIES),
        sections=_SECTIONS,
    )

    assert report["passed"] is True


# --- 与 lz-lesson-plan 的软门槛共存（集成冲突点，course_service.py:3478）------
#
# 两件事本来就该并存，不是二选一：
#   * 我的方向检查 = **源头拦截**，写 blocking_issues，让批次重做；
#   * 它的越界软门槛 = **兜底丢弃**，写 review_issues，不阻断发布。
# 合并后的 batch_report 必须同时表达两者，任何一方都不得覆盖另一方的字段。


def test_direction_check_preserves_soft_gate_review_issues():
    """方向检查增补 blocking_issues 时，不得丢掉软门槛写的 review_issues。"""
    report = {
        "passed": True,
        "blocking_issues": [],
        "issues": [{"code": "teaching_batch:future_relation_endpoint"}],
        "review_issues": [
            {"code": "teaching_batch:future_relation_endpoint",
             "severity": "review", "message": "该关系已丢弃"},
            {"code": "teaching_batch:relation_diversity_low",
             "severity": "review", "message": "知识网退化"},
        ],
    }

    out = enforce_batch_prerequisite_direction(
        report,
        batch=_batch("TP-B04", "L2-4-1", [("K022", "K021", "prerequisite")]),
        skeleton=_skeleton(_REAL_ENTRIES),
        sections=_SECTIONS,
    )

    # 软门槛的 review_issues 原样保留。
    assert len(out["review_issues"]) == 2
    assert {i["code"] for i in out["review_issues"]} == {
        "teaching_batch:future_relation_endpoint",
        "teaching_batch:relation_diversity_low",
    }
    # 我的方向错误进 blocking，并把 passed 置否。
    assert out["passed"] is False
    assert {i["code"] for i in out["blocking_issues"]} == {
        "teaching_batch:reversed_prerequisite",
    }


def test_soft_gated_batch_without_direction_error_stays_passing():
    """只有越界（软门槛）而没有方向错误时，不得被我的检查打成失败。

    这是两者语义的分界：越界关系会被汇编层丢弃、不阻断发布；
    方向错误则必须重做。混淆会让本可发布的课程卡住。
    """
    report = {
        "passed": True,
        "blocking_issues": [],
        "issues": [],
        "review_issues": [
            {"code": "teaching_batch:future_relation_endpoint",
             "severity": "review"},
        ],
    }

    out = enforce_batch_prerequisite_direction(
        report,
        # 方向正确的边：早 -> 晚
        batch=_batch("TP-B04", "L2-4-1", [("K021", "K022", "prerequisite")]),
        skeleton=_skeleton(_REAL_ENTRIES),
        sections=_SECTIONS,
    )

    assert out["passed"] is True
    assert out["blocking_issues"] == []
    assert len(out["review_issues"]) == 1


def test_detail_repair_cannot_launder_a_reversed_prerequisite():
    """补写重新校验后必须再挡一次方向——否则方向错误会被"洗白"。

    合并 lz-lesson-plan 的知识点补写后，流程是：
      校验失败 -> 逐知识点补写 -> **重新校验** -> passed 可能变真。
    补写只填 capability_points / mastery_criteria / misconceptions 等内容字段，
    结构上改不了关系端点（它们自己的 NOTES 17.8 也钉住了这点），所以一条方向
    错误的前置边补写完照样错。若重新校验后不再挡一次，这批就会带着反向边通过。
    """
    batch = _batch("TP-B04", "L2-4-1", [("K022", "K021", "prerequisite")])
    skeleton = _skeleton(_REAL_ENTRIES)

    # 模拟补写后的"干净"报告：内容字段都补齐了，校验器认为通过。
    after_repair = {
        "passed": True,
        "blocking_issues": [],
        "issues": [],
        "review_issues": [],
    }

    out = enforce_batch_prerequisite_direction(
        after_repair, batch=batch, skeleton=skeleton, sections=_SECTIONS,
    )

    assert out["passed"] is False, "补写不得让方向错误的批次通过"
    assert {i["code"] for i in out["blocking_issues"]} == {
        "teaching_batch:reversed_prerequisite",
    }
