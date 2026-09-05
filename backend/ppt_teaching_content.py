"""Source-bound teaching expressions embedded in the existing PPT manuscript.

This module owns meaning, never layout. Offsets are Python character offsets,
end-exclusive, into the exact frozen note text (not rendered Markdown).
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceRange(Contract):
    block_id: str = Field(min_length=1)
    block_revision: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("source_range_invalid")
        return self


class ScreenElement(Contract):
    element_id: str = Field(min_length=1, max_length=100)
    kind: Literal["text", "formula", "code", "quote", "data", "image"] = "text"
    text: str = Field(min_length=1, max_length=8000)
    role: Literal["label", "condition", "evidence", "question", "answer", "claim"] = "evidence"
    sources: list[SourceRange] = Field(min_length=1, max_length=30)
    exact: bool = False
    subject_id: str = ""
    dimension_id: str = ""
    asset_id: str = ""
    asset_digest: str = ""
    answers_question_id: str = ""

    @field_validator("role", mode="before")
    @classmethod
    def canonical_role(cls, value):
        # Both names denote the same teaching role; no visible text is changed.
        return "claim" if value == "conclusion" else value


class ComparisonSubject(Contract):
    subject_id: str = Field(min_length=1)
    label_element_id: str = Field(min_length=1)


class ComparisonDimension(Contract):
    dimension_id: str = Field(min_length=1)
    label_element_id: str = Field(min_length=1)


class ComparisonCell(Contract):
    subject_id: str
    dimension_id: str
    element_ids: list[str] = Field(min_length=1, max_length=4)


class ComparisonExpression(Contract):
    kind: Literal["comparison"] = "comparison"
    subjects: list[ComparisonSubject] = Field(min_length=2, max_length=4)
    dimensions: list[ComparisonDimension] = Field(min_length=1, max_length=6)
    cells: list[ComparisonCell] = Field(max_length=24)
    condition_element_ids: list[str] = Field(min_length=1)
    prompt_element_ids: list[str] = Field(default_factory=list, max_length=1)
    conclusion_element_ids: list[str] = Field(default_factory=list)
    scale: Literal["not_quantitative", "shared"] = "not_quantitative"
    scale_unit: str = ""
    relations: list[Relation] = Field(default_factory=list, max_length=24)


class Relation(Contract):
    relation_id: str = Field(min_length=1)
    source_id: str
    target_id: str
    kind: Literal["sequence", "causal", "parent_child", "association", "supports", "prepares", "defines", "contains", "causes", "contrasts", "equivalent", "condition", "transforms_to"]
    label: str = ""
    condition_element_ids: list[str] = Field(default_factory=list)
    sources: list[SourceRange] = Field(min_length=1)


class GraphExpression(Contract):
    kind: Literal["process", "causal", "hierarchy", "concept"]
    node_element_ids: list[str] = Field(min_length=2, max_length=12)
    relations: list[Relation] = Field(min_length=1, max_length=24)
    condition_element_ids: list[str] = Field(default_factory=list)
    conclusion_element_ids: list[str] = Field(default_factory=list)


class LinearExpression(Contract):
    kind: Literal["problem", "derivation", "exercise", "recap", "cover", "agenda", "evidence"]
    ordered_element_ids: list[str] = Field(min_length=1, max_length=12)


Expression = Annotated[ComparisonExpression | GraphExpression | LinearExpression, Field(discriminator="kind")]


class RevealState(Contract):
    state_id: str = Field(min_length=1, max_length=100)
    visible_element_ids: list[str] = Field(min_length=1)
    emphasized_element_ids: list[str] = Field(default_factory=list)
    teaching_note: str = Field(min_length=1, max_length=500)


class SourceDisposition(Contract):
    block_id: str
    purpose: Literal["screen", "notes"]
    element_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=500)


class AdoptedAssetBinding(Contract):
    asset_id: str
    sha256: str
    course_id: str
    representation_id: str
    representation_revision: str
    expression_digest: str
    source_block_id: str


class AdoptedDiagramBinding(Contract):
    representation_id: str
    representation_revision: str
    expression_digest: str
    source_block_id: str
    unit_id: str
    semantic_digest: str


class PageTeachingV2(Contract):
    schema_version: Literal["page_teaching_v2"] = "page_teaching_v2"
    elements: list[ScreenElement] = Field(min_length=1, max_length=80)
    expression: Expression
    must_show: list[str] = Field(min_length=1)
    source_dispositions: list[SourceDisposition] = Field(min_length=1)
    states: list[RevealState] = Field(min_length=1, max_length=12)
    adopted_assets: list[AdoptedAssetBinding] = Field(default_factory=list)
    adopted_diagram: AdoptedDiagramBinding | None = None

    @model_validator(mode="after")
    def references_and_meaning(self):
        elements = {e.element_id: e for e in self.elements}
        ids = set(elements)

        def unique(values, code):
            if len(values) != len(set(values)):
                raise ValueError(code)

        def known(values):
            unique(values, "element_reference_duplicate")
            if not set(values) <= ids:
                raise ValueError("element_reference_unknown")

        unique([e.element_id for e in self.elements], "element_id_duplicate")
        unique([s.state_id for s in self.states], "state_id_duplicate")
        unique([s.block_id for s in self.source_dispositions], "source_disposition_duplicate")
        known(self.must_show)
        ever_visible = set()
        for state in self.states:
            known(state.visible_element_ids)
            known(state.emphasized_element_ids)
            if not set(state.emphasized_element_ids) <= set(state.visible_element_ids):
                raise ValueError("emphasis_element_hidden")
            ever_visible.update(state.visible_element_ids)
        if ever_visible != ids or not set(self.must_show) <= ever_visible:
            raise ValueError("screen_element_never_visible")
        for disposition in self.source_dispositions:
            known(disposition.element_ids)
            if (disposition.purpose == "screen") != bool(disposition.element_ids):
                raise ValueError("source_disposition_invalid")
            for element_id in disposition.element_ids:
                if disposition.block_id not in {s.block_id for s in elements[element_id].sources}:
                    raise ValueError("source_disposition_binding_mismatch")
        disposed = {element_id for d in self.source_dispositions for element_id in d.element_ids}
        if disposed != ids:
            raise ValueError("screen_source_disposition_incomplete")
        for element in self.elements:
            if element.kind == "image" and not (element.asset_id and element.asset_digest):
                raise ValueError("image_identity_missing")
        expression = self.expression
        if isinstance(expression, ComparisonExpression):
            subjects = [s.subject_id for s in expression.subjects]
            dimensions = [d.dimension_id for d in expression.dimensions]
            unique(subjects, "comparison_subject_duplicate")
            unique(dimensions, "comparison_dimension_duplicate")
            for subject in expression.subjects:
                known([subject.label_element_id])
                if elements[subject.label_element_id].subject_id != subject.subject_id:
                    raise ValueError("comparison_subject_binding_mismatch")
            for dimension in expression.dimensions:
                known([dimension.label_element_id])
                if elements[dimension.label_element_id].dimension_id != dimension.dimension_id:
                    raise ValueError("comparison_dimension_binding_mismatch")
            keys = [(c.subject_id, c.dimension_id) for c in expression.cells]
            unique(keys, "comparison_cell_duplicate")
            if set(keys) != {(s, d) for s in subjects for d in dimensions}:
                raise ValueError("comparison_matrix_incomplete")
            assigned = []
            for cell in expression.cells:
                known(cell.element_ids)
                assigned.extend(cell.element_ids)
                for element_id in cell.element_ids:
                    element = elements[element_id]
                    if (element.subject_id, element.dimension_id) != (cell.subject_id, cell.dimension_id):
                        raise ValueError("comparison_cell_identity_mismatch")
            unique(assigned, "comparison_cell_reused")
            known(expression.condition_element_ids)
            known(expression.prompt_element_ids)
            known(expression.conclusion_element_ids)
            for key in expression.condition_element_ids:
                if elements[key].subject_id or elements[key].role != "condition":
                    raise ValueError(f"comparison_common_condition_invalid:{key}: use role=condition and empty subject_id")
            for state in self.states:
                visible = set(state.visible_element_ids)
                if visible & set(assigned):
                    required = {*expression.condition_element_ids,
                                *(s.label_element_id for s in expression.subjects),
                                *(d.label_element_id for d in expression.dimensions)}
                    if not required <= visible:
                        raise ValueError(f"comparison_visible_context_incomplete:{state.state_id}: missing={sorted(required - visible)}")
            if expression.scale == "shared" and not expression.scale_unit.strip():
                raise ValueError("comparison_scale_unit_missing")
            unique([r.relation_id for r in expression.relations], "relation_id_duplicate")
            for relation in expression.relations:
                known([relation.source_id, relation.target_id])
                known(relation.condition_element_ids)
                if not {relation.source_id, relation.target_id} <= set(assigned):
                    raise ValueError(
                        f"comparison_relation_endpoint_invalid:{relation.relation_id}: "
                        f"{relation.source_id}->{relation.target_id}; allowed_cell_nodes={assigned}. "
                        "Comparison edges connect cell elements only, never shared conditions, subject or dimension labels. "
                        "Remove redundant edges already expressed by table alignment, or select a concept/process layout for a branching relationship."
                    )
                if elements[relation.source_id].subject_id != elements[relation.target_id].subject_id:
                    raise ValueError(f"comparison_relation_crosses_subjects:{relation.relation_id}: "
                                     f"{relation.source_id}->{relation.target_id}; use a graph layout for cross-subject edges")
        elif isinstance(expression, GraphExpression):
            known(expression.node_element_ids)
            known(expression.condition_element_ids)
            known(expression.conclusion_element_ids)
            nodes = set(expression.node_element_ids)
            unique([r.relation_id for r in expression.relations], "relation_id_duplicate")
            unique([(r.source_id, r.target_id, r.kind) for r in expression.relations], "relation_duplicate")
            expected = {"process": "sequence", "causal": "causal", "hierarchy": "parent_child"}.get(expression.kind)
            parents = {n: [] for n in nodes}
            for relation in expression.relations:
                if relation.source_id not in nodes or relation.target_id not in nodes or relation.source_id == relation.target_id:
                    raise ValueError(f"relation_endpoint_invalid:{relation.relation_id}: {relation.source_id}->{relation.target_id}; node_ids={sorted(nodes)}")
                if expected and relation.kind != expected:
                    raise ValueError("relation_kind_mismatch")
                known(relation.condition_element_ids)
                parents[relation.target_id].append(relation.source_id)
            if expression.kind == "hierarchy" and (sum(not p for p in parents.values()) != 1 or any(len(p) > 1 for p in parents.values())):
                raise ValueError("hierarchy_parent_invalid")
            if expression.kind in {"process", "hierarchy"}:
                remaining = set(nodes)
                while remaining:
                    ready = {n for n in remaining if not (set(parents[n]) & remaining)}
                    if not ready:
                        raise ValueError("relation_cycle_invalid")
                    remaining -= ready
        else:
            known(expression.ordered_element_ids)
        # The initial exercise view must be answer-free. A later state owns the
        # answer; invisible answers in notes are available to the teacher only.
        questions = {e.element_id for e in self.elements if e.role == "question"}
        answers = {e.element_id for e in self.elements if e.role == "answer"}
        if expression.kind in {"exercise", "problem"} or answers:
            if not questions:
                raise ValueError(f"question_element_missing: answer_ids={sorted(answers)}; "
                                 "include a visible role=question element before its answer. "
                                 "Comparison observations that do not answer a classroom question use role=evidence, not answer.")
            if answers:
                for answer_id in answers:
                    answer = elements[answer_id]
                    paired = answer.answers_question_id or (next(iter(questions)) if len(questions) == 1 else "")
                    if paired not in questions:
                        raise ValueError(f"answer_question_binding_missing:{answer_id}")
                    first_question = next(i for i, s in enumerate(self.states) if paired in s.visible_element_ids)
                    if any(answer_id in s.visible_element_ids for s in self.states[:first_question + 1]):
                        raise ValueError("answer_revealed_before_question")
                    if any(answer_id in s.visible_element_ids and paired not in s.visible_element_ids for s in self.states):
                        raise ValueError("answer_question_context_hidden")
        return self


def relation_is_directed(kind):
    return kind not in {"association", "contrasts", "equivalent"}


def validate_source_bindings(content: PageTeachingV2, notes: dict[str, tuple[str, str]]) -> None:
    """Validate against frozen full-text notes, not client supplied provenance."""
    if {d.block_id for d in content.source_dispositions} != set(notes):
        raise ValueError("source_disposition_coverage_incomplete")

    def validate_range(source, owner):
        if source.block_id not in notes:
            raise ValueError("source_block_unknown")
        revision, text = notes[source.block_id]
        if revision != source.block_revision:
            raise ValueError("source_revision_stale")
        if source.end > len(text) or text[source.start:source.end] != source.quote:
            raise ValueError(f"source_excerpt_mismatch:{owner}: quote must be a literal substring of source {source.block_id}")

    for element in content.elements:
        for source in element.sources:
            validate_range(source, element.element_id)
        if element.exact or element.kind in {"formula", "code", "quote", "data"}:
            if len(element.sources) != 1 or element.text != element.sources[0].quote:
                raise ValueError(f"selected_artifact_not_exact:{element.element_id}: selected {element.kind} text must exactly equal its single source quote")
    if isinstance(content.expression, (GraphExpression, ComparisonExpression)):
        for relation in content.expression.relations:
            for source in relation.sources:
                validate_range(source, relation.relation_id)


__all__ = ["PageTeachingV2", "ComparisonExpression", "GraphExpression", "validate_source_bindings"]
