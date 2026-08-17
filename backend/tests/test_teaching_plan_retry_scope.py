"""教案阶段的重算范围：重试与目录改动都不得放大成整轮重跑。

本文件锁两条独立的失效范围，判据都是"哪些东西被重算"，不是肉眼看日志。

## 一、语义门重试（E-1b）

A-2 的调用账单实测到「55 次调用只有 20 个不同 prompt，67% 输入 token 浪费在
逐字节完全相同的 prompt 重发上」。机制：

1. 某个骨架分片本地兜底 → `fallback_units` 里留下 `skeleton_chunk_*`；
2. 语义门发现批次仍有非 AI 单元 → 递归重试；
3. 重试轮读到**上一轮**遗留的 `skeleton_chunk_*`，把 `skeleton_is_current`
   判为假 → **整份骨架重生成**；
4. 本地兜底每节只铸 1 个知识键，AI 骨架每节铸多个
   （`course_generation_adaptive.py`），所以重生成必然重铸键；
5. 键一换，已存批次在复用门上失配，全部回到 `pending_specs` 被重打。

A-2 把失效点归给 `candidate_report.get("passed")`——说 `normalize` 往返有损。
**这一条我实测不成立**：对内容完备的批次，normalize 往返是逐字节幂等的
（见 `test_normalize_roundtrip_is_idempotent`）。真正的触发条件是骨架重生成
导致的知识键重铸。

> 后续复核（lz-lesson-plan）：账单里那四轮重复其实是语义门真实失败率高导致的
> 正常重试，不是复用门失效。上面第 3-5 步的机制本身仍然成立且已修，
> 但它不是账单里 67% 浪费的主因。

## 二、目录局部改动（lz-lesson-plan 报的跨运行复用失效）

scope revision 是**全课**哈希：教师改一个小节标题它就会变，而此前
`teaching_stage.clear()` 会连带丢掉所有存量批次，于是整门课重来。改目录是
教师的常规操作，所以这条在真实使用中很容易触发。

这里锁的是"能不能局部化"这个判断本身的边界。不能局部化时必须诚实地整体重建——
不能为了省调用留下一份与新目录不符的骨架（尤其是知识点仍按旧标题命名）。
"""

from __future__ import annotations

from copy import deepcopy

from course_generation_adaptive import compile_fallback_teaching_skeleton
from course_generation_workflow import build_course_knowledge_scope_contract
from course_service import _changed_scope_section_ids
from course_teaching_plan_v3 import (
    normalize_teaching_plan_batch_v3,
    validate_teaching_plan_batch_v3,
)


def _full_detail(key: str) -> dict:
    """A knowledge detail complete enough to pass the strict semantic gate."""
    return {
        "knowledge_key": key,
        "concept_group": "核心机制",
        "group_description": "定义、条件与边界",
        "knowledge_type": "procedure",
        "conditions": ["维度匹配"],
        "boundaries": ["不含分块矩阵"],
        "counterexamples": ["逐元素相乘"],
        "capability_points": [{"observable_behavior": "能按定义计算两个矩阵的乘积"}],
        "mastery_criteria": [{
            "observable_performance": "能独立算对三阶矩阵乘法",
            "verification_method": "课堂小测三题",
        }],
        "misconceptions": [{
            "observable_error_pattern": "把矩阵乘法当成逐元素相乘",
            "discrimination": "检查是否逐位相乘",
            "repair_strategy": "回到定义按行列点积重算",
        }],
        "aliases": [],
    }


def _skeleton(keys: list[str], *, revision: str) -> dict:
    return {
        "schema_version": "course_teaching_plan_skeleton_v3",
        "knowledge_registry": [
            {
                "knowledge_key": key,
                "name": f"知识{key}",
                "statement": "陈述",
                "owner_node_id": "L2-1-1",
                "reused_in_node_ids": [],
                "prerequisite_keys": [],
                "module_ids": [],
            }
            for key in keys
        ],
        "sections": [{
            "node_id": "L2-1-1",
            "owned_knowledge_keys": list(keys),
            "reused_knowledge_keys": [],
        }],
        "revision_id": revision,
    }


_SPEC = {"batch_id": "TP-B01", "section_ids": ["L2-1-1"]}
_SECTIONS = [{"node_id": "L2-1-1", "node_name": "矩阵乘法", "title": "矩阵乘法"}]


def _roundtrip(payload: dict, skeleton: dict):
    """Do exactly what the reuse gate does: normalize the stored payload again."""
    first = normalize_teaching_plan_batch_v3(
        deepcopy(payload),
        batch_id="TP-B01",
        skeleton_revision_id=skeleton["revision_id"],
    )
    first_report = validate_teaching_plan_batch_v3(
        first, batch_spec=_SPEC, skeleton=skeleton, sections=_SECTIONS,
    )
    second = normalize_teaching_plan_batch_v3(
        deepcopy(first),
        batch_id="TP-B01",
        skeleton_revision_id=skeleton["revision_id"],
    )
    second_report = validate_teaching_plan_batch_v3(
        second, batch_spec=_SPEC, skeleton=skeleton, sections=_SECTIONS,
    )
    return first, first_report, second, second_report


def test_normalize_roundtrip_is_idempotent():
    """驳 A-2 的归因：内容完备的批次，normalize 往返不丢字段、仍然过门。

    A-2 认为复用失效是因为 `normalize_teaching_plan_batch_v3` 有损，
    重新校验时过不了。这条要是成立，任何一次重试都会重打所有批次——
    但实测往返是幂等的，所以真正的触发条件在别处（见下一个测试）。
    """
    skeleton = _skeleton(["K001"], revision="skeleton_stable")
    payload = {
        "sections": [{
            "node_id": "L2-1-1",
            "knowledge_details": [_full_detail("K001")],
            "knowledge_relations": [],
        }],
    }

    first, first_report, second, second_report = _roundtrip(payload, skeleton)

    assert first_report["passed"] is True
    assert second_report["passed"] is True, (
        "normalize 往返把一个已经过门的批次弄成不过门了"
    )
    assert first == second, "normalize 不是幂等的：往返后 payload 变了"
    assert first["revision_id"] == second["revision_id"]


def test_regenerated_skeleton_remints_keys_and_invalidates_stored_batches():
    """真正的触发条件：骨架重生成 → 知识键重铸 → 已完成批次复用失败。

    本地兜底每节只铸 1 个键，AI 骨架每节铸多个，所以"重生成骨架"必然改变
    知识注册表。批次里存的是旧键，对新骨架校验必然 key mismatch。
    """
    ai_skeleton = _skeleton(["K001", "K002"], revision="skeleton_round_1")
    stored_payload = {
        "sections": [{
            "node_id": "L2-1-1",
            "knowledge_details": [
                _full_detail("K001"),
                _full_detail("K002"),
            ],
            "knowledge_relations": [],
        }],
    }

    # 第一轮：批次针对当轮骨架是有效的。
    _first, first_report, _second, _r2 = _roundtrip(stored_payload, ai_skeleton)
    assert first_report["passed"] is True

    # 重试轮：整份骨架重生成，键被重铸（本地兜底只留一个键）。
    local_chunk = compile_fallback_teaching_skeleton(
        [{
            "node_id": "L2-1-1",
            "title": "矩阵乘法",
            "learning_objective": "能计算矩阵乘积",
            "module_plan": [{"module_id": "core_explanation"}],
        }],
        outline_revision_id="outline_1",
    )
    reminted_keys = [
        str(item.get("knowledge_key") or "")
        for item in local_chunk.get("knowledge_registry") or []
    ]
    assert reminted_keys, "本地兜底必须至少铸一个键"
    assert reminted_keys != ["K001", "K002"], (
        "本地兜底与 AI 骨架铸键数量本就不同，这正是重铸的来源"
    )

    # 同一份已完成批次，对重生成后的骨架不再有效 —— 于是被重打。
    _f, report_after, _s, _r = _roundtrip(stored_payload, local_chunk)
    codes = {issue.get("code") for issue in report_after.get("issues") or []}
    assert report_after["passed"] is False
    assert "teaching_batch:knowledge_key_mismatch" in codes, (
        f"预期知识键不匹配，实际 issue：{codes}"
    )


# --- 目录局部改动的失效范围（lz-lesson-plan 报的跨运行复用失效） -----------
#
# scope revision 是**全课**哈希：教师改一个小节标题，它就会变。此前
# `teaching_stage.clear()` 会连带丢掉所有存量批次，于是整门课重来。
# 这里锁住"能不能局部化"这个判断本身的边界——不能局部化时必须诚实地整体重建，
# 不能为了省调用留下一份与新目录不符的骨架。

def _contract(titles, *, positioning="系统学习", course_title="微积分"):
    return build_course_knowledge_scope_contract({
        "course_title": course_title,
        "positioning": positioning,
        "learning_objectives": ["能计算导数与积分"],
        "prerequisites": [],
        "chapters": [{
            "chapter_number": 1,
            "title": "第一章",
            "sections": [
                {
                    "node_id": f"L2-1-{index}",
                    "section_number": f"1.{index}",
                    "title": title,
                    "learning_objective": f"掌握{title}",
                    "scope_boundary": f"只覆盖{title}",
                    "prerequisite_node_ids": (
                        [f"L2-1-{index - 1}"] if index > 1 else []
                    ),
                }
                for index, title in enumerate(titles, start=1)
            ],
        }],
    })


_TITLES = ["函数与极限", "导数定义", "求导法则", "定积分", "积分应用", "微分方程"]


def test_one_title_edit_localizes_to_that_section_only():
    """改一个标题只影响那一节——邻居字段的移动不算受影响。

    `next_reserved_section` 会让前一节的记录也变，但那一节自身的教学责任没变。
    把邻居变化算进受影响范围，等于又把一处改动摊到全课。
    """
    edited = list(_TITLES)
    edited[2] = "求导法则（含链式法则）"

    changed = _changed_scope_section_ids(_contract(_TITLES), _contract(edited))

    assert changed == {"L2-1-3"}


def test_untouched_outline_reports_no_changed_sections():
    changed = _changed_scope_section_ids(_contract(_TITLES), _contract(_TITLES))

    assert changed == set()


def test_added_section_cannot_be_localized():
    """新增小节改变知识归属图，必须返回 None（整体重建）。"""
    changed = _changed_scope_section_ids(
        _contract(_TITLES), _contract(_TITLES + ["无穷级数"])
    )

    assert changed is None


def test_removed_section_cannot_be_localized():
    changed = _changed_scope_section_ids(
        _contract(_TITLES), _contract(_TITLES[:-1])
    )

    assert changed is None


def test_swapped_section_titles_localize_to_the_two_swapped_slots():
    """互换两节标题：节点 id 与顺序都没变，只有这两个位置的内容变了。

    这不是"重排小节"（那会改 node_id 顺序，走 None 分支），而是同一批 id 上
    换了内容。逐节比较应当诚实地只报这两个位置，不多不少。
    """
    swapped = list(_TITLES)
    swapped[1], swapped[3] = swapped[3], swapped[1]

    changed = _changed_scope_section_ids(
        _contract(_TITLES), _contract(swapped)
    )

    assert changed == {"L2-1-2", "L2-1-4"}


def test_course_level_change_cannot_be_localized():
    """课程定位/标题这类全课改动会重新框定每一节。"""
    assert _changed_scope_section_ids(
        _contract(_TITLES),
        _contract(_TITLES, positioning="换成另一种定位"),
    ) is None
    assert _changed_scope_section_ids(
        _contract(_TITLES),
        _contract(_TITLES, course_title="高等数学"),
    ) is None


def test_missing_previous_contract_cannot_be_localized():
    """没有上一份合同（老课程首次进入）时不得假设可以复用。"""
    assert _changed_scope_section_ids({}, _contract(_TITLES)) is None
    assert _changed_scope_section_ids(_contract(_TITLES), {}) is None


def test_schema_change_cannot_be_localized():
    previous = _contract(_TITLES)
    previous["schema_version"] = "course_knowledge_scope_v1"

    assert _changed_scope_section_ids(previous, _contract(_TITLES)) is None
