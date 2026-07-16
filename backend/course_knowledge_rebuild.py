"""AI-assisted, quality-gated knowledge reconstruction for historical courses."""

from __future__ import annotations

import json
from collections.abc import Iterator
from copy import deepcopy
from typing import Any

from ai_base import AIBase, AIProviderRequestError, AIProviderUnavailable
from content_blocks import set_node_content_blocks
from course_knowledge_base import (
    COURSE_KNOWLEDGE_BASE_SCHEMA,
    course_knowledge_source_fingerprint,
)
from course_repository import CourseDocumentConflict, CourseDocumentRepository
from course_versioning import stable_hash
from learning_assets import compile_learning_assets

MAX_SECTIONS_PER_BATCH = 6
MAX_BLOCK_CHARS = 1800


class CourseKnowledgeRebuildError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool,
        status_code: int = 422,
        quality_report: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code
        self.quality_report = deepcopy(quality_report or {})
        super().__init__(message)

    def detail(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.quality_report:
            payload["quality_report"] = self.quality_report
        return payload


class CourseKnowledgeRebuildModel(AIBase):
    async def generate_batch(
        self,
        *,
        course_name: str,
        sections: list[dict[str, Any]],
        existing_knowledge_names: list[str],
    ) -> dict[str, Any]:
        prompt = _rebuild_prompt(
            course_name=course_name,
            sections=sections,
            existing_knowledge_names=existing_knowledge_names,
        )
        response = await self._call_llm(
            prompt,
            system_prompt=(
                "你是课程知识工程师。你只重建当前课程自己的知识库，不生成跨课程本体，"
                "不复制章节标题，不创建正式ID，只输出完整JSON。"
            ),
            retry_count=1,
            enable_thinking=True,
            raise_on_failure=True,
        )
        value = self._extract_json(response) if response else None
        if not isinstance(value, dict):
            raise AIProviderRequestError("invalid_course_knowledge_json")
        return value


class CourseKnowledgeRebuildService:
    def __init__(
        self,
        course_repository: CourseDocumentRepository,
        *,
        model: CourseKnowledgeRebuildModel | None = None,
        batch_size: int = MAX_SECTIONS_PER_BATCH,
    ) -> None:
        self.course_repository = course_repository
        self.model = model or CourseKnowledgeRebuildModel()
        self.batch_size = max(1, min(MAX_SECTIONS_PER_BATCH, int(batch_size)))

    async def rebuild_course(self, course_id: str, *, force: bool = False) -> dict[str, Any]:
        original = self.course_repository.load_course_view(course_id)
        working = deepcopy(original)
        _ensure_content_blocks(working)
        source_fingerprint = course_knowledge_source_fingerprint(working)
        existing = working.get("course_knowledge_base") or {}
        if (
            not force
            and existing.get("schema_version") == COURSE_KNOWLEDGE_BASE_SCHEMA
            and existing.get("lifecycle_status") == "active"
            and existing.get("source_course_fingerprint") == source_fingerprint
        ):
            bundle = compile_learning_assets(working)
            return _result(course_id, bundle, reused=True, generation_calls=0)

        sections = [
            section for section in working.get("nodes") or []
            if int(section.get("node_level") or 1) == 2
        ]
        if not sections:
            raise CourseKnowledgeRebuildError(
                code="course_has_no_learning_sections",
                message="当前课程没有可知识化的小节",
                retryable=False,
            )
        empty_sections = [
            str(section.get("node_name") or section.get("node_id") or "未命名小节")
            for section in sections
            if not any(
                str(block.get("content") or block.get("markdown") or "").strip()
                for block in section.get("content_blocks") or []
            )
        ]
        if empty_sections:
            raise CourseKnowledgeRebuildError(
                code="course_section_has_no_source_content",
                message=f"以下小节没有可核验正文，不能凭标题生成知识点：{'、'.join(empty_sections[:6])}",
                retryable=False,
            )

        generated_names: list[str] = []
        generated_relations: list[dict[str, Any]] = []
        generation_calls = 0
        try:
            for batch in _chunks(sections, self.batch_size):
                generation_calls += 1
                section_payloads = [_section_payload(section) for section in batch]
                proposal = await self.model.generate_batch(
                    course_name=str(working.get("course_name") or "当前课程"),
                    sections=section_payloads,
                    existing_knowledge_names=generated_names,
                )
                names, relations = _apply_proposal_batch(batch, section_payloads, proposal)
                generated_names.extend(names)
                generated_relations.extend(relations)
        except AIProviderUnavailable as exc:
            raise CourseKnowledgeRebuildError(
                code="provider_unavailable",
                message="AI 服务当前不可用，原课程知识库保持不变",
                retryable=False,
                status_code=503,
            ) from exc
        except AIProviderRequestError as exc:
            raise CourseKnowledgeRebuildError(
                code="knowledge_generation_failed",
                message="课程知识化模型输出无效或调用失败，原课程知识库保持不变",
                retryable=True,
                status_code=503,
            ) from exc

        # Never let a previously stored CKB override the newly generated candidate.
        working.pop("course_knowledge_base", None)
        working.pop("course_knowledge_map", None)
        working["knowledge_relations"] = generated_relations
        bundle = compile_learning_assets(working)
        knowledge_base = next(iter(bundle["assets"].get("course_knowledge_base") or []), None)
        course_map = next(iter(bundle["assets"].get("course_knowledge_map") or []), None)
        if not knowledge_base or not course_map:
            raise CourseKnowledgeRebuildError(
                code="knowledge_compile_failed",
                message="课程知识化没有产生可保存结果，原课程保持不变",
                retryable=True,
            )
        quality = knowledge_base.get("quality_report") or {}
        if knowledge_base.get("lifecycle_status") != "active" or not quality.get("strict_passed"):
            messages = [
                str(item.get("message") or "")
                for item in quality.get("blocking_issues") or quality.get("issues") or []
                if str(item.get("message") or "").strip()
            ]
            raise CourseKnowledgeRebuildError(
                code="knowledge_quality_failed",
                message=(
                    "课程知识化结果未通过质量门，原课程保持不变："
                    + ("；".join(messages[:6]) or "请重新生成")
                ),
                retryable=True,
                quality_report=quality,
            )

        current = self.course_repository.load_course_view(course_id)
        _ensure_content_blocks(current)
        if course_knowledge_source_fingerprint(current) != source_fingerprint:
            raise CourseKnowledgeRebuildError(
                code="course_changed_during_rebuild",
                message="知识化期间课程正文发生变化，请基于最新版本重试",
                retryable=True,
                status_code=409,
            )

        audit = {
            "schema_version": "course_knowledge_rebuild_audit_v1",
            "source_course_fingerprint": source_fingerprint,
            "generation_calls": generation_calls,
            "section_count": len(sections),
            "knowledge_point_count": len(knowledge_base.get("knowledge_points") or []),
            "quality_score": quality.get("score"),
        }
        bundle_revision_id = stable_hash(
            {"course_id": course_id, "assets": bundle["assets"]},
            prefix="labr_",
        )
        try:
            await self.course_repository.update_metadata(course_id, {
                "course_knowledge_base": knowledge_base,
                "course_knowledge_map": course_map,
                "course_knowledge_quality_report": quality,
                "course_knowledge_rebuild_audit": audit,
                "learning_asset_plan": bundle["plan"],
                "learning_assets": bundle["assets"],
                "learning_asset_bundle_revision_id": bundle_revision_id,
                "asset_quality_report": bundle["quality_report"],
            })
        except CourseDocumentConflict as exc:
            raise CourseKnowledgeRebuildError(
                code="course_changed_during_rebuild",
                message="课程修订发生冲突，知识化结果未保存",
                retryable=True,
                status_code=409,
            ) from exc

        return _result(
            course_id,
            bundle,
            reused=False,
            generation_calls=generation_calls,
            bundle_revision_id=bundle_revision_id,
            audit=audit,
        )


def _ensure_content_blocks(course: dict[str, Any]) -> None:
    for section in course.get("nodes") or []:
        if int(section.get("node_level") or 1) != 2:
            continue
        if section.get("content_blocks") or not str(section.get("node_content") or "").strip():
            continue
        set_node_content_blocks(section, str(section.get("node_content") or ""))


def _section_payload(section: dict[str, Any]) -> dict[str, Any]:
    blocks = []
    for block in section.get("content_blocks") or []:
        content = str(block.get("content") or block.get("markdown") or "").strip()
        blocks.append({
            "block_id": str(block.get("block_id") or block.get("content_block_id") or ""),
            "title": str(block.get("title") or ""),
            "content": content[:MAX_BLOCK_CHARS],
        })
    return {
        "section_id": str(section.get("node_id") or ""),
        "title": str(section.get("node_name") or section.get("title") or ""),
        "learning_objective": str(section.get("learning_objective") or ""),
        "assessment": deepcopy(section.get("assessment") or []),
        "scope_boundary": str(section.get("scope_boundary") or ""),
        "legacy_key_points": deepcopy(section.get("key_points") or []),
        "blocks": blocks,
    }


def _apply_proposal_batch(
    sections: list[dict[str, Any]],
    section_payloads: list[dict[str, Any]],
    proposal: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    proposed = proposal.get("sections")
    if not isinstance(proposed, list):
        raise AIProviderRequestError("missing_generated_sections")
    expected_ids = {str(item.get("section_id") or "") for item in section_payloads}
    by_id = {
        str(item.get("section_id") or ""): item
        for item in proposed
        if isinstance(item, dict)
    }
    if set(by_id) != expected_ids:
        raise AIProviderRequestError("generated_section_coverage_mismatch")

    payload_by_id = {str(item["section_id"]): item for item in section_payloads}
    names: list[str] = []
    for section in sections:
        section_id = str(section.get("node_id") or "")
        generated = by_id[section_id]
        structures = generated.get("knowledge_structure")
        if not isinstance(structures, list) or not structures:
            raise AIProviderRequestError("missing_generated_knowledge_structure")
        allowed_blocks = {
            str(item.get("block_id") or "")
            for item in payload_by_id[section_id].get("blocks") or []
            if str(item.get("block_id") or "")
        }
        referenced_blocks: set[str] = set()
        for group in structures:
            if not isinstance(group, dict):
                raise AIProviderRequestError("invalid_generated_concept_group")
            for point in group.get("knowledge_points") or []:
                if not isinstance(point, dict):
                    raise AIProviderRequestError("invalid_generated_knowledge_point")
                name = str(point.get("name") or "").strip()
                if name:
                    names.append(name)
                refs = {
                    str(item) for item in point.get("content_block_refs") or []
                    if str(item)
                }
                if refs - allowed_blocks:
                    raise AIProviderRequestError("generated_unknown_block_reference")
                referenced_blocks.update(refs)
        if allowed_blocks - referenced_blocks:
            raise AIProviderRequestError("generated_incomplete_block_coverage")
        section["knowledge_structure"] = deepcopy(structures)
        reused_names = generated.get("reused_knowledge_names") or []
        if not isinstance(reused_names, list) or any(
            not isinstance(item, str) or not item.strip()
            for item in reused_names
        ):
            raise AIProviderRequestError("invalid_reused_knowledge_names")
        section["reused_knowledge_names"] = list(dict.fromkeys(reused_names))
        section["knowledge_structure_status"] = "structured"
        section["key_points"] = [
            str(point.get("name") or "")
            for group in structures
            for point in group.get("knowledge_points") or []
            if str(point.get("name") or "").strip()
        ]
    relations = proposal.get("knowledge_relations") or []
    if not isinstance(relations, list) or any(not isinstance(item, dict) for item in relations):
        raise AIProviderRequestError("invalid_generated_course_relations")
    return names, deepcopy(relations)


def _chunks(values: list[dict[str, Any]], size: int) -> Iterator[list[dict[str, Any]]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _result(
    course_id: str,
    bundle: dict[str, Any],
    *,
    reused: bool,
    generation_calls: int,
    bundle_revision_id: str | None = None,
    audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assets = bundle["assets"]
    knowledge_base = next(iter(assets.get("course_knowledge_base") or []), {})
    return {
        "course_id": course_id,
        "library": next(iter(assets.get("knowledge_library") or []), {}),
        "course_knowledge_base": knowledge_base,
        "course_map": next(iter(assets.get("course_knowledge_map") or []), {}),
        "quality_report": knowledge_base.get("quality_report") or {},
        "asset_quality_report": bundle.get("quality_report") or {},
        "reference_catalog_required": False,
        "reused": reused,
        "generation_calls": generation_calls,
        "bundle_revision_id": bundle_revision_id,
        "audit": deepcopy(audit or {}),
    }


def _rebuild_prompt(
    *,
    course_name: str,
    sections: list[dict[str, Any]],
    existing_knowledge_names: list[str],
) -> str:
    return f"""把下列历史课程正文重建为当前课程自己的知识库候选。

## 课程
{course_name}

## 已在前序批次使用的规范知识名称
{json.dumps(existing_knowledge_names, ensure_ascii=False)}

## 本批小节与正文块
{json.dumps(sections, ensure_ascii=False)}

## 硬规则
1. 必须逐个返回输入中的 section_id，不得增加、遗漏或改写 ID。
2. 每节生成 1-4 个概念组；概念组不能复制小节标题，每组包含 2-5 个可独立解释和考查的原子知识点。
3. 知识点必须包含 name、独立 statement、knowledge_type，以及 conditions 或 boundaries；knowledge_type 只能是 definition、principle、rule、method、condition、representation、procedure。
4. 每个知识点至少有一个 capability_points，且 observable_behavior 必须是可观察行为；至少有一个 mastery_criteria，且包含 observable_performance 与 verification_method。
5. misconceptions 可以为空；一旦生成，必须同时包含 observable_error_pattern、discrimination、repair_strategy，禁止模板填充。
6. 关系只允许 prerequisite、derives、equivalent_to、contrasts_with、applies_to、generalizes。当前批次同一知识点组内可在知识点的 relations 中写 target_name；连接当前批次与前序批次知识点时，必须写入顶层 knowledge_relations，并明确 source_name、target_name 和标准方向。每条关系必须有具体 reason；derives 必须有 derivation_steps；contrasts_with 必须有 distinction。
7. 每个没有关系入边的知识点必须写 entry_reason。禁止 related、章节顺序和父子包含关系混入知识关系网。
8. 每个知识点用 content_block_refs 精确引用它所解释、练习或检查的正文块 ID；本节每个正文块至少被一个知识点覆盖，禁止引用输入之外的块 ID。
9. 同一知识若已出现在前序批次，不得在 knowledge_structure 重新创建；必须把完全相同的规范名称写入当前小节的 reused_knowledge_names。别名写入 aliases。不得生成 ImprovementPoint 或跨课程正式 ID。
10. 只输出以下 JSON，不输出 Markdown 或解释：
{{
  "sections": [
    {{
      "section_id": "输入中的ID",
      "knowledge_structure": [
        {{
          "concept_group": "知识问题域",
          "description": "本组边界",
          "knowledge_points": [
            {{
              "name": "原子知识名称",
              "statement": "独立知识命题",
              "knowledge_type": "definition",
              "conditions": ["成立条件"],
              "boundaries": ["适用边界"],
              "counterexamples": [],
              "aliases": [],
              "content_block_refs": ["输入中的block_id"],
              "capability_points": [{{"name": "能力名", "observable_behavior": "可观察行为"}}],
              "misconceptions": [],
              "mastery_criteria": [{{"name": "掌握标准", "observable_performance": "可验证表现", "verification_method": "验证方式"}}],
              "entry_reason": "仅无入边时填写",
              "relations": [{{"target_name": "本课程知识点规范名称", "relation_type": "prerequisite", "reason": "具体理由"}}]
            }}
          ]
        }}
      ],
      "reused_knowledge_names": []
    }}
  ],
  "knowledge_relations": []
}}"""


__all__ = [
    "CourseKnowledgeRebuildError",
    "CourseKnowledgeRebuildModel",
    "CourseKnowledgeRebuildService",
]
