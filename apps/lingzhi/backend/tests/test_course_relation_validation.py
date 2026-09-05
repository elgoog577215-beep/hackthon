"""批次校验必须管住关系类型与多样性（需求 A2）。

原校验只检查关系端点是否合法（`course_teaching_plan_v3.py:520-529`），于是有两类
问题一路穿到编译层：

1. **非法类型**：`relation_type` 写成 `related` 之类不存在的值，校验放过，
   `_compile_relations` 再整条丢弃。
2. **缺必填字段**：`derives` 少 `derivation_steps`、`contrasts_with` 少
   `distinction`，同样是编译期整条丢弃。

两种情况都发生在校验通过之后，所以修正轮永远看不到它们 —— 模型没有机会改，
教师也不知道少了什么。判据因此不是"报了个错"，而是"编译层会丢弃的候选，在
校验层就变成可回灌修正轮的 blocking issue"。

多样性是另一回事：一节里全是 prerequisite 属于质量问题而非结构错误，不能阻断
发布，只能进复核。所以它必须出现在 review_issues 且不影响 passed。
"""

from __future__ import annotations

from copy import deepcopy

from course_knowledge_base import RELATION_TYPES
from course_teaching_plan_v3 import validate_teaching_plan_batch_v3

_KEYS = ["K001", "K002"]


def _detail(key: str) -> dict:
    return {
        "knowledge_key": key,
        "capability_points": [{
            "name": f"能力{key}",
            "observable_behavior": f"能独立完成{key}相关任务并说明依据",
        }],
        "mastery_criteria": [{
            "name": f"标准{key}",
            "observable_performance": f"在三个新情境中正确应用{key}",
            "verification_method": "现场完成三个案例并核对结果",
        }],
        "misconceptions": [{
            "name": f"易错{key}",
            "observable_error_pattern": f"把{key}的适用条件当作结论",
            "discrimination": "先检查条件是否成立",
            "repair_strategy": "逐条对照条件后重做",
        }],
    }


def _skeleton() -> dict:
    return {
        "revision_id": "skeleton-1",
        "sections": [{
            "node_id": "L2-1-1",
            "owned_knowledge_keys": list(_KEYS),
            "reused_knowledge_keys": [],
        }],
        "knowledge_registry": [
            {"knowledge_key": key, "name": f"知识点{key}", "owner_node_id": "L2-1-1"}
            for key in _KEYS
        ],
    }


def _sections() -> list[dict]:
    return [{
        "node_id": "L2-1-1",
        "title": "第一节",
        "module_plan": [{"module_id": "core_explanation"}],
    }]


def _batch(relations: list[dict]) -> dict:
    return {
        "batch_id": "TP-B01",
        "schema_version": "course_teaching_plan_batch_v3",
        "sections": [{
            "node_id": "L2-1-1",
            "knowledge_details": [_detail(key) for key in _KEYS],
            "knowledge_relations": deepcopy(relations),
            "teaching_modules": [{
                "module_id": "core_explanation",
                "knowledge_keys": list(_KEYS),
            }],
        }],
    }


def _report(relations: list[dict]) -> dict:
    return validate_teaching_plan_batch_v3(
        _batch(relations),
        batch_spec={"batch_id": "TP-B01", "section_ids": ["L2-1-1"]},
        skeleton=_skeleton(),
        sections=_sections(),
    )


def _codes(issues: list[dict]) -> set[str]:
    return {item["code"] for item in issues}


_PREREQUISITE = {
    "source_key": "K001",
    "target_key": "K002",
    "relation_type": "prerequisite",
    "reason": "必须先掌握 K001 才能理解 K002",
}
_DERIVES = {
    "source_key": "K001",
    "target_key": "K002",
    "relation_type": "derives",
    "reason": "K002 可由 K001 推导",
    "derivation_steps": ["代入定义", "整理得到结论"],
}
_CONTRASTS = {
    "source_key": "K002",
    "target_key": "K001",
    "relation_type": "contrasts_with",
    "reason": "两者常被混淆",
    "distinction": "看条件是否要求连续存储",
}


# --- 类型白名单 -------------------------------------------------------------


def test_unknown_relation_type_is_blocked() -> None:
    """`related` 这类不存在的类型必须在校验层被拦住。"""
    report = _report([{**_PREREQUISITE, "relation_type": "related"}])

    assert not report["passed"]
    assert "teaching_batch:unknown_relation_type" in _codes(report["blocking_issues"])


def test_empty_relation_type_is_blocked() -> None:
    """类型缺失和类型非法一样，都会让编译层丢弃整条关系。"""
    report = _report([{**_PREREQUISITE, "relation_type": ""}])

    assert not report["passed"]
    assert "teaching_batch:unknown_relation_type" in _codes(report["blocking_issues"])


def test_every_whitelisted_type_passes_the_type_gate() -> None:
    """六类合法类型都不能被类型门误伤。"""
    for name in sorted(RELATION_TYPES):
        relation = {**_PREREQUISITE, "relation_type": name}
        if name == "derives":
            relation["derivation_steps"] = ["代入定义"]
        if name == "contrasts_with":
            relation["distinction"] = "看条件是否成立"

        codes = _codes(_report([relation])["issues"])

        assert "teaching_batch:unknown_relation_type" not in codes, name


# --- 编译层会丢弃的候选必须在校验层可见 -------------------------------------


def test_derives_without_derivation_steps_is_blocked() -> None:
    """缺 derivation_steps 的 derives 会被编译层整条丢弃，必须先在校验层报出。"""
    report = _report([{k: v for k, v in _DERIVES.items() if k != "derivation_steps"}])

    assert not report["passed"]
    assert "teaching_batch:relation_missing_required_field" in _codes(
        report["blocking_issues"]
    )


def test_derives_with_empty_derivation_steps_is_blocked() -> None:
    """空数组和字段缺失等价 —— 编译层同样丢弃。"""
    report = _report([{**_DERIVES, "derivation_steps": []}])

    assert not report["passed"]
    assert "teaching_batch:relation_missing_required_field" in _codes(
        report["blocking_issues"]
    )


def test_contrasts_with_without_distinction_is_blocked() -> None:
    """缺 distinction 的易混关系无法辨析，编译层丢弃，校验层必须报出。"""
    report = _report([{k: v for k, v in _CONTRASTS.items() if k != "distinction"}])

    assert not report["passed"]
    assert "teaching_batch:relation_missing_required_field" in _codes(
        report["blocking_issues"]
    )


def test_blocked_relation_issues_name_the_missing_field() -> None:
    """回灌修正轮的前提是消息里说清缺哪个字段，否则模型改不动。"""
    report = _report([{k: v for k, v in _DERIVES.items() if k != "derivation_steps"}])

    messages = " ".join(
        item["message"] for item in report["blocking_issues"]
        if item["code"] == "teaching_batch:relation_missing_required_field"
    )

    assert "derivation_steps" in messages
    assert "derives" in messages


def test_relations_carrying_required_fields_are_accepted() -> None:
    """带齐必填字段的多类型关系必须完全通过，不能出现假警报。"""
    report = _report([_PREREQUISITE, _DERIVES, _CONTRASTS])

    assert report["passed"], report["issues"]
    assert report["review_issues"] == []


# --- 多样性软门槛：进复核，不阻断 -------------------------------------------


def test_only_prerequisite_relations_raise_a_review_issue() -> None:
    """一节里全是前置关系是质量问题：必须可见，但不能阻断发布。"""
    report = _report([_PREREQUISITE])

    assert report["passed"], report["blocking_issues"]
    assert "teaching_batch:relation_diversity_low" in _codes(report["review_issues"])


def test_missing_relations_entirely_raises_a_review_issue() -> None:
    """一条关系都没有同样进复核 —— 否则孤立知识点永远没人看见。"""
    report = _report([])

    assert report["passed"]
    assert "teaching_batch:relation_diversity_low" in _codes(report["review_issues"])


def test_one_non_prerequisite_relation_clears_the_soft_gate() -> None:
    """软门槛只要求本节至少有一条非前置关系。"""
    report = _report([_PREREQUISITE, _CONTRASTS])

    assert report["passed"]
    assert report["review_issues"] == []


def test_a_discardable_relation_does_not_satisfy_the_diversity_gate() -> None:
    """注定被编译层丢弃的关系不能充当多样性。

    否则一节里唯一的非前置关系缺了必填字段时：blocking 报出来了，但多样性门
    被这条关系骗过 —— 模型只修字段格式而不补真实关系，编译后照样是线性链。
    """
    missing_steps = {k: v for k, v in _DERIVES.items() if k != "derivation_steps"}

    report = _report([_PREREQUISITE, missing_steps])

    codes = {item["code"] for item in report["review_issues"]}
    assert "teaching_batch:relation_diversity_low" in codes


def test_issue_severity_labels_match_the_queue_they_land_in() -> None:
    """severity 字段是给下游读的：它必须与实际分流一致，不能只靠列表归属。"""
    report = _report([{**_PREREQUISITE, "relation_type": "related"}, _PREREQUISITE])

    assert {item["severity"] for item in report["blocking_issues"]} == {"blocking"}
    assert {item["severity"] for item in report["review_issues"]} == {"review"}


def test_review_issues_stay_out_of_blocking_issues() -> None:
    """软门槛绝不能混进 blocking_issues：那会把复核变成阻断。"""
    report = _report([_PREREQUISITE])

    assert report["review_issues"]
    assert report["blocking_issues"] == []
    assert _codes(report["issues"]) >= _codes(report["review_issues"])


def test_blocked_relation_reaches_the_correction_prompt() -> None:
    """回灌闭环的真正判据：被拦下的关系问题必须出现在修正 prompt 里。

    course_service 用 `blocking_issues` 构造修正轮（course_service.py:2260-2265）。
    校验层报出来但没进修正 prompt，等于没回灌。
    """
    from course_generation.prompts import CoursePromptComposer

    report = _report([{k: v for k, v in _DERIVES.items() if k != "derivation_steps"}])

    correction = CoursePromptComposer().build_teaching_plan_batch_v3_correction_prompt(
        original_prompt="原始批次 prompt",
        issues=report["blocking_issues"],
    )

    assert "derivation_steps" in correction
    assert "L2-1-1" in correction


def test_review_issues_do_not_trigger_a_correction_round() -> None:
    """软门槛不得触发修正轮：passed 为真时 course_service 不会进入纠正分支。"""
    report = _report([_PREREQUISITE])

    assert report["passed"]
    assert report["blocking_issues"] == []


def test_soft_gate_does_not_mask_a_real_structural_error() -> None:
    """软门槛与硬错误共存时，passed 必须由硬错误决定。"""
    report = _report([{**_PREREQUISITE, "relation_type": "related"}])

    assert not report["passed"]
    assert report["blocking_issues"]
