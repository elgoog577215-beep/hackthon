"""Cross-owner behavior for durable global changes and same-lecture recovery."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.tests.test_task_manager_runtime_durability import build_manager
from backend.tests.test_teacher_lesson_authoring import single_section_course_data, standard_lesson_plan
from course_document import CourseDocument, CourseSection, refresh_document_revision
from course_evolution.core import CourseEvolutionRepository
from course_evolution.jobs import (
    ANALYSIS_TASK_TYPE,
    enqueue_analysis,
    enqueue_candidates,
    run_analysis,
    run_candidates,
)
from course_evolution.teacher_execution import (
    _candidate_instruction,
    build_domain_candidate_applier,
    build_domain_candidate_undoer,
    generate_teacher_course_change_candidates,
)
from course_evolution.teacher_planning import (
    build_teacher_course_change_context,
    create_teacher_course_change_plan,
    review_teacher_course_change_scope,
)
from course_evolution.text_fields import editable_text_fields, replace_editable_text
from question_bank import QuestionBankRepository
from teacher_lesson_authoring import (
    TeacherLessonAuthoringError,
    TeacherLessonAuthoringRepository,
    generation_failure,
)
from teacher_script import (
    SCRIPT_PIPELINE_VERSION,
    compile_teacher_script_module_contract,
    compile_teacher_script_section,
    upgrade_script_quality_report,
)
from teaching_representations import TeachingRepresentationRepository


def fixture(tmp_path):
    course = single_section_course_data()
    repo = TeacherLessonAuthoringRepository(tmp_path / "authoring")
    lesson = repo.save_plan_revision(
        "course-1", "L1-1", standard_lesson_plan(), source_outline_revision_id="outline-v1"
    )
    plan_revision = lesson["working_revision_id"]
    plan = lesson["revisions"][-1]["plan"]
    contract = compile_teacher_script_module_contract(course["nodes"][1], plan["sections"][0])
    markdown = "\n\n".join(
        "## "
        + m["title"]
        + "\n\n我们先看核心概念的定义：定义、成立条件和适用边界共同决定一个判断是否成立。请用一个反例检验它。"
        for m in contract["modules"]
    )
    section = compile_teacher_script_section(markdown, contract)
    repo.save_script_revision("course-1", "L1-1", [section], source_lesson_plan_revision_id=plan_revision)
    document = refresh_document_revision(
        CourseDocument(
            course_id="course-1",
            title="概念课",
            sections=[
                CourseSection(section_id="L1-1", title="第一讲", position=0),
                CourseSection(section_id="L2-1-1", parent_section_id="L1-1", title="概念", level=2, position=1),
            ],
        )
    )
    ctx = build_teacher_course_change_context(
        course_id="course-1",
        document=document,
        preview=None,
        authoring=repo.load("course-1"),
        question_bank=None,
        representation_registries=[],
    )
    evolution = CourseEvolutionRepository(tmp_path / "evolution")
    return course, repo, evolution, ctx


async def prepared(tmp_path):
    course, authoring, repo, ctx = fixture(tmp_path)
    state = await create_teacher_course_change_plan(
        context=ctx,
        user_id="teacher",
        request_id="replace-concept",
        instruction="把“核心概念”替换为“关键概念”",
        repository=repo,
        asset_types=["lesson_plan", "script"],
    )
    plan = state.change_sets[0]
    state = review_teacher_course_change_scope(
        repository=repo,
        user_id="teacher",
        course_id="course-1",
        change_set_id=plan.change_set_id,
        selected_migration_ids=[m.migration_id for m in plan.teacher_change_planning.unit_migrations],
    )
    return course, authoring, repo, state.change_sets[0]


@pytest.mark.asyncio
async def test_same_lecture_candidates_apply_and_undo_against_real_repositories(tmp_path):
    course, authoring, repo, plan = await prepared(tmp_path)
    previous = authoring.lesson("course-1", "L1-1")
    representations = TeachingRepresentationRepository(tmp_path / "representations")
    questions = QuestionBankRepository(tmp_path / "questions")
    checkpoints = []

    async def progress(done, total):
        saved = repo.load("teacher", "course-1").change_sets[0]
        checkpoints.append([op.payload["domain"] for op in saved.operations])

    state = await generate_teacher_course_change_candidates(
        course_data=course,
        user_id="teacher",
        change_set_id=plan.change_set_id,
        repository=repo,
        authoring_repository=authoring,
        representation_repository=representations,
        question_bank_repository=questions,
        course_service=object(),
        on_progress=progress,
    )
    plan = state.change_sets[0]
    assert plan.impact_summary["candidate_bundle"]["failed_migration_count"] == 0
    assert checkpoints[0] == ["lesson_plan"]
    assert checkpoints[-1] == ["lesson_plan", "script"]
    script = authoring.lesson("course-1", "L1-1")["script_ai_candidates"][-1]
    assert script["source_lesson_plan_candidate_id"]
    applier = build_domain_candidate_applier(
        course_data=course,
        user_id="teacher",
        authoring_repository=authoring,
        representation_repository=representations,
        question_bank_repository=questions,
        document_repository=None,
        evolution_repository=repo,
    )
    receipt = applier(plan, plan.selected_operation_ids)
    assert all(item["status"] == "applied" for item in receipt["items"]), receipt
    current = authoring.lesson("course-1", "L1-1")
    assert current["script_revisions"][-1]["source_lesson_plan_revision_id"] == current["working_revision_id"]
    assert "关键概念" in current["script_revisions"][-1]["sections"][0]["content"]
    plan.application_receipt = {"domain_candidates": receipt}
    undo = build_domain_candidate_undoer(
        user_id="teacher",
        course_id="course-1",
        authoring_repository=authoring,
        representation_repository=representations,
        question_bank_repository=questions,
        document_repository=None,
    )(plan)
    assert all(item["status"] == "undone" for item in undo["items"]), undo
    restored = authoring.lesson("course-1", "L1-1")
    assert (
        restored["script_revisions"][-1]["sections"][0]["content"]
        == previous["script_revisions"][-1]["sections"][0]["content"]
    )
    assert restored["script_revisions"][-1]["source_lesson_plan_revision_id"] == restored["working_revision_id"]


@pytest.mark.asyncio
async def test_durable_enqueue_is_idempotent_and_restart_reuses_checkpoint(tmp_path, monkeypatch):
    course, authoring, repo, plan = await prepared(tmp_path)
    manager = build_manager(tmp_path, monkeypatch)
    manager.course_service = object()
    manager._course_document_repository = SimpleNamespace(load_course_view=lambda _: course)
    manager._question_bank_repository = QuestionBankRepository(tmp_path / "questions")
    manager.get_generation_workspace_course_for_task = lambda *args, **kw: course
    service = SimpleNamespace(evolution_repository=repo)
    first = await enqueue_candidates(
        manager=manager, service=service, user_id="teacher", course_id="course-1", plan_id=plan.change_set_id
    )
    job_id = first.change_sets[0].generation_job_id
    second = await enqueue_candidates(
        manager=manager, service=service, user_id="teacher", course_id="course-1", plan_id=plan.change_set_id
    )
    assert second.change_sets[0].generation_job_id == job_id
    assert len(manager.tasks) == 1
    manager.tasks[job_id]["status"] = "running"
    assert await manager._reconcile_task_after_restart(job_id)
    await run_candidates(
        manager,
        job_id,
        repository=repo,
        authoring_repository=authoring,
        representation_repository=TeachingRepresentationRepository(tmp_path / "representations"),
    )
    assert manager.tasks[job_id]["status"] == "completed", manager.tasks[job_id].get("error")
    saved = repo.load("teacher", "course-1").change_sets[0]
    ids = [op.operation_id for op in saved.operations]
    manager.tasks[job_id]["status"] = "running"
    assert await manager._reconcile_task_after_restart(job_id)
    await run_candidates(
        manager,
        job_id,
        repository=repo,
        authoring_repository=authoring,
        representation_repository=TeachingRepresentationRepository(tmp_path / "representations"),
    )
    assert [op.operation_id for op in repo.load("teacher", "course-1").change_sets[0].operations] == ids


@pytest.mark.asyncio
async def test_whole_course_analysis_uses_a_durable_task_instead_of_one_long_request(tmp_path, monkeypatch):
    manager = build_manager(tmp_path, monkeypatch)
    started = asyncio.Event()
    release = asyncio.Event()

    async def create_teacher_plan(**kwargs):
        started.set()
        await release.wait()
        return SimpleNamespace(change_sets=[SimpleNamespace(
            change_set_id="plan-1",
            impact_summary={"request_id": kwargs["request_id"]},
        )])

    service = SimpleNamespace(create_teacher_plan=create_teacher_plan)
    task = await enqueue_analysis(
        manager=manager,
        user_id="teacher",
        course_id="course-1",
        request_id="analysis-request-1",
        instruction="每讲安排一个实践项目",
        asset_types=["outline", "lesson_plan", "script"],
    )

    assert task["type"] == ANALYSIS_TASK_TYPE
    assert task["status"] == "pending"

    running = asyncio.create_task(run_analysis(manager, task["id"], service=service))
    await started.wait()
    assert manager.get_task_summary(task["id"])["status"] == "running"
    release.set()
    await running

    completed = manager.get_task_summary(task["id"])
    assert completed["status"] == "completed"
    assert completed["phase_detail"] == {
        "request_id": "analysis-request-1",
        "plan_id": "plan-1",
    }

    manager.tasks[task["id"]]["status"] = "running"
    assert await manager._reconcile_task_after_restart(task["id"])
    assert manager.tasks[task["id"]]["status"] == "pending"


def test_search_and_replacement_share_prose_and_preserve_identifiers():
    original = {
        "node_id": "旧词",
        "role": "旧词",
        "source_refs": [{"text": "旧词"}],
        "artifact_contract": {"description": "旧词"},
        "teaching_modules": [{"teacher_activity": "旧词旧词", "knowledge_names": ["旧词"], "module_id": "旧词"}],
        "homework": ["旧词"],
        "content": "正文  旧词\n末尾",
    }
    fields = editable_text_fields(original)
    replaced, count = replace_editable_text(original, "旧词", "")
    assert count == sum(value.count("旧词") for value in fields.values()) == 5
    assert replaced["node_id"] == replaced["role"] == "旧词"
    assert replaced["source_refs"] == original["source_refs"]
    assert replaced["artifact_contract"] == original["artifact_contract"]
    assert replaced["content"] == "正文  \n末尾"


def test_error_recovery_keeps_specific_gaps_and_distinguishes_version_conflict():
    error = TeacherLessonAuthoringError("lesson_plan_revision_conflict", "来源变化", details={"expected": "r1"})
    result = generation_failure(error, "generic")
    assert result["recovery_action"] == "reanalyze" and not result["retryable"]
    assert result["expected"] == "r1"
    gaps = TeacherLessonAuthoringError(
        "lesson_missing_input", "缺少器材条件", details={"missing_fields": ["可用仪器与精度"]}
    )
    assert generation_failure(gaps, "generic")["missing_fields"] == ["可用仪器与精度"]
    assert generation_failure(TimeoutError("timeout"), "generic")["retryable"] is True


def test_advice_upgrade_keeps_structural_failures_and_requires_known_contract():
    report = {
        "schema_version": "teacher_script_quality_v8",
        "pipeline_version": SCRIPT_PIPELINE_VERSION,
        "blocking_issues": [
            {"code": "teacher_script:missing_transition", "message": "承接建议"},
            {"code": "teacher_script:block_empty", "message": "空块"},
        ],
        "review_issues": [],
        "passed": False,
        "publication_eligible": False,
    }
    upgraded = upgrade_script_quality_report(report)
    assert [i["code"] for i in upgraded["blocking_issues"]] == ["teacher_script:block_empty"]
    assert upgraded["review_issues"] == [] and not upgraded["passed"]
    old = {**report, "schema_version": "unknown"}
    assert upgrade_script_quality_report(old) == old


@pytest.mark.asyncio
async def test_disconnect_after_first_candidate_retains_identity_on_retry(tmp_path):
    course, authoring, repo, plan = await prepared(tmp_path)
    kwargs = dict(
        course_data=course,
        user_id="teacher",
        change_set_id=plan.change_set_id,
        repository=repo,
        authoring_repository=authoring,
        representation_repository=TeachingRepresentationRepository(tmp_path / "representations"),
        question_bank_repository=QuestionBankRepository(tmp_path / "questions"),
        course_service=object(),
    )

    async def interrupted(done, total):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await generate_teacher_course_change_candidates(**kwargs, on_progress=interrupted)
    saved = repo.load("teacher", "course-1").change_sets[0]
    assert len(saved.operations) == 1
    first_id = saved.operations[0].operation_id
    first_candidate = saved.operations[0].payload["candidate_id"]
    resumed = await generate_teacher_course_change_candidates(**kwargs)
    assert resumed.change_sets[0].operations[0].operation_id == first_id
    assert resumed.change_sets[0].operations[0].payload["candidate_id"] == first_candidate
    assert len(authoring.lesson("course-1", "L1-1")["ai_candidates"]) == 1
    assert len(resumed.change_sets[0].operations) == 2


@pytest.mark.asyncio
async def test_complete_semantic_scan_has_no_top_eighty_limit_and_reports_batch_failure(tmp_path):
    from course_evolution.teacher_planning import TeacherCourseChangeUnit

    _, _, repo, context = fixture(tmp_path)
    context.units = [
        TeacherCourseChangeUnit(
            unit_id=f"unit-{i}",
            asset_type="lesson_plan",
            unit_type="lesson_plan_section",
            title=f"第{i}讲",
            text="完全不同的内容" * 100,
            source_revision=f"r{i}",
        )
        for i in range(101)
    ]
    seen = set()

    async def analyzer(overview, candidates, instruction):
        seen.update(item["unit_id"] for item in candidates)
        return {"signal_kind": "semantic", "affected_units": [], "structure": {"required": False}}

    result = await create_teacher_course_change_plan(
        context=context,
        user_id="teacher",
        request_id="full",
        instruction="检查术语",
        repository=repo,
        analyzer=analyzer,
    )
    assert len(seen) == 101
    coverage = result.change_sets[0].impact_summary["coverage"]
    assert coverage["scanned_units"] == coverage["indexed_units"] == 101
    assert not result.change_sets[0].teacher_change_planning.unit_migrations

    async def failing(overview, candidates, instruction):
        raise TimeoutError("provider timeout")

    failed = await create_teacher_course_change_plan(
        context=context,
        user_id="teacher",
        request_id="failure",
        instruction="检查术语",
        repository=repo,
        analyzer=failing,
    )
    plan = failed.change_sets[-1]
    assert plan.impact_summary["coverage"]["scanned_units"] == 0
    assert len(plan.impact_summary["coverage"]["unscanned_unit_ids"]) == 101
    assert plan.teacher_change_planning.intent.blocking_questions == []
    assert plan.teacher_change_planning.status == "blocked"
    blocker = plan.teacher_change_planning.intent.system_blockers[0]
    assert blocker.code == "analysis_incomplete"
    assert blocker.retryable is True
    assert blocker.affected_unit_count == 101
    assert plan.impact_summary["coverage"]["retried_batch_count"] > 0
    assert plan.impact_summary["coverage"]["failed_batches"]


@pytest.mark.asyncio
async def test_structured_question_misplaced_in_blocking_questions_is_recovered(tmp_path):
    _, _, repo, context = fixture(tmp_path)

    async def malformed(overview, candidates, instruction):
        return {
            "analysis_mode": "ai_ranked",
            "signal_kind": "semantic",
            "affected_units": [],
            "blocking_questions": [{
                "question_id": "q_practice_scope",
                "prompt": "实践项目是新增小节，还是补充进现有正文？",
                "response_type": "single_choice",
                "required": True,
                "options": [
                    {"option_id": "new_section", "label": "新增小节", "impact": "调整结构"},
                    {"option_id": "inline", "label": "补充正文", "impact": "结构不变"},
                ],
            }],
            "structure": {"required": False},
        }

    result = await create_teacher_course_change_plan(
        context=context,
        user_id="teacher",
        request_id="malformed-question",
        instruction="每章增加实践项目",
        repository=repo,
        analyzer=malformed,
    )
    intent = result.change_sets[-1].teacher_change_planning.intent
    assert intent.blocking_questions == ["实践项目是新增小节，还是补充进现有正文？"]
    assert len(intent.clarifications) == 1
    question = intent.clarifications[0]
    assert question.question_id == "q_practice_scope"
    assert question.response_type == "single_choice"
    assert [option.option_id for option in question.options] == ["new_section", "inline"]


@pytest.mark.asyncio
async def test_teacher_confirmation_clears_model_questions_but_not_incomplete_scan_blockers(tmp_path):
    _, _, repo, context = fixture(tmp_path)
    unit_id = context.units[0].unit_id

    async def questioning(overview, candidates, instruction):
        return {
            "analysis_mode": "ai_ranked",
            "signal_kind": "semantic",
            "affected_units": [{
                "unit_id": unit_id,
                "disposition": "regenerate",
                "reason": "每讲都需要实践项目",
                "confidence": 0.9,
            }],
            "blocking_questions": ["实践项目是否必须可运行？"],
            "structure": {"required": False},
        }

    confirmed = await create_teacher_course_change_plan(
        context=context,
        user_id="teacher",
        request_id="confirmed-understanding",
        instruction="每讲安排一个实践项目",
        repository=repo,
        analyzer=questioning,
        confirmed_interpretation=True,
    )
    confirmed_plan = confirmed.change_sets[0]
    assert confirmed_plan.teacher_change_planning.status != "needs_clarification"
    assert confirmed_plan.teacher_change_planning.intent.blocking_questions == []
    assert confirmed_plan.impact_summary["clarification_confirmation"]["acknowledged_questions"] == [
        "实践项目是否必须可运行？"
    ]

    async def timeout(overview, candidates, instruction):
        raise TimeoutError("provider timeout")

    incomplete = await create_teacher_course_change_plan(
        context=context,
        user_id="teacher",
        request_id="confirmed-but-incomplete",
        instruction="每讲安排一个实践项目",
        repository=repo,
        analyzer=timeout,
        confirmed_interpretation=True,
    )
    incomplete_plan = incomplete.change_sets[-1]
    assert incomplete_plan.teacher_change_planning.status == "blocked"
    assert incomplete_plan.teacher_change_planning.intent.blocking_questions == []
    assert incomplete_plan.teacher_change_planning.intent.system_blockers[0].code == "analysis_incomplete"


@pytest.mark.asyncio
async def test_structured_clarification_answers_become_a_versioned_ai_decision_snapshot(tmp_path):
    _, _, repo, context = fixture(tmp_path)
    unit_id = context.units[0].unit_id
    seen_snapshots = []

    async def analyzer(overview, candidates, instruction):
        seen_snapshots.append(overview.get("clarification_answer_snapshot"))
        if overview.get("clarification_answer_snapshot"):
            return {
                "analysis_mode": "ai_ranked",
                "signal_kind": "semantic",
                "affected_units": [{
                    "unit_id": unit_id,
                    "disposition": "regenerate",
                    "reason": "按教师确认的位置增加实践项目",
                    "confidence": 0.95,
                }],
                "blocking_questions": [],
                "clarifications": [],
                "structure": {"required": False},
            }
        return {
            "analysis_mode": "ai_ranked",
            "signal_kind": "semantic",
            "affected_units": [],
            "blocking_questions": ["实践项目放在哪里？"],
            "clarifications": [{
                "question_id": "project_placement",
                "prompt": "实践项目放在哪里？",
                "response_type": "single_choice",
                "required": True,
                "options": [
                    {
                        "option_id": "fixed_section",
                        "label": "每讲末尾固定小节",
                        "impact": "结构统一",
                        "recommended": True,
                    },
                    {
                        "option_id": "inline_case",
                        "label": "作为案例穿插",
                        "impact": "更贴合内容",
                        "recommended": False,
                    },
                ],
            }],
            "structure": {"required": False},
        }

    initial = await create_teacher_course_change_plan(
        context=context,
        user_id="teacher",
        request_id="clarification-initial",
        instruction="每讲安排一个实践项目",
        repository=repo,
        analyzer=analyzer,
    )
    first = initial.change_sets[0]
    question = first.teacher_change_planning.intent.clarifications[0]
    assert question.question_id == "project_placement"
    assert [option.option_id for option in question.options] == [
        "fixed_section",
        "inline_case",
    ]

    resolved = await create_teacher_course_change_plan(
        context=context,
        user_id="teacher",
        request_id="clarification-resolved",
        instruction="每讲安排一个实践项目",
        repository=repo,
        analyzer=analyzer,
        supersedes_plan_id=first.change_set_id,
        clarification_set_id=first.teacher_change_planning.intent.clarification_set_id,
        clarification_answers=[{
            "question_id": "project_placement",
            "option_id": "fixed_section",
        }],
    )
    plan = resolved.change_sets[-1]
    snapshot = plan.teacher_change_planning.intent.clarification_answer_snapshot
    assert snapshot is not None
    assert snapshot.answer_revision == 1
    assert snapshot.decision_facts == {
        "project_placement": "每讲末尾固定小节",
    }
    assert snapshot.answers[0].question_prompt == "实践项目放在哪里？"
    assert snapshot.answer_digest
    assert seen_snapshots[-1]["answer_digest"] == snapshot.answer_digest
    assert plan.impact_summary["clarification_answer_digest"] == snapshot.answer_digest
    candidate_instruction = _candidate_instruction(plan)
    assert "老师已确认以下决策，属于硬约束" in candidate_instruction
    assert "实践项目放在哪里？: 每讲末尾固定小节" in candidate_instruction


@pytest.mark.asyncio
async def test_teacher_exact_delete_is_structural_and_keeps_stable_survivor_ids(tmp_path):
    doc = refresh_document_revision(
        CourseDocument(
            course_id="lectures",
            title="讲次",
            sections=[CourseSection(section_id=f"lecture-{i}", title=f"第{i}讲", position=i - 1) for i in range(1, 13)],
        )
    )
    context = build_teacher_course_change_context(
        course_id="lectures", document=doc, preview=None, authoring={}, question_bank=None, representation_registries=[]
    )
    repo = CourseEvolutionRepository(tmp_path / "evolution")
    state = await create_teacher_course_change_plan(
        context=context,
        user_id="teacher",
        request_id="delete-ten",
        instruction="删除第10讲，后续讲次补位上来",
        repository=repo,
    )
    plan = state.change_sets[0]
    assert plan.impact_summary["analysis_mode"] == "deterministic_structure"
    assert [node["source_node_ids"][0] for node in plan.impact_summary["proposed_outline"]] == [
        f"lecture-{i}" for i in range(1, 13) if i != 10
    ]
    reviewed = review_teacher_course_change_scope(
        repository=repo,
        user_id="teacher",
        course_id="lectures",
        change_set_id=plan.change_set_id,
        selected_migration_ids=[],
        confirm_structure=True,
    )
    generated = await generate_teacher_course_change_candidates(
        course_data={"course_id": "lectures"},
        user_id="teacher",
        change_set_id=plan.change_set_id,
        repository=repo,
        authoring_repository=TeacherLessonAuthoringRepository(tmp_path / "authoring"),
        representation_repository=TeachingRepresentationRepository(tmp_path / "representations"),
        question_bank_repository=QuestionBankRepository(tmp_path / "questions"),
        course_service=object(),
    )
    assert generated.change_sets[0].selected_operation_ids == reviewed.change_sets[0].selected_operation_ids
    assert generated.change_sets[0].generation_status == "ready"


@pytest.mark.asyncio
async def test_review_during_generation_cannot_leave_phantom_run_or_write_late_candidate(tmp_path):
    course, authoring, repo, plan = await prepared(tmp_path)
    reviewed = False

    async def revise_scope(done, total):
        nonlocal reviewed
        if reviewed:
            return
        reviewed = True
        review_teacher_course_change_scope(
            repository=repo,
            user_id="teacher",
            course_id="course-1",
            change_set_id=plan.change_set_id,
            selected_migration_ids=plan.impact_summary["scope_review"]["selected_migration_ids"],
        )

    with pytest.raises(ValueError, match="迟到"):
        await generate_teacher_course_change_candidates(
            course_data=course,
            user_id="teacher",
            change_set_id=plan.change_set_id,
            repository=repo,
            authoring_repository=authoring,
            representation_repository=TeachingRepresentationRepository(tmp_path / "representations"),
            question_bank_repository=QuestionBankRepository(tmp_path / "questions"),
            course_service=object(),
            on_progress=revise_scope,
        )
    saved = repo.load("teacher", "course-1").change_sets[0]
    assert saved.generation_status != "generating"
    assert saved.review_revision == plan.review_revision + 1
    assert len(saved.operations) == 1


@pytest.mark.asyncio
async def test_candidate_generation_preserves_current_teacher_edit_on_source_conflict(tmp_path):
    course, authoring, repo, plan = await prepared(tmp_path)
    current = authoring.lesson("course-1", "L1-1")
    teacher_edit = deepcopy(current["revisions"][-1]["plan"])
    teacher_edit["lesson_title"] = "教师最新编辑"
    authoring.save_plan_revision("course-1", "L1-1", teacher_edit, source_outline_revision_id="outline-v1")
    state = await generate_teacher_course_change_candidates(
        course_data=course,
        user_id="teacher",
        change_set_id=plan.change_set_id,
        repository=repo,
        authoring_repository=authoring,
        representation_repository=TeachingRepresentationRepository(tmp_path / "representations"),
        question_bank_repository=QuestionBankRepository(tmp_path / "questions"),
        course_service=object(),
    )
    saved = state.change_sets[0]
    assert not saved.operations
    assert any(
        m.metadata.get("candidate_error_detail", {}).get("category") == "conflict"
        for m in saved.teacher_change_planning.unit_migrations
    )
    assert authoring.lesson("course-1", "L1-1")["revisions"][-1]["plan"]["lesson_title"] == "教师最新编辑"
