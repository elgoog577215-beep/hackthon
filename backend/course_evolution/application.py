"""Application service for the single formal course-change workflow."""

from __future__ import annotations

import asyncio
from typing import Any

from learning_contracts import LearnerCourseScope
from learning_events import record_learning_event
from representation_compiler import rebuild_core_representations_safely

from .adjustment_planning import generate_course_adjustment_plan
from .core import (
    CourseEvolutionRepository,
    accept_change_set,
    create_adjustment_plan,
    reject_change_set,
    retry_failed_domain_candidates,
    synchronize_and_evaluate_course_evolution,
    undo_change_set,
)
from .intake import CourseEvolutionRequest, record_course_evolution_request
from .teacher_execution import (
    build_domain_candidate_applier,
    build_domain_candidate_undoer,
    generate_teacher_course_change_candidates,
)
from .teacher_planning import (
    build_teacher_course_change_context,
    create_teacher_course_change_plan,
    review_teacher_course_change_scope,
)


class CourseEvolutionApplicationService:
    """Coordinates repositories without letting routers own business flow."""

    def __init__(
        self,
        *,
        evolution_repository: CourseEvolutionRepository,
        document_repository: Any,
        authoring_repository: Any,
        representation_repository: Any,
        question_bank_repository: Any,
        course_service: Any,
        task_manager: Any | None = None,
    ) -> None:
        self.evolution_repository = evolution_repository
        self.document_repository = document_repository
        self.authoring_repository = authoring_repository
        self.representation_repository = representation_repository
        self.question_bank_repository = question_bank_repository
        self.course_service = course_service
        self.task_manager = task_manager

    def teacher_context(self, course_id: str) -> Any:
        if self.task_manager is None:
            raise ValueError("course_change_task_manager_required")
        document, _canonical = self.document_repository.load_document(course_id)
        preview = self.task_manager.get_generation_preview(
            course_id,
            task_types={"teacher_outline_generation"},
        )
        authoring = self.authoring_repository.load(course_id)
        question_bank = self.question_bank_repository.load_bundle(course_id)
        synthetic_course_ids = {
            str(asset.get("synthetic_course_id") or "")
            for lesson in (authoring.get("lessons") or {}).values()
            if isinstance(lesson, dict)
            for asset in lesson.get("ppt_assets") or []
            if isinstance(asset, dict) and asset.get("synthetic_course_id")
        }
        representation_registries = [
            self.representation_repository.load_payload(value)
            for value in sorted(synthetic_course_ids)
        ]
        return build_teacher_course_change_context(
            course_id=course_id,
            document=document,
            preview=preview,
            authoring=authoring,
            question_bank=question_bank,
            representation_registries=representation_registries,
        )

    async def create_teacher_plan(
        self,
        *,
        course_id: str,
        user_id: str,
        request_id: str,
        instruction: str,
        supersedes_plan_id: str = "",
    ) -> Any:
        context = await asyncio.to_thread(self.teacher_context, course_id)
        return await create_teacher_course_change_plan(
            context=context,
            user_id=user_id,
            request_id=request_id,
            instruction=instruction,
            repository=self.evolution_repository,
            analyzer=self.course_service.analyze_teacher_course_change,
            supersedes_plan_id=supersedes_plan_id,
        )

    async def create_course_adjustment(
        self,
        *,
        course_data: dict[str, Any],
        user_id: str,
        request_id: str,
        instruction: str,
        section_id: str,
        scope_selection: str,
        block_id: str = "",
        expected_document_revision: str = "",
        expected_block_revision: str = "",
        direction: str = "custom",
        anchor_role: str = "",
    ) -> Any:
        """Use one planner for evidence-triggered and teacher-requested adjustments."""
        course_id = str(course_data.get("course_id") or "")
        learning_scope = LearnerCourseScope.from_course(
            course_data,
            user_id=user_id,
            expected_course_id=course_id,
        )
        evolution_request = CourseEvolutionRequest(
            scope=learning_scope,
            request_id=request_id,
            instruction=instruction,
            entrypoint="course_adjustment",
            requested_scope=scope_selection,
            section_id=section_id,
            block_id=block_id,
            surface_entrypoint="course_adjustment",
            direction=direction,
            anchor_role=anchor_role,
            expected_document_revision=expected_document_revision,
            expected_block_revision=expected_block_revision,
        )
        if evolution_request.can_use_evidence_flow():
            await asyncio.to_thread(
                record_course_evolution_request,
                evolution_request,
                recorder=record_learning_event,
            )
            return await asyncio.to_thread(
                synchronize_and_evaluate_course_evolution,
                course_data,
                user_id=user_id,
            )
        return await generate_course_adjustment_plan(
            course_data,
            user_id=user_id,
            section_id=section_id,
            block_id=block_id,
            instruction=instruction,
            scope_selection=scope_selection,
            expected_document_revision=expected_document_revision,
            expected_block_revision=expected_block_revision,
            direction=direction,
            anchor_role=anchor_role or None,
            request_id=request_id,
            repository=self.evolution_repository,
            document_repository=self.document_repository,
        )

    def review_teacher_plan(
        self,
        *,
        user_id: str,
        course_id: str,
        change_set_id: str,
        selected_migration_ids: list[str],
        confirm_structure: bool,
        migration_dispositions: dict[str, str] | None = None,
        proposed_outline: list[dict[str, Any]] | None = None,
    ) -> Any:
        context = self.teacher_context(course_id) if proposed_outline is not None else None
        return review_teacher_course_change_scope(
            repository=self.evolution_repository,
            user_id=user_id,
            course_id=course_id,
            change_set_id=change_set_id,
            selected_migration_ids=selected_migration_ids,
            confirm_structure=confirm_structure,
            migration_dispositions=migration_dispositions,
            proposed_outline=proposed_outline,
            context=context,
        )

    async def generate_suggested(
        self,
        *,
        course_data: dict[str, Any],
        user_id: str,
        change_set_id: str,
    ) -> Any:
        course_id = str(course_data.get("course_id") or "")
        state = self.evolution_repository.load(user_id, course_id)
        plan = next(
            (item for item in state.change_sets if item.change_set_id == change_set_id),
            None,
        )
        if plan is None:
            raise KeyError(change_set_id)
        if plan.teacher_change_planning is not None:
            return await generate_teacher_course_change_candidates(
                course_data=course_data,
                user_id=user_id,
                change_set_id=change_set_id,
                repository=self.evolution_repository,
                authoring_repository=self.authoring_repository,
                representation_repository=self.representation_repository,
                question_bank_repository=self.question_bank_repository,
                course_service=self.course_service,
            )
        return await generate_course_adjustment_plan(
            course_data,
            user_id=user_id,
            section_id=plan.target_section_id,
            instruction=plan.request_text,
            scope_selection=plan.scope_selection,
            request_id=plan.change_set_id,
            repository=self.evolution_repository,
            document_repository=self.document_repository,
            existing_change_set_id=plan.change_set_id,
        )

    def accept(
        self,
        *,
        course_data: dict[str, Any],
        user_id: str,
        change_set_id: str,
        selected_scope: str,
        selected_operation_ids: list[str] | None,
        retry_failed: bool = False,
    ) -> Any:
        applier = build_domain_candidate_applier(
            course_data=course_data,
            user_id=user_id,
            authoring_repository=self.authoring_repository,
            representation_repository=self.representation_repository,
            question_bank_repository=self.question_bank_repository,
            document_repository=self.document_repository,
            evolution_repository=self.evolution_repository,
        )
        state = (
            retry_failed_domain_candidates(
                course_data,
                user_id=user_id,
                change_set_id=change_set_id,
                domain_candidate_applier=applier,
                selected_operation_ids=selected_operation_ids,
                repository=self.evolution_repository,
            )
            if retry_failed
            else accept_change_set(
                course_data,
                user_id=user_id,
                change_set_id=change_set_id,
                selected_scope=selected_scope,
                selected_operation_ids=selected_operation_ids,
                document_repository=self.document_repository,
                domain_candidate_applier=applier,
            )
        )
        return self._record_representation_sync(state, change_set_id, receipt_key="application_receipt")

    def undo(self, *, user_id: str, course_id: str, change_set_id: str) -> Any:
        undoer = build_domain_candidate_undoer(
            user_id=user_id,
            course_id=course_id,
            authoring_repository=self.authoring_repository,
            representation_repository=self.representation_repository,
            question_bank_repository=self.question_bank_repository,
            document_repository=self.document_repository,
        )
        state = undo_change_set(
            user_id=user_id,
            course_id=course_id,
            change_set_id=change_set_id,
            document_repository=self.document_repository,
            domain_candidate_undoer=undoer,
        )
        return self._record_representation_sync(state, change_set_id, receipt_key="undo_receipt")

    def reject(
        self,
        *,
        user_id: str,
        course_id: str,
        change_set_id: str,
        reason: str,
    ) -> Any:
        return reject_change_set(
            user_id=user_id,
            course_id=course_id,
            change_set_id=change_set_id,
            reason=reason,
            document_repository=self.document_repository,
        )

    def adjust(self, *, user_id: str, course_id: str, change_set_id: str) -> Any:
        return create_adjustment_plan(
            user_id=user_id,
            course_id=course_id,
            change_set_id=change_set_id,
            document_repository=self.document_repository,
        )

    def _record_representation_sync(self, state: Any, change_set_id: str, *, receipt_key: str) -> Any:
        plan = next(item for item in state.change_sets if item.change_set_id == change_set_id)
        getattr(plan, receipt_key)["representation_sync"] = self._synchronize_representations(
            state.course_id,
        )
        return self.evolution_repository.save(state)

    def _synchronize_representations(self, course_id: str) -> dict[str, Any]:
        try:
            raw = self.document_repository.load_raw(course_id)
            self.representation_repository.reconcile_course_operation_log(
                course_id,
                list(raw.get("course_operation_log") or []),
            )
            document, canonical = self.document_repository.load_document(course_id)
            if not canonical:
                raise ValueError("course_not_canonical")
            return rebuild_core_representations_safely(
                document,
                self.document_repository.load_course_view(course_id),
                self.representation_repository,
            )
        except Exception as exc:  # noqa: BLE001 - preserve last usable representation
            return {
                "status": "failed_using_last_available",
                "quality": {
                    "passed": False,
                    "issues": [{
                        "severity": "critical",
                        "code": "representation_sync_unavailable",
                        "message": str(exc),
                    }],
                },
            }


__all__ = ["CourseEvolutionApplicationService"]
