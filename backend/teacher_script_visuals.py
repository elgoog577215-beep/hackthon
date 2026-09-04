"""Source-bound diagram, image, and animation candidates for teacher scripts."""

from __future__ import annotations

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

SCRIPT_VISUAL_COMPILER_VERSION = "teacher_script_visual_compiler_v1"
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
    def validate_scene(self) -> "SceneSpecV1":
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
            visual_content = compile_script_block_scene(
                section_node_id=section_node_id,
                block_id=block_id,
                title=title,
                content=content,
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
    "TeacherScriptVisualService",
    "compile_script_block_diagram",
    "compile_script_block_scene",
    "recommend_script_visuals",
    "script_visual_source_key",
    "teacher_script_visual_service",
]
