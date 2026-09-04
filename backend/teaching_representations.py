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
from course_revisions import (
    CourseRevisionEvent,
    CourseRevisionVector,
    revision_vector_for_document,
)

TEACHING_REPRESENTATION_REGISTRY_SCHEMA = "teaching_representation_registry_v1"


def _teacher_script_animation_runtime_enabled() -> bool:
    return os.getenv("TEACHER_SCRIPT_ANIMATION_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

RepresentationType = Literal[
    "outline",
    "lesson_plan",
    "slide_deck",
    "handout",
    "practice_sheet",
    "diagram",
    "image",
    "animation",
    "audio",
    "video",
    "interaction",
]
RepresentationStatus = Literal[
    "candidate",
    "accepted",
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
    variant_key: str = ""
    source_bindings: list[SourceBinding]
    source_revision_vector: dict[str, str] = Field(default_factory=dict)
    spec_id: str
    artifact_ids: list[str] = Field(default_factory=list)
    semantic_fingerprint: str = ""
    render_fingerprint: str = ""
    quality_report_id: str = ""
    revision: str
    status: RepresentationStatus = "planned"
    rebuild_required: bool = False
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
    variant_key: str = ""
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
    section_reference_tombstones: list[dict[str, Any]] = Field(default_factory=list)
    structure_reference_rebinds: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: str


_STRUCTURE_SCALAR_REFERENCE_FIELDS = {
    "section_id",
    "lesson_unit_id",
    "parent_section_id",
    "target_section_id",
}
_STRUCTURE_LIST_REFERENCE_FIELDS = {
    "section_ids",
    "lesson_unit_ids",
    "target_section_ids",
}


def _rewrite_explicit_structure_references(
    value: Any,
    primary_by_source: dict[str, str],
    *,
    path: tuple[str | int, ...] = (),
) -> list[dict[str, Any]]:
    """Rewrite only typed identity fields and retain a reversible path journal."""

    mutations: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key in list(value):
            current = value[key]
            current_path = (*path, key)
            if key in {"source_revisions", "source_revision_vector"} and isinstance(current, dict):
                rebound: dict[str, Any] = {}
                for source_key, revision in current.items():
                    if source_key.startswith("section:"):
                        source_id = source_key.removeprefix("section:")
                        target_id = primary_by_source.get(source_id)
                        target_key = f"section:{target_id}" if target_id else source_key
                    else:
                        target_key = source_key
                    if target_key in rebound and rebound[target_key] != revision:
                        raise RepresentationConflict(
                            "Structure rebind would collapse conflicting source revisions"
                        )
                    rebound[target_key] = revision
                if rebound != current:
                    mutations.append({
                        "path": list(current_path),
                        "before": deepcopy(current),
                        "after": deepcopy(rebound),
                    })
                    value[key] = rebound
                continue
            if (
                key in _STRUCTURE_SCALAR_REFERENCE_FIELDS
                and isinstance(current, str)
                and primary_by_source.get(current)
                and primary_by_source[current] != current
            ):
                replacement = primary_by_source[current]
                mutations.append({
                    "path": list(current_path),
                    "before": current,
                    "after": replacement,
                })
                value[key] = replacement
                continue
            if key in _STRUCTURE_LIST_REFERENCE_FIELDS and isinstance(current, list):
                replacement = list(dict.fromkeys(
                    primary_by_source.get(str(item), str(item))
                    for item in current
                ))
                if replacement != current:
                    mutations.append({
                        "path": list(current_path),
                        "before": deepcopy(current),
                        "after": replacement,
                    })
                    value[key] = replacement
                continue
            mutations.extend(_rewrite_explicit_structure_references(
                value[key],
                primary_by_source,
                path=current_path,
            ))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            mutations.extend(_rewrite_explicit_structure_references(
                item,
                primary_by_source,
                path=(*path, index),
            ))
    return mutations


def _contains_explicit_structure_reference(
    value: Any,
    affected_section_ids: set[str],
) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                key in _STRUCTURE_SCALAR_REFERENCE_FIELDS
                and str(item or "") in affected_section_ids
            ):
                return True
            if (
                key in _STRUCTURE_LIST_REFERENCE_FIELDS
                and isinstance(item, list)
                and affected_section_ids.intersection(str(entry) for entry in item)
            ):
                return True
            if (
                key in {"source_revisions", "source_revision_vector"}
                and isinstance(item, dict)
                and affected_section_ids.intersection(
                    source_key.removeprefix("section:")
                    for source_key in item
                    if source_key.startswith("section:")
                )
            ):
                return True
            if _contains_explicit_structure_reference(item, affected_section_ids):
                return True
    elif isinstance(value, list):
        return any(
            _contains_explicit_structure_reference(item, affected_section_ids)
            for item in value
        )
    return False


def _value_at_path(value: Any, path: list[str | int]) -> Any:
    current = value
    for part in path:
        current = current[part]
    return current


def _set_value_at_path(value: Any, path: list[str | int], replacement: Any) -> None:
    current = value
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = deepcopy(replacement)


def _record_replacement(
    mutations: list[dict[str, Any]],
    value: dict[str, Any],
    *,
    path: list[str | int],
    field: str,
    replacement: Any,
) -> None:
    target = _value_at_path(value, path)
    before = deepcopy(target.get(field))
    if before == replacement:
        return
    target[field] = deepcopy(replacement)
    mutations.append({
        "path": [*path, field],
        "before": before,
        "after": deepcopy(replacement),
    })


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

    def load_payload(self, course_id: str) -> dict[str, Any]:
        """Load a read-only registry projection without validating every spec body."""

        path = self._path(course_id)
        if not path.exists():
            return self._empty_registry(course_id).model_dump(mode="json")
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        if value.get("course_id") != course_id:
            raise RepresentationConflict(
                "Teaching representation registry belongs to another course"
            )
        if value.get("schema_version") != TEACHING_REPRESENTATION_REGISTRY_SCHEMA:
            raise RepresentationConflict(
                "Teaching representation registry schema is unsupported"
            )
        return value

    def save(self, registry: TeachingRepresentationRegistry) -> TeachingRepresentationRegistry:
        with self._lock(registry.course_id):
            refreshed = self._refresh_registry(registry)
            self._atomic_write(self._path(registry.course_id), refreshed.model_dump(mode="json"))
            return refreshed

    def apply_structure_reference_rebind(
        self,
        course_id: str,
        *,
        operation_id: str,
        mapping_revision: str,
        reference_migrations: list[dict[str, Any]],
        section_tombstones: list[dict[str, Any]],
        affected_section_ids: list[str],
    ) -> dict[str, Any]:
        """Rebind explicit identities and stale a registry in one atomic write."""

        with self._lock(course_id):
            registry = self.load(course_id)
            existing = next(
                (
                    item
                    for item in registry.structure_reference_rebinds
                    if item.get("operation_id") == operation_id
                ),
                None,
            )
            if isinstance(existing, dict):
                if (
                    existing.get("status") == "applied"
                    and existing.get("mapping_revision") == mapping_revision
                ):
                    return {
                        "registry_revision": registry.registry_revision,
                        "record": deepcopy(existing),
                    }
                raise RepresentationConflict(
                    "Teaching representation structure rebind conflicts with history"
                )

            primary_by_source = {
                str(item.get("source_section_id") or ""): str(
                    item.get("primary_target_section_id") or ""
                )
                for item in reference_migrations
                if isinstance(item, dict) and item.get("source_section_id")
            }
            raw = registry.model_dump(mode="json")
            records = list(raw.pop("structure_reference_rebinds", []))
            previous_tombstones = deepcopy(
                raw.pop("section_reference_tombstones", [])
            )
            before_graph = deepcopy(raw.pop("derivation_graph"))
            before_graph.pop("graph_revision", None)
            affected = set(affected_section_ids)
            affected_indexes: dict[str, list[int]] = {}
            mutations: list[dict[str, Any]] = []
            for collection_name in (
                "plans",
                "specs",
                "representations",
                "representation_sets",
            ):
                for index, item in enumerate(raw.get(collection_name) or []):
                    if not _contains_explicit_structure_reference(item, affected):
                        continue
                    affected_indexes.setdefault(collection_name, []).append(index)
                    mutations.extend(_rewrite_explicit_structure_references(
                        item,
                        primary_by_source,
                        path=(collection_name, index),
                    ))
            affected_spec_ids_before = {
                str((raw.get("specs") or [])[index].get("spec_id") or "")
                for index in affected_indexes.get("specs", [])
            }
            representation_indexes = affected_indexes.setdefault(
                "representations",
                [],
            )
            for index, representation in enumerate(raw.get("representations") or []):
                if (
                    str(representation.get("spec_id") or "")
                    in affected_spec_ids_before
                    and index not in representation_indexes
                ):
                    representation_indexes.append(index)
            reason = f"structure_reference_rebound:{mapping_revision}"
            for index in affected_indexes.get("representations", []):
                representation = raw["representations"][index]
                path = ["representations", index]
                _record_replacement(
                    mutations,
                    raw,
                    path=path,
                    field="status",
                    replacement="stale",
                )
                _record_replacement(
                    mutations,
                    raw,
                    path=path,
                    field="rebuild_required",
                    replacement=True,
                )
                _record_replacement(
                    mutations,
                    raw,
                    path=path,
                    field="stale_reasons",
                    replacement=list(dict.fromkeys([
                        *list(representation.get("stale_reasons") or []),
                        reason,
                    ])),
                )
                _record_replacement(
                    mutations,
                    raw,
                    path=path,
                    field="stale_unit_ids",
                    replacement=list(dict.fromkeys([
                        *list(representation.get("stale_unit_ids") or []),
                        *[
                            section_id
                            for section_id in affected_section_ids
                            if _contains_explicit_structure_reference(
                                representation,
                                {section_id, primary_by_source.get(section_id, "")},
                            )
                        ],
                    ])),
                )

            raw["derivation_graph"] = before_graph
            rebound_registry = TeachingRepresentationRegistry.model_validate(raw)
            affected_spec_ids = {
                rebound_registry.specs[index].spec_id
                for index in affected_indexes.get("specs", [])
            }
            affected_representation_ids = {
                rebound_registry.representations[index].representation_id
                for index in affected_indexes.get("representations", [])
            }
            for spec in rebound_registry.specs:
                if spec.spec_id in affected_spec_ids:
                    self._bind_spec(rebound_registry.derivation_graph, spec)
            for representation in rebound_registry.representations:
                if representation.representation_id not in affected_representation_ids:
                    continue
                old_edge = next(
                    (
                        item
                        for item in registry.derivation_graph.edges
                        if item.to_node_id
                        == f"representation::{representation.representation_id}"
                    ),
                    None,
                )
                self._bind_representation(
                    rebound_registry.derivation_graph,
                    representation,
                    dependency_kind=(
                        old_edge.dependency_kind if old_edge else "semantic_content"
                    ),
                    rebuild_policy=(
                        old_edge.rebuild_policy if old_edge else "on_demand"
                    ),
                )
            referenced_node_ids = {
                node_id
                for edge in rebound_registry.derivation_graph.edges
                for node_id in (edge.from_node_id, edge.to_node_id)
            }
            rebound_registry.derivation_graph.nodes = [
                node
                for node in rebound_registry.derivation_graph.nodes
                if node.node_type != "source" or node.node_id in referenced_node_ids
            ]
            after_graph = rebound_registry.derivation_graph.model_dump(mode="json")
            after_graph.pop("graph_revision", None)
            raw = rebound_registry.model_dump(mode="json")

            tombstones_by_id = {
                str(item.get("section_id") or ""): deepcopy(item)
                for item in previous_tombstones
                if isinstance(item, dict) and item.get("section_id")
            }
            for item in section_tombstones:
                if isinstance(item, dict) and item.get("section_id"):
                    tombstones_by_id[str(item["section_id"])] = deepcopy(item)
            result_tombstones = list(tombstones_by_id.values())
            record = {
                "operation_id": operation_id,
                "mapping_revision": mapping_revision,
                "status": "applied",
                "affected_section_ids": list(dict.fromkeys(affected_section_ids)),
                "mutations": mutations,
                "before_graph": before_graph,
                "after_graph": after_graph,
                "previous_tombstones": previous_tombstones,
                "result_tombstones": deepcopy(result_tombstones),
                "applied_at": datetime.now(timezone.utc).isoformat(),
            }
            raw["section_reference_tombstones"] = result_tombstones
            raw["structure_reference_rebinds"] = [*records, record]
            saved = self.save(TeachingRepresentationRegistry.model_validate(raw))
            return {
                "registry_revision": saved.registry_revision,
                "record": deepcopy(record),
            }

    def structure_reference_rebind(
        self,
        course_id: str,
        operation_id: str,
    ) -> dict[str, Any] | None:
        registry = self.load(course_id)
        record = next(
            (
                item
                for item in registry.structure_reference_rebinds
                if item.get("operation_id") == operation_id
            ),
            None,
        )
        if not isinstance(record, dict):
            return None
        return {
            "registry_revision": registry.registry_revision,
            "record": deepcopy(record),
        }

    def undo_structure_reference_rebind(
        self,
        course_id: str,
        *,
        operation_id: str,
        expected_mapping_revision: str,
    ) -> dict[str, Any]:
        """Restore the exact reference and stale markers when CAS still matches."""

        with self._lock(course_id):
            registry = self.load(course_id)
            raw = registry.model_dump(mode="json")
            record_index = next(
                (
                    index
                    for index, item in enumerate(
                        raw.get("structure_reference_rebinds") or []
                    )
                    if isinstance(item, dict)
                    and item.get("operation_id") == operation_id
                ),
                None,
            )
            if record_index is None:
                raise RepresentationConflict(
                    "Teaching representation structure rebind receipt is missing"
                )
            record = raw["structure_reference_rebinds"][record_index]
            if record.get("status") == "undone":
                return {
                    "registry_revision": registry.registry_revision,
                    "record": deepcopy(record),
                }
            if record.get("mapping_revision") != expected_mapping_revision:
                raise RepresentationConflict(
                    "Teaching representation structure rebind revision conflicts"
                )
            for mutation in record.get("mutations") or []:
                path = list(mutation.get("path") or [])
                try:
                    current = _value_at_path(raw, path)
                except (IndexError, KeyError, TypeError) as exc:
                    raise RepresentationConflict(
                        "Teaching representation changed after structure rebind"
                    ) from exc
                if current != mutation.get("after"):
                    raise RepresentationConflict(
                        "Teaching representation changed after structure rebind"
                    )
            if list(raw.get("section_reference_tombstones") or []) != list(
                record.get("result_tombstones") or []
            ):
                raise RepresentationConflict(
                    "Teaching representation tombstones changed after structure rebind"
                )
            current_graph = deepcopy(raw.get("derivation_graph") or {})
            current_graph.pop("graph_revision", None)
            if current_graph != (record.get("after_graph") or {}):
                raise RepresentationConflict(
                    "Teaching representation graph changed after structure rebind"
                )
            for mutation in reversed(record.get("mutations") or []):
                _set_value_at_path(
                    raw,
                    list(mutation.get("path") or []),
                    mutation.get("before"),
                )
            raw["derivation_graph"] = deepcopy(record.get("before_graph") or {})
            raw["section_reference_tombstones"] = deepcopy(
                record.get("previous_tombstones") or []
            )
            record["status"] = "undone"
            record["undone_at"] = datetime.now(timezone.utc).isoformat()
            saved = self.save(TeachingRepresentationRegistry.model_validate(raw))
            return {
                "registry_revision": saved.registry_revision,
                "record": deepcopy(
                    saved.structure_reference_rebinds[record_index]
                ),
            }

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
            self._bind_spec(registry.derivation_graph, spec)
            return self.save(registry)

    def publish_spec_and_representation(
        self,
        spec: TeachingRepresentationSpec,
        representation: TeachingRepresentation,
        *,
        dependency_kind: DependencyKind = "semantic_content",
        rebuild_policy: Literal["automatic", "on_demand", "manual"] = "automatic",
    ) -> TeachingRepresentationRegistry:
        """Persist a final spec and its public pointer in one registry write."""

        if spec.course_id != representation.course_id or spec.spec_id != representation.spec_id:
            raise RepresentationConflict("Spec and representation publication targets differ")
        with self._lock(spec.course_id):
            registry = self.load(spec.course_id)
            registry.specs = [item for item in registry.specs if item.spec_id != spec.spec_id]
            registry.specs.append(spec)
            registry.representations = [
                item
                for item in registry.representations
                if item.representation_id != representation.representation_id
            ]
            registry.representations.append(representation)
            self._bind_spec(registry.derivation_graph, spec)
            self._bind_representation(
                registry.derivation_graph,
                representation,
                dependency_kind=dependency_kind,
                rebuild_policy=rebuild_policy,
            )
            return self.save(registry)

    def publish_candidate(
        self,
        spec: TeachingRepresentationSpec,
        representation: TeachingRepresentation,
        *,
        dependency_kind: DependencyKind = "semantic_content",
        rebuild_policy: Literal["automatic", "on_demand", "manual"] = "on_demand",
    ) -> TeachingRepresentationRegistry:
        """Atomically publish one review candidate and retire its predecessor."""

        if representation.status != "candidate":
            raise RepresentationConflict("Candidate publication requires candidate status")
        if spec.course_id != representation.course_id or spec.spec_id != representation.spec_id:
            raise RepresentationConflict("Spec and representation publication targets differ")
        with self._lock(spec.course_id):
            registry = self.load(spec.course_id)
            now = representation.updated_at
            for current in registry.representations:
                if (
                    current.representation_type == representation.representation_type
                    and current.variant_key == representation.variant_key
                    and current.status == "candidate"
                ):
                    current.status = "archived"
                    current.updated_at = now
                    self._bind_representation(
                        registry.derivation_graph,
                        current,
                        dependency_kind=dependency_kind,
                        rebuild_policy=rebuild_policy,
                    )
            registry.specs = [item for item in registry.specs if item.spec_id != spec.spec_id]
            registry.specs.append(spec)
            registry.representations = [
                item
                for item in registry.representations
                if item.representation_id != representation.representation_id
            ]
            registry.representations.append(representation)
            self._bind_spec(registry.derivation_graph, spec)
            self._bind_representation(
                registry.derivation_graph,
                representation,
                dependency_kind=dependency_kind,
                rebuild_policy=rebuild_policy,
            )
            return self.save(registry)

    def complete_candidate(
        self,
        spec: TeachingRepresentationSpec,
        representation: TeachingRepresentation,
        *,
        dependency_kind: DependencyKind = "semantic_content",
        rebuild_policy: Literal["automatic", "on_demand", "manual"] = "on_demand",
    ) -> TeachingRepresentationRegistry:
        """Replace the persisted body of one still-current candidate."""

        if representation.status != "candidate":
            raise RepresentationConflict("Candidate completion requires candidate status")
        if spec.course_id != representation.course_id or spec.spec_id != representation.spec_id:
            raise RepresentationConflict("Spec and representation completion targets differ")
        with self._lock(spec.course_id):
            registry = self.load(spec.course_id)
            current = next(
                (
                    item
                    for item in registry.representations
                    if item.representation_id == representation.representation_id
                ),
                None,
            )
            if current is None or current.spec_id != spec.spec_id:
                raise RepresentationConflict("Teaching representation candidate does not exist")
            if current.status != "candidate":
                raise RepresentationConflict("Teaching representation candidate is no longer current")
            source_nodes = {
                node.object_id: node
                for node in registry.derivation_graph.nodes
                if node.node_type == "source"
            }
            if any(
                source_nodes.get(source_key) is None
                or source_nodes[source_key].revision_or_fingerprint != revision
                or source_nodes[source_key].status != "current"
                for source_key, revision in representation.source_revision_vector.items()
            ):
                raise RepresentationConflict("Teaching representation candidate source changed")
            registry.specs = [item for item in registry.specs if item.spec_id != spec.spec_id]
            registry.specs.append(spec)
            registry.representations = [
                item
                for item in registry.representations
                if item.representation_id != representation.representation_id
            ]
            registry.representations.append(representation)
            self._bind_spec(registry.derivation_graph, spec)
            self._bind_representation(
                registry.derivation_graph,
                representation,
                dependency_kind=dependency_kind,
                rebuild_policy=rebuild_policy,
            )
            return self.save(registry)

    def resolve_candidate(
        self,
        course_id: str,
        representation_id: str,
        *,
        accept: bool,
        set_id: str,
        member_variant_prefix: str,
        target_scope: dict[str, Any],
    ) -> TeachingRepresentationRegistry:
        """Accept or archive a candidate and refresh its shared representation set."""

        with self._lock(course_id):
            registry = self.load(course_id)
            representation = next(
                (
                    item
                    for item in registry.representations
                    if item.representation_id == representation_id
                ),
                None,
            )
            if representation is None:
                raise RepresentationConflict("Teaching representation candidate does not exist")
            if representation.status == "stale":
                raise RepresentationConflict("Stale teaching representation cannot be accepted")
            expected_status = "accepted" if accept else "archived"
            if representation.status == expected_status:
                return registry
            if representation.status != "candidate":
                raise RepresentationConflict("Teaching representation candidate was already resolved")

            now = datetime.now(timezone.utc).isoformat()
            representation.status = expected_status
            representation.updated_at = now
            if accept:
                for current in registry.representations:
                    if (
                        current.representation_id != representation.representation_id
                        and current.representation_type == representation.representation_type
                        and current.variant_key == representation.variant_key
                        and current.status == "accepted"
                    ):
                        current.status = "archived"
                        current.updated_at = now
                        self._bind_representation(
                            registry.derivation_graph,
                            current,
                            dependency_kind="semantic_content",
                            rebuild_policy="on_demand",
                        )

            self._bind_representation(
                registry.derivation_graph,
                representation,
                dependency_kind="semantic_content",
                rebuild_policy="on_demand",
            )
            if accept:
                accepted = [
                    item
                    for item in registry.representations
                    if item.status == "accepted"
                    and item.variant_key.startswith(member_variant_prefix)
                ]
                previous = next(
                    (item for item in registry.representation_sets if item.set_id == set_id),
                    None,
                )
                accepted_ids = {item.representation_id for item in accepted}
                default_id = (
                    previous.default_representation_id
                    if previous and previous.default_representation_id in accepted_ids
                    else representation.representation_id
                )
                ordered = sorted(
                    accepted,
                    key=lambda item: (
                        {"diagram": 0, "image": 1, "animation": 2}.get(
                            item.representation_type, 9
                        ),
                        item.created_at,
                    ),
                )
                representation_set = RepresentationSet(
                    set_id=set_id,
                    course_id=course_id,
                    target_scope=deepcopy(target_scope),
                    default_representation_id=default_id,
                    complementary_representation_ids=[
                        item.representation_id
                        for item in ordered
                        if item.representation_id != default_id
                    ],
                    fallback_chain=[item.representation_id for item in ordered],
                    selection_policy={
                        "policy": "teacher_accepted",
                        "consumer_targets": ["teacher_script", "slide_deck", "learner"],
                    },
                    revision=stable_hash(
                        {
                            "set_id": set_id,
                            "members": [item.representation_id for item in ordered],
                        },
                        prefix="trs_",
                    ),
                )
                registry.representation_sets = [
                    item for item in registry.representation_sets if item.set_id != set_id
                ]
                registry.representation_sets.append(representation_set)
            return self.save(registry)

    def accepted_sets_for_consumer(
        self,
        course_id: str,
        *,
        consumer: Literal["teacher_script", "slide_deck", "learner"],
        lesson_unit_id: str = "",
    ) -> dict[str, Any]:
        """Project only accepted shared expressions for one downstream consumer."""

        registry = self.load(course_id)
        accepted_by_id = {
            item.representation_id: item
            for item in registry.representations
            if item.status == "accepted"
            and not (
                item.representation_type == "animation"
                and item.variant_key.startswith("script-visual:")
                and not _teacher_script_animation_runtime_enabled()
            )
        }
        specs_by_id = {item.spec_id: item for item in registry.specs}
        projected_sets: list[dict[str, Any]] = []
        projected_items: list[dict[str, Any]] = []
        emitted_ids: set[str] = set()
        for representation_set in registry.representation_sets:
            targets = representation_set.selection_policy.get("consumer_targets") or []
            if consumer not in targets:
                continue
            if lesson_unit_id and str(
                representation_set.target_scope.get("lesson_unit_id") or ""
            ) != lesson_unit_id:
                continue
            member_ids = list(dict.fromkeys([
                representation_set.default_representation_id,
                *representation_set.alternative_representation_ids,
                *representation_set.complementary_representation_ids,
                *representation_set.accessibility_representation_ids,
                *representation_set.fallback_chain,
            ]))
            active_ids = [
                representation_id
                for representation_id in member_ids
                if representation_id in accepted_by_id
            ]
            if not active_ids:
                continue
            default_id = (
                representation_set.default_representation_id
                if representation_set.default_representation_id in active_ids
                else active_ids[0]
            )
            projected_sets.append({
                **representation_set.model_dump(mode="json"),
                "default_representation_id": default_id,
                "alternative_representation_ids": [
                    item for item in representation_set.alternative_representation_ids
                    if item in active_ids
                ],
                "complementary_representation_ids": [
                    item for item in representation_set.complementary_representation_ids
                    if item in active_ids
                ],
                "accessibility_representation_ids": [
                    item for item in representation_set.accessibility_representation_ids
                    if item in active_ids
                ],
                "fallback_chain": [
                    item for item in representation_set.fallback_chain
                    if item in active_ids
                ],
            })
            for representation_id in active_ids:
                if representation_id in emitted_ids:
                    continue
                representation = accepted_by_id[representation_id]
                spec = specs_by_id.get(representation.spec_id)
                if spec is None:
                    continue
                projected_items.append({
                    "representation": representation.model_dump(mode="json"),
                    "spec": spec.model_dump(mode="json"),
                })
                emitted_ids.add(representation_id)
        return {
            "schema_version": "accepted_representation_sets_v1",
            "course_id": course_id,
            "consumer": consumer,
            "lesson_unit_id": lesson_unit_id,
            "representation_sets": projected_sets,
            "items": projected_items,
        }

    def reconcile_external_source(
        self,
        course_id: str,
        source_key: str,
        current_revision: str,
    ) -> TeachingRepresentationRegistry:
        """Reconcile a source revision owned outside CourseDocument."""

        with self._lock(course_id):
            registry = self.load(course_id)
            source_node = next(
                (
                    node
                    for node in registry.derivation_graph.nodes
                    if node.node_type == "source" and node.object_id == source_key
                ),
                None,
            )
            if source_node is None or source_node.revision_or_fingerprint == current_revision:
                return registry
            previous_revisions = {
                node.object_id: node.revision_or_fingerprint
                for node in registry.derivation_graph.nodes
                if node.node_type == "source"
            }
            current_revisions = {**previous_revisions, source_key: current_revision}
            timestamp = datetime.now(timezone.utc).isoformat()
            event_payload = {
                "course_id": course_id,
                "command_id": "",
                "operation": "reconcile_external_source",
                "previous": CourseRevisionVector(
                    course_id=course_id,
                    revisions=previous_revisions,
                ).model_dump(mode="json"),
                "current": CourseRevisionVector(
                    course_id=course_id,
                    revisions=current_revisions,
                ).model_dump(mode="json"),
                "changed_source_keys": [source_key],
                "added_source_keys": [],
                "removed_source_keys": [],
                "affected_block_ids": [],
                "created_at": timestamp,
            }
            return self.apply_revision_event(
                course_id,
                CourseRevisionEvent(
                    event_id=stable_hash(event_payload, prefix="cre_"),
                    **event_payload,
                ),
            )

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

    def reconcile_source_revision_vector(
        self,
        course_id: str,
        current: CourseRevisionVector | dict[str, Any],
    ) -> TeachingRepresentationRegistry:
        """Mark derived artifacts stale when non-document source revisions drift."""
        vector = (
            current
            if isinstance(current, CourseRevisionVector)
            else CourseRevisionVector.model_validate(current)
        )
        if vector.course_id != course_id:
            raise RepresentationConflict("Course revision vector belongs to another course")
        registry = self.load(course_id)
        previous_revisions = {
            node.object_id: node.revision_or_fingerprint
            for node in registry.derivation_graph.nodes
            if node.node_type == "source"
        }
        bound_keys = set(previous_revisions)
        current_keys = set(vector.revisions)
        managed_bound_keys = {
            key
            for key in bound_keys
            if (
                key in {
                    "course_document",
                    "course_title",
                    "course_teaching_plan",
                    "course_knowledge_base",
                    "course_coherence_contract",
                }
                or key.startswith((
                    "block:",
                    "section:",
                    "section_structure:",
                    "objective:",
                ))
            )
        }
        changed = sorted(
            key
            for key in managed_bound_keys & current_keys
            if previous_revisions[key] != vector.revisions[key]
        )
        removed = sorted(managed_bound_keys - current_keys)
        if not changed and not removed:
            return registry
        timestamp = datetime.now(timezone.utc).isoformat()
        event_payload = {
            "course_id": course_id,
            "command_id": "",
            "operation": "reconcile_source_revision_vector",
            "previous": CourseRevisionVector(
                course_id=course_id,
                revisions=previous_revisions,
            ).model_dump(mode="json"),
            "current": vector.model_dump(mode="json"),
            "changed_source_keys": changed,
            "added_source_keys": sorted(current_keys - bound_keys),
            "removed_source_keys": removed,
            "affected_block_ids": [],
            "created_at": timestamp,
        }
        return self.apply_revision_event(
            course_id,
            CourseRevisionEvent(
                event_id=stable_hash(event_payload, prefix="cre_"),
                **event_payload,
            ),
        )

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
    def _bind_spec(
        graph: AssetDerivationGraph,
        spec: TeachingRepresentationSpec,
    ) -> None:
        spec_node_id = f"spec::{spec.spec_id}"
        unit_prefix = f"spec-unit::{spec.spec_id}::"
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
