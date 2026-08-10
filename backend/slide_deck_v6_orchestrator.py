"""Single durable orchestration boundary for slide-deck V6 builds."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from course_document import CourseDocument, stable_hash
from course_presentation_graph import compile_course_presentation_graph
from course_revisions import revision_vector_for_course
from slide_ai_planning_v6 import Planner, plan_slide_story_v3, plan_slide_visuals_v2
from slide_build_progress_v2 import (
    SlideBuildProgressRepositoryV2,
    SlideBuildProgressTrackerV2,
    SlideWorkItemV2,
)
from slide_deck_v6 import (
    V6BuildError,
    compile_ppt_source_contract_v2,
    compile_slide_deck_v6,
)
from teaching_representations import (
    SourceBinding,
    TeachingRepresentation,
    TeachingRepresentationRepository,
    TeachingRepresentationSpec,
    source_binding_for_document,
)
from template_layout_contract import compile_builtin_template_layout_contract_v1


ProgressCallback = Callable[[dict[str, object]], Awaitable[None] | None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SlideDeckV6CandidateRepository:
    """Task-scoped candidate diagnostics, separate from the public registry."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        safe = "".join(character for character in task_id if character.isalnum() or character in "-_")
        if safe != task_id or not safe:
            raise ValueError("Invalid V6 candidate task ID")
        path = (self.root / f"{safe}.json").resolve()
        path.relative_to(self.root)
        return path

    def save(self, task_id: str, payload: dict[str, Any]) -> None:
        path = self._path(task_id)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)

    def load(self, task_id: str) -> dict[str, Any]:
        path = self._path(task_id)
        if not path.is_file():
            raise FileNotFoundError(task_id)
        return json.loads(path.read_text(encoding="utf-8"))


async def _emit(callback: ProgressCallback | None, payload: dict[str, object]) -> None:
    if callback is None:
        return
    result = callback(payload)
    if inspect.isawaitable(result):
        await result


async def _await_with_heartbeats(
    awaitable: Awaitable[Any],
    *,
    tracker: SlideBuildProgressTrackerV2,
    callback: ProgressCallback | None,
) -> Any:
    task = asyncio.create_task(awaitable)
    while not task.done():
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
        except asyncio.TimeoutError:
            if tracker.heartbeat_due():
                await _emit(callback, tracker.heartbeat())
    return await task


def _source_binding_with_course_logic(
    document: CourseDocument,
    course_data: dict[str, Any],
    *,
    block_id: str | None = None,
    section_id: str | None = None,
) -> SourceBinding:
    binding = source_binding_for_document(
        document,
        block_id=block_id,
        section_id=section_id,
    )
    vector = revision_vector_for_course(document, course_data).revisions
    for key in (
        "course_teaching_plan",
        "course_knowledge_base",
        "course_coherence_contract",
    ):
        if key in vector:
            binding.source_revisions[key] = vector[key]
    return SourceBinding.model_validate(binding.model_dump(mode="json"))


class SlideDeckV6Orchestrator:
    def __init__(
        self,
        *,
        representation_repository: TeachingRepresentationRepository,
        candidate_repository: SlideDeckV6CandidateRepository,
        progress_root: str | Path,
    ) -> None:
        self.representations = representation_repository
        self.candidates = candidate_repository
        self.progress_repository = SlideBuildProgressRepositoryV2(progress_root)

    async def build(
        self,
        *,
        task_id: str,
        document: CourseDocument,
        course_data: dict[str, Any],
        mode: str,
        theme: str,
        story_planner: Planner,
        visual_planner: Planner,
        source_revision_provider: Callable[[], str],
        template_digest_provider: Callable[[], str] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        tracker = SlideBuildProgressTrackerV2.create(
            task_id,
            repository=self.progress_repository,
        )
        current_work = "source-contract"
        source_contract = None
        graph = None
        story = None
        visual = None
        template = compile_builtin_template_layout_contract_v1(theme)
        tracker.add_work([
            SlideWorkItemV2(item_id="source-contract", kind="local", stage="source", label="冻结课程与模板真源"),
            SlideWorkItemV2(item_id="course-graph", kind="local", stage="course_graph", label="构建完整教学单元图"),
        ])
        await _emit(progress_callback, tracker.snapshot())
        try:
            tracker.start("source-contract")
            source_contract = compile_ppt_source_contract_v2(
                document,
                teaching_plan=dict(course_data.get("course_teaching_plan") or {}),
                knowledge_snapshot=dict(course_data.get("course_knowledge_base") or {}),
                template_contract=template,
                locale=str(course_data.get("language") or course_data.get("locale") or "zh-CN"),
            )
            tracker.complete("source-contract")
            await _emit(progress_callback, tracker.snapshot())

            current_work = "course-graph"
            tracker.start("course-graph")
            graph = compile_course_presentation_graph(
                document,
                teaching_plan=dict(course_data.get("course_teaching_plan") or {}),
            )
            if graph.primary_block_coverage != 1.0 or graph.diagnostics:
                raise V6BuildError(
                    stage="course_graph",
                    code="course_block_coverage_incomplete",
                    message="Course presentation graph does not own every formal block exactly once",
                )
            tracker.complete("course-graph")
            story_sections = list(dict.fromkeys(unit.section_id for unit in graph.units))
            tracker.add_work([
                SlideWorkItemV2(
                    item_id=f"story-{index + 1}",
                    kind="ai_batch",
                    stage="story",
                    label=f"故事规划批次 {index + 1}",
                    chapter_id=section_id,
                    batch_id=f"story-{index + 1}",
                )
                for index, section_id in enumerate(story_sections)
            ])
            await _emit(progress_callback, tracker.snapshot())

            for index, section_id in enumerate(story_sections):
                current_work = f"story-{index + 1}"
                tracker.start(
                    current_work,
                    chapter_id=section_id,
                    batch_id=current_work,
                    provider_wait=True,
                )
            story = await _await_with_heartbeats(
                plan_slide_story_v3(graph, template, ai_planner=story_planner),
                tracker=tracker,
                callback=progress_callback,
            )
            for index in range(len(story_sections)):
                tracker.complete(f"story-{index + 1}")
            tracker.add_work([
                SlideWorkItemV2(
                    item_id=f"visual-{index + 1}",
                    kind="ai_batch",
                    stage="visual",
                    label=f"视觉规划批次 {index + 1}",
                    chapter_id=batch.chapter_id,
                    batch_id=f"visual-{index + 1}",
                )
                for index, batch in enumerate(story.batches)
            ])
            await _emit(progress_callback, tracker.snapshot())

            for index, batch in enumerate(story.batches):
                current_work = f"visual-{index + 1}"
                tracker.start(
                    current_work,
                    chapter_id=batch.chapter_id,
                    batch_id=current_work,
                    provider_wait=True,
                )
            visual = await _await_with_heartbeats(
                plan_slide_visuals_v2(
                    story,
                    graph,
                    template,
                    ai_planner=visual_planner,
                ),
                tracker=tracker,
                callback=progress_callback,
            )
            for index in range(len(story.batches)):
                tracker.complete(f"visual-{index + 1}")

            tracker.add_work([
                *[
                    SlideWorkItemV2(
                        item_id=f"render-{page.page_id}",
                        kind="render_page",
                        stage="render",
                        label=f"编译页面 {page.page_ordinal + 1}",
                        page_id=page.page_id,
                    )
                    for page in story.pages
                ],
                SlideWorkItemV2(item_id="quality", kind="local", stage="quality", label="执行忠实度与渲染门禁"),
                SlideWorkItemV2(item_id="publish", kind="local", stage="publish", label="原子发布正式课件"),
            ])
            await _emit(progress_callback, tracker.snapshot())

            for page in story.pages:
                current_work = f"render-{page.page_id}"
                tracker.start(current_work, page_id=page.page_id)
                tracker.complete(current_work)
            current_work = "quality"
            tracker.start("quality")
            deck = compile_slide_deck_v6(document, graph, story, visual, template)
            tracker.complete("quality")

            current_work = "publish"
            tracker.start("publish")
            if str(source_revision_provider() or "") != source_contract.course_document_revision:
                raise V6BuildError(
                    stage="publish",
                    code="source_revision_changed",
                    message="Course revision changed while V6 was building",
                    retryable=True,
                )
            current_template_digest = (
                str(template_digest_provider() or "")
                if template_digest_provider
                else template.template_digest
            )
            if current_template_digest != source_contract.template_digest:
                raise V6BuildError(
                    stage="publish",
                    code="template_revision_changed",
                    message="Template revision changed while V6 was building",
                    retryable=True,
                )
            content = {
                **deck.model_dump(mode="json"),
                "source_contract": source_contract.model_dump(mode="json"),
                "course_presentation_graph": graph.model_dump(mode="json"),
                "story_plan": story.model_dump(mode="json"),
                "visual_plan": visual.model_dump(mode="json"),
            }
            unit_bindings = {
                page.page_id: [
                    _source_binding_with_course_logic(
                        document,
                        course_data,
                        block_id=block_id,
                    )
                    for block_id in page.source_block_ids
                ]
                for page in deck.pages
            }
            bindings_by_key: dict[tuple[str, str, tuple[tuple[str, str], ...]], SourceBinding] = {}
            for values in unit_bindings.values():
                for binding in values:
                    key = (
                        str(binding.section_id or ""),
                        str(binding.block_id or ""),
                        tuple(sorted(binding.source_revisions.items())),
                    )
                    bindings_by_key[key] = binding
            bindings = list(bindings_by_key.values())
            variant_key = f"{mode}:{theme}"
            now = _utc_now()
            spec_payload = {
                "compiler_version": "representation_compiler_v6:slide_deck_v6",
                "representation_type": "slide_deck",
                "variant_key": variant_key,
                "content": content,
                "quality_report": deck.quality.model_dump(mode="json"),
            }
            spec_id = stable_hash(
                {
                    "course_id": document.course_id,
                    "variant_key": variant_key,
                    "source_digest": source_contract.source_digest,
                    "payload": spec_payload,
                },
                prefix="trs_",
            )
            spec_revision = stable_hash(spec_payload, prefix="tsr_")
            spec = TeachingRepresentationSpec(
                spec_id=spec_id,
                course_id=document.course_id,
                representation_type="slide_deck",
                variant_key=variant_key,
                source_bindings=bindings,
                unit_bindings=unit_bindings,
                payload=spec_payload,
                revision=spec_revision,
                created_at=now,
                updated_at=now,
            )
            representation_id = stable_hash(
                {"course_id": document.course_id, "type": "slide_deck", "variant_key": variant_key},
                prefix="trp_",
            )
            representation = TeachingRepresentation(
                representation_id=representation_id,
                course_id=document.course_id,
                representation_type="slide_deck",
                variant_key=variant_key,
                source_bindings=bindings,
                spec_id=spec_id,
                semantic_fingerprint=stable_hash(
                    {"graph": graph.graph_digest, "story": story.model_dump(mode="json")},
                    prefix="sem_",
                ),
                render_fingerprint=stable_hash(
                    {"template": template.template_digest, "pages": [page.resolved_layout for page in deck.pages]},
                    prefix="rnd_",
                ),
                quality_report_id=stable_hash(deck.quality.model_dump(mode="json"), prefix="rqr_"),
                revision=stable_hash(
                    {"spec_revision": spec_revision, "source_digest": source_contract.source_digest},
                    prefix="rpr_",
                ),
                status="ready",
                created_at=now,
                updated_at=now,
            )
            candidate_payload = {
                "schema_version": "slide_deck_v6_candidate_v1",
                "task_id": task_id,
                "course_id": document.course_id,
                "status": deck.status,
                "source_contract": source_contract.model_dump(mode="json"),
                "course_presentation_graph": graph.model_dump(mode="json"),
                "story_plan": story.model_dump(mode="json"),
                "visual_plan": visual.model_dump(mode="json"),
                "deck": deck.model_dump(mode="json"),
                "failure": None,
                "updated_at": now,
            }
            self.candidates.save(task_id, candidate_payload)
            registry = self.representations.publish_spec_and_representation(
                spec,
                representation,
                dependency_kind="layout",
                rebuild_policy="on_demand",
            )
            tracker.complete("publish")
            tracker.mark_published()
            progress = tracker.snapshot()
            await _emit(progress_callback, progress)
            return {
                "status": deck.status,
                "candidate_status": deck.status,
                "representation_id": representation_id,
                "spec_id": spec_id,
                "quality": deck.quality.model_dump(mode="json"),
                "registry": registry.model_dump(mode="json"),
                "progress": progress,
            }
        except V6BuildError as error:
            if any(item.item_id == current_work for item in tracker.manifest.items):
                tracker.fail(
                    current_work,
                    **error.failure.model_dump(mode="python"),
                )
            failure_payload = {
                "schema_version": "slide_deck_v6_candidate_v1",
                "task_id": task_id,
                "course_id": document.course_id,
                "status": "v6_failed",
                "source_contract": source_contract.model_dump(mode="json") if source_contract else None,
                "course_presentation_graph": graph.model_dump(mode="json") if graph else None,
                "story_plan": story.model_dump(mode="json") if story else None,
                "visual_plan": visual.model_dump(mode="json") if visual else None,
                "deck": None,
                "failure": error.failure.model_dump(mode="json"),
                "updated_at": _utc_now(),
            }
            self.candidates.save(task_id, failure_payload)
            await _emit(progress_callback, tracker.snapshot())
            raise


__all__ = [
    "SlideDeckV6CandidateRepository",
    "SlideDeckV6Orchestrator",
]
