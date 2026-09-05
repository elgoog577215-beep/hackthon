"""Bounded, source-grounded rule diagrams for deterministic slide rendering."""

from __future__ import annotations

import html
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RULE_DIAGRAM_SCHEMA = "rule_diagram_program_v1"
RuleDiagramTemplate = Literal[
    "relation_graph",
    "process_flow",
    "cycle",
    "system_boundary",
    "apparatus",
    "energy_balance",
    "qualitative_plot",
]

RULE_DIAGRAM_TEMPLATES = {
    "relation_graph",
    "process_flow",
    "cycle",
    "system_boundary",
    "apparatus",
    "energy_balance",
    "qualitative_plot",
}

_HEADER_RE = re.compile(
    r"^\s*(?:graph|flowchart)\s+(?P<direction>TD|TB|BT|LR|RL)\s*;?\s*$",
    flags=re.I,
)
_EDGE_RE = re.compile(
    r"^\s*(?P<source>.+?)\s*(?P<arrow>-->|==>|-\.->)\s*"
    r"(?:\|(?P<label>[^|]*)\|\s*)?(?P<target>.+?)\s*;?\s*$"
)
_NODE_RE = re.compile(
    r"^\s*(?P<node_id>[A-Za-z_][\w-]*)"
    r"(?P<shape>\[\[.*\]\]|\(\(.*\)\)|\[.*\]|\(.*\)|\{.*\})?\s*$",
    flags=re.S,
)
_IGNORED_DIRECTIVE_RE = re.compile(
    r"^\s*(?:%%|classDef\b|class\b|style\b|linkStyle\b)",
    flags=re.I,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuleDiagramNodeV1(_StrictModel):
    node_id: str = Field(pattern=r"^[A-Za-z_][\w-]*$")
    label: str = Field(min_length=1, max_length=80)
    source_fragment_ids: list[str] = Field(min_length=1)


class RuleDiagramEdgeV1(_StrictModel):
    source: str
    target: str
    label: str = Field(default="", max_length=40)
    relation: Literal[
        "sequence",
        "supports",
        "contrasts",
        "causes",
        "contains",
        "maps_to",
    ] = "sequence"


class RuleDiagramProgramV1(_StrictModel):
    schema_version: Literal["rule_diagram_program_v1"] = RULE_DIAGRAM_SCHEMA
    template: RuleDiagramTemplate
    direction: Literal["horizontal", "vertical"] = "horizontal"
    source_fragment_ids: list[str] = Field(min_length=1)
    nodes: list[RuleDiagramNodeV1] = Field(min_length=2, max_length=8)
    edges: list[RuleDiagramEdgeV1] = Field(min_length=1, max_length=12)
    relation_evidence: list[str] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_program(self) -> "RuleDiagramProgramV1":
        if self.template not in RULE_DIAGRAM_TEMPLATES:
            raise ValueError("Rule diagram template is not allow-listed")
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("Rule diagram node ids must be unique")
        if any(edge.source not in node_ids or edge.target not in node_ids for edge in self.edges):
            raise ValueError("Rule diagram edges must reference declared nodes")
        source_ids = set(self.source_fragment_ids)
        if any(set(node.source_fragment_ids) - source_ids for node in self.nodes):
            raise ValueError("Rule diagram node evidence must belong to the program")
        return self


def parse_mermaid_rule_diagram(
    source: str,
    *,
    fragment_id: str,
) -> RuleDiagramProgramV1 | None:
    """Compile a conservative Mermaid graph subset; unsupported input fails closed."""
    lines = [
        line.strip()
        for line in str(source or "").replace("\r\n", "\n").split("\n")
        if line.strip()
    ]
    if not lines:
        return None
    header = _HEADER_RE.fullmatch(lines[0])
    if header is None:
        return None

    labels: dict[str, str] = {}
    edges: list[RuleDiagramEdgeV1] = []
    relation_evidence: list[str] = []
    for line in lines[1:]:
        if _IGNORED_DIRECTIVE_RE.match(line):
            continue
        edge_match = _EDGE_RE.fullmatch(line)
        if edge_match is not None:
            source_node = _parse_node_reference(edge_match.group("source"))
            target_node = _parse_node_reference(edge_match.group("target"))
            if source_node is None or target_node is None:
                return None
            source_id, source_label = source_node
            target_id, target_label = target_node
            labels[source_id] = source_label or labels.get(source_id, "")
            labels[target_id] = target_label or labels.get(target_id, "")
            raw_edge_label = edge_match.group("label") or ""
            edge_label = _clean_label(raw_edge_label, maximum=40)
            if raw_edge_label.strip() and not edge_label:
                return None
            edges.append(RuleDiagramEdgeV1(
                source=source_id,
                target=target_id,
                label=edge_label,
                relation="maps_to" if edge_label else "sequence",
            ))
            relation_evidence.append(line)
            continue
        node = _parse_node_reference(line.rstrip(";"))
        if node is None or not node[1]:
            return None
        labels[node[0]] = node[1]

    if (
        not edges
        or len(labels) < 2
        or len(labels) > 8
        or len(edges) > 12
        or any(not label for label in labels.values())
    ):
        return None
    nodes = [
        RuleDiagramNodeV1(
            node_id=node_id,
            label=label,
            source_fragment_ids=[fragment_id],
        )
        for node_id, label in labels.items()
    ]
    direction = (
        "horizontal"
        if header.group("direction").upper() in {"LR", "RL"}
        else "vertical"
    )
    return RuleDiagramProgramV1(
        template="process_flow",
        direction=direction,
        source_fragment_ids=[fragment_id],
        nodes=nodes,
        edges=edges,
        relation_evidence=relation_evidence,
    )


def _parse_node_reference(value: str) -> tuple[str, str] | None:
    match = _NODE_RE.fullmatch(value.strip())
    if match is None:
        return None
    node_id = match.group("node_id")
    shape = match.group("shape") or ""
    label = _clean_label(_unwrap_shape(shape), maximum=80) if shape else ""
    if shape and not label:
        return None
    return node_id, label


def _unwrap_shape(value: str) -> str:
    current = value.strip()
    pairs = (("[[", "]]"), ("((", "))"), ("[", "]"), ("(", ")"), ("{", "}"))
    for opening, closing in pairs:
        if current.startswith(opening) and current.endswith(closing):
            return current[len(opening):-len(closing)]
    return current


def _clean_label(value: str, *, maximum: int) -> str:
    clean = html.unescape(str(value or "")).strip().strip("\"'")
    clean = re.sub(r"<br\s*/?>", " ", clean, flags=re.I)
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean or len(clean) > maximum or "<" in clean or ">" in clean:
        return ""
    return clean


__all__ = [
    "RULE_DIAGRAM_SCHEMA",
    "RULE_DIAGRAM_TEMPLATES",
    "RuleDiagramEdgeV1",
    "RuleDiagramNodeV1",
    "RuleDiagramProgramV1",
    "parse_mermaid_rule_diagram",
]
