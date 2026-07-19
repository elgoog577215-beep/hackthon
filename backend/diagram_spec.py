"""Deterministic same-source diagrams compiled from the canonical course."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from course_document import CourseDocument, stable_hash

DIAGRAM_COMPILER_VERSION = "diagram_compiler_v1"


class DiagramNodeSpec(BaseModel):
    node_id: str
    label: str
    kind: Literal["objective", "knowledge", "course_block"]
    source_ref: str


class DiagramEdgeSpec(BaseModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation: Literal["supports", "prepares"]


class DiagramUnitSpec(BaseModel):
    unit_id: str
    section_id: str
    title: str
    diagram_kind: Literal["concept_map", "learning_path"] = "concept_map"
    nodes: list[DiagramNodeSpec] = Field(default_factory=list)
    edges: list[DiagramEdgeSpec] = Field(default_factory=list)
    source_section_ids: list[str] = Field(default_factory=list)
    source_block_ids: list[str] = Field(default_factory=list)
    source_keys: list[str] = Field(default_factory=list)
    knowledge_refs: list[str] = Field(default_factory=list)
    learning_objective_ids: list[str] = Field(default_factory=list)
    mermaid: str = ""

    @model_validator(mode="after")
    def validate_graph(self) -> "DiagramUnitSpec":
        node_ids = {item.node_id for item in self.nodes}
        if not self.nodes:
            raise ValueError("Diagram unit must contain at least one source-bound node")
        if any(
            edge.source_node_id not in node_ids or edge.target_node_id not in node_ids
            for edge in self.edges
        ):
            raise ValueError("Diagram edge references an unknown node")
        return self


class DiagramSpec(BaseModel):
    schema_version: Literal["diagram_spec_v1"] = "diagram_spec_v1"
    compiler_version: Literal["diagram_compiler_v1"] = DIAGRAM_COMPILER_VERSION
    title: str
    units: list[DiagramUnitSpec] = Field(default_factory=list)
    quality_report: dict[str, Any] = Field(default_factory=dict)


def compile_diagram_spec(document: CourseDocument) -> dict[str, Any]:
    blocks_by_section: dict[str, list[Any]] = {}
    for block in sorted(document.blocks, key=lambda item: (item.section_id, item.position)):
        if block.status != "retired":
            blocks_by_section.setdefault(block.section_id, []).append(block)

    units: list[DiagramUnitSpec] = []
    for section in sorted(document.sections, key=lambda item: item.position):
        blocks = blocks_by_section.get(section.section_id, [])
        if not blocks:
            continue
        objective_id = str(section.objective_id or section.section_id)
        objective_node_id = f"objective::{objective_id}"
        nodes = [DiagramNodeSpec(
            node_id=objective_node_id,
            label=str(section.learning_objective or section.title),
            kind="objective",
            source_ref=f"objective:{objective_id}",
        )]
        knowledge_refs = list(dict.fromkeys(
            str(ref)
            for block in blocks
            for ref in block.concept_refs
            if str(ref).strip()
        ))
        if knowledge_refs:
            for reference in knowledge_refs:
                nodes.append(DiagramNodeSpec(
                    node_id=f"knowledge::{reference}",
                    label=_humanize_reference(reference),
                    kind="knowledge",
                    source_ref=reference,
                ))
        else:
            for block in blocks:
                nodes.append(DiagramNodeSpec(
                    node_id=f"block::{block.block_id}",
                    label=str(block.payload.get("title") or block.role or "课程内容"),
                    kind="course_block",
                    source_ref=f"block:{block.block_id}",
                ))
        edges: list[DiagramEdgeSpec] = []
        content_nodes = [item.node_id for item in nodes if item.node_id != objective_node_id]
        for target in content_nodes:
            edges.append(DiagramEdgeSpec(
                edge_id=stable_hash({"source": objective_node_id, "target": target}, prefix="dge_"),
                source_node_id=objective_node_id,
                target_node_id=target,
                relation="supports",
            ))
        for source, target in zip(content_nodes, content_nodes[1:]):
            edges.append(DiagramEdgeSpec(
                edge_id=stable_hash({"source": source, "target": target}, prefix="dge_"),
                source_node_id=source,
                target_node_id=target,
                relation="prepares",
            ))
        unit = DiagramUnitSpec(
            unit_id=f"diagram:{section.section_id}",
            section_id=section.section_id,
            title=f"{section.title} · 知识路径",
            nodes=nodes,
            edges=edges,
            source_section_ids=[section.section_id],
            source_block_ids=[block.block_id for block in blocks],
            source_keys=[f"objective:{section.objective_id}"] if section.objective_id else [],
            knowledge_refs=knowledge_refs,
            learning_objective_ids=[section.objective_id] if section.objective_id else [],
        )
        unit.mermaid = _to_mermaid(unit)
        units.append(unit)

    payload = DiagramSpec(title=f"{document.title} 图解", units=units)
    report = validate_diagram_spec(payload.model_dump(mode="json"))
    payload.quality_report = report
    return payload.model_dump(mode="json")


def validate_diagram_spec(payload: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    units = payload.get("units") or []
    if not units:
        issues.append({"severity": "critical", "code": "diagram_empty", "message": "图解没有可用教学单元"})
    for unit in units:
        unit_id = str(unit.get("unit_id") or "")
        nodes = unit.get("nodes") or []
        node_ids = [str(item.get("node_id") or "") for item in nodes]
        if not unit_id or not unit.get("source_section_ids") or not unit.get("source_block_ids"):
            issues.append({"severity": "critical", "code": "diagram_missing_source", "message": f"{unit_id or 'diagram'} 缺少课程来源"})
        if not node_ids or any(not value for value in node_ids) or len(node_ids) != len(set(node_ids)):
            issues.append({"severity": "critical", "code": "diagram_invalid_nodes", "message": f"{unit_id} 的节点为空或重复"})
        for edge in unit.get("edges") or []:
            if edge.get("source_node_id") not in node_ids or edge.get("target_node_id") not in node_ids:
                issues.append({"severity": "critical", "code": "diagram_unknown_endpoint", "message": f"{unit_id} 包含悬空关系"})
    return {
        "passed": not any(item["severity"] == "critical" for item in issues),
        "issues": issues,
        "unit_count": len(units),
    }


def _humanize_reference(value: str) -> str:
    text = re.sub(r"^(?:ckp|kp|knowledge)[-_:]", "", value, flags=re.I)
    text = re.sub(r"[-_:]+", " ", text).strip()
    return text or value


def _to_mermaid(unit: DiagramUnitSpec) -> str:
    aliases = {node.node_id: f"N{index}" for index, node in enumerate(unit.nodes, start=1)}
    lines = ["flowchart LR"]
    for node in unit.nodes:
        label = node.label.replace('"', "'").replace("\n", " ")[:80]
        lines.append(f'  {aliases[node.node_id]}["{label}"]')
    for edge in unit.edges:
        arrow = "-->|支撑|" if edge.relation == "supports" else "-->|承接|"
        lines.append(f"  {aliases[edge.source_node_id]} {arrow} {aliases[edge.target_node_id]}")
    return "\n".join(lines)


__all__ = [
    "DIAGRAM_COMPILER_VERSION",
    "DiagramSpec",
    "compile_diagram_spec",
    "validate_diagram_spec",
]
