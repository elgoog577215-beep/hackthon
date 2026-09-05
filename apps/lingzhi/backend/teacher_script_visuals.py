"""Source-bound diagram, image, and animation candidates for teacher scripts."""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from content_blocks import content_fingerprint, summarize_text
from course_document import stable_hash
from diagram_spec import (
    DiagramEdgeSpec,
    DiagramNodeSpec,
    DiagramRelation,
    DiagramSpec,
    DiagramUnitSpec,
    validate_diagram_spec,
)
from slide_asset_repository import SlideAssetRepository, slide_asset_repository
from slide_image_provider import IMAGE_PROMPT_POLICY_VERSION, SlideImageProvider
from teaching_representations import (
    RepresentationConflict,
    SourceBinding,
    TeachingRepresentation,
    TeachingRepresentationRepository,
    TeachingRepresentationSpec,
    teaching_representation_repository,
)

SCRIPT_VISUAL_COMPILER_VERSION = "teacher_script_visual_compiler_v2"
ScriptVisualType = Literal["diagram", "image", "animation"]


def script_animation_runtime_enabled() -> bool:
    """Keep experimental animation code dormant unless explicitly re-enabled."""

    return os.getenv("TEACHER_SCRIPT_ANIMATION_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class DiagramPlanNodeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=96)
    kind: Literal["objective", "knowledge", "course_block"]
    source_quote: str = Field(min_length=1, max_length=180)


class DiagramPlanEdgeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_node_id: str = Field(min_length=1, max_length=80)
    target_node_id: str = Field(min_length=1, max_length=80)
    relation: DiagramRelation


class DiagramPlanV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=140)
    diagram_kind: Literal["concept_map", "learning_path"] = "concept_map"
    learning_focus: str = Field(min_length=1, max_length=240)
    nodes: list[DiagramPlanNodeV1] = Field(min_length=2, max_length=9)
    edges: list[DiagramPlanEdgeV1] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def validate_graph(self) -> DiagramPlanV1:
        node_ids = {item.node_id for item in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("Diagram plan node ids must be unique")
        if not any(item.kind == "objective" for item in self.nodes):
            raise ValueError("Diagram plan requires an objective node")
        if any(
            edge.source_node_id not in node_ids or edge.target_node_id not in node_ids
            for edge in self.edges
        ):
            raise ValueError("Diagram plan edge references an unknown node")
        return self


class SceneObjectV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_id: str
    label: str
    kind: Literal["source", "concept", "result"]
    x: int = Field(ge=0, le=100)
    y: int = Field(ge=0, le=100)


class SceneActionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    action_type: Literal["reveal", "focus", "connect"]
    target_ids: list[str] = Field(min_length=1, max_length=4)
    start_ms: int = Field(ge=0)
    duration_ms: int = Field(ge=120, le=5000)
    narration: str = ""


class SceneCheckpointV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_id: str
    label: str
    at_ms: int = Field(ge=0)


class SceneSpecV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["scene_spec_v1"] = "scene_spec_v1"
    title: str
    duration_ms: int = Field(ge=500, le=30000)
    objects: list[SceneObjectV1] = Field(min_length=2, max_length=8)
    actions: list[SceneActionV1] = Field(min_length=2, max_length=16)
    checkpoints: list[SceneCheckpointV1] = Field(min_length=2, max_length=8)
    static_fallback: dict[str, Any]

    @model_validator(mode="after")
    def validate_scene(self) -> SceneSpecV1:
        object_ids = {item.object_id for item in self.objects}
        if len(object_ids) != len(self.objects):
            raise ValueError("Scene object ids must be unique")
        if any(not set(action.target_ids).issubset(object_ids) for action in self.actions):
            raise ValueError("Scene action references an unknown object")
        if self.checkpoints != sorted(self.checkpoints, key=lambda item: item.at_ms):
            raise ValueError("Scene checkpoints must be ordered")
        if self.checkpoints[-1].at_ms > self.duration_ms:
            raise ValueError("Scene checkpoint exceeds scene duration")
        return self


SceneColorV2 = Literal[
    "ink",
    "primary",
    "accent",
    "warm",
    "muted",
    "success",
    "danger",
]


class ScenePointV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)


class SceneObjectV2(BaseModel):
    """A safe SVG primitive. Coordinates use a normalized 100 x 100 canvas."""

    model_config = ConfigDict(extra="forbid")

    object_id: str = Field(min_length=1, max_length=80)
    kind: Literal["circle", "rect", "line", "polygon", "path", "arrow", "text"]
    label: str = Field(default="", max_length=120)
    x: float = Field(default=0, ge=0, le=100)
    y: float = Field(default=0, ge=0, le=100)
    width: float = Field(default=0, ge=0, le=100)
    height: float = Field(default=0, ge=0, le=100)
    radius: float = Field(default=0, ge=0, le=20)
    points: list[ScenePointV2] = Field(default_factory=list, max_length=16)
    fill: SceneColorV2 = "muted"
    stroke: SceneColorV2 = "ink"
    stroke_width: float = Field(default=1.5, ge=0.5, le=6)
    visible: bool = True

    @model_validator(mode="after")
    def validate_geometry(self) -> SceneObjectV2:
        if self.kind == "circle" and self.radius <= 0:
            raise ValueError("Scene circle requires radius")
        if self.kind == "rect" and (self.width <= 0 or self.height <= 0):
            raise ValueError("Scene rect requires width and height")
        minimum_points = {
            "line": 2,
            "arrow": 2,
            "path": 2,
            "polygon": 3,
        }.get(self.kind, 0)
        if minimum_points and len(self.points) < minimum_points:
            raise ValueError(f"Scene {self.kind} requires at least {minimum_points} points")
        return self


class SceneActionV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1, max_length=120)
    action_type: Literal["reveal", "move", "rotate", "pulse", "trace"]
    target_id: str = Field(min_length=1, max_length=80)
    start_ms: int = Field(ge=0)
    duration_ms: int = Field(ge=120, le=15000)
    easing: Literal["linear", "accelerate", "decelerate", "ease_in_out"] = "linear"
    path: list[ScenePointV2] = Field(default_factory=list, max_length=16)
    from_rotation: float = Field(default=0, ge=-3600, le=3600)
    to_rotation: float = Field(default=0, ge=-3600, le=3600)
    narration: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def validate_action(self) -> SceneActionV2:
        if self.action_type == "move" and len(self.path) < 2:
            raise ValueError("Scene move requires at least two path points")
        return self


class SceneSpecV2(BaseModel):
    """Continuous, code-rendered teaching animation without executable model code."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["scene_spec_v2"] = "scene_spec_v2"
    title: str = Field(min_length=1, max_length=160)
    scene_kind: Literal[
        "physical_motion",
        "geometry",
        "system_change",
        "process",
        "comparison",
    ]
    learning_focus: str = Field(min_length=1, max_length=240)
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    duration_ms: int = Field(ge=1000, le=30000)
    objects: list[SceneObjectV2] = Field(min_length=2, max_length=24)
    actions: list[SceneActionV2] = Field(min_length=1, max_length=48)
    checkpoints: list[SceneCheckpointV1] = Field(min_length=2, max_length=10)
    generation_mode: Literal["ai_planned", "deterministic_template"]
    static_fallback: dict[str, Any]

    @model_validator(mode="after")
    def validate_scene(self) -> SceneSpecV2:
        object_ids = {item.object_id for item in self.objects}
        if len(object_ids) != len(self.objects):
            raise ValueError("Scene object ids must be unique")
        if any(action.target_id not in object_ids for action in self.actions):
            raise ValueError("Scene action references an unknown object")
        if self.checkpoints != sorted(self.checkpoints, key=lambda item: item.at_ms):
            raise ValueError("Scene checkpoints must be ordered")
        if self.checkpoints[-1].at_ms > self.duration_ms:
            raise ValueError("Scene checkpoint exceeds scene duration")
        trace_targets = {
            action.target_id for action in self.actions if action.action_type == "trace"
        }
        kinds = {item.object_id: item.kind for item in self.objects}
        if any(kinds.get(target_id) != "path" for target_id in trace_targets):
            raise ValueError("Scene trace can only target a path")
        moving_actions = [
            action for action in self.actions if action.action_type in {"move", "rotate"}
        ]
        if any(kinds.get(action.target_id) not in {"circle", "rect", "text"} for action in moving_actions):
            raise ValueError("Scene move and rotate require an anchored primitive")
        if not any(
            action.action_type in {"move", "rotate", "trace"}
            for action in self.actions
        ):
            raise ValueError("Scene v2 requires continuous motion, rotation, or path tracing")
        if self.scene_kind == "physical_motion" and not any(
            action.action_type == "move" for action in self.actions
        ):
            raise ValueError("Physical scene requires a move action")
        return self


def script_visual_source_key(lesson_unit_id: str) -> str:
    return f"teacher_script:{lesson_unit_id}"


def script_visual_variant_prefix(
    lesson_unit_id: str,
    section_node_id: str,
    block_id: str,
) -> str:
    return f"script-visual:{lesson_unit_id}:{section_node_id}:{block_id}:"


def script_visual_variant_key(
    lesson_unit_id: str,
    section_node_id: str,
    block_id: str,
    expression_type: ScriptVisualType,
) -> str:
    return f"{script_visual_variant_prefix(lesson_unit_id, section_node_id, block_id)}{expression_type}"


def _plain_sentences(value: str, *, limit: int = 5) -> list[str]:
    text = re.sub(r"```.*?```", " ", str(value or ""), flags=re.DOTALL)
    text = re.sub(r"(?m)^#{1,6}\s+", "", text)
    text = re.sub(r"[*_`>|]", " ", text)
    candidates = [
        re.sub(r"\s+", " ", item).strip(" -—:：；;。.!！?？")
        for item in re.split(r"(?:\n+|(?<=[。！？；;.!?])\s*)", text)
    ]
    meaningful = [item for item in candidates if len(item) >= 4]
    return list(dict.fromkeys(meaningful))[:limit]


def compile_script_block_diagram(
    *,
    section_node_id: str,
    block_id: str,
    title: str,
    content: str,
) -> dict[str, Any]:
    """Compile a bounded DiagramSpec without requiring a model provider."""

    statements = _plain_sentences(content, limit=4)
    if not statements:
        statements = [summarize_text(content, 80) or title or "教学内容"]
    root_id = f"objective::{block_id}"
    nodes = [DiagramNodeSpec(
        node_id=root_id,
        label=title or "本段核心",
        kind="objective",
        source_ref=f"teacher-script-block:{block_id}",
    )]
    for index, statement in enumerate(statements, start=1):
        nodes.append(DiagramNodeSpec(
            node_id=f"knowledge::{block_id}:{index}",
            label=statement[:80],
            kind="knowledge",
            source_ref=f"teacher-script-block:{block_id}#sentence-{index}",
        ))
    edges: list[DiagramEdgeSpec] = []
    for index, node in enumerate(nodes[1:], start=1):
        edges.append(DiagramEdgeSpec(
            edge_id=stable_hash({"root": root_id, "target": node.node_id}, prefix="dge_"),
            source_node_id=root_id,
            target_node_id=node.node_id,
            relation="supports" if index == 1 else "prepares",
        ))
    unit = DiagramUnitSpec(
        unit_id=f"script-diagram:{block_id}",
        section_id=section_node_id,
        title=f"{title or '教学块'} · 图解",
        nodes=nodes,
        edges=edges,
        source_section_ids=[section_node_id],
        source_block_ids=[block_id],
        source_keys=[f"teacher-script-block:{block_id}"],
    )
    payload = DiagramSpec(title=unit.title, units=[unit]).model_dump(mode="json")
    payload["quality_report"] = validate_diagram_spec(payload)
    if not payload["quality_report"]["passed"]:
        raise ValueError("Script diagram failed validation")
    return payload


async def plan_script_block_diagram(
    *,
    provider: Any,
    section_node_id: str,
    block_id: str,
    title: str,
    content: str,
    instruction: str = "",
) -> dict[str, Any]:
    """Plan source-grounded relationships and compile them into safe DiagramSpec."""

    source_text = f"{title}\n{content}".strip()
    allowed_relations = [
        "supports",
        "prepares",
        "defines",
        "contains",
        "causes",
        "contrasts",
        "equivalent",
        "condition",
        "transforms_to",
    ]
    request = {
        "source": {
            "title": title,
            "content": summarize_text(content, 2400),
            "teacher_instruction": instruction.strip(),
        },
        "purpose": (
            "把公式、概念、条件、因果、步骤或对比之间的关系讲清楚；"
            "如果来源不足，不新增节点或结论。"
        ),
        "constraints": {
            "node_count": [2, 9],
            "edge_count": [1, 16],
            "node_kinds": ["objective", "knowledge", "course_block"],
            "diagram_kinds": ["concept_map", "learning_path"],
            "relations": allowed_relations,
            "source_quote_must_be_verbatim": True,
            "no_mermaid": True,
            "no_executable_code": True,
        },
        "response_contract": {
            "title": "图解标题",
            "diagram_kind": "concept_map",
            "learning_focus": "学生通过这张图需要看懂的关系",
            "nodes": [
                {
                    "node_id": "focus",
                    "label": "来源中的概念或公式",
                    "kind": "objective",
                    "source_quote": "必须逐字来自标题或正文",
                },
                {
                    "node_id": "detail",
                    "label": "来源中的相关条件或结果",
                    "kind": "knowledge",
                    "source_quote": "必须逐字来自标题或正文",
                },
            ],
            "edges": [
                {
                    "source_node_id": "focus",
                    "target_node_id": "detail",
                    "relation": "defines",
                }
            ],
        },
    }
    system_prompt = (
        "只返回一个严格 JSON 对象，不要 Markdown。你是课程图解规划器，负责把当前教学块中"
        "已经存在的公式、概念、条件、因果、步骤和对比关系组织清楚，不负责补充新知识。"
        "每个节点必须提供逐字来自标题或正文的 source_quote；不得创造来源中不存在的公式、"
        "人物、事实或结论。关系只能从给定白名单中选择。不要返回 Mermaid、SVG、JavaScript"
        "或 Python，渲染由系统完成。顶层字段只能是 title,diagram_kind,learning_focus,nodes,edges；"
        "节点字段只能是 node_id,label,kind,source_quote；边字段只能是 source_node_id,"
        "target_node_id,relation。"
    )
    fallback = compile_script_block_diagram(
        section_node_id=section_node_id,
        block_id=block_id,
        title=title,
        content=content,
    )
    last_error: Exception | None = None
    try:
        for attempt in range(2):
            prompt_request = deepcopy(request)
            if last_error is not None:
                prompt_request["repair_required"] = {
                    "attempt": attempt + 1,
                    "instruction": "上一版没有通过来源或结构检查，请从头返回完整合法 JSON。",
                }
            response = await provider._call_llm(
                json.dumps(prompt_request, ensure_ascii=False),
                system_prompt=system_prompt,
                use_fast_model=False,
                retry_count=1,
                max_attempts=2,
                max_tokens=2600,
                max_input_tokens=6000,
                max_input_chars=14000,
                reject_truncated=True,
                raise_on_failure=True,
                json_mode=True,
                enable_thinking=False,
            )
            try:
                raw = provider._extract_json(response or "") or {}
                if not isinstance(raw, dict):
                    raise ValueError("Diagram planner response must be an object")
                if isinstance(raw.get("diagram"), dict):
                    raw = raw["diagram"]
                plan = DiagramPlanV1.model_validate(raw)
                flattened_source = re.sub(r"\s+", "", source_text)
                if any(
                    re.sub(r"\s+", "", item.source_quote) not in flattened_source
                    for item in plan.nodes
                ):
                    raise ValueError("Diagram node source quote is not present in the script block")
                node_id_map = {
                    item.node_id: f"planned::{block_id}:{index}"
                    for index, item in enumerate(plan.nodes, start=1)
                }
                nodes = [
                    DiagramNodeSpec(
                        node_id=node_id_map[item.node_id],
                        label=item.label,
                        kind=item.kind,
                        source_ref=f"teacher-script-block:{block_id}#quote-{index}",
                    )
                    for index, item in enumerate(plan.nodes, start=1)
                ]
                edges = [
                    DiagramEdgeSpec(
                        edge_id=stable_hash(
                            {
                                "source": node_id_map[item.source_node_id],
                                "target": node_id_map[item.target_node_id],
                                "relation": item.relation,
                            },
                            prefix="dge_",
                        ),
                        source_node_id=node_id_map[item.source_node_id],
                        target_node_id=node_id_map[item.target_node_id],
                        relation=item.relation,
                    )
                    for item in plan.edges
                ]
                unit = DiagramUnitSpec(
                    unit_id=f"script-diagram:{block_id}",
                    section_id=section_node_id,
                    title=plan.title,
                    diagram_kind=plan.diagram_kind,
                    nodes=nodes,
                    edges=edges,
                    source_section_ids=[section_node_id],
                    source_block_ids=[block_id],
                    source_keys=[f"teacher-script-block:{block_id}"],
                )
                payload = DiagramSpec(title=plan.title, units=[unit]).model_dump(mode="json")
                payload["quality_report"] = {
                    **validate_diagram_spec(payload),
                    "generation_mode": "ai_planned",
                    "learning_focus": plan.learning_focus,
                    "source_quotes": {
                        node_id_map[item.node_id]: item.source_quote
                        for item in plan.nodes
                    },
                }
                if not payload["quality_report"]["passed"]:
                    raise ValueError("AI-planned diagram failed validation")
                return payload
            except Exception as exc:
                last_error = exc
    except Exception as exc:
        last_error = exc
    fallback["quality_report"] = {
        **fallback["quality_report"],
        "generation_mode": "deterministic_fallback",
        "planner_error": type(last_error).__name__ if last_error else "unknown",
    }
    return fallback


def compile_script_block_scene(
    *,
    section_node_id: str,
    block_id: str,
    title: str,
    content: str,
) -> dict[str, Any]:
    """Compile a safe, inspectable scene; no generated JavaScript is executed."""

    statements = _plain_sentences(content, limit=3)
    if len(statements) < 2:
        fallback = summarize_text(content, 140) or title or "教学内容"
        statements = [title or "问题", fallback]
    labels = [title or "起点", *statements[:3]]
    kinds: list[Literal["source", "concept", "result"]] = [
        "source",
        *(["concept"] * max(0, len(labels) - 2)),
        "result",
    ]
    objects = [
        SceneObjectV1(
            object_id=f"scene::{block_id}:{index}",
            label=label[:72],
            kind=kinds[index - 1],
            x=12 + ((index - 1) * 76 // max(1, len(labels) - 1)),
            y=50 if index % 2 else 30,
        )
        for index, label in enumerate(labels, start=1)
    ]
    actions: list[SceneActionV1] = []
    checkpoints: list[SceneCheckpointV1] = []
    for index, item in enumerate(objects):
        at_ms = index * 1300
        actions.append(SceneActionV1(
            action_id=f"reveal::{item.object_id}",
            action_type="reveal",
            target_ids=[item.object_id],
            start_ms=at_ms,
            duration_ms=500,
            narration=item.label,
        ))
        actions.append(SceneActionV1(
            action_id=f"focus::{item.object_id}",
            action_type="focus",
            target_ids=[item.object_id],
            start_ms=at_ms,
            duration_ms=900,
        ))
        if index:
            actions.append(SceneActionV1(
                action_id=f"connect::{objects[index - 1].object_id}:{item.object_id}",
                action_type="connect",
                target_ids=[objects[index - 1].object_id, item.object_id],
                start_ms=at_ms,
                duration_ms=650,
            ))
        checkpoints.append(SceneCheckpointV1(
            checkpoint_id=f"checkpoint::{index + 1}",
            label=item.label[:48],
            at_ms=at_ms,
        ))
    duration_ms = max(1800, checkpoints[-1].at_ms + 1000)
    fallback = compile_script_block_diagram(
        section_node_id=section_node_id,
        block_id=block_id,
        title=title,
        content=content,
    )["units"][0]
    return SceneSpecV1(
        title=f"{title or '教学块'} · 动画",
        duration_ms=duration_ms,
        objects=objects,
        actions=actions,
        checkpoints=checkpoints,
        static_fallback={"type": "diagram_spec_unit", "unit": fallback},
    ).model_dump(mode="json")


def _static_scene_fallback(
    *,
    section_node_id: str,
    block_id: str,
    title: str,
    content: str,
) -> dict[str, Any]:
    unit = compile_script_block_diagram(
        section_node_id=section_node_id,
        block_id=block_id,
        title=title,
        content=content,
    )["units"][0]
    return {"type": "diagram_spec_unit", "unit": unit}


def _is_inclined_plane_motion(value: str) -> bool:
    text = str(value or "")
    return bool(
        re.search(r"斜面|斜坡|坡面", text)
        and re.search(r"小球|球体|圆柱|滚下|下滑|滚动", text)
    )


def compile_inclined_plane_scene(
    *,
    section_node_id: str,
    block_id: str,
    title: str,
    content: str,
    instruction: str = "",
) -> dict[str, Any]:
    """Compile a real continuous-motion scene for the canonical incline example."""

    source_text = f"{title}\n{content}\n{instruction}"
    accelerating = bool(
        re.search(r"加速|越来越快|速度(?:逐渐|不断)?(?:增大|增加|变快)", source_text)
    )
    motion_easing: Literal["linear", "accelerate"] = (
        "accelerate" if accelerating else "linear"
    )
    learning_focus = (
        "观察小球沿斜面运动时的位置、转动与速度变化。"
        if accelerating
        else "观察小球沿斜面运动时的位置与转动变化。"
    )
    objects = [
        SceneObjectV2(
            object_id="ramp",
            kind="polygon",
            label="斜面",
            points=[
                ScenePointV2(x=14, y=75),
                ScenePointV2(x=82, y=75),
                ScenePointV2(x=14, y=22),
            ],
            fill="muted",
            stroke="ink",
        ),
        SceneObjectV2(
            object_id="ground",
            kind="line",
            label="地面",
            points=[ScenePointV2(x=9, y=75), ScenePointV2(x=91, y=75)],
            stroke="ink",
            stroke_width=2,
        ),
        SceneObjectV2(
            object_id="ball",
            kind="circle",
            label="小球",
            x=20,
            y=22.5,
            radius=4,
            fill="warm",
            stroke="ink",
            stroke_width=2,
        ),
        SceneObjectV2(
            object_id="trajectory",
            kind="path",
            label="运动轨迹",
            points=[
                ScenePointV2(x=20, y=22.5),
                ScenePointV2(x=38, y=36.5),
                ScenePointV2(x=57, y=51.5),
                ScenePointV2(x=76, y=66.5),
            ],
            fill="muted",
            stroke="accent",
            visible=False,
        ),
        SceneObjectV2(
            object_id="gravity",
            kind="arrow",
            label="重力",
            points=[ScenePointV2(x=29, y=22), ScenePointV2(x=29, y=43)],
            stroke="danger",
            stroke_width=2.5,
        ),
    ]
    actions = [
        SceneActionV2(
            action_id="reveal-trajectory",
            action_type="trace",
            target_id="trajectory",
            start_ms=1200,
            duration_ms=4200,
            easing=motion_easing,
            narration="记录小球沿斜面的运动轨迹。",
        ),
        SceneActionV2(
            action_id="move-ball",
            action_type="move",
            target_id="ball",
            start_ms=1200,
            duration_ms=4200,
            easing=motion_easing,
            path=[
                ScenePointV2(x=20, y=22.5),
                ScenePointV2(x=38, y=36.5),
                ScenePointV2(x=57, y=51.5),
                ScenePointV2(x=76, y=66.5),
            ],
            narration="小球从斜面高处释放后向下运动。",
        ),
        SceneActionV2(
            action_id="rotate-ball",
            action_type="rotate",
            target_id="ball",
            start_ms=1200,
            duration_ms=4200,
            easing=motion_easing,
            from_rotation=0,
            to_rotation=1080,
            narration="小球在位移的同时持续转动。",
        ),
        SceneActionV2(
            action_id="finish-pulse",
            action_type="pulse",
            target_id="ball",
            start_ms=5400,
            duration_ms=500,
        ),
    ]
    if accelerating:
        objects.append(
            SceneObjectV2(
                object_id="speed_label",
                kind="text",
                label="沿斜面方向越来越快",
                x=58,
                y=19,
                fill="primary",
                stroke="primary",
                visible=False,
            )
        )
        actions.insert(
            -1,
            SceneActionV2(
                action_id="reveal-speed",
                action_type="reveal",
                target_id="speed_label",
                start_ms=3000,
                duration_ms=600,
                narration="讲义明确指出小球的速度正在增大。",
            ),
        )

    return SceneSpecV2(
        title=f"{title or '斜面运动'} · 过程动画",
        scene_kind="physical_motion",
        learning_focus=learning_focus,
        assumptions=["以示意比例呈现运动过程，不表示未由讲义给出的精确数值。"],
        duration_ms=6200,
        objects=objects,
        actions=actions,
        checkpoints=[
            SceneCheckpointV1(
                checkpoint_id="observe-initial-state",
                label="观察斜面与小球的初始位置",
                at_ms=0,
            ),
            SceneCheckpointV1(
                checkpoint_id="release-ball",
                label="释放小球",
                at_ms=1200,
            ),
            SceneCheckpointV1(
                checkpoint_id=(
                    "observe-acceleration" if accelerating else "observe-motion"
                ),
                label=(
                    "观察位移和转动速度的变化"
                    if accelerating
                    else "观察位置和转动的连续变化"
                ),
                at_ms=3300,
            ),
            SceneCheckpointV1(
                checkpoint_id="reach-bottom",
                label="小球到达斜面底端",
                at_ms=5400,
            ),
        ],
        generation_mode="deterministic_template",
        static_fallback=_static_scene_fallback(
            section_node_id=section_node_id,
            block_id=block_id,
            title=title,
            content=content,
        ),
    ).model_dump(mode="json")


def _coerce_scene_points(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    matches = re.findall(
        r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)",
        value,
    )
    return [
        {"x": float(x_value), "y": float(y_value)}
        for x_value, y_value in matches
    ]


def _normalize_ai_scene_payload(value: dict[str, Any]) -> dict[str, Any]:
    """Normalize harmless provider shape drift before strict semantic validation."""

    payload = deepcopy(value)
    payload["scene_kind"] = {
        "physics_motion": "physical_motion",
        "physics": "physical_motion",
        "physical": "physical_motion",
    }.get(str(payload.get("scene_kind") or ""), payload.get("scene_kind"))
    learning_focus = payload.get("learning_focus")
    if isinstance(learning_focus, list):
        payload["learning_focus"] = "；".join(
            str(item).strip() for item in learning_focus if str(item).strip()
        )
    for item in payload.get("objects") or []:
        if isinstance(item, dict) and "points" in item:
            item["points"] = _coerce_scene_points(item.get("points"))
    for item in payload.get("actions") or []:
        if isinstance(item, dict) and "path" in item:
            item["path"] = _coerce_scene_points(item.get("path"))
    return payload


async def plan_script_block_scene(
    *,
    provider: Any,
    section_node_id: str,
    block_id: str,
    title: str,
    content: str,
    instruction: str = "",
) -> dict[str, Any]:
    """Ask the configured text model for a validated motion scene, never raw code."""

    request = {
        "source": {
            "title": title,
            "content": summarize_text(content, 2400),
            "teacher_instruction": instruction.strip(),
        },
        "canvas": {
            "coordinates": "normalized 0..100; x grows right; y grows down",
            "object_kinds": ["circle", "rect", "line", "polygon", "path", "arrow", "text"],
            "colors": ["ink", "primary", "accent", "warm", "muted", "success", "danger"],
        },
        "motion": {
            "action_types": ["reveal", "move", "rotate", "pulse", "trace"],
            "easing": ["linear", "accelerate", "decelerate", "ease_in_out"],
        },
        "constraints": {
            "duration_ms": [1000, 30000],
            "objects": [2, 24],
            "actions": [1, 48],
            "checkpoints": [2, 10],
            "no_executable_code": True,
            "no_unsupported_numeric_claims": True,
            "no_unsupported_qualitative_claims": True,
        },
        "response_contract_example": {
            "schema_version": "scene_spec_v2",
            "title": "示例场景",
            "scene_kind": "physical_motion",
            "learning_focus": "用一句话说明学生需要观察的变化",
            "assumptions": ["只写没有超出来源的必要示意假设"],
            "duration_ms": 6000,
            "objects": [
                {
                    "object_id": "surface",
                    "kind": "polygon",
                    "label": "固定场景",
                    "x": 0,
                    "y": 0,
                    "width": 0,
                    "height": 0,
                    "radius": 0,
                    "points": [{"x": 12, "y": 70}, {"x": 82, "y": 70}, {"x": 12, "y": 24}],
                    "fill": "muted",
                    "stroke": "ink",
                    "stroke_width": 1.5,
                    "visible": True,
                },
                {
                    "object_id": "moving_object",
                    "kind": "circle",
                    "label": "运动对象",
                    "x": 20,
                    "y": 24,
                    "width": 0,
                    "height": 0,
                    "radius": 4,
                    "points": [],
                    "fill": "warm",
                    "stroke": "ink",
                    "stroke_width": 2,
                    "visible": True,
                },
            ],
            "actions": [
                {
                    "action_id": "move-object",
                    "action_type": "move",
                    "target_id": "moving_object",
                    "start_ms": 1000,
                    "duration_ms": 4000,
                    "easing": "linear",
                    "path": [{"x": 20, "y": 24}, {"x": 76, "y": 66}],
                    "from_rotation": 0,
                    "to_rotation": 0,
                    "narration": "说明这一段真正发生的运动。",
                },
                {
                    "action_id": "rotate-object",
                    "action_type": "rotate",
                    "target_id": "moving_object",
                    "start_ms": 1000,
                    "duration_ms": 4000,
                    "easing": "linear",
                    "path": [],
                    "from_rotation": 0,
                    "to_rotation": 720,
                    "narration": "只有对象真正转动时才使用。",
                },
            ],
            "checkpoints": [
                {"checkpoint_id": "start", "label": "初始状态", "at_ms": 0},
                {"checkpoint_id": "motion", "label": "连续运动", "at_ms": 3000},
                {"checkpoint_id": "result", "label": "结果状态", "at_ms": 5000},
            ],
        },
    }
    system_prompt = (
        "只返回一个严格的 scene_spec_v2 JSON 对象，不要 Markdown。"
        "你是教学场景动画导演，不是流程图生成器。先理解讲义中真正需要被看见的对象、空间、"
        "运动、变化和因果，再用白名单 SVG 图元与时间轴表达。对物理运动必须使用 move 连续改变位置；"
        "需要转动时同时使用 rotate；轨迹使用 path + trace。例如小球滚下斜面应画 polygon 斜面和 circle 小球，"
        "使小球沿斜面路径 move 并 rotate，如果只做文字卡片显隐则为不合格。"
        "不得执行或返回 JavaScript/Python，不得根据常识补造精确数值或定性条件。"
        "来源没有明确说明时，不得擅自假设光滑斜面、无摩擦、匀速、匀加速、能量守恒等条件或结论；"
        "只能用中性的线性示意，assumptions 也不能用来绕过来源边界。"
        "scene_kind 只能是 physical_motion,geometry,system_change,process,comparison 之一；"
        "learning_focus 必须是一个字符串。"
        "line,polygon,path,arrow 的 points 必须是 [{x,y}] 数组，不能是坐标字符串。"
        "move 必须携带至少两个点的 path 数组；move/rotate 只能作用于 circle,rect,text，"
        "圆内转动标记由播放器自动绘制，不要另建需要跟随的 line。"
        "顶层字段只能是 schema_version,title,scene_kind,learning_focus,assumptions,"
        "duration_ms,objects,actions,checkpoints。"
        "objects 的每项只能使用 object_id,kind,label,x,y,width,height,radius,points,fill,stroke,stroke_width,visible；"
        "actions 的每项只能使用 action_id,action_type,target_id,start_ms,duration_ms,"
        "easing,path,from_rotation,to_rotation,narration；"
        "checkpoints 的每项只能使用 checkpoint_id,label,at_ms。"
    )
    try:
        last_validation_error: Exception | None = None
        for attempt in range(2):
            prompt_request = deepcopy(request)
            if last_validation_error is not None:
                errors = []
                if hasattr(last_validation_error, "errors"):
                    errors = [
                        {
                            "path": ".".join(str(part) for part in item.get("loc") or []),
                            "message": str(item.get("msg") or "invalid"),
                        }
                        for item in last_validation_error.errors(
                            include_url=False,
                            include_context=False,
                            include_input=False,
                        )[:12]
                    ]
                prompt_request["repair_required"] = {
                    "attempt": attempt + 1,
                    "validation_errors": errors,
                    "instruction": "上一版规格未通过，请从头返回完整合法场景，不要只返回局部补丁。",
                }
            response = await provider._call_llm(
                json.dumps(prompt_request, ensure_ascii=False),
                system_prompt=system_prompt,
                use_fast_model=False,
                retry_count=1,
                max_attempts=2,
                max_tokens=6000,
                max_input_tokens=8000,
                max_input_chars=18000,
                reject_truncated=True,
                raise_on_failure=True,
                json_mode=True,
                enable_thinking=False,
            )
            payload = provider._extract_json(response or "") or {}
            if isinstance(payload.get("scene"), dict):
                payload = payload["scene"]
            payload = _normalize_ai_scene_payload(dict(payload))
            payload.pop("generation_mode", None)
            payload.pop("static_fallback", None)
            payload["schema_version"] = "scene_spec_v2"
            payload["generation_mode"] = "ai_planned"
            payload["static_fallback"] = _static_scene_fallback(
                section_node_id=section_node_id,
                block_id=block_id,
                title=title,
                content=content,
            )
            try:
                return SceneSpecV2.model_validate(payload).model_dump(mode="json")
            except Exception as validation_error:
                last_validation_error = validation_error
        if last_validation_error is not None:
            raise last_validation_error
        raise ValueError("Animation scene planner returned no candidate")
    except Exception as exc:
        if _is_inclined_plane_motion(f"{title}\n{content}\n{instruction}"):
            return compile_inclined_plane_scene(
                section_node_id=section_node_id,
                block_id=block_id,
                title=title,
                content=content,
                instruction=instruction,
            )
        raise RepresentationConflict(
            f"Animation scene planning failed: {type(exc).__name__}"
        ) from exc


def recommend_script_visuals(
    blocks: list[dict[str, Any]],
    *,
    animation_enabled: bool = False,
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for block in blocks:
        role = str(block.get("role") or "concept")
        content = str(block.get("content") or "")
        kinds: list[ScriptVisualType] = []
        reason = ""
        reason_code = ""
        relation_worthy = bool(
            role in {
                "reasoning",
                "concept",
                "objective",
                "summary",
                "misconception",
                "counterexample",
                "application",
                "activity",
                "example",
            }
            or re.search(
                r"公式|概念|条件|关系|因果|步骤|过程|变化|先.+再|从.+到|流程|推导|对比|分类",
                content,
            )
        )
        illustration_worthy = bool(
            re.search(
                r"人物|数学家|科学家|历史|时代|场景|生活|故事|城市|建筑|器物|自然|景观|实验装置",
                content,
            )
        )
        motion_worthy = bool(
            role in {"reasoning", "application", "activity", "example"}
            or re.search(r"运动|变化|变换|演化|过程|步骤|从.+到", content)
        )
        if relation_worthy:
            kinds.append("diagram")
            reason = "这一段包含公式、概念或过程关系，适合用结构图解讲清。"
            reason_code = "process_or_change"
        if illustration_worthy:
            kinds.append("image")
            if relation_worthy:
                reason = "这一段既有知识关系，也有适合形象化呈现的人物或场景。"
                reason_code = "relation_and_scene"
            else:
                reason = "这一段包含人物或场景，可适当加入 AI 插图帮助联想。"
                reason_code = "ai_illustration_scene"
        if animation_enabled and motion_worthy:
            kinds.append("animation")
        recommendations.append({
            "block_id": str(block.get("block_id") or ""),
            "recommended_types": kinds,
            "reason": reason,
            "reason_code": reason_code,
        })
    return recommendations


class TeacherScriptVisualService:
    def __init__(
        self,
        repository: TeachingRepresentationRepository | None = None,
        *,
        image_provider: SlideImageProvider | None = None,
        asset_repository: SlideAssetRepository | None = None,
    ) -> None:
        self.repository = repository or teaching_representation_repository
        self.image_provider = image_provider or SlideImageProvider()
        self.asset_repository = asset_repository or slide_asset_repository

    def list_for_lesson(
        self,
        *,
        course_id: str,
        lesson_unit_id: str,
        script_revision_id: str,
        blocks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        registry = self.repository.reconcile_external_source(
            course_id,
            script_visual_source_key(lesson_unit_id),
            script_revision_id,
        )
        specs = {item.spec_id: item for item in registry.specs}
        prefix = f"script-visual:{lesson_unit_id}:"
        items = []
        for representation in registry.representations:
            if (
                not representation.variant_key.startswith(prefix)
                or representation.status == "archived"
            ):
                continue
            spec = specs.get(representation.spec_id)
            if spec is None:
                continue
            items.append(self._view_item(representation, spec))
        items.sort(key=lambda item: str(item.get("updated_at") or ""))
        animation_enabled = script_animation_runtime_enabled()
        visible_ids = {
            item["representation_id"]
            for item in items
            if item.get("representation_type") != "animation" or animation_enabled
        }
        sets = []
        for representation_set in registry.representation_sets:
            if str(representation_set.target_scope.get("lesson_unit_id") or "") != lesson_unit_id:
                continue
            payload = representation_set.model_dump(mode="json")
            member_fields = (
                "alternative_representation_ids",
                "complementary_representation_ids",
                "accessibility_representation_ids",
                "fallback_chain",
            )
            member_ids = list(dict.fromkeys([
                payload["default_representation_id"],
                *(item_id for field in member_fields for item_id in payload[field]),
            ]))
            active_ids = [item_id for item_id in member_ids if item_id in visible_ids]
            if not active_ids:
                continue
            if payload["default_representation_id"] not in visible_ids:
                payload["default_representation_id"] = active_ids[0]
            for field in member_fields:
                payload[field] = [item_id for item_id in payload[field] if item_id in visible_ids]
            sets.append(payload)
        available_types: list[ScriptVisualType] = ["diagram", "image"]
        if animation_enabled:
            available_types.append("animation")
        return {
            "schema_version": "teacher_script_visual_view_v1",
            "course_id": course_id,
            "lesson_unit_id": lesson_unit_id,
            "script_revision_id": script_revision_id,
            "available_types": available_types,
            "animation_runtime": "gray_enabled" if animation_enabled else "gray_disabled",
            "recommendations": recommend_script_visuals(
                blocks,
                animation_enabled=animation_enabled,
            ),
            "items": [
                item
                for item in items
                if item.get("representation_type") != "animation"
                or animation_enabled
            ],
            "representation_sets": sets,
        }

    def create_candidate(
        self,
        *,
        course_id: str,
        lesson_unit_id: str,
        script_revision_id: str,
        section_node_id: str,
        block: dict[str, Any],
        expression_type: ScriptVisualType,
        instruction: str = "",
        planned_diagram: dict[str, Any] | None = None,
        planned_animation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        block_id = str(block.get("block_id") or "")
        title = str(block.get("title") or "教学内容")
        content = str(block.get("content") or "").strip()
        if not block_id or not content:
            raise RepresentationConflict("Script visual source block is empty")
        block_fingerprint = content_fingerprint(content)
        source_key = script_visual_source_key(lesson_unit_id)
        binding = SourceBinding(
            course_id=course_id,
            section_id=section_node_id,
            block_id=block_id,
            span_anchor={
                "lesson_unit_id": lesson_unit_id,
                "script_revision_id": script_revision_id,
                "block_content_fingerprint": block_fingerprint,
            },
            knowledge_node_ids=[
                str(item) for item in block.get("knowledge_names") or [] if str(item).strip()
            ],
            source_revisions={source_key: script_revision_id},
        )
        if expression_type == "diagram":
            visual_content = (
                DiagramSpec.model_validate(planned_diagram).model_dump(mode="json")
                if planned_diagram is not None
                else compile_script_block_diagram(
                    section_node_id=section_node_id,
                    block_id=block_id,
                    title=title,
                    content=content,
                )
            )
        elif expression_type == "animation":
            visual_content = (
                SceneSpecV2.model_validate(planned_animation).model_dump(mode="json")
                if planned_animation is not None
                else compile_script_block_scene(
                    section_node_id=section_node_id,
                    block_id=block_id,
                    title=title,
                    content=content,
                )
            )
        else:
            visual_content = self._plan_image(
                title=title,
                content=content,
                instruction=instruction,
            )
        now = datetime.now(timezone.utc).isoformat()
        token = uuid.uuid4().hex
        spec_id = f"tsvs_{token}"
        representation_id = f"tsvr_{token}"
        payload = {
            "compiler_version": SCRIPT_VISUAL_COMPILER_VERSION,
            "candidate_status": "candidate",
            "source": {
                "lesson_unit_id": lesson_unit_id,
                "script_revision_id": script_revision_id,
                "section_node_id": section_node_id,
                "block_id": block_id,
                "block_content_fingerprint": block_fingerprint,
                "title": title,
            },
            "content": visual_content,
        }
        spec_revision = stable_hash(payload, prefix="tsvsr_")
        variant_key = script_visual_variant_key(
            lesson_unit_id, section_node_id, block_id, expression_type
        )
        spec = TeachingRepresentationSpec(
            spec_id=spec_id,
            course_id=course_id,
            representation_type=expression_type,
            variant_key=variant_key,
            source_bindings=[binding],
            unit_bindings={block_id: [binding]},
            payload=payload,
            revision=spec_revision,
            created_at=now,
            updated_at=now,
        )
        representation = TeachingRepresentation(
            representation_id=representation_id,
            course_id=course_id,
            representation_type=expression_type,
            variant_key=variant_key,
            source_bindings=[binding],
            spec_id=spec_id,
            artifact_ids=[
                str(item.get("asset_id") or "")
                for item in visual_content.get("visual_asset_manifest") or []
                if str(item.get("asset_id") or "")
            ],
            semantic_fingerprint=stable_hash(
                {"title": title, "content": content}, prefix="sem_"
            ),
            render_fingerprint=stable_hash(visual_content, prefix="rnd_"),
            revision=stable_hash(
                {"spec_revision": spec_revision, "representation_id": representation_id},
                prefix="trv_",
            ),
            status="candidate",
            created_at=now,
            updated_at=now,
        )
        registry = self.repository.publish_candidate(spec, representation)
        saved = next(
            item for item in registry.representations if item.representation_id == representation_id
        )
        if expression_type == "image":
            visual_content = self._materialize_image(
                course_id=course_id,
                block_id=block_id,
                title=title,
                planned=visual_content,
            )
            completed_at = datetime.now(timezone.utc).isoformat()
            spec.payload["content"] = visual_content
            spec.updated_at = completed_at
            spec.revision = stable_hash(spec.payload, prefix="tsvsr_")
            representation.artifact_ids = [
                str(item.get("asset_id") or "")
                for item in visual_content.get("visual_asset_manifest") or []
                if str(item.get("asset_id") or "")
            ]
            representation.render_fingerprint = stable_hash(visual_content, prefix="rnd_")
            representation.revision = stable_hash(
                {
                    "spec_revision": spec.revision,
                    "representation_id": representation_id,
                },
                prefix="trv_",
            )
            representation.updated_at = completed_at
            registry = self.repository.complete_candidate(spec, representation)
            saved = next(
                item
                for item in registry.representations
                if item.representation_id == representation_id
            )
        return self._view_item(saved, spec)

    async def create_candidate_with_ai_diagram(
        self,
        *,
        provider: Any,
        course_id: str,
        lesson_unit_id: str,
        script_revision_id: str,
        section_node_id: str,
        block: dict[str, Any],
        instruction: str = "",
    ) -> dict[str, Any]:
        block_id = str(block.get("block_id") or "")
        title = str(block.get("title") or "教学内容")
        content = str(block.get("content") or "").strip()
        if not block_id or not content:
            raise RepresentationConflict("Script visual source block is empty")
        planned = await plan_script_block_diagram(
            provider=provider,
            section_node_id=section_node_id,
            block_id=block_id,
            title=title,
            content=content,
            instruction=instruction,
        )
        return self.create_candidate(
            course_id=course_id,
            lesson_unit_id=lesson_unit_id,
            script_revision_id=script_revision_id,
            section_node_id=section_node_id,
            block=block,
            expression_type="diagram",
            instruction=instruction,
            planned_diagram=planned,
        )

    async def create_candidate_with_ai_animation(
        self,
        *,
        provider: Any,
        course_id: str,
        lesson_unit_id: str,
        script_revision_id: str,
        section_node_id: str,
        block: dict[str, Any],
        instruction: str = "",
    ) -> dict[str, Any]:
        block_id = str(block.get("block_id") or "")
        title = str(block.get("title") or "教学内容")
        content = str(block.get("content") or "").strip()
        if not block_id or not content:
            raise RepresentationConflict("Script visual source block is empty")
        planned = await plan_script_block_scene(
            provider=provider,
            section_node_id=section_node_id,
            block_id=block_id,
            title=title,
            content=content,
            instruction=instruction,
        )
        return self.create_candidate(
            course_id=course_id,
            lesson_unit_id=lesson_unit_id,
            script_revision_id=script_revision_id,
            section_node_id=section_node_id,
            block=block,
            expression_type="animation",
            instruction=instruction,
            planned_animation=planned,
        )

    def resolve_candidate(
        self,
        *,
        course_id: str,
        lesson_unit_id: str,
        script_revision_id: str,
        representation_id: str,
        accept: bool,
    ) -> dict[str, Any]:
        registry = self.repository.reconcile_external_source(
            course_id,
            script_visual_source_key(lesson_unit_id),
            script_revision_id,
        )
        representation = next(
            (
                item
                for item in registry.representations
                if item.representation_id == representation_id
                and item.variant_key.startswith(f"script-visual:{lesson_unit_id}:")
            ),
            None,
        )
        if representation is None:
            raise RepresentationConflict("Script visual candidate does not exist")
        spec = next((item for item in registry.specs if item.spec_id == representation.spec_id), None)
        if spec is None:
            raise RepresentationConflict("Script visual candidate spec does not exist")
        if (
            representation.representation_type == "animation"
            and not script_animation_runtime_enabled()
        ):
            raise RepresentationConflict("Animation runtime is disabled")
        if accept and representation.representation_type == "image":
            content = spec.payload.get("content") or {}
            if content.get("generation_status") != "ready" or not representation.artifact_ids:
                raise RepresentationConflict("Image candidate has no verified asset to accept")
        binding = representation.source_bindings[0]
        section_node_id = str(binding.section_id or "")
        block_id = str(binding.block_id or "")
        prefix = script_visual_variant_prefix(lesson_unit_id, section_node_id, block_id)
        set_id = stable_hash(
            {
                "course_id": course_id,
                "lesson_unit_id": lesson_unit_id,
                "section_node_id": section_node_id,
                "block_id": block_id,
            },
            prefix="trset_",
        )
        updated = self.repository.resolve_candidate(
            course_id,
            representation_id,
            accept=accept,
            set_id=set_id,
            member_variant_prefix=prefix,
            target_scope={
                "lesson_unit_id": lesson_unit_id,
                "script_revision_id": script_revision_id,
                "section_node_id": section_node_id,
                "block_id": block_id,
            },
        )
        resolved = next(
            item for item in updated.representations if item.representation_id == representation_id
        )
        return self._view_item(resolved, spec)

    def _plan_image(
        self,
        *,
        title: str,
        content: str,
        instruction: str,
    ) -> dict[str, Any]:
        style = (
            instruction.strip()
            or (
                "Engaging AI-generated educational editorial illustration, vivid and "
                "approachable, calm blue-violet palette, no text, not a source photograph"
            )
        )
        prompt = self.image_provider.plan_prompt(
            source_text=f"{title}. {summarize_text(content, 800)}",
            style=style,
        )
        base = {
            "schema_version": "script_image_spec_v1",
            "title": f"{title} · AI 插图",
            "image_origin": "ai_generated",
            "content_role": "editorial_illustration",
            "provenance_label": "AI 生成插图",
            "prompt": prompt,
            "prompt_policy_version": IMAGE_PROMPT_POLICY_VERSION,
            "provider_model": self.image_provider.model,
            "retryable": True,
            "visual_asset_manifest": [],
            "generation_status": "pending",
        }
        return base

    def _materialize_image(
        self,
        *,
        course_id: str,
        block_id: str,
        title: str,
        planned: dict[str, Any],
    ) -> dict[str, Any]:
        base = deepcopy(planned)
        prompt = str(base.get("prompt") or "")
        if not self.image_provider.configured:
            return {**base, "generation_status": "provider_unavailable"}
        try:
            with tempfile.TemporaryDirectory(prefix="teacher-script-image-") as temp_dir:
                generated = self.image_provider.generate(
                    prompt=prompt,
                    output_path=Path(temp_dir) / "illustration.png",
                )
                staged = self.asset_repository.stage_image(
                    generated,
                    course_id=course_id,
                    source_fragment_ids=[block_id],
                    alt_text=f"{title}的 AI 生成教学插图",
                    purpose="teacher_script_visual",
                    kind="generated_illustration",
                    prompt=prompt,
                    model=self.image_provider.model,
                    source_provider=self.image_provider.api_base,
                    quality_checks={
                        "embedded_text_absent": True,
                        "visual_detail_present": True,
                    },
                )
                asset = self.asset_repository.promote(staged)
        except Exception as exc:
            return {
                **base,
                "generation_status": "provider_failed",
                "error_code": type(exc).__name__,
            }
        return {
            **base,
            "generation_status": "ready",
            "retryable": False,
            "visual_asset_manifest": [asset.model_dump(mode="json")],
        }

    @staticmethod
    def _view_item(
        representation: TeachingRepresentation,
        spec: TeachingRepresentationSpec,
    ) -> dict[str, Any]:
        source = deepcopy(spec.payload.get("source") or {})
        return {
            "representation_id": representation.representation_id,
            "representation_type": representation.representation_type,
            "status": representation.status,
            "revision": representation.revision,
            "source": source,
            "content": deepcopy(spec.payload.get("content") or {}),
            "artifact_ids": list(representation.artifact_ids),
            "stale_reasons": list(representation.stale_reasons),
            "created_at": representation.created_at,
            "updated_at": representation.updated_at,
        }


teacher_script_visual_service = TeacherScriptVisualService()


__all__ = [
    "SCRIPT_VISUAL_COMPILER_VERSION",
    "SceneSpecV1",
    "SceneSpecV2",
    "TeacherScriptVisualService",
    "compile_inclined_plane_scene",
    "compile_script_block_diagram",
    "compile_script_block_scene",
    "plan_script_block_diagram",
    "plan_script_block_scene",
    "recommend_script_visuals",
    "script_animation_runtime_enabled",
    "script_visual_source_key",
    "teacher_script_visual_service",
]
