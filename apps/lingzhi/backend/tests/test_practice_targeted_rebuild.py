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
    build_rebuild_runners,
    practice_rebuild_receipts,
    question_bank_job_enqueue,
    resolve_question_revisions,
)
from question_bank import approved_formal_tasks, reconcile_item_question_bank
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


def test_question_group_expands_to_one_atomic_rebuild_unit() -> None:
    """A selected member cannot leave the rest of its formal group stale."""
    first = _bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1")
    second = _bank_item(item_id="qbi_2", revision_id="qbr_2", node_id="L2-1-1")
    independent = _bank_item(item_id="qbi_3", revision_id="qbr_3", node_id="L2-1-1")
    first["question_group_id"] = "group-1"
    second["question_group_id"] = "group-1"

    assert resolve_question_revisions(
        _bundle(first, second, independent),
        object_id="qbr_1",
    ) == ["qbr_1", "qbr_2"]


def test_shared_stimulus_expands_to_one_atomic_rebuild_unit() -> None:
    first = _bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1")
    second = _bank_item(item_id="qbi_2", revision_id="qbr_2", node_id="L2-1-1")
    for item in (first, second):
        item["question_spec"] = {
            "stimulus": {
                "rendered_text": "共同材料",
                "shared_material_id": "material-1",
            },
        }

    assert resolve_question_revisions(
        _bundle(first, second),
        object_id="qbr_2",
    ) == ["qbr_1", "qbr_2"]


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


# --- 接线：与真实作业仓库对接 -----------------------------------------------


def test_enqueue_creates_a_real_item_scoped_job(tmp_path) -> None:
    """用真实的 QuestionBankRebuildJobRepository，不是 stub。

    验证登记出来的作业确实是 scope="items" 的定向作业，且带着我们指定的
    revision_ids——如果退化成 scope="nodes"，该节没受影响的题会被一起重出。
    """
    from question_bank_jobs import QuestionBankRebuildJobRepository

    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    enqueue = question_bank_job_enqueue(
        job_repository=repository,
        actor_id="teacher-1",
        knowledge_revision_id="ckb_rev_7",
    )
    job = enqueue(course_id="c1", revision_ids=["qbr_2", "qbr_1"], reason="知识变化")

    assert job["scope"] == "items", "必须是定向重建，不是整节重出"
    assert job["revision_ids"] == ["qbr_1", "qbr_2"]
    assert job["mode"] == "incremental"
    assert job["actor_id"] == "teacher-1"
    assert job["status"] == "queued"
    assert job["job_id"].startswith("qbr_")
    # 作业带完整的 10 阶段，交给既有出题管线接手。
    assert len(job["stages"]) == 10


def test_new_real_job_is_submitted_to_the_existing_executor(tmp_path) -> None:
    from question_bank_jobs import QuestionBankRebuildJobRepository

    class RecordingExecutor:
        def __init__(self) -> None:
            self.instance_id = "question-bank-worker-1"
            self.calls = []

        def submit(self, **kwargs):
            self.calls.append(kwargs)

    class Payload(dict):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.__dict__.update(kwargs)

    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    executor = RecordingExecutor()
    course = {"course_id": "c1", "nodes": [{"node_id": "L2-1-1"}]}
    enqueue = question_bank_job_enqueue(
        job_repository=repository,
        job_executor=executor,
        payload_factory=Payload,
        course_data=course,
        actor_id="teacher-1",
        knowledge_revision_id="ckb_rev_7",
    )

    job = enqueue(course_id="c1", revision_ids=["qbr_1"])
    assert len(executor.calls) == 1
    submitted = executor.calls[0]
    assert submitted["job_id"] == job["job_id"]
    assert submitted["payload"].scope == "items"
    assert submitted["payload"].revision_ids == ["qbr_1"]
    assert submitted["course"] == course
    assert job["worker_id"] == "question-bank-worker-1"


def test_default_runtime_fails_before_creating_an_orphan_job(
    monkeypatch,
    tmp_path,
) -> None:
    import question_bank_jobs
    import question_bank_rebuild_runtime
    from question_bank_jobs import QuestionBankRebuildJobRepository

    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    monkeypatch.setattr(
        question_bank_jobs,
        "question_bank_rebuild_job_repository",
        repository,
    )
    monkeypatch.setattr(question_bank_rebuild_runtime, "_executor", None)
    monkeypatch.setattr(question_bank_rebuild_runtime, "_payload_factory", None)

    with pytest.raises(RuntimeError, match="尚未完成启动注册"):
        question_bank_job_enqueue()

    assert repository.latest_for_course("c1") is None


def test_default_runtime_submits_through_the_registered_adapter(
    monkeypatch,
    tmp_path,
) -> None:
    import question_bank_jobs
    import question_bank_rebuild_runtime
    from question_bank_jobs import QuestionBankRebuildJobRepository

    class RecordingExecutor:
        instance_id = "question-bank-worker-runtime"

        def __init__(self) -> None:
            self.calls = []

        def submit(self, **kwargs):
            self.calls.append(kwargs)

    class Payload(dict):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.__dict__.update(kwargs)

    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    executor = RecordingExecutor()
    monkeypatch.setattr(
        question_bank_jobs,
        "question_bank_rebuild_job_repository",
        repository,
    )
    monkeypatch.setattr(question_bank_rebuild_runtime, "_executor", executor)
    monkeypatch.setattr(
        question_bank_rebuild_runtime,
        "_payload_factory",
        Payload,
    )

    enqueue = question_bank_job_enqueue(course_data={"course_id": "c1"})
    job = enqueue(course_id="c1", revision_ids=["qbr_1"])

    assert job["worker_id"] == executor.instance_id
    assert len(executor.calls) == 1
    assert executor.calls[0]["job_id"] == job["job_id"]
    assert executor.calls[0]["payload"].revision_ids == ["qbr_1"]


def test_reconcile_expands_question_group_before_atomic_publish() -> None:
    first = _bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1")
    second = _bank_item(item_id="qbi_2", revision_id="qbr_2", node_id="L2-1-1")
    first["question_group_id"] = "group-1"
    second["question_group_id"] = "group-1"
    replacement_first = deepcopy(first)
    replacement_second = deepcopy(second)
    replacement_first["revision_id"] = "qbr_1_new"
    replacement_second["revision_id"] = "qbr_2_new"

    merged = reconcile_item_question_bank(
        _bundle(first, second),
        _bundle(replacement_first, replacement_second),
        revision_ids=["qbr_1"],
    )
    revisions = {
        item["item_id"]: item["revision_id"]
        for item in merged["items"]
    }
    assert revisions == {"qbi_1": "qbr_1_new", "qbi_2": "qbr_2_new"}


def test_same_knowledge_revision_does_not_create_duplicate_jobs(tmp_path) -> None:
    """幂等：同一次知识修订重复点重建，不该堆出第二个作业。"""
    from question_bank_jobs import QuestionBankRebuildJobRepository

    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    enqueue = question_bank_job_enqueue(
        job_repository=repository,
        actor_id="teacher-1",
        knowledge_revision_id="ckb_rev_7",
    )
    first = enqueue(course_id="c1", revision_ids=["qbr_1"])
    second = enqueue(course_id="c1", revision_ids=["qbr_1"])
    assert first["job_id"] == second["job_id"]


def test_a_second_rebuild_coalesces_while_the_first_is_still_running(tmp_path) -> None:
    """同一批题已有在跑的作业时，不再叠加第二个。

    这是作业仓库自己的去重口径（`_same_active_scope`：scope + node_ids +
    revision_ids + mode + actor + retrieval 全同且状态为 queued/running 才算
    同一个），不是我这层的发明。教师连点两次不会排出两条重建。
    """
    from question_bank_jobs import QuestionBankRebuildJobRepository

    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    first = question_bank_job_enqueue(
        job_repository=repository, knowledge_revision_id="ckb_rev_7",
    )(course_id="c1", revision_ids=["qbr_1"])
    second = question_bank_job_enqueue(
        job_repository=repository, knowledge_revision_id="ckb_rev_8",
    )(course_id="c1", revision_ids=["qbr_1"])
    assert first["job_id"] == second["job_id"]


def test_a_new_knowledge_revision_rebuilds_again_after_the_first_finished(
    tmp_path,
) -> None:
    """上一轮跑完之后，新一次知识修订必须能重新重建这道题。

    否则题目会永久停在第一次重建的结果上，后续知识修订再也落不下来。
    """
    from question_bank_jobs import QuestionBankRebuildJobRepository

    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    first = question_bank_job_enqueue(
        job_repository=repository, knowledge_revision_id="ckb_rev_7",
    )(course_id="c1", revision_ids=["qbr_1"])
    repository.start(first["job_id"])
    repository.complete(first["job_id"], result={"ok": True})

    second = question_bank_job_enqueue(
        job_repository=repository, knowledge_revision_id="ckb_rev_8",
    )(course_id="c1", revision_ids=["qbr_1"])
    assert first["job_id"] != second["job_id"]


def test_a_different_question_set_is_always_a_distinct_job(tmp_path) -> None:
    from question_bank_jobs import QuestionBankRebuildJobRepository

    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    enqueue = question_bank_job_enqueue(
        job_repository=repository, knowledge_revision_id="ckb_rev_7",
    )
    first = enqueue(course_id="c1", revision_ids=["qbr_1"])
    second = enqueue(course_id="c1", revision_ids=["qbr_2"])
    assert first["job_id"] != second["job_id"]


def test_end_to_end_through_executor_with_real_job_repository(tmp_path) -> None:
    """端到端：影响报告 -> executor -> practice runner -> 真实作业仓库。

    这是任务书要接上的那一段的完整形状，中间不打桩。
    """
    from question_bank_jobs import QuestionBankRebuildJobRepository

    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    bundle = _bundle(
        _bank_item(item_id="qbi_1", revision_id="qbr_1", node_id="L2-1-1"),
        _bank_item(item_id="qbi_2", revision_id="qbr_2", node_id="L2-2-1"),
    )
    snapshot = deepcopy(bundle)

    runners = build_rebuild_runners(
        bundle=bundle,
        course_id="c1",
        knowledge_revision_id="ckb_rev_7",
        actor_id="teacher-1",
        job_repository=repository,
    )
    downstream = build_downstream_state(
        _impact(
            needs_regeneration=[
                {"type": "practice", "id": "qbr_1", "section_id": "L2-1-1",
                 "reason": "知识陈述变化"},
            ],
            unchanged=[
                {"type": "practice", "id": "qbr_2", "section_id": "L2-2-1",
                 "reason": "未引用该知识"},
            ],
        ),
        plan_revision_id="ckb_rev_7",
    )
    result = execute_rebuild(downstream, runners=runners)

    # 受影响的题进入候选，未受影响的题原样不动。
    states = {i["id"]: i["state"] for i in result["downstream"]["items"]}
    assert states["qbr_1"] == "candidate"
    assert states["qbr_2"] == "current"

    # 真实作业已落盘，且是定向的。
    active = repository.active_for_course("c1")
    assert active is not None
    assert active["scope"] == "items"
    assert active["revision_ids"] == ["qbr_1"]

    # 题库本身没有被 runner 动过——重建由既有出题管线做。
    assert bundle == snapshot

    # 逐题回执可追溯。
    receipt = practice_rebuild_receipts(runners["practice"])[0]
    assert receipt["question_revision_ids"] == ["qbr_1"]
    assert receipt["knowledge_revision_id"] == "ckb_rev_7"
    assert receipt["status"] == "candidate_ready"


def test_only_practice_runner_is_registered() -> None:
    """不给别人那条线塞占位实现。

    缺 runner 时 executor 自己会标 blocked 并说明原因，那是诚实的缺口；
    塞一个占位会把「没人实现」伪装成「实现了但失败」。
    """
    runners = build_rebuild_runners(
        bundle=_bundle(), course_id="c1", enqueue=lambda **kw: {"job_id": "x"},
    )
    assert set(runners) == {"practice"}
