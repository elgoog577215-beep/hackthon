from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

import course_evolution.teacher_execution as teacher_execution
from course_document import CourseDocument, refresh_document_revision
from course_evolution.core import (
    CourseEvolutionJournalPersistenceError,
    CourseEvolutionOperation,
    CourseEvolutionOperationJournalEntry,
    CourseEvolutionPlan,
    CourseEvolutionRepository,
    CourseEvolutionState,
    accept_change_set,
    retry_failed_domain_candidates,
)
from course_evolution.teacher_execution import build_domain_candidate_applier

NOW = "2026-09-04T00:00:00+00:00"


def _operation(
    operation_id: str,
    domain: str,
    *,
    lesson_id: str = "lesson-1",
) -> CourseEvolutionOperation:
    payload = {
        "domain": domain,
        "candidate_id": f"candidate-{operation_id}",
        "lesson_unit_id": lesson_id,
        "migration_ids": [f"migration-{operation_id}"],
        "unit_ids": [f"{domain}:{lesson_id}"],
        "previous_revision_id": f"previous-{operation_id}",
    }
    if domain == "ppt":
        payload.update({
            "previous_spec_id": "spec-base",
            "representation_id": "representation-1",
            "synthetic_course_id": "synthetic-course-1",
        })
    if domain == "question_bank":
        payload.update({
            "candidate_revision_id": "qbb-candidate",
            "changed_item_revision_ids": ["question-r2"],
        })
    return CourseEvolutionOperation(
        operation_id=operation_id,
        operation_type="APPLY_DOMAIN_CANDIDATE",
        target_block_id="",
        target_section_id="",
        reason="测试逐操作持久化",
        payload=payload,
    )


def _plan() -> CourseEvolutionPlan:
    plan = CourseEvolutionPlan(
        change_set_id="change-journal-1",
        user_id="teacher-1",
        course_id="course-1",
        hypothesis_id="teacher-change-journal-1",
        source_kind="manual_request",
        request_text="更新教学资产",
        operations=[
            _operation("operation-plan", "lesson_plan", lesson_id="lesson-plan"),
            _operation("operation-script", "script", lesson_id="lesson-script"),
            _operation("operation-ppt", "ppt", lesson_id="lesson-ppt"),
            _operation("operation-question", "question_bank", lesson_id=""),
        ],
        allowed_scopes=["current"],
        selected_scope="current",
        selected_operation_ids=[
            "operation-plan",
            "operation-script",
            "operation-ppt",
            "operation-question",
        ],
        expected_effect="逐项安全应用",
        status="accepted",
        created_at=NOW,
        updated_at=NOW,
    )
    plan.operation_journal = [
        CourseEvolutionOperationJournalEntry(
            operation_id=operation.operation_id,
            domain=str(operation.payload.get("domain") or ""),
            previous_revision_id=str(
                operation.payload.get("previous_revision_id")
                or operation.payload.get("previous_spec_id")
                or ""
            ),
            created_at=NOW,
            updated_at=NOW,
        )
        for operation in plan.operations
    ]
    return plan


class FakeAuthoringRepository:
    def __init__(self) -> None:
        self.lessons = {
            "lesson-plan": {
                "working_revision_id": "previous-operation-plan",
                "revisions": [],
                "ai_candidates": [{
                    "candidate_id": "candidate-operation-plan",
                    "status": "pending",
                }],
            },
            "lesson-script": {
                "working_script_revision_id": "previous-operation-script",
                "script_revisions": [],
                "script_ai_candidates": [{
                    "candidate_id": "candidate-operation-script",
                    "status": "pending",
                }],
            },
            "lesson-ppt": {
                "ppt_assets": [{
                    "role": "primary",
                    "engine": "slide_deck_v6",
                    "working_v6_revision_id": "binding-base",
                    "v6_revisions": [{
                        "revision_id": "binding-base",
                        "spec_id": "spec-base",
                    }],
                    "v6_ai_candidates": [{
                        "candidate_id": "candidate-operation-ppt",
                        "status": "pending",
                    }],
                }],
            },
        }

    def lesson(self, _course_id: str, lesson_id: str) -> dict:
        return deepcopy(self.lessons[lesson_id])


class FakeQuestionBankRepository:
    def __init__(self) -> None:
        self.revisions = {
            "qbb-candidate": {
                "course_id": "course-1",
                "bundle_revision_id": "qbb-candidate",
                "items": [],
            },
        }
        self.active_revision_id = "previous-operation-question"

    def load_bundle(self, _course_id: str, revision_id: str | None = None):
        effective = revision_id or self.active_revision_id
        return deepcopy(self.revisions.get(effective))

    def save_bundle(self, _course_id: str, bundle: dict, *, activate: bool = True):
        saved = deepcopy(bundle)
        self.revisions[saved["bundle_revision_id"]] = saved
        if activate:
            self.active_revision_id = saved["bundle_revision_id"]
        return saved

    def activate_bundle(self, _course_id: str, revision_id: str) -> None:
        self.active_revision_id = revision_id


class FakeDocumentRepository:
    def __init__(self) -> None:
        self.document = refresh_document_revision(CourseDocument(
            course_id="course-1",
            title="逐操作恢复测试课程",
        ))
        self.raw = {
            "course_id": "course-1",
            "course_name": self.document.title,
            "course_schema_version": "course_document_v1",
            "course_document": self.document.model_dump(mode="json"),
            "course_document_revision": self.document.document_revision,
            "course_document_authoritative": True,
            "course_operation_log": [],
        }
        self.command_receipt = None

    async def update_metadata(self, _course_id: str, updates: dict) -> dict:
        self.raw.update(deepcopy(updates))
        return deepcopy(self.raw)

    def load_raw(self, _course_id: str) -> dict:
        return deepcopy(self.raw)

    def load_document(self, _course_id: str):
        return self.document.model_copy(deep=True), True

    def receipt_for_command(self, _course_id: str, _command_id: str):
        return deepcopy(self.command_receipt)


class InterruptingEvolutionRepository(CourseEvolutionRepository):
    def __init__(self, root) -> None:
        super().__init__(root)
        self.interrupt_once = True
        self.transitions: list[tuple[str, str]] = []

    def update(self, user_id, course_id, updater):
        def recording(current):
            updated = updater(current)
            value = current if updated is None else updated
            plan = next(
                item
                for item in value.change_sets
                if item.change_set_id == "change-journal-1"
            )
            for entry in plan.operation_journal:
                marker = (entry.operation_id, entry.status)
                if not self.transitions or self.transitions[-1] != marker:
                    self.transitions.append(marker)
            ppt_entry = next(
                (
                    item
                    for item in plan.operation_journal
                    if item.operation_id == "operation-ppt"
                ),
                None,
            )
            if (
                self.interrupt_once
                and ppt_entry is not None
                and ppt_entry.status == "applied"
            ):
                self.interrupt_once = False
                raise OSError("injected journal write interruption")
            return value

        return super().update(user_id, course_id, recording)


def _install_asset_stubs(monkeypatch, authoring, calls):
    def resolve_plan(service, **kwargs):
        calls.append("operation-plan")
        lesson = authoring.lessons[kwargs["lesson_unit_id"]]
        revision_id = kwargs["result_revision_id_override"]
        lesson["working_revision_id"] = revision_id
        lesson["revisions"].append({"revision_id": revision_id})
        lesson["ai_candidates"][0].update({
            "status": "accepted",
            "result_revision_id": revision_id,
        })
        return deepcopy(lesson)

    def apply_script(**kwargs):
        calls.append("operation-script")
        lesson = authoring.lessons[kwargs["lesson_id"]]
        revision_id = kwargs["result_revision_id_override"]
        lesson["working_script_revision_id"] = revision_id
        lesson["script_revisions"].append({"revision_id": revision_id})
        lesson["script_ai_candidates"][0].update({
            "status": "accepted",
            "result_revision_id": revision_id,
        })
        return revision_id

    def apply_ppt(**kwargs):
        calls.append("operation-ppt")
        asset = authoring.lessons[kwargs["lesson_id"]]["ppt_assets"][0]
        asset["working_v6_revision_id"] = "binding-result"
        asset["v6_revisions"].append({
            "revision_id": "binding-result",
            "spec_id": "spec-result",
        })
        asset["v6_ai_candidates"][0].update({
            "status": "accepted",
            "result_spec_id": "spec-result",
        })
        return "spec-result", "binding-result", "binding-base"

    monkeypatch.setattr(
        teacher_execution.TeacherLessonAuthoringService,
        "resolve_ai_candidate",
        resolve_plan,
    )
    monkeypatch.setattr(teacher_execution, "_apply_script_candidate", apply_script)
    monkeypatch.setattr(teacher_execution, "_apply_ppt_candidate", apply_ppt)
    monkeypatch.setattr(
        teacher_execution,
        "review_question_bank_item",
        lambda bundle, *_args, **_kwargs: deepcopy(bundle),
    )
    monkeypatch.setattr(
        teacher_execution,
        "refresh_question_bank_bundle",
        lambda bundle: {**deepcopy(bundle), "bundle_revision_id": "qbb-result"},
    )


def test_legacy_plan_without_operation_journal_remains_readable():
    payload = _plan().model_dump(mode="json")
    payload.pop("operation_journal")

    restored = CourseEvolutionPlan.model_validate(payload)

    assert restored.operation_journal == []
    with pytest.raises(ValidationError):
        CourseEvolutionOperationJournalEntry(
            operation_id="operation-invalid",
            status="unknown",
        )


def test_interrupted_third_asset_is_reconciled_without_replay(
    tmp_path,
    monkeypatch,
):
    repository = InterruptingEvolutionRepository(tmp_path / "evolution")
    plan = _plan()
    plan.status = "pending"
    plan.selected_scope = None
    plan.selected_operation_ids = []
    plan.operation_journal = []
    repository.save(CourseEvolutionState(
        user_id=plan.user_id,
        course_id=plan.course_id,
        change_sets=[plan],
        updated_at=NOW,
    ))
    authoring = FakeAuthoringRepository()
    question_bank = FakeQuestionBankRepository()
    document_repository = FakeDocumentRepository()
    calls: list[str] = []
    _install_asset_stubs(monkeypatch, authoring, calls)
    applier = build_domain_candidate_applier(
        course_data={"course_id": "course-1"},
        user_id="teacher-1",
        authoring_repository=authoring,
        representation_repository=object(),
        question_bank_repository=question_bank,
        document_repository=document_repository,
        evolution_repository=repository,
    )
    course_data = deepcopy(document_repository.raw)
    selected_operation_ids = [item.operation_id for item in plan.operations]

    with pytest.raises(CourseEvolutionJournalPersistenceError):
        accept_change_set(
            course_data,
            user_id="teacher-1",
            change_set_id=plan.change_set_id,
            selected_scope="current",
            selected_operation_ids=selected_operation_ids,
            repository=repository,
            document_repository=document_repository,
            domain_candidate_applier=applier,
        )

    interrupted = repository.load("teacher-1", "course-1").change_sets[0]
    assert [item.status for item in interrupted.operation_journal] == [
        "applied",
        "applied",
        "applying",
        "pending",
    ]
    assert calls == ["operation-plan", "operation-script", "operation-ppt"]

    document_repository.command_receipt = {
        "operation": "course_evolution_apply",
        "command_id": "durable-command",
        "document_revision": document_repository.document.document_revision,
    }
    resumed_state = accept_change_set(
        course_data,
        user_id="teacher-1",
        change_set_id=plan.change_set_id,
        selected_scope="current",
        selected_operation_ids=selected_operation_ids,
        repository=repository,
        document_repository=document_repository,
        domain_candidate_applier=applier,
    )
    receipt = resumed_state.change_sets[0].application_receipt["domain_candidates"]

    assert receipt["status"] == "applied"
    assert receipt["applied_count"] == 4
    assert calls == [
        "operation-plan",
        "operation-script",
        "operation-ppt",
    ]
    assert question_bank.active_revision_id == "qbb-result"
    assert document_repository.raw["question_bank_bundle_revision_id"] == "qbb-result"
    final = repository.load("teacher-1", "course-1").change_sets[0]
    assert [item.status for item in final.operation_journal] == [
        "applied",
        "applied",
        "applied",
        "applied",
    ]
    assert final.operation_journal[2].detail == "已与正式修订对账，无需重复应用"
    assert ("operation-plan", "applying") in repository.transitions
    assert ("operation-plan", "applied") in repository.transitions
    assert ("operation-script", "applying") in repository.transitions
    assert ("operation-script", "applied") in repository.transitions


def test_retry_of_five_operations_dispatches_only_the_failed_operation(tmp_path):
    repository = CourseEvolutionRepository(tmp_path / "retry")
    plan = _plan()
    extra = _operation("operation-extra", "lesson_plan", lesson_id="lesson-extra")
    plan.operations.append(extra)
    plan.selected_operation_ids.append(extra.operation_id)
    plan.status = "applied"
    plan.operation_journal.append(CourseEvolutionOperationJournalEntry(
        operation_id=extra.operation_id,
        domain="lesson_plan",
        status="applied",
        attempt=1,
        result_revision_id="result-operation-extra",
        result_receipt={
            "operation_id": extra.operation_id,
            "status": "applied",
            "result_revision_id": "result-operation-extra",
            "detail": "已完成",
        },
        created_at=NOW,
        completed_at=NOW,
        updated_at=NOW,
    ))
    failed_id = "operation-script"
    receipt_items = []
    for entry in plan.operation_journal:
        entry.status = "failed" if entry.operation_id == failed_id else "applied"
        entry.attempt = 1
        entry.detail = "暂时失败" if entry.status == "failed" else "已完成"
        entry.error_code = "script_candidate_apply_failed" if entry.status == "failed" else ""
        entry.retryable = entry.status == "failed"
        entry.result_revision_id = (
            "" if entry.status == "failed" else f"result-{entry.operation_id}"
        )
        entry.result_receipt = {
            "operation_id": entry.operation_id,
            "status": entry.status,
            "result_revision_id": entry.result_revision_id,
            "detail": entry.detail,
        }
        receipt_items.append(deepcopy(entry.result_receipt))
    plan.application_receipt = {
        "domain_candidates": {
            "schema_version": "teacher_course_domain_receipt_v1",
            "status": "partial",
            "applied_count": 4,
            "failed_count": 1,
            "items": deepcopy(receipt_items),
        },
        "items": deepcopy(receipt_items),
        "applied_count": 4,
        "failed_count": 1,
        "unchanged_count": 0,
    }
    repository.save(CourseEvolutionState(
        user_id=plan.user_id,
        course_id=plan.course_id,
        change_sets=[plan],
        updated_at=NOW,
    ))
    dispatched: list[str] = []

    def retry_one(_plan, operation_ids):
        dispatched.extend(operation_ids)
        return {
            "items": [{
                "operation_id": failed_id,
                "status": "applied",
                "result_revision_id": "result-operation-script",
                "detail": "重试成功",
            }],
        }

    updated = retry_failed_domain_candidates(
        {"course_id": "course-1"},
        user_id="teacher-1",
        change_set_id=plan.change_set_id,
        domain_candidate_applier=retry_one,
        selected_operation_ids=[failed_id],
        repository=repository,
    ).change_sets[0]

    assert dispatched == [failed_id]
    assert updated.application_receipt["domain_candidates"]["applied_count"] == 5
    assert updated.application_receipt["domain_candidates"]["failed_count"] == 0
    assert all(item.status == "applied" for item in updated.operation_journal)
    assert {
        item.operation_id: item.result_revision_id
        for item in updated.operation_journal
        if item.operation_id != failed_id
    } == {
        item.operation_id: f"result-{item.operation_id}"
        for item in updated.operation_journal
        if item.operation_id != failed_id
    }
