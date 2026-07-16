"""Same-source teaching representation registry and derivation graph."""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from course_document import CourseDocument, stable_hash
from course_revisions import CourseRevisionEvent, revision_vector_for_document

TEACHING_REPRESENTATION_REGISTRY_SCHEMA = "teaching_representation_registry_v1"

RepresentationType = Literal[
    "outline",
    "lesson_plan",
    "slide_deck",
    "handout",
    "practice_sheet",
    "diagram",
    "animation",
    "audio",
    "video",
    "interaction",
]
RepresentationStatus = Literal[
    "planned",
    "building",
    "ready",
    "stale",
    "failed",
    "archived",
]
DerivationNodeType = Literal["source", "spec", "representation", "artifact"]
DerivationNodeStatus = Literal["current", "stale", "removed", "failed", "archived"]
DependencyKind = Literal[
    "semantic_content",
    "structure_order",
    "learning_objective",
    "knowledge_reference",
    "practice_reference",
    "material_evidence",
    "visual_theme",
    "layout",
    "narration",
    "accessibility",
]


class RepresentationConflict(RuntimeError):
    pass


class SourceBinding(BaseModel):
    course_id: str
    section_id: str | None = None
    block_id: str | None = None
    span_anchor: dict[str, Any] | None = None
    knowledge_node_ids: list[str] = Field(default_factory=list)
    learning_objective_ids: list[str] = Field(default_factory=list)
    practice_task_ids: list[str] = Field(default_factory=list)
    material_evidence_ids: list[str] = Field(default_factory=list)
    source_revisions: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_revisions(self) -> SourceBinding:
        if not self.source_revisions:
            raise ValueError("Source binding must include at least one source revision")
        return self


class RepresentationPlan(BaseModel):
    plan_id: str
    course_id: str
    source_revision_vector: dict[str, str] = Field(default_factory=dict)
    target_scope: dict[str, Any] = Field(default_factory=dict)
    learning_objective_ids: list[str] = Field(default_factory=list)
    knowledge_refs: list[str] = Field(default_factory=list)
    practice_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    requested_representations: list[RepresentationType] = Field(default_factory=list)
    rejected_representations: list[dict[str, Any]] = Field(default_factory=list)
    pedagogical_reasons: list[str] = Field(default_factory=list)
    cost_class: Literal["low", "medium", "high"] = "low"
    accessibility_requirements: list[str] = Field(default_factory=list)
    quality_requirements: list[str] = Field(default_factory=list)
    fallback_chain: list[RepresentationType] = Field(default_factory=list)
    planner_version: str = "representation_planner_v1"
    status: Literal["draft", "ready", "superseded", "archived"] = "draft"


class TeachingRepresentation(BaseModel):
    representation_id: str
    course_id: str
    representation_type: RepresentationType
    source_bindings: list[SourceBinding]
    source_revision_vector: dict[str, str] = Field(default_factory=dict)
    spec_id: str
    artifact_ids: list[str] = Field(default_factory=list)
    semantic_fingerprint: str = ""
    render_fingerprint: str = ""
    quality_report_id: str = ""
    revision: str
    status: RepresentationStatus = "planned"
    stale_reasons: list[str] = Field(default_factory=list)
    stale_unit_ids: list[str] = Field(default_factory=list)
    fallback_representation_id: str | None = None
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def validate_bindings(self) -> TeachingRepresentation:
        if not self.source_bindings:
            raise ValueError("Teaching representation must have source bindings")
        if any(binding.course_id != self.course_id for binding in self.source_bindings):
            raise ValueError("Teaching representation bindings must belong to the same course")
        bound_revisions: dict[str, str] = {}
        for binding in self.source_bindings:
            for source_key, revision in binding.source_revisions.items():
                existing = bound_revisions.get(source_key)
                if existing is not None and existing != revision:
                    raise ValueError("Teaching representation bindings contain conflicting source revisions")
                bound_revisions[source_key] = revision
        if self.source_revision_vector and self.source_revision_vector != bound_revisions:
            raise ValueError("Teaching representation revision vector must match its source bindings")
        self.source_revision_vector = bound_revisions
        return self


class RepresentationSet(BaseModel):
    set_id: str
    course_id: str
    target_scope: dict[str, Any] = Field(default_factory=dict)
    default_representation_id: str
    alternative_representation_ids: list[str] = Field(default_factory=list)
    complementary_representation_ids: list[str] = Field(default_factory=list)
    accessibility_representation_ids: list[str] = Field(default_factory=list)
    fallback_chain: list[str] = Field(default_factory=list)
    selection_policy: dict[str, Any] = Field(default_factory=dict)
    revision: str


class TeachingRepresentationSpec(BaseModel):
    spec_id: str
    course_id: str
    representation_type: RepresentationType
    source_bindings: list[SourceBinding]
    unit_bindings: dict[str, list[SourceBinding]] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    revision: str
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def validate_bindings(self) -> TeachingRepresentationSpec:
        if not self.source_bindings:
            raise ValueError("Teaching representation spec must have source bindings")
        if any(binding.course_id != self.course_id for binding in self.source_bindings):
            raise ValueError("Teaching representation spec bindings must belong to the same course")
        for bindings in self.unit_bindings.values():
            if not bindings:
                raise ValueError("Teaching representation units must include source bindings")
            if any(binding.course_id != self.course_id for binding in bindings):
                raise ValueError("Teaching representation unit bindings must belong to the same course")
        return self


class DerivationNode(BaseModel):
    node_id: str
    node_type: DerivationNodeType
    object_id: str
    revision_or_fingerprint: str
    status: DerivationNodeStatus = "current"


class DerivationEdge(BaseModel):
    edge_id: str
    from_node_id: str
    to_node_id: str
    dependency_kind: DependencyKind = "semantic_content"
    dependency_scope: dict[str, Any] = Field(default_factory=dict)
    rebuild_policy: Literal["automatic", "on_demand", "manual"] = "automatic"


class AssetDerivationGraph(BaseModel):
    graph_id: str
    course_id: str
    nodes: list[DerivationNode] = Field(default_factory=list)
    edges: list[DerivationEdge] = Field(default_factory=list)
    graph_revision: str = ""


class TeachingRepresentationRegistry(BaseModel):
    schema_version: Literal["teaching_representation_registry_v1"] = (
        TEACHING_REPRESENTATION_REGISTRY_SCHEMA
    )
    course_id: str
    registry_revision: str = ""
    plans: list[RepresentationPlan] = Field(default_factory=list)
    specs: list[TeachingRepresentationSpec] = Field(default_factory=list)
    representations: list[TeachingRepresentation] = Field(default_factory=list)
    representation_sets: list[RepresentationSet] = Field(default_factory=list)
    derivation_graph: AssetDerivationGraph
    applied_revision_event_ids: list[str] = Field(default_factory=list)
    updated_at: str


def source_binding_for_document(
    document: CourseDocument | dict[str, Any],
    *,
    section_id: str | None = None,
    block_id: str | None = None,
    span_anchor: dict[str, Any] | None = None,
    knowledge_node_ids: list[str] | None = None,
    learning_objective_ids: list[str] | None = None,
    practice_task_ids: list[str] | None = None,
    material_evidence_ids: list[str] | None = None,
) -> SourceBinding:
    item = document if isinstance(document, CourseDocument) else CourseDocument.model_validate(document)
    vector = revision_vector_for_document(item).revisions
    selected: dict[str, str] = {}
    if block_id:
        key = f"block:{block_id}"
        if key not in vector:
            raise RepresentationConflict("Course block source does not exist")
        selected[key] = vector[key]
    elif section_id:
        key = f"section:{section_id}"
        if key not in vector:
            raise RepresentationConflict("Course section source does not exist")
        selected[key] = vector[key]
    else:
        selected["course_document"] = vector["course_document"]

    for objective_id in learning_objective_ids or []:
        key = f"objective:{objective_id}"
        if key in vector:
            selected[key] = vector[key]

    return SourceBinding(
        course_id=item.course_id,
        section_id=section_id,
        block_id=block_id,
        span_anchor=deepcopy(span_anchor),
        knowledge_node_ids=list(knowledge_node_ids or []),
        learning_objective_ids=list(learning_objective_ids or []),
        practice_task_ids=list(practice_task_ids or []),
        material_evidence_ids=list(material_evidence_ids or []),
        source_revisions=selected,
    )


class TeachingRepresentationRepository:
    """Course-isolated atomic registry with deterministic stale propagation."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        if root_dir is None:
            from storage import DATA_DIR

            root_dir = Path(DATA_DIR) / "teaching_representations"
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def load(self, course_id: str) -> TeachingRepresentationRegistry:
        path = self._path(course_id)
        if not path.exists():
            return self._empty_registry(course_id)
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        registry = TeachingRepresentationRegistry.model_validate(value)
        if registry.course_id != course_id:
            raise RepresentationConflict("Teaching representation registry belongs to another course")
        return registry

    def save(self, registry: TeachingRepresentationRegistry) -> TeachingRepresentationRegistry:
        with self._lock(registry.course_id):
            refreshed = self._refresh_registry(registry)
            self._atomic_write(self._path(registry.course_id), refreshed.model_dump(mode="json"))
            return refreshed

    def register_plan(self, plan: RepresentationPlan) -> TeachingRepresentationRegistry:
        with self._lock(plan.course_id):
            registry = self.load(plan.course_id)
            registry.plans = [item for item in registry.plans if item.plan_id != plan.plan_id]
            registry.plans.append(plan)
            return self.save(registry)

    def register_spec(self, spec: TeachingRepresentationSpec) -> TeachingRepresentationRegistry:
        with self._lock(spec.course_id):
            registry = self.load(spec.course_id)
            registry.specs = [item for item in registry.specs if item.spec_id != spec.spec_id]
            registry.specs.append(spec)
            spec_node_id = f"spec::{spec.spec_id}"
            unit_prefix = f"spec-unit::{spec.spec_id}::"
            graph = registry.derivation_graph
            graph.nodes = [
                node for node in graph.nodes
                if node.node_id != spec_node_id and not node.node_id.startswith(unit_prefix)
            ]
            graph.nodes.append(DerivationNode(
                node_id=spec_node_id,
                node_type="spec",
                object_id=spec.spec_id,
                revision_or_fingerprint=spec.revision,
            ))
            graph.edges = [
                edge for edge in graph.edges
                if edge.to_node_id != spec_node_id
                and not edge.from_node_id.startswith(unit_prefix)
                and not edge.to_node_id.startswith(unit_prefix)
            ]
            units = spec.unit_bindings or {"__whole__": spec.source_bindings}
            for unit_id, bindings in units.items():
                unit_node_id = f"{unit_prefix}{unit_id}"
                graph.nodes.append(DerivationNode(
                    node_id=unit_node_id,
                    node_type="spec",
                    object_id=f"{spec.spec_id}:{unit_id}",
                    revision_or_fingerprint=stable_hash({
                        "spec_revision": spec.revision,
                        "unit_id": unit_id,
                    }, prefix="tur_"),
                ))
                graph.edges.append(DerivationEdge(
                    edge_id=stable_hash({
                        "course_id": spec.course_id,
                        "source": unit_node_id,
                        "target": spec_node_id,
                    }, prefix="dre_"),
                    from_node_id=unit_node_id,
                    to_node_id=spec_node_id,
                    dependency_scope={"unit_id": unit_id},
                ))
                for binding in bindings:
                    for source_key, revision in binding.source_revisions.items():
                        source_node_id = f"source::{source_key}"
                        source_node = next(
                            (node for node in graph.nodes if node.node_id == source_node_id),
                            None,
                        )
                        if source_node is None:
                            source_node = DerivationNode(
                                node_id=source_node_id,
                                node_type="source",
                                object_id=source_key,
                                revision_or_fingerprint=revision,
                            )
                            graph.nodes.append(source_node)
                        else:
                            source_node.revision_or_fingerprint = revision
                            source_node.status = "current"
                        graph.edges.append(DerivationEdge(
                            edge_id=stable_hash({
                                "course_id": spec.course_id,
                                "source": source_node_id,
                                "target": unit_node_id,
                            }, prefix="dre_"),
                            from_node_id=source_node_id,
                            to_node_id=unit_node_id,
                            dependency_scope={
                                "unit_id": unit_id,
                                "section_id": binding.section_id,
                                "block_id": binding.block_id,
                            },
                        ))
            return self.save(registry)

    def register_representation(
        self,
        representation: TeachingRepresentation,
        *,
        dependency_kind: DependencyKind = "semantic_content",
        rebuild_policy: Literal["automatic", "on_demand", "manual"] = "automatic",
    ) -> TeachingRepresentationRegistry:
        with self._lock(representation.course_id):
            registry = self.load(representation.course_id)
            registry.representations = [
                item
                for item in registry.representations
                if item.representation_id != representation.representation_id
            ]
            registry.representations.append(representation)
            self._bind_representation(
                registry.derivation_graph,
                representation,
                dependency_kind=dependency_kind,
                rebuild_policy=rebuild_policy,
            )
            return self.save(registry)

    def apply_revision_event(
        self,
        course_id: str,
        event: CourseRevisionEvent | dict[str, Any],
    ) -> TeachingRepresentationRegistry:
        item = event if isinstance(event, CourseRevisionEvent) else CourseRevisionEvent.model_validate(event)
        if item.course_id != course_id:
            raise RepresentationConflict("Course revision event belongs to another course")

        with self._lock(course_id):
            registry = self.load(course_id)
            if item.event_id in registry.applied_revision_event_ids:
                return registry

            changed_keys = set(item.changed_source_keys) | set(item.removed_source_keys)
            graph = registry.derivation_graph
            source_nodes = {node.object_id: node for node in graph.nodes if node.node_type == "source"}
            for source_key, revision in item.current.revisions.items():
                node = source_nodes.get(source_key)
                if node:
                    node.revision_or_fingerprint = revision
                    node.status = "current"
            for source_key in item.removed_source_keys:
                node = source_nodes.get(source_key)
                if node:
                    node.status = "removed"

            downstream_node_ids = self._downstream_node_ids(graph, changed_keys)
            stale_representation_ids = {
                node.object_id
                for node in graph.nodes
                if node.node_id in downstream_node_ids and node.node_type == "representation"
            }
            removed = set(item.removed_source_keys)
            for representation in registry.representations:
                if representation.representation_id not in stale_representation_ids:
                    continue
                representation.status = "stale"
                reasons = [
                    f"source_removed:{key}" if key in removed else f"source_revision_changed:{key}"
                    for key in sorted(changed_keys)
                    if self._representation_depends_on(graph, representation.representation_id, key)
                ]
                for reason in reasons:
                    if reason not in representation.stale_reasons:
                        representation.stale_reasons.append(reason)
                spec = next(
                    (value for value in registry.specs if value.spec_id == representation.spec_id),
                    None,
                )
                if spec:
                    affected_units = [
                        unit_id
                        for unit_id, bindings in spec.unit_bindings.items()
                        if any(
                            changed_keys.intersection(binding.source_revisions)
                            for binding in bindings
                        )
                    ]
                    representation.stale_unit_ids = sorted(set(
                        representation.stale_unit_ids + affected_units
                    ))
                representation.updated_at = item.created_at

            for node in graph.nodes:
                if node.node_id in downstream_node_ids and node.node_type != "source":
                    node.status = "stale"

            registry.applied_revision_event_ids.append(item.event_id)
            registry.applied_revision_event_ids = registry.applied_revision_event_ids[-500:]
            return self.save(registry)

    def reconcile_course_operation_log(
        self,
        course_id: str,
        operation_log: list[dict[str, Any]],
    ) -> TeachingRepresentationRegistry:
        registry = self.load(course_id)
        for entry in operation_log:
            receipt = entry.get("receipt") if isinstance(entry, dict) else None
            event = receipt.get("revision_change") if isinstance(receipt, dict) else None
            if event:
                registry = self.apply_revision_event(course_id, event)
        return registry

    @staticmethod
    def _bind_representation(
        graph: AssetDerivationGraph,
        representation: TeachingRepresentation,
        *,
        dependency_kind: DependencyKind,
        rebuild_policy: Literal["automatic", "on_demand", "manual"],
    ) -> None:
        representation_node_id = f"representation::{representation.representation_id}"
        graph.nodes = [
            node
            for node in graph.nodes
            if not (node.node_type == "representation" and node.object_id == representation.representation_id)
        ]
        graph.nodes.append(DerivationNode(
            node_id=representation_node_id,
            node_type="representation",
            object_id=representation.representation_id,
            revision_or_fingerprint=representation.revision,
            status={
                "stale": "stale",
                "failed": "failed",
                "archived": "archived",
            }.get(representation.status, "current"),
        ))
        graph.edges = [edge for edge in graph.edges if edge.to_node_id != representation_node_id]

        spec_node_id = f"spec::{representation.spec_id}"
        if any(node.node_id == spec_node_id for node in graph.nodes):
            graph.edges.append(DerivationEdge(
                edge_id=stable_hash({
                    "course_id": representation.course_id,
                    "source": spec_node_id,
                    "target": representation_node_id,
                }, prefix="dre_"),
                from_node_id=spec_node_id,
                to_node_id=representation_node_id,
                dependency_kind=dependency_kind,
                rebuild_policy=rebuild_policy,
            ))

        nodes_by_id = {node.node_id: node for node in graph.nodes}
        for binding in representation.source_bindings:
            for source_key, revision in binding.source_revisions.items():
                source_node_id = f"source::{source_key}"
                if source_node_id not in nodes_by_id:
                    source_node = DerivationNode(
                        node_id=source_node_id,
                        node_type="source",
                        object_id=source_key,
                        revision_or_fingerprint=revision,
                    )
                    graph.nodes.append(source_node)
                    nodes_by_id[source_node_id] = source_node
                edge_payload = {
                    "course_id": representation.course_id,
                    "source": source_node_id,
                    "target": representation_node_id,
                    "dependency_kind": dependency_kind,
                }
                graph.edges.append(DerivationEdge(
                    edge_id=stable_hash(edge_payload, prefix="dre_"),
                    from_node_id=source_node_id,
                    to_node_id=representation_node_id,
                    dependency_kind=dependency_kind,
                    dependency_scope={
                        "section_id": binding.section_id,
                        "block_id": binding.block_id,
                    },
                    rebuild_policy=rebuild_policy,
                ))

    @staticmethod
    def _downstream_node_ids(
        graph: AssetDerivationGraph,
        changed_source_keys: set[str],
    ) -> set[str]:
        start_nodes = {f"source::{key}" for key in changed_source_keys}
        adjacency: dict[str, list[str]] = {}
        for edge in graph.edges:
            adjacency.setdefault(edge.from_node_id, []).append(edge.to_node_id)
        queue = list(start_nodes)
        visited = set(queue)
        while queue:
            current = queue.pop(0)
            for target in adjacency.get(current, []):
                if target not in visited:
                    visited.add(target)
                    queue.append(target)
        return visited

    @staticmethod
    def _representation_depends_on(
        graph: AssetDerivationGraph,
        representation_id: str,
        source_key: str,
    ) -> bool:
        source_node_id = f"source::{source_key}"
        target_node_id = f"representation::{representation_id}"
        adjacency: dict[str, list[str]] = {}
        for edge in graph.edges:
            adjacency.setdefault(edge.from_node_id, []).append(edge.to_node_id)
        queue = [source_node_id]
        visited = set(queue)
        while queue:
            current = queue.pop(0)
            if current == target_node_id:
                return True
            for target in adjacency.get(current, []):
                if target not in visited:
                    visited.add(target)
                    queue.append(target)
        return False

    def _empty_registry(self, course_id: str) -> TeachingRepresentationRegistry:
        now = datetime.now(timezone.utc).isoformat()
        return self._refresh_registry(TeachingRepresentationRegistry(
            course_id=course_id,
            derivation_graph=AssetDerivationGraph(
                graph_id=stable_hash({"course_id": course_id}, prefix="adg_"),
                course_id=course_id,
            ),
            updated_at=now,
        ))

    @staticmethod
    def _refresh_registry(
        registry: TeachingRepresentationRegistry,
    ) -> TeachingRepresentationRegistry:
        graph_payload = registry.derivation_graph.model_dump(mode="json", exclude={"graph_revision"})
        registry.derivation_graph.graph_revision = stable_hash(graph_payload, prefix="dgr_")
        registry.updated_at = datetime.now(timezone.utc).isoformat()
        payload = registry.model_dump(mode="json", exclude={"registry_revision", "updated_at"})
        registry.registry_revision = stable_hash(payload, prefix="trr_")
        return registry

    def _path(self, course_id: str) -> Path:
        file_id = stable_hash({"course_id": course_id}, prefix="course_")
        return self.root_dir / f"{file_id}.json"

    def _lock(self, course_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(course_id, threading.RLock())

    @staticmethod
    def _atomic_write(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()


teaching_representation_repository = TeachingRepresentationRepository()
