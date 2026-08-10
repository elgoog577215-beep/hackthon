"""练习题定向重建 runner。

任务书三条硬要求，每条都有正面测试：

1. **重建失败时旧的正式题目继续可读可作答**（产品级承诺）。这里不是只断言
   「返回了 failed」，而是断言失败后 `approved_formal_tasks` 仍然返回旧题、
   题库活动指针没有变、bundle 没有被写过。
2. **走既有题目质量门与修订机制，不绕过**。断言 runner 自己不出题、不写
   bundle，只登记 `scope="items"` 的作业——真正的重建与质量门在既有管线里。
3. **逐题回执可追溯**：哪道题、依据哪次知识修订、成功还是失败及原因。
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from downstream_rebuild import execute_rebuild, pipeline_for
from practice_targeted_rebuild import (
    PRACTICE_REBUILD_RECEIPT_SCHEMA,
    build_practice_rebuild_runner,
    practice_rebuild_receipts,
    resolve_question_revisions,
)
from question_bank import approved_formal_tasks
from teaching_plan_impact import build_downstream_state


def _impact(**groups) -> dict:
    report = {group: [] for group in
              ("changed", "needs_regeneration", "stale", "unchanged", "blocked")}
    report.update(groups)
    report["blocking"] = bool(report.get("blocked"))
    return report


def _downstream(**groups) -> dict:
    return build_downstream_state(_impact(**groups), plan_revision_id="tpr_1")


def _bank_item(
    *,
    item_id: str,
    revision_id: str,
    node_id: str,
    approved: bool = True,
    lifecycle_status: str | None = None,
) -> dict:
    """一道最小但结构真实的题库 item。

    字段取自 question_bank 的正式 item 形状；approved + quality passed 才会
    被 approved_formal_tasks 投影给学生。
    """
    status = lifecycle_status or ("approved" if approved else "candidate")
    return {
        "schema_version": "question_bank_item_v1",
        "item_id": item_id,
        "revision_id": revision_id,
        "node_id": node_id,
        "node_ids": [node_id],
        "prompt": f"{node_id} 的正式题目",
        "answer_spec": {"kind": "short_answer", "expected": "参考答案"},
        "explanation": "解析",
        "question_type": "short_answer",
        "assessment_role": "practice",
        "practice_level": "concept_check",
        "practice_levels": ["concept_check"],
        "lifecycle_status": status,
        "review_status": status,
        "source_type": "generated",
        "source_records": [{"source_type": "course_knowledge_base"}],
        "course_knowledge_refs": ["kp_1"],
        "quality_report": {"passed": True, "status": "passed"},
        "formal_task": {
            "revision_id": f"ft_{revision_id}",
            "task_id": item_id,
            "node_id": node_id,
            "prompt": f"{node_id} 的正式题目",
        },
        "formal_task_revision_id": f"ft_{revision_id}",
    }


def _bundle(*items: dict) -> dict:
    return {
        "schema_version": "question_bank_bundle_v1",
        "course_id": "c1",
        "bundle_revision_id": "qbb_before",
        "items": list(items),
        "solution_envelopes": {},
    }


# --- 对象 ID 对齐 -----------------------------------------------------------


def test_object_id_resolves_by_revision_id() -> None:
    bundle = _bundle(_bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1"))
    assert resolve_question_revisions(bundle, object_id="qbr_1") == ["qbr_1"]


def test_object_id_resolves_by_item_id() -> None:
    bundle = _bundle(_bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1"))
    assert resolve_question_revisions(bundle, object_id="qbi_1") == ["qbr_1"]


def test_asset_question_id_falls_back_to_section_scope() -> None:
    """影响报告用的是 learning_assets 的 q_ 前缀 ID，与题库不是一个命名空间。

    对不上时按小节取该节的题；一个小节可能有多道题（按 practice_level 分层），
    必须全部返回，漏一道就等于漏重建。
    """
    bundle = _bundle(
        _bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1"),
        _bank_item(item_id="qbi_2", revision_id="qbr_2", node_id="L2-1-1"),
        _bank_item(item_id="qbi_3", revision_id="qbr_3", node_id="L2-2-1"),
    )
    resolved = resolve_question_revisions(
        bundle, object_id="q_abc123", section_id="L2-1-1",
    )
    assert resolved == ["qbr_1", "qbr_2"]


def test_retired_questions_are_not_rebuilt() -> None:
    bundle = _bundle(
        _bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1"),
        _bank_item(
            item_id="qbi_2", revision_id="qbr_2", node_id="L2-1-1",
            lifecycle_status="retired",
        ),
    )
    resolved = resolve_question_revisions(
        bundle, object_id="q_abc", section_id="L2-1-1",
    )
    assert resolved == ["qbr_1"], "已退休的题不再是课程资产"


def test_unresolvable_object_returns_empty_rather_than_guessing() -> None:
    """宁可报解析不到，也不能随便挑一道题重建。"""
    bundle = _bundle(_bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1"))
    assert resolve_question_revisions(bundle, object_id="unknown") == []
    assert resolve_question_revisions(
        bundle, object_id="unknown", section_id="L2-9-9",
    ) == []


# --- 接入既有执行链 ---------------------------------------------------------


def test_practice_types_route_to_this_runner() -> None:
    """executor 把这三类对象路由到 runners["practice"]。"""
    for object_type in ("practice", "question", "mastery_criterion"):
        assert pipeline_for(object_type) == "practice"


def test_runner_enqueues_scoped_job_and_reports_candidate() -> None:
    """成功路径：登记 scope=items 作业，回执记候选，不谎报 succeeded。"""
    bundle = _bundle(_bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1"))
    enqueued: list[dict] = []

    def enqueue(*, course_id, revision_ids, reason):
        enqueued.append({
            "course_id": course_id,
            "revision_ids": list(revision_ids),
            "reason": reason,
        })
        return {"job_id": "qbr_job_1"}

    runner = build_practice_rebuild_runner(
        bundle=bundle, enqueue=enqueue, course_id="c1",
        knowledge_revision_id="ckb_rev_7",
    )
    downstream = _downstream(needs_regeneration=[
        {"type": "practice", "id": "qbr_1", "section_id": "L2-1-1",
         "reason": "知识陈述变化"},
    ])
    result = execute_rebuild(downstream, runners={"practice": runner})

    assert len(enqueued) == 1
    assert enqueued[0]["revision_ids"] == ["qbr_1"]
    assert enqueued[0]["course_id"] == "c1"

    item = next(i for i in result["downstream"]["items"] if i["id"] == "qbr_1")
    assert item["state"] == "candidate", "登记成功 != 重建完成，必须等教师确认"
    assert item["candidate_revision"] == "qbr_job_1"


def test_runner_does_not_generate_questions_itself() -> None:
    """不建第二真源：runner 自己不出题、不写 bundle。"""
    bundle = _bundle(_bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1"))
    snapshot = deepcopy(bundle)

    runner = build_practice_rebuild_runner(
        bundle=bundle,
        enqueue=lambda **kwargs: {"job_id": "qbr_job_1"},
        course_id="c1",
    )
    execute_rebuild(
        _downstream(needs_regeneration=[
            {"type": "practice", "id": "qbr_1", "section_id": "L2-1-1"},
        ]),
        runners={"practice": runner},
    )
    assert bundle == snapshot, "runner 不得直接改题库，重建必须走既有出题管线"


# --- 产品级承诺：失败时旧题继续可读可作答 -----------------------------------


def test_failed_rebuild_keeps_old_questions_readable_and_answerable() -> None:
    """任务书的产品级承诺，正面测试。

    不是只断言「返回 failed」，而是断言失败之后：
    - 题库 bundle 一个字节都没变；
    - approved_formal_tasks 仍然返回旧题（学生照常拿到题目）；
    - 旧题带着可作答所需的正式契约（prompt + formal_task）。
    """
    old_item = _bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1")
    bundle = _bundle(old_item)
    snapshot = deepcopy(bundle)

    def failing_enqueue(**kwargs):
        raise RuntimeError("出题服务不可用")

    runner = build_practice_rebuild_runner(
        bundle=bundle, enqueue=failing_enqueue, course_id="c1",
    )
    result = execute_rebuild(
        _downstream(needs_regeneration=[
            {"type": "practice", "id": "qbr_1", "section_id": "L2-1-1",
             "reason": "知识陈述变化"},
        ]),
        runners={"practice": runner},
    )

    # 1. 题库没有被动过。
    assert bundle == snapshot

    # 2. 学生侧投影仍然给出旧题。
    tasks = approved_formal_tasks(bundle, assessment_role="practice")
    assert len(tasks) == 1
    assert tasks[0]["node_id"] == "L2-1-1"

    # 3. 旧题仍然可作答：正式契约与题干都在。
    assert tasks[0].get("prompt")
    assert tasks[0].get("revision_id")

    # 4. 下游状态如实记失败，并保留最后可用产物。
    receipt = next(r for r in result["receipts"] if r["id"] == "qbr_1")
    assert receipt["outcome"] == "stale"
    assert "重建失败" in receipt["detail"]


def test_unresolvable_question_fails_without_touching_the_bank() -> None:
    """解析不到题目时如实失败，不做任何写入，也不假装成功。"""
    bundle = _bundle(_bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1"))
    snapshot = deepcopy(bundle)
    calls: list[dict] = []

    runner = build_practice_rebuild_runner(
        bundle=bundle,
        enqueue=lambda **kwargs: calls.append(kwargs) or {"job_id": "x"},
        course_id="c1",
    )
    result = execute_rebuild(
        _downstream(needs_regeneration=[
            {"type": "practice", "id": "q_orphan", "section_id": "L2-9-9"},
        ]),
        runners={"practice": runner},
    )

    assert calls == [], "解析不到题目就不该登记作业"
    assert bundle == snapshot
    assert approved_formal_tasks(bundle, assessment_role="practice")
    receipt = next(r for r in result["receipts"] if r["id"] == "q_orphan")
    assert receipt["outcome"] == "stale"


def test_job_without_job_id_is_a_failure_not_a_silent_success() -> None:
    bundle = _bundle(_bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1"))
    runner = build_practice_rebuild_runner(
        bundle=bundle, enqueue=lambda **kwargs: {}, course_id="c1",
    )
    result = execute_rebuild(
        _downstream(needs_regeneration=[
            {"type": "practice", "id": "qbr_1", "section_id": "L2-1-1"},
        ]),
        runners={"practice": runner},
    )
    receipt = next(r for r in result["receipts"] if r["id"] == "qbr_1")
    assert receipt["outcome"] == "stale"
    assert approved_formal_tasks(bundle, assessment_role="practice")


def test_one_failing_question_does_not_abort_the_rest() -> None:
    """逐题失败不中断整批，否则一道坏题会卡住整节课的重建。"""
    bundle = _bundle(
        _bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1"),
        _bank_item(item_id="qbi_2", revision_id="qbr_2", node_id="L2-2-1"),
    )

    def enqueue(*, course_id, revision_ids, reason):
        if "qbr_1" in revision_ids:
            raise RuntimeError("这道题重建失败")
        return {"job_id": "qbr_job_ok"}

    runner = build_practice_rebuild_runner(
        bundle=bundle, enqueue=enqueue, course_id="c1",
    )
    result = execute_rebuild(
        _downstream(needs_regeneration=[
            {"type": "practice", "id": "qbr_1", "section_id": "L2-1-1"},
            {"type": "practice", "id": "qbr_2", "section_id": "L2-2-1"},
        ]),
        runners={"practice": runner},
    )
    states = {i["id"]: i["state"] for i in result["downstream"]["items"]}
    assert states["qbr_2"] == "candidate", "另一道题必须照常重建"
    assert states["qbr_1"] == "rebuild_required", "失败的题仍挂待重建"


# --- 逐题回执可追溯 ---------------------------------------------------------


def test_receipt_records_question_knowledge_revision_and_outcome() -> None:
    """哪道题、依据哪次知识修订、成功还是失败及原因——三者都要在回执里。"""
    bundle = _bundle(_bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1"))
    runner = build_practice_rebuild_runner(
        bundle=bundle,
        enqueue=lambda **kwargs: {"job_id": "qbr_job_1"},
        course_id="c1",
        knowledge_revision_id="ckb_rev_7",
    )
    execute_rebuild(
        _downstream(needs_regeneration=[
            {"type": "practice", "id": "qbr_1", "section_id": "L2-1-1",
             "reason": "知识陈述变化"},
        ]),
        runners={"practice": runner},
    )
    receipts = practice_rebuild_receipts(runner)
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt["schema_version"] == PRACTICE_REBUILD_RECEIPT_SCHEMA
    assert receipt["question_revision_ids"] == ["qbr_1"]      # 哪道题
    assert receipt["knowledge_revision_id"] == "ckb_rev_7"    # 依据哪次修订
    assert receipt["status"] == "candidate_ready"             # 结果
    assert receipt["job_id"] == "qbr_job_1"
    assert receipt["impact_reason"] == "知识陈述变化"


def test_failure_receipt_records_the_reason() -> None:
    bundle = _bundle(_bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1"))

    def failing_enqueue(**kwargs):
        raise RuntimeError("出题服务不可用")

    runner = build_practice_rebuild_runner(
        bundle=bundle, enqueue=failing_enqueue, course_id="c1",
        knowledge_revision_id="ckb_rev_7",
    )
    execute_rebuild(
        _downstream(needs_regeneration=[
            {"type": "practice", "id": "qbr_1", "section_id": "L2-1-1"},
        ]),
        runners={"practice": runner},
    )
    receipt = practice_rebuild_receipts(runner)[0]
    assert receipt["status"] == "failed"
    assert "出题服务不可用" in receipt["error"]
    assert receipt["knowledge_revision_id"] == "ckb_rev_7"


def test_receipts_are_a_copy_not_the_live_list() -> None:
    """回执要写进作业结果，调用方改它不该污染 runner 内部状态。"""
    bundle = _bundle(_bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1"))
    runner = build_practice_rebuild_runner(
        bundle=bundle,
        enqueue=lambda **kwargs: {"job_id": "qbr_job_1"},
        course_id="c1",
    )
    execute_rebuild(
        _downstream(needs_regeneration=[
            {"type": "practice", "id": "qbr_1", "section_id": "L2-1-1"},
        ]),
        runners={"practice": runner},
    )
    first = practice_rebuild_receipts(runner)
    first[0]["status"] = "tampered"
    assert practice_rebuild_receipts(runner)[0]["status"] == "candidate_ready"


def test_empty_bank_resolves_to_nothing() -> None:
    assert resolve_question_revisions(None, object_id="x", section_id="y") == []
    assert resolve_question_revisions({}, object_id="x", section_id="y") == []
