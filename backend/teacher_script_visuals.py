"""Source-bound diagram, image, and animation candidates for teacher scripts."""

from __future__ import annotations

import json
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
from diagram_spec import DiagramEdgeSpec, DiagramNodeSpec, DiagramSpec, DiagramUnitSpec, validate_diagram_spec
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


def recommend_script_visuals(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for block in blocks:
        role = str(block.get("role") or "concept")
        content = str(block.get("content") or "")
        kinds: list[ScriptVisualType] = []
        reason = ""
        reason_code = ""
        if role in {"reasoning", "application", "activity", "example"} or re.search(
            r"步骤|过程|变化|先.+再|从.+到|流程|推导", content
        ):
            kinds = ["animation", "diagram"]
            reason = "这一段包含过程或变化关系，逐步呈现更容易讲清。"
            reason_code = "process_or_change"
        elif role in {"concept", "objective", "summary", "misconception", "counterexample"}:
            kinds = ["diagram"]
            reason = "这一段包含概念或关系，适合压缩成结构图。"
            reason_code = "concept_or_relation"
        elif len(content) >= 160:
            kinds = ["diagram", "image"]
            reason = "这一段信息较密，可用视觉表达降低口头解释负担。"
            reason_code = "dense_content"
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
        sets = [
            item.model_dump(mode="json")
            for item in registry.representation_sets
            if str(item.target_scope.get("lesson_unit_id") or "") == lesson_unit_id
        ]
        return {
            "schema_version": "teacher_script_visual_view_v1",
            "course_id": course_id,
            "lesson_unit_id": lesson_unit_id,
            "script_revision_id": script_revision_id,
            "recommendations": recommend_script_visuals(blocks),
            "items": items,
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
            visual_content = compile_script_block_diagram(
                section_node_id=section_node_id,
                block_id=block_id,
                title=title,
                content=content,
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
            or "Clean educational editorial illustration, calm blue-violet palette, no text"
        )
        prompt = self.image_provider.plan_prompt(
            source_text=f"{title}. {summarize_text(content, 800)}",
            style=style,
        )
        base = {
            "schema_version": "script_image_spec_v1",
            "title": f"{title} · 插图",
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
                    alt_text=f"{title}的教学插图",
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
    "plan_script_block_scene",
    "recommend_script_visuals",
    "script_visual_source_key",
    "teacher_script_visual_service",
]
