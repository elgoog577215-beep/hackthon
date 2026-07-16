"""Application service for subject ontology generation, binding, and review."""

from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

from ai_base import AIBase, AIProviderRequestError, AIProviderUnavailable
from course_knowledge_map import compile_course_knowledge_map
from course_repository import CourseDocumentConflict, CourseDocumentRepository
from course_versioning import stable_hash
from subject_library_repository import (
    SubjectLibraryConflict,
    SubjectLibraryRepository,
    subject_library_repository,
)
from subject_ontology import (
    build_subject_ontology,
    build_subject_ontology_from_proposal,
    evaluate_subject_ontology_quality,
    resolve_subject_identity,
)
from subject_knowledge import load_subject_library


class SubjectLibraryVersionConflict(RuntimeError):
    pass


class SubjectOntologyGenerationError(RuntimeError):
    def __init__(self, *, code: str, message: str, retryable: bool, status_code: int | None = None):
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code or (429 if code in {"insufficient_quota", "rate_limited"} else 503)
        super().__init__(message)


class SubjectOntologyModel(AIBase):
    async def generate(self, course: dict[str, Any]) -> dict[str, Any]:
        prompt = _ontology_prompt(course)
        response = await self._call_llm(
            prompt,
            system_prompt="你是学科本体工程师。生成独立于课程目录的学科知识体系，不得创建任何正式ID。",
            retry_count=1,
            enable_thinking=False,
            raise_on_failure=True,
        )
        value = self._extract_json(response) if response else None
        if not isinstance(value, dict):
            raise AIProviderRequestError("invalid_ontology_json")
        return value

    async def review(self, library: dict[str, Any]) -> dict[str, Any] | None:
        summary = {
            "nodes": [
                {"id": item.get("knowledge_id"), "type": item.get("node_type"), "name": item.get("name")}
                for item in library.get("nodes") or []
            ],
            "relations": library.get("relations") or [],
            "skills": library.get("skill_units") or [],
            "mistakes": library.get("mistake_points") or [],
        }
        response = await self._call_llm(
            "审查下列学科知识库是否存在章节镜像、关系错误或模板化易错点。只输出"
            '{"passed":true|false,"issues":["..."]}。\n' + json.dumps(summary, ensure_ascii=False),
            system_prompt="你是独立的知识库语义审核员。",
            retry_count=1,
            enable_thinking=False,
            raise_on_failure=True,
        )
        value = self._extract_json(response) if response else None
        if not isinstance(value, dict):
            raise AIProviderRequestError("invalid_review_json")
        return value

    async def repair(
        self,
        course: dict[str, Any],
        library: dict[str, Any],
        issues: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """One bounded repair pass that may change the proposed ontology structure."""
        current = {
            "hierarchy": [
                {"type": item.get("node_type"), "name": item.get("name"), "parent": item.get("parent_id")}
                for item in library.get("nodes") or []
            ],
            "relations": library.get("relations") or [],
            "skills": library.get("skill_units") or [],
            "mistakes": library.get("mistake_points") or [],
            "improvements": library.get("improvement_points") or [],
        }
        response = await self._call_llm(
            _ontology_prompt(
                course,
                repair_context={"current": current, "issues": issues},
            ),
            system_prompt="你是学科本体修复工程师。针对问题重构层级、关系和教学标准，只输出完整替换JSON。",
            retry_count=1,
            enable_thinking=False,
            raise_on_failure=True,
        )
        value = self._extract_json(response) if response else None
        if not isinstance(value, dict):
            raise AIProviderRequestError("invalid_repair_json")
        return value


class SubjectLibraryService:
    def __init__(
        self,
        course_repository: CourseDocumentRepository,
        library_repository: SubjectLibraryRepository | None = None,
        *,
        model: SubjectOntologyModel | None = None,
        use_model: bool = True,
    ) -> None:
        self.course_repository = course_repository
        self.library_repository = library_repository or subject_library_repository
        self.model = model or SubjectOntologyModel()
        self.use_model = use_model

    def resolve_course_library(self, course: dict[str, Any]) -> dict[str, Any] | None:
        """Resolve the immutable revision pinned by one course workspace."""
        return self.library_repository.resolve_for_course(course)

    async def rebuild_course(
        self,
        course_id: str,
        *,
        force: bool = False,
        strict_provider: bool = True,
    ) -> dict[str, Any]:
        course = self.course_repository.load_course_view(course_id)
        result = await self.prepare_course(course, force=force, strict_provider=strict_provider)
        try:
            await self.course_repository.update_metadata(
                course_id,
                {"knowledge_library_binding": result["binding"]},
            )
        except CourseDocumentConflict as exc:
            raise SubjectLibraryVersionConflict(str(exc)) from exc
        return result

    async def degrade_course_index(self, course_id: str, *, reason: str) -> dict[str, Any]:
        """Persist a deterministic course index when migration cannot complete ontology generation."""
        course = self.course_repository.load_course_view(course_id)
        existing_binding = course.get("knowledge_library_binding") or {}
        supersedes = str(existing_binding.get("revision_id") or "") or None
        library = build_subject_ontology(course, supersedes_revision_id=supersedes)
        library["identity_migrations"] = self._identity_migrations(existing_binding, library)
        course_map, course_maps, quality = _evaluate_for_courses(library, course, [course])
        _append_quality_issue(quality, {
            "code": "migration_generation_failed",
            "severity": "critical",
            "message": f"学科知识库迁移失败，已保留课程索引：{reason}",
        })
        library.update({
            "lifecycle_status": "degraded",
            "origin": "course_index",
            "quality_report": quality,
            "generation_audit": {
                **(library.get("generation_audit") or {}),
                "provider_failure": {"code": "migration_failure", "message": reason, "retryable": True},
            },
        })
        library["revision_id"] = stable_hash(
            {key: value for key, value in library.items() if key not in {"revision_id", "created_at"}},
            prefix="sklr_",
        )
        stored = self.library_repository.save_revision(library)
        binding = self.library_repository.binding_for(stored)
        try:
            await self.course_repository.update_metadata(
                course_id,
                {"knowledge_library_binding": binding},
            )
        except CourseDocumentConflict as exc:
            raise SubjectLibraryVersionConflict(str(exc)) from exc
        return {
            "library": stored,
            "course_map": course_map,
            "course_maps": course_maps,
            "quality_report": quality,
            "binding": binding,
            "reused_accepted": False,
        }

    async def rebuild_courses(
        self,
        course_ids: list[str],
        *,
        force: bool = False,
        prefer_curated: bool = False,
    ) -> list[dict[str, Any]]:
        """Generate one subject revision and pin every contributing course to it."""
        ordered_ids = list(dict.fromkeys(str(course_id) for course_id in course_ids if course_id))
        if not ordered_ids:
            return []
        courses = [self.course_repository.load_course_view(course_id) for course_id in ordered_ids]
        subject_ids = {resolve_subject_identity(course)["subject_id"] for course in courses}
        if len(subject_ids) != 1:
            raise ValueError("A shared knowledge-library rebuild must contain one subject")

        generation_course = _merge_subject_courses(courses)
        result = await self.prepare_course(
            generation_course,
            force=force,
            mapping_courses=courses,
            prefer_curated=prefer_curated,
        )
        responses: list[dict[str, Any]] = []
        for course in courses:
            course_id = str(course.get("course_id") or "")
            try:
                await self.course_repository.update_metadata(
                    course_id,
                    {"knowledge_library_binding": result["binding"]},
                )
            except CourseDocumentConflict as exc:
                raise SubjectLibraryVersionConflict(str(exc)) from exc
            responses.append({
                **result,
                "course_id": course_id,
                "course_map": result.get("course_maps", {}).get(course_id, result["course_map"]),
            })
        return responses

    async def prepare_course(
        self,
        course: dict[str, Any],
        *,
        force: bool = False,
        mapping_courses: list[dict[str, Any]] | None = None,
        prefer_curated: bool = False,
        strict_provider: bool = False,
    ) -> dict[str, Any]:
        """Build and persist a library revision for a generation workspace course."""
        mapping_courses = mapping_courses or [course]
        identity = resolve_subject_identity(course)
        if identity["library_id"] == "math.linear_algebra.v1":
            curated = deepcopy(load_subject_library("math.linear_algebra.v1"))
            curated.update({
                "schema_version": "knowledge_library_v3",
                "lifecycle_status": "accepted",
                "origin": "curated",
                "source_course_ids": [],
                "supersedes_revision_id": None,
                "identity_migrations": [],
                "quality_report": {
                    "schema_version": "subject_ontology_quality_v1",
                    "passed": True,
                    "score": 100,
                    "metrics": {"curated": True},
                    "issues": [],
                    "blocking_issues": [],
                },
            })
            stored_curated = self.library_repository.save_revision(curated)
            curated_maps = _compile_course_maps(mapping_courses, stored_curated)
            curated_map = compile_course_knowledge_map(deepcopy(course), stored_curated)
            if prefer_curated or _minimum_mapped_ratio(curated_maps) >= 0.85:
                binding = self.library_repository.binding_for(stored_curated)
                return {
                    "library": stored_curated,
                    "course_map": curated_map,
                    "course_maps": curated_maps,
                    "quality_report": stored_curated["quality_report"],
                    "binding": binding,
                    "reused_accepted": True,
                }
        accepted = self.library_repository.load_accepted(identity["subject_id"])
        if accepted and not force:
            accepted_maps = _compile_course_maps(mapping_courses, accepted)
            accepted_map = compile_course_knowledge_map(deepcopy(course), accepted)
            if _minimum_mapped_ratio(accepted_maps) >= 0.85:
                binding = self.library_repository.binding_for(accepted)
                return {
                    "library": accepted,
                    "course_map": accepted_map,
                    "course_maps": accepted_maps,
                    "quality_report": accepted.get("quality_report") or {},
                    "binding": binding,
                    "reused_accepted": True,
                }

        existing_binding = course.get("knowledge_library_binding") or {}
        supersedes = str(existing_binding.get("revision_id") or "") or None
        baseline = build_subject_ontology(course, supersedes_revision_id=supersedes)
        candidate = baseline
        generation_calls = 0
        review_calls = 0
        repair_calls = 0
        semantic_review = None
        provider_failure: SubjectOntologyGenerationError | None = None
        if self.use_model:
            generation_calls = 1
            try:
                proposal = await self.model.generate(course)
                candidate = build_subject_ontology_from_proposal(
                    course,
                    proposal,
                    supersedes_revision_id=supersedes,
                )
            except (AIProviderRequestError, AIProviderUnavailable, ValueError) as exc:
                provider_failure = _translate_generation_error(exc, "generation")
                if strict_provider:
                    raise provider_failure from exc

        candidate["identity_migrations"] = self._identity_migrations(existing_binding, candidate)

        course_map, course_maps, quality = _evaluate_for_courses(candidate, course, mapping_courses)
        if self.use_model and provider_failure is None:
            review_calls = 1
            try:
                semantic_review = await self.model.review(candidate)
            except (AIProviderRequestError, AIProviderUnavailable, ValueError) as exc:
                provider_failure = _translate_generation_error(exc, "review")
                if strict_provider:
                    raise provider_failure from exc
            if semantic_review and semantic_review.get("passed") is False:
                issue = {
                    "code": "model_semantic_review",
                    "severity": "critical",
                    "message": "；".join(str(item) for item in semantic_review.get("issues") or ["语义审核未通过"]),
                }
                _append_quality_issue(quality, issue)

        if self.use_model and provider_failure is None and not quality["passed"]:
            repair_calls = 1
            try:
                repair = await self.model.repair(course, candidate, quality.get("blocking_issues") or [])
                candidate = build_subject_ontology_from_proposal(
                    course,
                    repair,
                    supersedes_revision_id=supersedes,
                )
                candidate["identity_migrations"] = self._identity_migrations(existing_binding, candidate)
                course_map, course_maps, quality = _evaluate_for_courses(candidate, course, mapping_courses)
            except (AIProviderRequestError, AIProviderUnavailable, ValueError) as exc:
                provider_failure = _translate_generation_error(exc, "repair")
                if strict_provider:
                    raise provider_failure from exc

        if provider_failure is not None:
            _append_quality_issue(quality, {
                "code": f"model_{provider_failure.code}",
                "severity": "critical",
                "message": provider_failure.message,
            })

        candidate["quality_report"] = quality
        candidate["generation_audit"] = {
            **(candidate.get("generation_audit") or {}),
            "generation_calls": generation_calls,
            "review_calls": review_calls,
            "repair_calls": repair_calls,
            "semantic_review": semantic_review,
            "provider_failure": ({
                "code": provider_failure.code,
                "message": provider_failure.message,
                "retryable": provider_failure.retryable,
            } if provider_failure else None),
        }
        if quality["passed"]:
            candidate["lifecycle_status"] = "candidate"
        else:
            candidate["lifecycle_status"] = "degraded"
            candidate["origin"] = "course_index"
        candidate["revision_id"] = stable_hash(
            {key: value for key, value in candidate.items() if key not in {"revision_id", "created_at"}},
            prefix="sklr_",
        )
        stored = self.library_repository.save_revision(candidate)
        binding = self.library_repository.binding_for(stored)
        return {
            "library": stored,
            "course_map": course_map,
            "course_maps": course_maps,
            "quality_report": quality,
            "binding": binding,
            "reused_accepted": False,
        }

    def _identity_migrations(
        self,
        existing_binding: dict[str, Any],
        candidate: dict[str, Any],
    ) -> list[dict[str, Any]]:
        old_library_id = str(existing_binding.get("library_id") or "")
        old_revision_id = str(existing_binding.get("revision_id") or "")
        if not old_library_id or not old_revision_id:
            return []
        try:
            previous = self.library_repository.load_revision(old_library_id, old_revision_id)
        except KeyError:
            return []
        if old_library_id == str(candidate.get("library_id") or ""):
            return []

        new_by_identity: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for node in candidate.get("nodes") or []:
            key = (str(node.get("node_type") or ""), _normalized_identity_name(node.get("name")))
            if key[1]:
                new_by_identity.setdefault(key, []).append(node)

        migrations: list[dict[str, Any]] = []
        used_new_ids: set[str] = set()
        for old_node in previous.get("nodes") or []:
            key = (str(old_node.get("node_type") or ""), _normalized_identity_name(old_node.get("name")))
            matches = new_by_identity.get(key) or []
            new_node = next(
                (item for item in matches if str(item.get("knowledge_id") or "") not in used_new_ids),
                None,
            )
            if not new_node:
                continue
            old_id = str(old_node.get("knowledge_id") or "")
            new_id = str(new_node.get("knowledge_id") or "")
            if not old_id or not new_id or old_id == new_id:
                continue
            used_new_ids.add(new_id)
            migrations.append({
                "migration_id": stable_hash(
                    {"from": old_id, "to": new_id, "from_revision": old_revision_id},
                    prefix="skim_",
                ),
                "old_knowledge_id": old_id,
                "new_knowledge_id": new_id,
                "from_library_id": old_library_id,
                "from_revision_id": old_revision_id,
                "to_library_id": str(candidate.get("library_id") or ""),
                "reason": "canonical_subject_identity_normalization",
                "source_type": "course_source",
                "confidence": 1.0,
            })
        return migrations

    def get_review(self, course_id: str) -> dict[str, Any]:
        course = self.course_repository.load_course_view(course_id)
        binding = course.get("knowledge_library_binding") or {}
        if not binding.get("library_id") or not binding.get("revision_id"):
            raise KeyError("Course has no pinned knowledge library")
        return self.library_repository.review_summary(
            str(binding["library_id"]), str(binding["revision_id"]),
        )

    async def review_course_library(
        self,
        course_id: str,
        *,
        revision_id: str,
        decision: str,
        note: str = "",
    ) -> dict[str, Any]:
        course = self.course_repository.load_course_view(course_id)
        binding = course.get("knowledge_library_binding") or {}
        current_revision = str(binding.get("revision_id") or "")
        if not current_revision or current_revision != revision_id:
            raise SubjectLibraryVersionConflict("Knowledge-library review targets a stale revision")
        current_library = self.library_repository.load_revision(str(binding["library_id"]), revision_id)
        target_status = "accepted" if decision == "accept" else "rejected"
        if current_library.get("lifecycle_status") not in {"candidate", target_status}:
            raise SubjectLibraryVersionConflict("Only candidate knowledge-library revisions can be reviewed")
        try:
            library = self.library_repository.review_revision(
                str(binding["library_id"]), revision_id, decision=decision, note=note,
            )
        except SubjectLibraryConflict as exc:
            raise SubjectLibraryVersionConflict(str(exc)) from exc
        updated_binding = self.library_repository.binding_for(library)
        try:
            await self.course_repository.update_metadata(
                course_id,
                {"knowledge_library_binding": updated_binding},
                expected_binding_revision_id=revision_id,
            )
        except CourseDocumentConflict as exc:
            raise SubjectLibraryVersionConflict(str(exc)) from exc
        return {"library": library, "binding": updated_binding}


def _merge_subject_courses(courses: list[dict[str, Any]]) -> dict[str, Any]:
    merged = deepcopy(courses[0])
    merged["source_course_ids"] = [str(course.get("course_id") or "") for course in courses]
    merged_nodes: list[dict[str, Any]] = []
    for course in courses:
        course_id = str(course.get("course_id") or "course")
        nodes = deepcopy(course.get("nodes") or [])
        id_map = {
            str(node.get("node_id") or ""): f"{course_id}:{node.get('node_id')}"
            for node in nodes
            if node.get("node_id")
        }
        for node in nodes:
            node_id = str(node.get("node_id") or "")
            if node_id:
                node["node_id"] = id_map[node_id]
            parent_id = str(node.get("parent_id") or "")
            if parent_id in id_map:
                node["parent_id"] = id_map[parent_id]
            node["prerequisite_node_ids"] = [
                id_map.get(str(item), str(item))
                for item in node.get("prerequisite_node_ids") or []
            ]
            merged_nodes.append(node)
    merged["nodes"] = merged_nodes
    return merged


def _ontology_prompt(
    course: dict[str, Any],
    *,
    repair_context: dict[str, Any] | None = None,
) -> str:
    course_summary = {
        "course_name": course.get("course_name"),
        "subject": (course.get("generation_request") or {}).get("subject") or course.get("subject"),
        "sections": [
            {
                "name": item.get("node_name"),
                "knowledge_structure": item.get("knowledge_structure"),
                "prerequisite_node_ids": item.get("prerequisite_node_ids") or [],
            }
            for item in course.get("nodes") or []
            if int(item.get("node_level") or 1) == 2
        ],
        "materials": [
            item if isinstance(item, str) else {
                "id": item.get("material_id") or item.get("id"),
                "name": item.get("name") or item.get("title"),
                "summary": item.get("summary"),
            }
            for collection in ("uploaded_materials", "source_materials", "materials")
            for item in course.get(collection) or []
        ],
    }
    schema = {
        "domains": [{
            "name": "学科领域名", "description": "...", "source_type": "model_inferred",
            "topics": [{
                "name": "学科主题名", "description": "...",
                "concepts": [{
                    "name": "规范概念名", "aliases": ["真实别名"], "description": "...",
                    "knowledge_points": [{
                        "name": "可诊断知识点", "description": "...", "learning_action": "...",
                        "typical_problems": ["..."], "source_type": "course_source|material_source|model_inferred",
                        "confidence": 0.8,
                    }],
                }],
            }],
        }],
        "relations": [{
            "source_name": "规范名", "target_name": "规范名",
            "relation_type": "prerequisite|application|related|confusable|derives",
            "reason": "具体学科原因", "source_type": "model_inferred", "confidence": 0.8,
        }],
        "course_mappings": [{
            "course_name": "课程输入中的原始主题或知识点原词",
            "knowledge_name": "上面层级中唯一的规范节点名",
            "reason": "二者语义对应理由", "confidence": 0.9,
        }],
        "skills": [{
            "name": "能力名", "knowledge_names": ["1到5个知识点名"],
            "description": "可观察能力", "learning_goal": "...",
        }],
        "mistakes": [{
            "name": "学科特异错误", "skill_name": "能力名", "knowledge_names": ["知识点名"],
            "description": "具体错误表现", "misconception": "错误认知", "trigger": "触发场景",
            "symptom": "可观察症状", "repair_strategy": "具体修复办法",
        }],
        "improvements": [{
            "name": "提升项", "skill_name": "能力名", "knowledge_names": ["知识点名"],
            "related_mistake_names": ["错误名"], "description": "...",
            "practice_strategy": "具体训练", "student_benefit": "...",
        }],
    }
    repair_instruction = ""
    if repair_context:
        repair_instruction = (
            "\n这是唯一一次修复。必须返回完整替换对象，不能只返回关系。"
            "当前候选与门禁问题：" + json.dumps(repair_context, ensure_ascii=False)
        )
    return (
        "根据课程、正文摘要和资料生成学科级知识库提案，只输出JSON对象。\n"
        "必须使用 subject→domain→topic→concept→knowledge_point 五级学科逻辑；课程只决定覆盖详度，"
        "不得把章节名、诊断测试、项目、总结直接当作概念。当前课程覆盖处细化，未覆盖领域只保留必要骨架。\n"
        "关系必须跨概念体现真实学科逻辑，至少一半课程概念参与关系；禁止前置环。"
        "每个技能绑定1到5个知识点，至少30%的技能跨知识点。"
        "易错点和提升项必须学科特异，禁止换名复用模板。\n"
        "只能引用输入课程/资料或模型通识；没有资料证据时不得标material_source，禁止伪造书目、论文和链接。"
        "不要输出任何ID，后端会确定性分配。\n"
        "必须逐项检查课程输入：除诊断评估、项目流程、章节总结等教学脚手架外，每个课程topic和knowledge point"
        "若未原词出现在规范节点name/aliases中，必须写入course_mappings，course_name必须逐字复制课程原词，"
        "knowledge_name必须逐字引用本次输出的唯一规范节点名。\n"
        f"输出结构示例：{json.dumps(schema, ensure_ascii=False)}\n"
        f"课程输入：{json.dumps(course_summary, ensure_ascii=False)}"
        f"{repair_instruction}"
    )


def _translate_generation_error(exc: Exception, stage: str) -> SubjectOntologyGenerationError:
    message = str(exc).lower()
    if "insufficient_quota" in message or "insufficient balance" in message or "额度" in message:
        return SubjectOntologyGenerationError(
            code="insufficient_quota",
            message=f"AI 服务额度不足，知识库{stage}未完成，原版本保持不变",
            retryable=True,
            status_code=429,
        )
    if "rate limit" in message or "limit_burst_rate" in message or "速率" in message:
        return SubjectOntologyGenerationError(
            code="rate_limited",
            message=f"AI 服务限流，知识库{stage}未完成，原版本保持不变",
            retryable=True,
            status_code=429,
        )
    if isinstance(exc, ValueError) or "invalid_" in message or "empty_response" in message:
        return SubjectOntologyGenerationError(
            code="invalid_model_output",
            message=f"AI 返回的知识库{stage}结果不完整，原版本保持不变",
            retryable=True,
            status_code=502,
        )
    retryable = not isinstance(exc, AIProviderUnavailable) or getattr(exc, "reason", "") == "not_configured"
    return SubjectOntologyGenerationError(
        code=getattr(exc, "reason", "provider_unavailable"),
        message=f"AI 服务不可用，知识库{stage}未完成，原版本保持不变",
        retryable=retryable,
        status_code=503,
    )


def _append_quality_issue(quality: dict[str, Any], issue: dict[str, Any]) -> None:
    issues = quality.setdefault("issues", [])
    if not any(item.get("code") == issue.get("code") for item in issues):
        issues.append(issue)
        quality["score"] = max(0, int(quality.get("score") or 0) - 20)
    quality["blocking_issues"] = [
        item for item in issues if item.get("severity") == "critical"
    ]
    quality["passed"] = not quality["blocking_issues"]


def _normalized_identity_name(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").casefold())


def _compile_course_maps(
    courses: list[dict[str, Any]],
    library: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        str(course.get("course_id") or index): compile_course_knowledge_map(deepcopy(course), library)
        for index, course in enumerate(courses)
    }


def _minimum_mapped_ratio(course_maps: dict[str, dict[str, Any]]) -> float:
    if not course_maps:
        return 0.0
    return min(
        float((course_map.get("coverage") or {}).get("mapped_ratio") or 0.0)
        for course_map in course_maps.values()
    )


def _evaluate_for_courses(
    library: dict[str, Any],
    generation_course: dict[str, Any],
    mapping_courses: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    generation_map = compile_course_knowledge_map(deepcopy(generation_course), library)
    course_maps = _compile_course_maps(mapping_courses, library)
    quality = evaluate_subject_ontology_quality(library, generation_course, generation_map)
    minimum_ratio = _minimum_mapped_ratio(course_maps)
    quality.setdefault("metrics", {})["minimum_course_mapped_ratio"] = minimum_ratio
    if minimum_ratio < 0.85 and not any(
        item.get("code") == "insufficient_individual_course_mapping"
        for item in quality.get("issues") or []
    ):
        issue = {
            "code": "insufficient_individual_course_mapping",
            "severity": "critical",
            "message": f"至少一门来源课程的知识映射率仅为 {minimum_ratio:.0%}",
        }
        quality.setdefault("issues", []).append(issue)
        quality.setdefault("blocking_issues", []).append(issue)
        quality["passed"] = False
        quality["score"] = max(0, int(quality.get("score") or 0) - 15)
    return generation_map, course_maps, quality


__all__ = [
    "SubjectLibraryService",
    "SubjectLibraryVersionConflict",
    "SubjectOntologyGenerationError",
    "SubjectOntologyModel",
]
