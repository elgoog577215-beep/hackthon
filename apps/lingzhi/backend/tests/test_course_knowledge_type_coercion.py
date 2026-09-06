"""词表外的 `knowledge_type` 必须留痕，不能静默改写（Gap：静默数据损坏）。

`course_knowledge_base.py` 在编译知识点时，把不在 `KNOWLEDGE_TYPES` 里的
`knowledge_type` **无条件改写成 `definition`**，不报错、不留痕。

这不是"生成质量差一点"，是**静默数据损坏**：真机实测千问三次生成里，模型
先后自造了 `relationship` 与 `concept`（都不在词表内），系统把它们统统改成
`definition`。结果是模型填错、系统改错、没有任何人知道——一个本该是
`procedure` 的知识点，最终以 `definition` 的身份进入知识库、进入题目生成、
进入教师看到的界面。

判据因此不是"改写后的值对不对"，而是**改写这件事本身能不能被审计到**：
原始取值是什么、被改成了什么、发生在哪个知识点上。
"""

from __future__ import annotations

from copy import deepcopy

from content_blocks import set_node_content_blocks
from course_knowledge_base import KNOWLEDGE_TYPES, compile_course_knowledge_base

# 与 backend/tests 内其他用例一致：夹具自带，不跨模块引用兄弟测试
# （仓库根目录也有一个 `tests` 包且在 sys.path 里排在前面）。
_ILLEGAL_TYPE = "relationship"   # 千问真机实测自造过的取值
_ILLEGAL_TYPE_2 = "concept"      # 补了取值表之后仍然出现过的另一个


def _course(*knowledge_types: str) -> dict:
    """一门最小课程，知识点的 knowledge_type 由参数给定。"""
    points = []
    for index, ktype in enumerate(knowledge_types):
        point = {
            "name": f"知识点{index + 1}",
            "statement": f"这是第 {index + 1} 个知识点的独立命题陈述。",
            "capability_points": [{
                "name": f"能力{index + 1}",
                "observable_behavior": f"能独立完成与知识点{index + 1}相关的任务并说明依据",
            }],
            "mastery_criteria": [{
                "name": f"标准{index + 1}",
                "observable_performance": "在三个新情境中正确应用并说明依据",
                "verification_method": "现场完成三个案例并核对结果",
            }],
        }
        if ktype is not None:
            point["knowledge_type"] = ktype
        points.append(point)

    course = {
        "course_id": "course-ktype",
        "course_name": "词表外类型测试课",
        "nodes": [{
            "node_id": "L2-1-1",
            "node_level": 2,
            "node_name": "测试小节",
            "learning_objective": "验证 knowledge_type 改写留痕",
            "knowledge_structure": [{
                "concept_group": "测试概念组",
                "description": "用于验证类型改写留痕",
                "knowledge_points": points,
            }],
            "key_points": [p["name"] for p in points],
            "node_content": "## 测试\n\n正文内容。",
            "generation_status": "completed",
        }],
    }
    set_node_content_blocks(course["nodes"][0], course["nodes"][0]["node_content"])
    return course


def _audit(course: dict) -> list[dict]:
    base = compile_course_knowledge_base(course)
    return (base.get("generation_audit") or {}).get("coerced_knowledge_types") or []


def test_illegal_type_is_recorded_not_silently_rewritten() -> None:
    """核心判据：改写必须留痕，能审计到原始取值。"""
    trace = _audit(_course(_ILLEGAL_TYPE))

    assert len(trace) == 1, "词表外取值必须留下恰好一条记录"
    entry = trace[0]
    assert entry["original"] == _ILLEGAL_TYPE
    assert entry["coerced_to"] == "definition"


def test_trace_identifies_which_knowledge_point() -> None:
    """光知道"有过改写"不够——必须能定位到是哪个知识点，否则无法修。"""
    trace = _audit(_course("definition", _ILLEGAL_TYPE_2))

    assert len(trace) == 1
    entry = trace[0]
    assert entry["knowledge_name"] == "知识点2"
    assert entry["section_ref"] == "L2-1-1"
    assert entry["knowledge_id"], "要能按稳定 ID 定位"


def test_multiple_illegal_types_each_get_a_record() -> None:
    """两个知识点各填错一次，就该有两条记录，不能合并成一条。"""
    trace = _audit(_course(_ILLEGAL_TYPE, _ILLEGAL_TYPE_2))

    assert [item["original"] for item in trace] == [_ILLEGAL_TYPE, _ILLEGAL_TYPE_2]


def test_legal_types_leave_no_trace() -> None:
    """合法取值不得产生噪声——否则这个审计字段会被无关记录淹没。"""
    assert _audit(_course(*sorted(KNOWLEDGE_TYPES))) == []


def test_missing_type_is_not_treated_as_corruption() -> None:
    """完全没填 `knowledge_type` 与"填了个错的"性质不同。

    没填是缺省，走默认值是合理行为；填了词表外的值才是模型误解了契约。
    把两者混为一谈会让审计记录失去信噪比。
    """
    assert _audit(_course(None)) == []


def test_coerced_value_still_lands_in_the_knowledge_point() -> None:
    """留痕不改变兜底行为：知识点本身仍然拿到合法的 `definition`。

    这条锁的是"加了审计不等于放行脏数据"——下游读到的仍是词表内取值。
    """
    base = compile_course_knowledge_base(_course(_ILLEGAL_TYPE))
    point = base["knowledge_points"][0]

    assert point["knowledge_type"] == "definition"
    assert point["knowledge_type"] in KNOWLEDGE_TYPES


def test_validator_surfaces_the_coercion_as_an_issue() -> None:
    """审计字段本身教师不会去翻，必须浮到校验结果里才算"可见"。"""
    from course_knowledge_base import validate_course_knowledge_base

    base = compile_course_knowledge_base(_course(_ILLEGAL_TYPE))
    report = validate_course_knowledge_base(base)

    codes = {item["code"] for item in report["issues"]}
    assert "coerced_knowledge_type" in codes


def test_coercion_does_not_block_publication() -> None:
    """判失败还是只留痕是产品判断；本轮的决定是**只留痕不阻断**。

    理由写在 NOTES：改写后的 `definition` 是合法值，下游不会崩；真正的损失是
    语义精度，属质量问题而非结构错误。而且真机实测模型自造率不低，直接判失败
    会让大量课程卡在生成阶段——先让它可见、可统计，再决定要不要升级。
    """
    from course_knowledge_base import validate_course_knowledge_base

    base = compile_course_knowledge_base(_course(_ILLEGAL_TYPE))
    report = validate_course_knowledge_base(base)

    coerced = next(
        item for item in report["issues"] if item["code"] == "coerced_knowledge_type"
    )
    assert coerced["severity"] != "critical"
    assert report["passed"] is True
