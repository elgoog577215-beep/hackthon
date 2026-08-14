"""Single durable orchestration boundary for slide-deck V6 builds."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import tempfile
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from course_document import CourseDocument, stable_hash
from course_presentation_graph import compile_course_presentation_graph
from course_revisions import revision_vector_for_course
from slide_ai_planning_v6 import Planner, plan_slide_story_v3, plan_slide_visuals_v2
from slide_build_progress_v2 import (
    SlideBuildProgressRepositoryV2,
    SlideBuildProgressTrackerV2,
    SlideWorkItemV2,
)
from slide_deck_renderer import audit_exported_pptx
from slide_deck_v6 import (
    AIBatchDiagnosticV1,
    SlideStoryBatchV3,
    SlideStoryPlanV3,
    SlideVisualDecisionV2,
    SlideVisualPlanV2,
    V6BuildError,
    build_signature_v6,
    compile_ppt_source_contract_v2,
    compile_slide_deck_v6,
    prepare_story_plan_for_final_compilation,
)
from slide_deck_v6_renderer import export_slide_deck_v6_pptx
from teaching_representations import (
    SourceBinding,
    TeachingRepresentation,
    TeachingRepresentationRepository,
    TeachingRepresentationSpec,
    source_binding_for_document,
)
from template_layout_contract import TemplateLayoutPackContractV1, compile_builtin_template_layout_contract_v1

ProgressCallback = Callable[[dict[str, object]], Awaitable[None] | None]
SLIDE_DECK_V6_BUILD_CONTRACT_VERSION = "slide_deck_v6_build_contract_v6"


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

    def _checkpoint_path(self, task_id: str) -> Path:
        safe = "".join(character for character in task_id if character.isalnum() or character in "-_")
        if safe != task_id or not safe:
            raise ValueError("Invalid V6 checkpoint task ID")
        checkpoint_root = (self.root / "checkpoints").resolve()
        checkpoint_root.mkdir(parents=True, exist_ok=True)
        path = (checkpoint_root / f"{safe}.json").resolve()
        path.relative_to(checkpoint_root)
        return path

    def save_checkpoint(self, task_id: str, payload: dict[str, Any]) -> None:
        path = self._checkpoint_path(task_id)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def load_checkpoint(self, task_id: str) -> dict[str, Any]:
        path = self._checkpoint_path(task_id)
        if not path.is_file():
            raise FileNotFoundError(task_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def summarize(
        self,
        *,
        course_id: str | None = None,
        progress_root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Aggregate terminal V6 outcomes without exposing course content."""

        candidates: list[dict[str, Any]] = []
        for path in self.root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("schema_version") != "slide_deck_v6_candidate_v1":
                continue
            if payload.get("status") not in {"v6_ready", "v6_needs_manual_edit", "v6_failed"}:
                continue
            if course_id is not None and payload.get("course_id") != course_id:
                continue
            candidates.append(payload)

        total = len(candidates)
        successful = sum(
            item.get("status") in {"v6_ready", "v6_needs_manual_edit"}
            for item in candidates
        )
        failed = sum(item.get("status") == "v6_failed" for item in candidates)
        manual = sum(item.get("status") == "v6_needs_manual_edit" for item in candidates)
        story_failures = sum(
            (item.get("failure") or {}).get("stage") == "story"
            for item in candidates
        )
        template_conflicts = sum(
            (
                (item.get("failure") or {}).get("stage") == "template"
                or "template" in str((item.get("failure") or {}).get("code") or "")
            )
            for item in candidates
        )
        visual_decisions = [
            decision
            for item in candidates
            for decision in ((item.get("visual_plan") or {}).get("decisions") or [])
        ]
        degraded_visuals = sum(bool(item.get("degraded")) for item in visual_decisions)

        duration_totals: dict[str, float] = {}
        duration_counts: dict[str, int] = {}
        resolved_progress_root = Path(progress_root).resolve() if progress_root else None
        if resolved_progress_root and resolved_progress_root.is_dir():
            for candidate in candidates:
                task_id = str(candidate.get("task_id") or "")
                if not task_id or any(
                    not (character.isalnum() or character in "-_")
                    for character in task_id
                ):
                    continue
                path = (resolved_progress_root / f"{task_id}.json").resolve()
                try:
                    path.relative_to(resolved_progress_root)
                    manifest = json.loads(path.read_text(encoding="utf-8"))
                except (ValueError, OSError, json.JSONDecodeError):
                    continue
                for item in manifest.get("items") or []:
                    started_at = str(item.get("started_at") or "")
                    completed_at = str(item.get("completed_at") or "")
                    stage = str(item.get("stage") or "")
                    if not stage or not started_at or not completed_at:
                        continue
                    try:
                        duration_ms = max(
                            0.0,
                            (datetime.fromisoformat(completed_at) - datetime.fromisoformat(started_at)).total_seconds()
                            * 1000,
                        )
                    except ValueError:
                        continue
                    duration_totals[stage] = duration_totals.get(stage, 0.0) + duration_ms
                    duration_counts[stage] = duration_counts.get(stage, 0) + 1

        def rate(numerator: int, denominator: int = total) -> float:
            return round(numerator / denominator, 4) if denominator else 0.0

        return {
            "schema_version": "slide_deck_v6_metrics_v1",
            "course_id": course_id or "",
            "total_builds": total,
            "successful_builds": successful,
            "failed_builds": failed,
            "success_rate": rate(successful),
            "story_ai_failure_rate": rate(story_failures),
            "visual_degradation_rate": rate(degraded_visuals, len(visual_decisions)),
            "manual_edit_rate": rate(manual),
            "template_conflict_rate": rate(template_conflicts),
            "average_stage_duration_ms": {
                stage: round(duration_totals[stage] / duration_counts[stage])
                for stage in sorted(duration_totals)
            },
        }


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

    async def repair_visuals(
        self,
        *,
        task_id: str,
        document: CourseDocument,
        course_data: dict[str, Any],
        representation_id: str,
        mode: str,
        theme: str,
        story_planner: Planner,
        visual_planner: Planner,
        source_revision_provider: Callable[[], str],
        target_page_ids: list[str] | None = None,
        template_contract: TemplateLayoutPackContractV1 | None = None,
        template_digest_provider: Callable[[], str] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Seed a new durable task from a published V6 deck's healthy work."""

        registry = self.representations.load(document.course_id)
        representation = next(
            (
                item
                for item in registry.representations
                if item.representation_id == representation_id
                and item.representation_type == "slide_deck"
                and item.status == "ready"
            ),
            None,
        )
        if representation is None:
            raise V6BuildError(
                stage="visual_repair",
                code="visual_repair_base_unavailable",
                message="Visual repair requires a currently published slide deck",
                retryable=False,
            )
        spec = next(
            (item for item in registry.specs if item.spec_id == representation.spec_id),
            None,
        )
        content = dict((spec.payload.get("content") if spec else None) or {})
        if content.get("schema_version") != "slide_deck_v6":
            raise V6BuildError(
                stage="visual_repair",
                code="visual_repair_requires_v6",
                message="Only a published V6 deck can use selective visual repair",
                retryable=False,
            )
        template = template_contract or (
            TemplateLayoutPackContractV1.model_validate(content["template_contract"])
            if isinstance(content.get("template_contract"), dict)
            else compile_builtin_template_layout_contract_v1(theme)
        )
        source_contract = dict(content.get("source_contract") or {})
        if (
            str(source_contract.get("course_document_revision") or "")
            != str(document.document_revision or "")
            or str(source_revision_provider() or "")
            != str(document.document_revision or "")
        ):
            raise V6BuildError(
                stage="visual_repair",
                code="visual_repair_source_changed",
                message="The published deck no longer matches the frozen course revision",
                retryable=True,
            )
        if str(source_contract.get("template_digest") or "") != template.template_digest:
            raise V6BuildError(
                stage="visual_repair",
                code="visual_repair_template_changed",
                message="The published deck no longer matches the selected template contract",
                retryable=True,
            )
        expected_signature = build_signature_v6(
            document=document,
            course_data=course_data,
            mode=mode,
            theme=theme,
            template_contract=template,
        )
        if (
            str((content.get("build_signature") or {}).get("signature") or "")
            != expected_signature["signature"]
        ):
            raise V6BuildError(
                stage="visual_repair",
                code="visual_repair_build_contract_changed",
                message="Course logic, mode, or template inputs changed after publication",
                retryable=True,
            )

        story_payload = dict(content.get("story_plan") or {})
        story_payload.pop("pages", None)
        story = SlideStoryPlanV3.model_validate(story_payload)
        visual = SlideVisualPlanV2.model_validate(content.get("visual_plan"))
        degraded_page_ids = [
            decision.page_id for decision in visual.decisions if decision.degraded
        ]
        requested_page_ids = list(dict.fromkeys(target_page_ids or degraded_page_ids))
        invalid_targets = set(requested_page_ids) - set(degraded_page_ids)
        if invalid_targets:
            raise V6BuildError(
                stage="visual_repair",
                code="visual_repair_target_not_degraded",
                message="Selective visual repair can target only degraded published pages",
                retryable=False,
                page_id=sorted(invalid_targets)[0],
            )
        if not requested_page_ids:
            raise V6BuildError(
                stage="visual_repair",
                code="visual_repair_not_required",
                message="The published V6 deck has no degraded visual pages",
                retryable=False,
            )
        repair_context = {
            "schema_version": "slide_visual_repair_context_v1",
            "base_representation_id": representation.representation_id,
            "base_representation_revision": representation.revision,
            "base_spec_id": representation.spec_id,
            "target_page_ids": requested_page_ids,
        }
        checkpoint = {
            "schema_version": "slide_deck_v6_checkpoint_v1",
            "build_contract_version": SLIDE_DECK_V6_BUILD_CONTRACT_VERSION,
            "task_id": task_id,
            "course_id": document.course_id,
            "course_document_revision": document.document_revision,
            "template_digest": template.template_digest,
            "mode": mode,
            "theme": theme,
            "source_contract": source_contract,
            "course_presentation_graph": content.get("course_presentation_graph"),
            "story_plan": story.model_dump(mode="json"),
            "story_batches": [
                batch.model_dump(mode="json") for batch in story.batches
            ],
            "visual_decisions": [
                decision.model_dump(mode="json")
                for decision in visual.decisions
                if decision.page_id not in set(requested_page_ids)
            ],
            "ai_batch_diagnostics": list(content.get("ai_batch_diagnostics") or []),
            "visual_repair": repair_context,
            "updated_at": _utc_now(),
        }
        self.candidates.save_checkpoint(task_id, checkpoint)
        return await self.build(
            task_id=task_id,
            document=document,
            course_data=course_data,
            mode=mode,
            theme=theme,
            story_planner=story_planner,
            visual_planner=visual_planner,
            source_revision_provider=source_revision_provider,
            template_contract=template,
            template_digest_provider=template_digest_provider,
            publish_result=True,
            progress_callback=progress_callback,
        )

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
        template_contract: TemplateLayoutPackContractV1 | None = None,
        template_digest_provider: Callable[[], str] | None = None,
        publish_result: bool = True,
        shadow_context: dict[str, Any] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        template = template_contract or compile_builtin_template_layout_contract_v1(theme)
        try:
            restored_checkpoint = self.candidates.load_checkpoint(task_id)
        except FileNotFoundError:
            restored_checkpoint = None
        if restored_checkpoint and restored_checkpoint.get("schema_version") == "slide_deck_v6_checkpoint_v1":
            identity = (
                restored_checkpoint.get("course_id") == document.course_id
                and restored_checkpoint.get("course_document_revision") == document.document_revision
                and restored_checkpoint.get("template_digest") == template.template_digest
                and restored_checkpoint.get("mode") == mode
                and restored_checkpoint.get("theme") == theme
                and restored_checkpoint.get("build_contract_version")
                == SLIDE_DECK_V6_BUILD_CONTRACT_VERSION
            )
            if not identity:
                raise V6BuildError(
                    stage="recovery",
                    code="v6_recovery_contract_mismatch",
                    message=(
                        "Persisted V6 work belongs to a different frozen source, "
                        "template, or build contract"
                    ),
                    retryable=False,
                )
        try:
            tracker = SlideBuildProgressTrackerV2.load(
                task_id,
                repository=self.progress_repository,
            )
        except FileNotFoundError:
            tracker = SlideBuildProgressTrackerV2.create(
                task_id,
                repository=self.progress_repository,
            )
        else:
            if tracker.manifest.status == "active":
                tracker.resume_active()
            elif (
                tracker.manifest.status == "failed"
                and tracker.manifest.failure is not None
                and tracker.manifest.failure.retryable
                and restored_checkpoint is not None
            ):
                tracker.resume_failed()
            else:
                raise V6BuildError(
                    stage="recovery",
                    code="v6_terminal_task_requires_new_task",
                    message="A terminal V6 task cannot be restarted with the same task ID",
                    retryable=False,
                )
        current_work = "source-contract"
        source_contract = None
        graph = None
        story = None
        visual = None
        finalize_item_id = "publish" if publish_result else "finalize-shadow"
        checkpoint: dict[str, Any] = {
            "schema_version": "slide_deck_v6_checkpoint_v1",
            "build_contract_version": SLIDE_DECK_V6_BUILD_CONTRACT_VERSION,
            "task_id": task_id,
            "course_id": document.course_id,
            "course_document_revision": document.document_revision,
            "template_digest": template.template_digest,
            "mode": mode,
            "theme": theme,
            "story_batches": [],
            "visual_decisions": [],
            "updated_at": _utc_now(),
        }
        if restored_checkpoint and restored_checkpoint.get("schema_version") == "slide_deck_v6_checkpoint_v1":
            checkpoint.update(restored_checkpoint)

        def save_checkpoint(**updates: Any) -> None:
            checkpoint.update(updates)
            checkpoint["updated_at"] = _utc_now()
            self.candidates.save_checkpoint(task_id, checkpoint)

        ai_batch_diagnostics_by_key = {
            (diagnostic.kind, diagnostic.batch_id): diagnostic
            for diagnostic in (
                AIBatchDiagnosticV1.model_validate(item)
                for item in checkpoint.get("ai_batch_diagnostics") or []
            )
        }

        def store_ai_batch_diagnostic(value: Any) -> None:
            if value is None:
                return
            diagnostic = AIBatchDiagnosticV1.model_validate(
                value.model_dump(mode="json")
                if isinstance(value, AIBatchDiagnosticV1)
                else value
            )
            ai_batch_diagnostics_by_key[(diagnostic.kind, diagnostic.batch_id)] = diagnostic

        def serialized_ai_batch_diagnostics() -> list[dict[str, Any]]:
            return [
                diagnostic.model_dump(mode="json")
                for diagnostic in ai_batch_diagnostics_by_key.values()
            ]

        tracker.add_work([
            SlideWorkItemV2(item_id="source-contract", kind="local", stage="source", label="冻结课程与模板真源"),
            SlideWorkItemV2(item_id="course-graph", kind="local", stage="course_graph", label="构建完整教学单元图"),
            SlideWorkItemV2(
                item_id="materialize",
                kind="local",
                stage="materialize",
                label="Compile source-faithful pages",
            ),
            SlideWorkItemV2(
                item_id="quality",
                kind="local",
                stage="quality",
                label="Run fidelity and render gates",
            ),
            SlideWorkItemV2(
                item_id=finalize_item_id,
                kind="local",
                stage="publish" if publish_result else "shadow_finalize",
                label="Publish atomically" if publish_result else "Finalize read-only shadow",
            ),
        ])
        await _emit(progress_callback, tracker.snapshot())
        try:
            tracker.start("source-contract")
            source_contract = compile_ppt_source_contract_v2(
                document,
                teaching_plan=dict(course_data.get("course_teaching_plan") or {}),
                knowledge_snapshot=dict(course_data.get("course_knowledge_base") or {}),
                coherence_contract=dict(course_data.get("course_coherence_contract") or {}),
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
            save_checkpoint(
                source_contract=source_contract.model_dump(mode="json"),
                course_presentation_graph=graph.model_dump(mode="json"),
            )
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
            ] + [
                SlideWorkItemV2(
                    item_id=f"visual-{index + 1}",
                    kind="ai_batch",
                    stage="visual",
                    label=f"Visual planning batch {index + 1}",
                    chapter_id=section_id,
                    batch_id=f"visual-{index + 1}",
                )
                for index, section_id in enumerate(story_sections)
            ])
            tracker.complete("course-graph")
            await _emit(progress_callback, tracker.snapshot())

            resumed_story_batches = [
                SlideStoryBatchV3.model_validate(item)
                for item in checkpoint.get("story_batches") or []
            ]
            story_batches_by_id = {
                batch.batch_id: batch for batch in resumed_story_batches
            }

            async def story_batch_progress(event: dict[str, Any]) -> None:
                nonlocal current_work
                work_id = str(event["batch_id"])
                current_work = work_id
                phase = str(event["phase"])
                if phase == "started":
                    tracker.start(
                        work_id,
                        chapter_id=str(event["chapter_id"]),
                        batch_id=work_id,
                        provider_wait=True,
                        retry_attempt=int(event.get("retry_attempt") or 0),
                    )
                elif phase == "completed":
                    batch = event["batch"]
                    story_batches_by_id[work_id] = batch
                    store_ai_batch_diagnostic(event.get("diagnostic"))
                    save_checkpoint(story_batches=[
                        story_batches_by_id[key].model_dump(mode="json")
                        for key in sorted(story_batches_by_id)
                    ], ai_batch_diagnostics=serialized_ai_batch_diagnostics())
                    tracker.complete(work_id)
                elif phase == "failed":
                    store_ai_batch_diagnostic(event.get("diagnostic"))
                    save_checkpoint(
                        ai_batch_diagnostics=serialized_ai_batch_diagnostics()
                    )
                await _emit(progress_callback, tracker.snapshot())

            story = await _await_with_heartbeats(
                plan_slide_story_v3(
                    graph,
                    template,
                    ai_planner=story_planner,
                    batch_callback=story_batch_progress,
                    resume_batches=resumed_story_batches,
                ),
                tracker=tracker,
                callback=progress_callback,
            )
            save_checkpoint(
                story_plan=story.model_dump(mode="json"),
                story_batches=[
                    batch.model_dump(mode="json") for batch in story.batches
                ],
            )
            tracker.add_work([
                SlideWorkItemV2(
                    item_id=f"render-{page.page_id}",
                    kind="render_page",
                    stage="render",
                    label=f"Compile planned page {page.page_ordinal + 1}",
                    page_id=page.page_id,
                )
                for page in story.pages
            ])
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

            resumed_visual_decisions = [
                SlideVisualDecisionV2.model_validate(item)
                for item in checkpoint.get("visual_decisions") or []
            ]
            visual_decisions_by_page = {
                decision.page_id: decision for decision in resumed_visual_decisions
            }

            async def visual_batch_progress(event: dict[str, Any]) -> None:
                nonlocal current_work
                work_id = str(event["batch_id"])
                current_work = work_id
                phase = str(event["phase"])
                if phase == "started":
                    tracker.start(
                        work_id,
                        chapter_id=str(event["chapter_id"]),
                        batch_id=work_id,
                        provider_wait=True,
                    )
                elif phase == "completed":
                    for decision in event["decisions"]:
                        visual_decisions_by_page[decision.page_id] = decision
                    store_ai_batch_diagnostic(event.get("diagnostic"))
                    save_checkpoint(visual_decisions=[
                        visual_decisions_by_page[key].model_dump(mode="json")
                        for key in sorted(visual_decisions_by_page)
                    ], ai_batch_diagnostics=serialized_ai_batch_diagnostics())
                    tracker.complete(work_id)
                elif phase == "failed":
                    store_ai_batch_diagnostic(event.get("diagnostic"))
                    save_checkpoint(
                        ai_batch_diagnostics=serialized_ai_batch_diagnostics()
                    )
                await _emit(progress_callback, tracker.snapshot())

            visual = await _await_with_heartbeats(
                plan_slide_visuals_v2(
                    story,
                    graph,
                    template,
                    ai_planner=visual_planner,
                    batch_callback=visual_batch_progress,
                    resume_decisions=resumed_visual_decisions,
                ),
                tracker=tracker,
                callback=progress_callback,
            )
            save_checkpoint(
                visual_plan=visual.model_dump(mode="json"),
                visual_decisions=[
                    decision.model_dump(mode="json") for decision in visual.decisions
                ],
            )
            repair_context = dict(checkpoint.get("visual_repair") or {})
            if repair_context:
                target_page_ids = set(repair_context.get("target_page_ids") or [])
                incomplete_repairs = [
                    decision
                    for decision in visual.decisions
                    if decision.page_id in target_page_ids and decision.degraded
                ]
                if incomplete_repairs:
                    failed = incomplete_repairs[0]
                    raise V6BuildError(
                        stage="visual_repair",
                        code="visual_repair_incomplete",
                        message=(
                            "The targeted page is still degraded after visual replanning: "
                            f"{failed.degradation_reason}"
                        ),
                        retryable=True,
                        page_id=failed.page_id,
                    )

            tracker.add_work([
                SlideWorkItemV2(item_id="materialize", kind="local", stage="materialize", label="编译课程忠实型页面"),
                SlideWorkItemV2(item_id="quality", kind="local", stage="quality", label="执行忠实度与渲染门禁"),
                SlideWorkItemV2(
                    item_id=finalize_item_id,
                    kind="local",
                    stage="publish" if publish_result else "shadow_finalize",
                    label="原子发布正式课件" if publish_result else "完成只读影子候选",
                ),
            ])
            await _emit(progress_callback, tracker.snapshot())

            current_work = "materialize"
            tracker.start("materialize")
            story = prepare_story_plan_for_final_compilation(
                story,
                graph,
                template,
            )
            save_checkpoint(story_plan=story.model_dump(mode="json"))
            deck = compile_slide_deck_v6(document, graph, story, visual, template)
            tracker.add_work([
                SlideWorkItemV2(
                    item_id=f"render-{page.page_id}",
                    kind="render_page",
                    stage="render",
                    label=f"Compile page {page.page_ordinal + 1}",
                    page_id=page.page_id,
                )
                for page in deck.pages
            ])
            tracker.complete("materialize")
            await _emit(progress_callback, tracker.snapshot())

            first_page = deck.pages[0]
            current_work = f"render-{first_page.page_id}"
            tracker.start(current_work, page_id=first_page.page_id)
            try:
                with tempfile.TemporaryDirectory(prefix="lingzhi-v6-render-gate-") as review_dir:
                    review_path = Path(review_dir) / "candidate.pptx"
                    await _await_with_heartbeats(
                        asyncio.to_thread(export_slide_deck_v6_pptx, deck, review_path),
                        tracker=tracker,
                        callback=progress_callback,
                    )
                    render_review = await _await_with_heartbeats(
                        asyncio.to_thread(
                            audit_exported_pptx,
                            review_path,
                            expected_slide_count=len(deck.pages),
                        ),
                        tracker=tracker,
                        callback=progress_callback,
                    )
            except V6BuildError:
                raise
            except Exception as error:
                raise V6BuildError(
                    stage="render",
                    code="render_export_failed",
                    message=str(error) or "V6 PPTX export could not be opened and audited",
                    retryable=True,
                    page_id=first_page.page_id,
                ) from error
            if not render_review.get("passed"):
                first_blocker = next(iter(render_review.get("blockers") or []), {})
                page_number = int(first_blocker.get("page") or 0)
                failed_page_id = (
                    deck.pages[page_number - 1].page_id
                    if 0 < page_number <= len(deck.pages)
                    else first_page.page_id
                )
                raise V6BuildError(
                    stage="render",
                    code="render_quality_gate_failed",
                    message=str(first_blocker.get("code") or "Exported V6 deck failed render audit"),
                    retryable=False,
                    page_id=failed_page_id,
                )
            for page in deck.pages:
                work_id = f"render-{page.page_id}"
                if work_id != current_work:
                    tracker.start(work_id, page_id=page.page_id)
                tracker.complete(work_id)
            current_work = "quality"
            tracker.start("quality")
            deck.quality.render_review = dict(render_review)
            if not deck.quality.passed:
                raise V6BuildError(
                    stage="quality",
                    code="v6_quality_gate_failed",
                    message="V6 deck failed its final source, template, subject, or render gate",
                    retryable=False,
                )
            tracker.complete("quality")
            await _emit(progress_callback, tracker.snapshot())

            current_work = finalize_item_id
            tracker.start(finalize_item_id)
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
            repair_context = dict(checkpoint.get("visual_repair") or {})
            if repair_context:
                current_registry = self.representations.load(document.course_id)
                current_representation = next(
                    (
                        item
                        for item in current_registry.representations
                        if item.representation_id
                        == repair_context.get("base_representation_id")
                    ),
                    None,
                )
                if (
                    current_representation is None
                    or current_representation.spec_id
                    != repair_context.get("base_spec_id")
                    or current_representation.revision
                    != repair_context.get("base_representation_revision")
                ):
                    raise V6BuildError(
                        stage="publish",
                        code="visual_repair_base_changed",
                        message="A newer deck revision was published while visual repair was running",
                        retryable=True,
                    )
            degraded_visual_count = sum(
                1 for decision in visual.decisions if decision.degraded
            )
            planning_status = {
                "story_ai": {
                    "status": "completed",
                    "batch_count": len(story.batches),
                    "providers": list(dict.fromkeys(
                        batch.provider for batch in story.batches if batch.provider
                    )),
                },
                "visual_ai": {
                    "status": (
                        "partial_degraded" if degraded_visual_count else "completed"
                    ),
                    "page_count": len(visual.decisions),
                    "degraded_page_count": degraded_visual_count,
                    "providers": list(dict.fromkeys(
                        decision.provider
                        for decision in visual.decisions
                        if decision.provider
                    )),
                },
            }
            if degraded_visual_count:
                planning_status["visual_ai"]["degraded_pages"] = [
                    {
                        "page_id": decision.page_id,
                        "reason": decision.degradation_reason,
                    }
                    for decision in visual.decisions
                    if decision.degraded
                ]
            content = {
                **deck.model_dump(mode="json"),
                "build_signature": build_signature_v6(
                    document=document,
                    course_data=course_data,
                    mode=mode,
                    theme=theme,
                    template_contract=template,
                ),
                "source_contract": source_contract.model_dump(mode="json"),
                "course_presentation_graph": graph.model_dump(mode="json"),
                "story_plan": story.model_dump(mode="json"),
                "visual_plan": visual.model_dump(mode="json"),
                "template_contract": template.model_dump(mode="json"),
                "ai_batch_diagnostics": serialized_ai_batch_diagnostics(),
                "planning_status": planning_status,
                **({"visual_repair": repair_context} if repair_context else {}),
            }
            unit_bindings = {
                page.page_id: (
                    [
                        _source_binding_with_course_logic(
                            document,
                            course_data,
                            block_id=block_id,
                        )
                        for block_id in page.source_block_ids
                    ]
                    or [
                        _source_binding_with_course_logic(
                            document,
                            course_data,
                            section_id=section_id,
                        )
                        for section_id in page.source_section_ids
                    ]
                )
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
                "ai_batch_diagnostics": serialized_ai_batch_diagnostics(),
                "planning_status": planning_status,
                "visual_repair": repair_context or None,
                "deck": deck.model_dump(mode="json"),
                "published": publish_result,
                "shadow_context": dict(shadow_context or {}),
                "failure": None,
                "updated_at": now,
            }
            self.candidates.save(task_id, candidate_payload)
            if publish_result:
                registry_payload = self.representations.publish_spec_and_representation(
                    spec,
                    representation,
                    dependency_kind="layout",
                    rebuild_policy="on_demand",
                ).model_dump(mode="json")
            else:
                registry_payload = {}
            tracker.complete(finalize_item_id)
            tracker.mark_completed(published=publish_result)
            progress = tracker.snapshot()
            await _emit(progress_callback, progress)
            return {
                "status": deck.status,
                "candidate_status": deck.status,
                "published": publish_result,
                "representation_id": representation_id,
                "spec_id": spec_id,
                "quality": deck.quality.model_dump(mode="json"),
                "registry": registry_payload,
                "progress": progress,
            }
        except V6BuildError as error:
            failure_work = (
                error.failure.batch_id
                if any(
                    item.item_id == error.failure.batch_id
                    for item in tracker.manifest.items
                )
                else current_work
            )
            if any(item.item_id == failure_work for item in tracker.manifest.items):
                tracker.fail(
                    failure_work,
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
                "ai_batch_diagnostics": serialized_ai_batch_diagnostics(),
                "visual_repair": dict(checkpoint.get("visual_repair") or {}) or None,
                "deck": None,
                "published": False,
                "shadow_context": dict(shadow_context or {}),
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
