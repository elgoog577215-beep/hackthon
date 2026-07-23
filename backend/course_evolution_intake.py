"""把不同学习入口统一为课程生长可消费的正式请求协议。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from course_evolution import strong_self_report_contract
from learning_contracts import LearnerCourseScope
from learning_events import record_learning_event, summarize_text


COURSE_EVOLUTION_REQUEST_SCHEMA = "course_evolution_request_v1"
CourseEvolutionEntrypoint = Literal["ai_teacher", "course_adjustment"]
CourseEvolutionScope = Literal[
    "current_block",
    "current_section",
    "whole_course",
]


@dataclass(frozen=True, slots=True)
class CourseEvolutionRequest:
    """一次可能推动课程变化的学习者请求。"""

    scope: LearnerCourseScope
    request_id: str
    instruction: str
    entrypoint: CourseEvolutionEntrypoint
    requested_scope: CourseEvolutionScope
    section_id: str = ""
    section_name: str = ""
    block_id: str = ""
    conversation_id: str = ""
    selection: str = ""
    surface_entrypoint: str = ""
    direction: str = "custom"
    anchor_role: str = ""
    expected_document_revision: str = ""
    expected_block_revision: str = ""
    context_ref: dict[str, Any] | None = None
    task_ref: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not str(self.request_id or "").strip():
            raise ValueError("course evolution request_id is required")
        if not str(self.instruction or "").strip():
            raise ValueError("course evolution instruction is required")

    @property
    def request_contract(self) -> dict[str, Any]:
        return strong_self_report_contract(
            self.instruction,
            course_id=self.scope.course_id,
        )

    def can_use_evidence_flow(self) -> bool:
        """判断请求能否直接进入证据驱动的课程生长链。"""
        contract = self.request_contract
        revision_is_current = bool(
            not self.expected_document_revision
            or not self.scope.course_version_id
            or self.expected_document_revision == self.scope.course_version_id
        )
        return bool(
            revision_is_current
            and self.requested_scope != "current_block"
            and contract["is_strong"]
            and (
                contract["scope"] != "current_and_next"
                or self.requested_scope == "whole_course"
            )
        )

    def learning_event_payload(self) -> dict[str, Any]:
        contract = self.request_contract
        protocol = {
            "schema_version": COURSE_EVOLUTION_REQUEST_SCHEMA,
            "request_id": self.request_id,
            "entrypoint": self.entrypoint,
            "surface_entrypoint": self.surface_entrypoint or self.entrypoint,
            "requested_scope": self.requested_scope,
            "scope": self.scope.to_dict(),
            "section_id": self.section_id,
            "block_id": self.block_id,
            "direction": self.direction,
            "anchor_role": self.anchor_role,
            "expected_document_revision": self.expected_document_revision,
            "expected_block_revision": self.expected_block_revision,
        }
        source = (
            "ai_teacher.ask_events"
            if self.entrypoint == "ai_teacher"
            else "course_adjustment.learner_request"
        )
        idempotency_key = (
            f"ai-teacher-request:{self.request_id}"
            if self.entrypoint == "ai_teacher"
            else f"course-adjustment:{self.request_id}"
        )
        return {
            "event_type": "assistant_question_submitted",
            "actor": "user",
            "source": source,
            "user_id": self.scope.user_id,
            "course_id": self.scope.course_id,
            "course_version_id": self.scope.course_version_id or None,
            "node_id": self.section_id or None,
            "node_name": self.section_name,
            "idempotency_key": idempotency_key,
            "evidence": {
                "question": summarize_text(self.instruction, limit=5000),
                "selection": summarize_text(self.selection, limit=10000),
                "entrypoint": self.surface_entrypoint or self.entrypoint,
                "conversation_id": self.conversation_id,
                "requested_scope": self.requested_scope,
            },
            "metadata": {
                "block_id": self.block_id,
                "anchor_role": self.anchor_role,
                "task_ref": self.task_ref or {},
                "context_ref": self.context_ref or {},
                "request_contract": contract,
                "course_evolution_request": protocol,
            },
        }


def record_course_evolution_request(
    request: CourseEvolutionRequest,
    *,
    recorder: Callable[..., dict[str, Any]] = record_learning_event,
) -> dict[str, Any]:
    """通过可替换记录器持久化统一请求，便于路由测试和后续存储迁移。"""
    return recorder(**request.learning_event_payload())


__all__ = [
    "COURSE_EVOLUTION_REQUEST_SCHEMA",
    "CourseEvolutionRequest",
    "record_course_evolution_request",
]
