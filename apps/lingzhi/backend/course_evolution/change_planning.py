"""Teacher-facing whole-course change planning contracts.

The teacher's wording is evidence, not an API enum.  A model or another
interpreter keeps the original request, records its current interpretation and
emits semantic/structural signals.  This module then turns those signals into a
safe, revisable execution plan without trying to classify the raw sentence by
keywords.

The plan is an orchestration candidate, never a second course truth.  Existing
domain repositories continue to own outline, lesson-plan, question-bank,
teacher-script and slide-deck revisions.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

COURSE_CHANGE_INTENT_SCHEMA = "course_change_intent_v1"
COURSE_CHANGE_PLAN_SCHEMA = "course_change_plan_v1"
COURSE_CHANGE_SCENARIO_MATRIX_SCHEMA = "course_change_scenario_matrix_v1"

ExecutionStrategy = Literal["semantic_impact", "structural_regeneration"]
SignalKind = Literal["semantic", "structural", "mixed", "uncertain"]
PlanningStatus = Literal[
    "draft",
    "impact_ready",
    "needs_clarification",
    "candidate_ready",
    "blocked",
]
StrategyStatus = Literal["provisional", "resolved"]
StructureReviewStatus = Literal["not_required", "pending", "confirmed"]
ValidationPhase = Literal["impact_preview", "downstream_generation", "publish"]
MigrationDisposition = Literal[
    "reuse_exact",
    "reuse_rebind",
    "rewrite_partial",
    "regenerate",
    "retire",
    "blocked",
]
CandidateStatus = Literal["not_started", "ready", "failed", "not_required"]
StructureOperationType = Literal[
    "INSERT_OUTLINE_NODE",
    "UPDATE_OUTLINE_NODE",
    "MOVE_OUTLINE_NODE",
    "REORDER_OUTLINE_NODES",
    "SPLIT_OUTLINE_NODE",
    "MERGE_OUTLINE_NODES",
    "RETIRE_OUTLINE_NODE",
    "REBUILD_OUTLINE",
]


class CourseChangeSignal(BaseModel):
    """One explainable clue produced while interpreting the teacher request."""

    signal_id: str
    kind: SignalKind
    evidence: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = "ai_interpretation"


class CourseChangeIntent(BaseModel):
    """A revisable interpretation that always preserves what the teacher said."""

    schema_version: Literal["course_change_intent_v1"] = COURSE_CHANGE_INTENT_SCHEMA
    intent_id: str
    course_id: str
    raw_request: str
    interpreted_goal: str
    scope_hint: dict[str, Any] = Field(default_factory=dict)
    hard_constraints: list[str] = Field(default_factory=list)
    soft_preferences: list[str] = Field(default_factory=list)
    protected_requirements: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    signals: list[CourseChangeSignal] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    blocking_questions: list[str] = Field(default_factory=list)
    can_proceed_without_clarification: bool = True
    interpretation_revision: str = "intent-1"

    @model_validator(mode="after")
    def validate_intent(self) -> CourseChangeIntent:
        for field_name in ("intent_id", "course_id", "raw_request", "interpreted_goal"):
            if not str(getattr(self, field_name) or "").strip():
                raise ValueError(f"{field_name} is required")
        if self.blocking_questions and self.can_proceed_without_clarification:
            raise ValueError(
                "An intent with blocking questions cannot proceed without clarification"
            )
        return self


class ProposedOutlineNode(BaseModel):
    """A provisional node; the domain command allocates its final stable ID."""

    provisional_id: str
    title: str
    parent_ref: str = ""
    position: int | None = Field(default=None, ge=0)
    learning_focus: str = ""
    source_node_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class CourseStructureOperation(BaseModel):
    """Executable graph primitives created after flexible language interpretation."""

    operation_id: str
    operation_type: StructureOperationType
    base_blueprint_revision_id: str
    idempotency_key: str
    source_node_ids: list[str] = Field(default_factory=list)
    target_parent_id: str = ""
    target_position: int | None = Field(default=None, ge=0)
    proposed_nodes: list[ProposedOutlineNode] = Field(default_factory=list)
    depends_on_operation_ids: list[str] = Field(default_factory=list)
    reason: str
    assumptions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    requires_teacher_checkpoint: bool = True

    @model_validator(mode="after")
    def validate_operation_shape(self) -> CourseStructureOperation:
        if not self.operation_id or not self.base_blueprint_revision_id:
            raise ValueError("Structure operations require an ID and base blueprint revision")
        if not self.idempotency_key or not self.reason.strip():
            raise ValueError("Structure operations require an idempotency key and reason")
        self.depends_on_operation_ids = list(dict.fromkeys(
            str(value)
            for value in self.depends_on_operation_ids
            if str(value)
        ))
        if self.operation_id in self.depends_on_operation_ids:
            raise ValueError("Structure operations cannot depend on themselves")

        source_count = len(self.source_node_ids)
        proposed_count = len(self.proposed_nodes)
        if self.operation_type == "INSERT_OUTLINE_NODE" and proposed_count < 1:
            raise ValueError("Insert requires at least one proposed node")
        if self.operation_type in {
            "UPDATE_OUTLINE_NODE",
            "MOVE_OUTLINE_NODE",
            "RETIRE_OUTLINE_NODE",
        } and source_count != 1:
            raise ValueError(f"{self.operation_type} requires exactly one source node")
        if self.operation_type == "REORDER_OUTLINE_NODES" and source_count < 2:
            raise ValueError("Reorder requires at least two source nodes")
        if self.operation_type == "SPLIT_OUTLINE_NODE":
            if source_count != 1 or proposed_count < 2:
                raise ValueError("Split requires one source node and at least two proposed nodes")
        if self.operation_type == "MERGE_OUTLINE_NODES":
            if source_count < 2 or proposed_count != 1:
                raise ValueError("Merge requires at least two sources and one proposed node")
        if self.operation_type == "REBUILD_OUTLINE" and proposed_count < 1:
            raise ValueError("Outline rebuild requires a proposed structure")
        return self


class CourseUnitMigration(BaseModel):
    """One unit-level reuse, rewrite, regeneration or retirement decision."""

    migration_id: str
    asset_type: str
    unit_type: str
    source_unit_ids: list[str] = Field(default_factory=list)
    target_unit_ids: list[str] = Field(default_factory=list)
    disposition: MigrationDisposition
    reason: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    dependency_ids: list[str] = Field(default_factory=list)
    base_revisions: dict[str, str] = Field(default_factory=dict)
    protected_by: list[str] = Field(default_factory=list)
    protection_override_reason: str = ""
    requires_review: bool = False
    candidate_status: CandidateStatus = "not_started"
    candidate_instruction: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_migration_shape(self) -> CourseUnitMigration:
        if not self.migration_id or not self.asset_type.strip() or not self.unit_type.strip():
            raise ValueError("Migration ID, asset type and unit type are required")
        if not self.reason.strip():
            raise ValueError("Every migration decision requires an explainable reason")
        if self.disposition in {"reuse_exact", "reuse_rebind", "rewrite_partial"}:
            if not self.source_unit_ids or not self.target_unit_ids:
                raise ValueError(f"{self.disposition} requires source and target units")
        if self.disposition == "regenerate" and not self.target_unit_ids:
            raise ValueError("Regeneration requires at least one target unit")
        if self.disposition == "retire" and not self.source_unit_ids:
            raise ValueError("Retirement requires at least one source unit")
        if self.disposition == "blocked":
            self.requires_review = True
        if self.disposition in {"reuse_exact", "reuse_rebind", "retire"}:
            if self.candidate_status == "not_started":
                self.candidate_status = "not_required"
        return self


class CourseChangeScenario(BaseModel):
    """Advisory coverage case, never a prerequisite selected by the teacher."""

    scenario_id: str
    name: str
    examples: list[str]
    suggested_strategies: list[ExecutionStrategy]
    typical_dispositions: list[MigrationDisposition]
    escalate_when: list[str] = Field(default_factory=list)
    advisory_only: Literal[True] = True


class CourseChangeScenarioMatrix(BaseModel):
    schema_version: Literal["course_change_scenario_matrix_v1"] = (
        COURSE_CHANGE_SCENARIO_MATRIX_SCHEMA
    )
    scenarios: list[CourseChangeScenario]
    routing_principle: str = (
        "Teacher language remains open-ended; scenarios guide coverage and testing, "
        "while evidence and the current course determine execution."
    )


def course_change_scenario_matrix() -> CourseChangeScenarioMatrix:
    """Return the V1 coverage matrix used by design review and tests."""

    return CourseChangeScenarioMatrix(scenarios=[
        CourseChangeScenario(
            scenario_id="exact_reference_update",
            name="精确术语、版本或实体更新",
            examples=["将 DeepSeek V3 更新为 V4", "替换已经更名的工具"],
            suggested_strategies=["semantic_impact"],
            typical_dispositions=["rewrite_partial", "regenerate", "reuse_exact"],
            escalate_when=["版本变化同时改变课程目标、章节或课时"],
        ),
        CourseChangeScenario(
            scenario_id="knowledge_or_policy_update",
            name="知识事实、政策或来源更新",
            examples=["按新政策修订全课", "纠正一个核心概念"],
            suggested_strategies=["semantic_impact"],
            typical_dispositions=["rewrite_partial", "regenerate", "blocked"],
            escalate_when=["新事实缺少可信来源", "影响范围无法收敛"],
        ),
        CourseChangeScenario(
            scenario_id="teaching_goal_or_strategy",
            name="教学目标、难度、受众或教学策略变化",
            examples=["更强调项目实践", "改为面向高职学生"],
            suggested_strategies=["semantic_impact"],
            typical_dispositions=["reuse_rebind", "rewrite_partial", "regenerate"],
            escalate_when=["目标变化要求重排章节或重新分配课时"],
        ),
        CourseChangeScenario(
            scenario_id="assessment_change",
            name="考核、题库或评分标准变化",
            examples=["增加实践考核", "删除超纲题目"],
            suggested_strategies=["semantic_impact"],
            typical_dispositions=["reuse_rebind", "rewrite_partial", "retire", "regenerate"],
            escalate_when=["新的评价结构改变课程目标或章节组织"],
        ),
        CourseChangeScenario(
            scenario_id="rename_move_reorder",
            name="节点重命名、移动或排序",
            examples=["把第三章移动到第一章之后", "调整章节顺序"],
            suggested_strategies=["structural_regeneration"],
            typical_dispositions=["reuse_exact", "reuse_rebind", "rewrite_partial"],
            escalate_when=["顺序改变破坏先修关系或教学叙事"],
        ),
        CourseChangeScenario(
            scenario_id="insert_or_retire",
            name="新增或退休章节",
            examples=["新增一章 Agent 实践", "删除已经过时的章节"],
            suggested_strategies=["structural_regeneration"],
            typical_dispositions=["regenerate", "retire", "rewrite_partial", "blocked"],
            escalate_when=["删除对象仍被其他正式资产依赖"],
        ),
        CourseChangeScenario(
            scenario_id="split_or_merge",
            name="章节拆分或合并",
            examples=["把第三章拆成基础与实战两章", "合并重复章节"],
            suggested_strategies=["structural_regeneration", "semantic_impact"],
            typical_dispositions=["reuse_rebind", "rewrite_partial", "regenerate", "retire"],
            escalate_when=["旧资产无法可靠归属到新节点", "合并后知识或目标冲突"],
        ),
        CourseChangeScenario(
            scenario_id="whole_course_restructure",
            name="整课结构重构",
            examples=["从知识章节改为项目任务组织", "重新设计整门课"],
            suggested_strategies=["structural_regeneration", "semantic_impact"],
            typical_dispositions=["reuse_rebind", "rewrite_partial", "regenerate", "retire", "blocked"],
            escalate_when=["保护要求与新结构冲突", "新结构未通过课时或覆盖检查"],
        ),
        CourseChangeScenario(
            scenario_id="ambiguous_or_evolving_request",
            name="表达模糊、变化中或混合需求",
            examples=["这部分重新整理一下", "感觉课程太散了，帮我改好"],
            suggested_strategies=["semantic_impact"],
            typical_dispositions=["blocked", "rewrite_partial", "regenerate"],
            escalate_when=["AI 发现结构信号", "安全假设不足以继续", "老师补充了新目标"],
        ),
    ])


def derive_execution_strategies(
    intent: CourseChangeIntent,
    structural_operations: list[CourseStructureOperation] | None = None,
) -> tuple[list[ExecutionStrategy], StrategyStatus]:
    """Resolve current execution order from evidence, never raw-word matching."""

    operations = structural_operations or []
    kinds = {signal.kind for signal in intent.signals}
    needs_structure = bool(operations or kinds.intersection({"structural", "mixed"}))
    needs_semantic = bool(kinds.intersection({"semantic", "mixed"}))

    strategies: list[ExecutionStrategy] = []
    if needs_structure:
        strategies.append("structural_regeneration")
    if needs_semantic:
        strategies.append("semantic_impact")
    if not strategies:
        # Begin with the cheaper discovery loop, but keep the route provisional:
        # a later structure signal can replan the same request without changing
        # what the teacher originally said.
        return ["semantic_impact"], "provisional"
    return strategies, "resolved"


class CourseChangePlan(BaseModel):
    """A versioned candidate plan that can be superseded as understanding improves."""

    schema_version: Literal["course_change_plan_v1"] = COURSE_CHANGE_PLAN_SCHEMA
    scenario_matrix_version: Literal["course_change_scenario_matrix_v1"] = (
        COURSE_CHANGE_SCENARIO_MATRIX_SCHEMA
    )
    plan_id: str
    course_id: str
    intent: CourseChangeIntent
    base_revision_vector: dict[str, str] = Field(default_factory=dict)
    execution_strategies: list[ExecutionStrategy] = Field(default_factory=list)
    strategy_status: StrategyStatus = "provisional"
    scenario_tags: list[str] = Field(default_factory=list)
    structural_operations: list[CourseStructureOperation] = Field(default_factory=list)
    unit_migrations: list[CourseUnitMigration] = Field(default_factory=list)
    structure_review_status: StructureReviewStatus = "not_required"
    status: PlanningStatus = "draft"
    supersedes_plan_id: str = ""
    replan_reasons: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def validate_plan(self) -> CourseChangePlan:
        if not self.plan_id or not self.course_id:
            raise ValueError("Plan ID and course ID are required")
        if self.intent.course_id != self.course_id:
            raise ValueError("Change plan and intent belong to different courses")
        strategies, strategy_status = derive_execution_strategies(
            self.intent,
            self.structural_operations,
        )
        # Callers may supply a resolved strategy list after additional analysis.
        # Structural work still runs first so downstream candidates target the
        # proposed graph rather than a graph that is about to disappear.
        supplied = list(dict.fromkeys(self.execution_strategies))
        merged = list(dict.fromkeys([*strategies, *supplied]))
        self.execution_strategies = sorted(
            merged,
            key=lambda value: 0 if value == "structural_regeneration" else 1,
        )
        if self.strategy_status == "provisional" and strategy_status == "resolved":
            self.strategy_status = "resolved"
        if self.structural_operations and self.structure_review_status == "not_required":
            self.structure_review_status = "pending"
        if self.status != "needs_clarification" and self.intent.blocking_questions:
            raise ValueError("Plans with blocking questions must remain needs_clarification")
        known_operation_ids = {
            item.operation_id for item in self.structural_operations
        }
        pending = {
            item.operation_id: set(item.depends_on_operation_ids)
            for item in self.structural_operations
        }
        if any(
            not dependencies.issubset(known_operation_ids)
            for dependencies in pending.values()
        ):
            raise ValueError(
                "Structure operation dependencies must belong to the same plan"
            )
        resolved: set[str] = set()
        while pending:
            ready = sorted(
                operation_id
                for operation_id, dependencies in pending.items()
                if dependencies.issubset(resolved)
            )
            if not ready:
                raise ValueError("Structure operation dependency graph contains a cycle")
            for operation_id in ready:
                pending.pop(operation_id)
                resolved.add(operation_id)
        return self


class CourseChangePlanValidation(BaseModel):
    phase: ValidationPhase
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    review_migration_ids: list[str] = Field(default_factory=list)


class CourseChangePlanSummary(BaseModel):
    """Compact projection for the workbench impact navigator and header."""

    execution_strategies: list[ExecutionStrategy]
    structural_operation_count: int
    total_migrations: int
    by_disposition: dict[str, int]
    by_asset_type: dict[str, dict[str, int]]
    review_required: int
    structure_review_status: StructureReviewStatus


def summarize_course_change_plan(plan: CourseChangePlan) -> CourseChangePlanSummary:
    by_disposition: dict[str, int] = {}
    by_asset_type: dict[str, dict[str, int]] = {}
    review_required = 0
    for migration in plan.unit_migrations:
        by_disposition[migration.disposition] = (
            by_disposition.get(migration.disposition, 0) + 1
        )
        asset_counts = by_asset_type.setdefault(migration.asset_type, {})
        asset_counts[migration.disposition] = asset_counts.get(migration.disposition, 0) + 1
        if migration.requires_review or migration.disposition == "blocked":
            review_required += 1
    return CourseChangePlanSummary(
        execution_strategies=list(plan.execution_strategies),
        structural_operation_count=len(plan.structural_operations),
        total_migrations=len(plan.unit_migrations),
        by_disposition=by_disposition,
        by_asset_type=by_asset_type,
        review_required=review_required,
        structure_review_status=plan.structure_review_status,
    )


def validate_course_change_plan(
    plan: CourseChangePlan,
    *,
    phase: ValidationPhase,
) -> CourseChangePlanValidation:
    """Validate only hard execution safety; interpretation remains revisable."""

    errors: list[str] = []
    warnings: list[str] = []
    review_ids: list[str] = []

    if not plan.base_revision_vector:
        errors.append("The plan is not pinned to a base course revision")
    if plan.intent.blocking_questions:
        errors.append("The teacher intent still has blocking questions")
    if not plan.structural_operations and not plan.unit_migrations:
        errors.append("The plan contains no executable change or migration decision")

    operation_ids = [item.operation_id for item in plan.structural_operations]
    migration_ids = [item.migration_id for item in plan.unit_migrations]
    if len(operation_ids) != len(set(operation_ids)):
        errors.append("Structure operation IDs must be unique")
    if len(migration_ids) != len(set(migration_ids)):
        errors.append("Migration IDs must be unique")

    if phase in {"downstream_generation", "publish"}:
        if plan.structural_operations and plan.structure_review_status != "confirmed":
            errors.append("Structural changes require teacher confirmation before downstream generation")

    for migration in plan.unit_migrations:
        if migration.requires_review or migration.disposition == "blocked":
            review_ids.append(migration.migration_id)
        if (
            migration.protected_by
            and migration.disposition in {"rewrite_partial", "regenerate", "retire"}
            and not migration.protection_override_reason.strip()
        ):
            errors.append(
                f"Migration {migration.migration_id} changes protected content without an override reason"
            )
        if phase == "publish":
            if migration.disposition == "blocked":
                errors.append(f"Migration {migration.migration_id} is still blocked")
            if (
                migration.disposition in {"rewrite_partial", "regenerate"}
                and migration.candidate_status != "ready"
            ):
                errors.append(f"Migration {migration.migration_id} has no ready candidate")
            if migration.candidate_status == "failed":
                errors.append(f"Migration {migration.migration_id} failed candidate generation")

    if plan.strategy_status == "provisional":
        warnings.append("Execution strategy is provisional and may expand after impact discovery")
    if review_ids:
        warnings.append("Some migration decisions still require teacher review")

    return CourseChangePlanValidation(
        phase=phase,
        passed=not errors,
        errors=errors,
        warnings=warnings,
        review_migration_ids=sorted(set(review_ids)),
    )


def replan_course_change(
    plan: CourseChangePlan,
    *,
    new_plan_id: str,
    reason: str,
    intent: CourseChangeIntent | None = None,
    structural_operations: list[CourseStructureOperation] | None = None,
    unit_migrations: list[CourseUnitMigration] | None = None,
    updated_at: str,
) -> CourseChangePlan:
    """Supersede a plan without losing the teacher's original request or history."""

    payload = deepcopy(plan.model_dump(mode="json"))
    payload.update({
        "plan_id": new_plan_id,
        "intent": (intent or plan.intent).model_dump(mode="json"),
        "structural_operations": [
            item.model_dump(mode="json")
            for item in (
                structural_operations
                if structural_operations is not None
                else plan.structural_operations
            )
        ],
        "unit_migrations": [
            item.model_dump(mode="json")
            for item in (
                unit_migrations if unit_migrations is not None else plan.unit_migrations
            )
        ],
        "execution_strategies": [],
        "strategy_status": "provisional",
        "structure_review_status": "not_required",
        "status": "draft",
        "supersedes_plan_id": plan.plan_id,
        "replan_reasons": [*plan.replan_reasons, reason],
        "updated_at": updated_at,
    })
    return CourseChangePlan.model_validate(payload)


__all__ = [
    "COURSE_CHANGE_INTENT_SCHEMA",
    "COURSE_CHANGE_PLAN_SCHEMA",
    "COURSE_CHANGE_SCENARIO_MATRIX_SCHEMA",
    "CourseChangeIntent",
    "CourseChangePlan",
    "CourseChangePlanSummary",
    "CourseChangePlanValidation",
    "CourseChangeScenarioMatrix",
    "CourseChangeSignal",
    "CourseStructureOperation",
    "CourseUnitMigration",
    "ProposedOutlineNode",
    "course_change_scenario_matrix",
    "derive_execution_strategies",
    "replan_course_change",
    "summarize_course_change_plan",
    "validate_course_change_plan",
]
