"""E-1b：语义门重试的重算范围不得放大到整轮。

A-2 的调用账单实测到「55 次调用只有 20 个不同 prompt，67% 输入 token 浪费在
逐字节完全相同的 prompt 重发上」，且重复位置分散在四个互相远离的区段——那是
整轮重跑的指纹，不是局部重试。

机制（我复核 A-2 的结论后修正了它指出的失效点）：

1. 某个骨架分片本地兜底 → `fallback_units` 里留下 `skeleton_chunk_*`
   （`course_service.py`，`compile_fallback_teaching_skeleton` 的调用处）；
2. 语义门发现批次仍有非 AI 单元 → 递归重试（`course_service.py:2806`）；
3. 重试轮读到**上一轮**遗留的 `skeleton_chunk_*`，把 `skeleton_is_current`
   判为假（`course_service.py:2053-2062`）→ **整份骨架重生成**；
4. 本地兜底每节只铸 1 个知识键，AI 骨架每节铸多个
   （`course_generation_adaptive.py:375-377`），所以重生成必然重铸键；
5. 键一换，已存批次在复用门第三、四个条件上失败
   （`course_service.py:2251-2258`），全部回到 `pending_specs` 被重打。

A-2 把失效点归给 `candidate_report.get("passed")`——说 `normalize` 往返有损。
**这一条我实测不成立**：对内容完备的批次，normalize 往返是逐字节幂等的
（见 `test_normalize_roundtrip_is_idempotent`）。真正的触发条件是骨架被重生成
导致的知识键重铸，也就是复用门更前面的 `skeleton_revision_id` 一致性判断。
"""

from __future__ import annotations

from copy import deepcopy

from course_generation_adaptive import compile_fallback_teaching_skeleton
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
