"""Replay two production PPT checkpoints in memory with the feature branch."""

import asyncio
import hashlib
import io
import json
import re
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path


COURSE_ID = "2b3f4d8c-2af7-4133-a4f2-1060e8e9f54b"
TARGET_LESSONS = ("L1-3", "L1-4", "L1-5", "L1-6")
AUTHORING = Path("/opt/lingzhi/state/backend-data/teacher_lesson_authoring") / f"{COURSE_ID}.json"


def emit(**value) -> None:
    print(json.dumps(value, ensure_ascii=True), flush=True)


def module_contract(block: dict) -> dict:
    return {
        key: deepcopy(value)
        for key, value in block.items()
        if key not in {"content", "generation_contract_version", "generation_source"}
        and not key.startswith("ppt_")
    }


async def main() -> None:
    from course_generation.service import get_course_service
    from course_document import CourseBlock, CourseDocument, CourseSection, stable_hash
    from course_presentation_graph import compile_course_presentation_graph
    from slide_deck_v6 import compile_slide_deck_v6_from_manuscript
    from slide_deck_v6_renderer import export_slide_deck_v6_pptx
    from ppt_fixed_templates import compile_fixed_template
    from teacher_script_ppt import (
        RECOVERY_CONTRACT,
        compile_bundle_manuscript,
        completion_seed_blocks,
        generate_bundle,
        require_valid_bundle_pages,
        validate_block_pages,
    )
    from template_layout_contract import TemplateLayoutPackContractV1

    payload = json.loads(AUTHORING.read_text(encoding="utf-8"))
    service = get_course_service()
    completed_lessons = []
    for lesson_id in TARGET_LESSONS:
        lesson = payload["lessons"][lesson_id]
        script_revision_id = str(lesson.get("working_script_revision_id") or "")
        if not script_revision_id:
            raise ValueError(f"source_revision_missing:{lesson_id}")
        revision = next(
            item
            for item in lesson.get("script_revisions", [])
            if item.get("revision_id") == script_revision_id
        )
        state = lesson.get("ppt_manuscript") or {}
        task_id = str(state.get("task_id") or "")
        job = payload.get("jobs", {}).get(task_id) or {}
        if job.get("status") in {"pending", "running"}:
            raise ValueError(f"target_lesson_busy:{lesson_id}:{task_id}")
        template_payload = (job.get("request_snapshot") or {}).get("ppt_template")
        if not template_payload:
            template_payload = compile_fixed_template("qizhi-classroom").model_dump(mode="json")
        template = TemplateLayoutPackContractV1.model_validate(template_payload)
        checkpoint = job.get("bundle_blocks") or {}
        generated_sections = []
        model_calls = 0
        checkpoint_events = 0

        async def invoke(prompt, instructions, *, output_tokens, stream_delta=None, stream_reset=None):
            nonlocal model_calls
            model_calls += 1
            return await service._call_llm(
                prompt,
                instructions,
                use_fast_model=True,
                retry_count=1,
                max_attempts=1,
                enable_thinking=False,
                wait_for_capacity=True,
                reject_truncated=True,
                raise_on_failure=True,
                json_mode=True,
                max_tokens=output_tokens,
                request_timeout_seconds=float(
                    service._generation_budget.teacher_script_request_timeout_seconds
                ),
                on_content_delta=stream_delta,
                on_content_reset=stream_reset,
            )

        async def remember(_block):
            nonlocal checkpoint_events
            checkpoint_events += 1

        for section in revision.get("sections", []):
            source_blocks = section.get("blocks") or []
            contract = {
                "section_node_id": section.get("section_node_id") or lesson_id,
                "title": section.get("title") or lesson_id,
                "modules": [module_contract(block) for block in source_blocks],
            }
            generated = await generate_bundle(
                invoke=invoke,
                contract=contract,
                instructions="",
                template=template,
                seed_blocks=completion_seed_blocks(source_blocks, checkpoint),
                immutable_handout=True,
                on_checkpoint=remember,
            )
            expected_content = {block["block_id"]: block["content"] for block in source_blocks}
            actual_content = {
                block["block_id"]: block["content"] for block in generated.get("blocks", [])
            }
            if actual_content != expected_content:
                raise ValueError(f"handout_changed:{lesson_id}")
            require_valid_bundle_pages([generated])
            for block in generated.get("blocks", []):
                validate_block_pages(block, template)
            generated_sections.append(generated)

        blocks = [
            block for section in generated_sections for block in section.get("blocks", [])
        ]
        fallback_pages = sum(
            "页面事实缺少讲义依据"
            in str((page.get("fields") or {}).get("split_reason") or "")
            for block in blocks
            for page in block.get("ppt_pages", [])
        )
        document_revision = stable_hash(
            {block["block_id"]: block["content"] for block in blocks},
            prefix="isolated_ppt_doc_",
        )
        document = CourseDocument(
            course_id=f"isolated-{COURSE_ID}-{lesson_id}",
            title=f"isolated-{lesson_id}",
            document_revision=document_revision,
            sections=[CourseSection(section_id="lesson", title=lesson_id, position=0)],
            blocks=[
                CourseBlock(
                    block_id=block["block_id"],
                    section_id="lesson",
                    position=index,
                    payload={"markdown": block["content"]},
                    internal_revision=stable_hash(block["content"], prefix="block_"),
                )
                for index, block in enumerate(blocks)
            ],
        )
        manuscript = compile_bundle_manuscript(
            document,
            template,
            generated_sections,
            plan_revision_id=str(job.get("source_lesson_plan_revision_id") or ""),
            script_revision_id=script_revision_id,
        )
        graph = compile_course_presentation_graph(document, teaching_plan={})
        deck = compile_slide_deck_v6_from_manuscript(document, graph, manuscript, template)
        with tempfile.TemporaryDirectory(prefix=f"isolated-ppt-{lesson_id}-") as directory:
            output = Path(directory) / f"{lesson_id}.pptx"
            export_slide_deck_v6_pptx(
                {
                    **deck.model_dump(mode="json"),
                    "ppt_manuscript": manuscript.model_dump(mode="json"),
                },
                output,
            )
            content = output.read_bytes()
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            slides = [
                name
                for name in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            ]
            notes = [
                name
                for name in archive.namelist()
                if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", name)
            ]
        if len(slides) != manuscript.page_count or len(notes) != len(slides):
            raise ValueError(f"isolated_export_page_count_mismatch:{lesson_id}")
        emit(
            event="isolated_lesson_complete",
            lesson_id=lesson_id,
            original_task_id=task_id,
            original_status=job.get("status") or "not_started",
            source_revision=script_revision_id,
            recovery_contract=RECOVERY_CONTRACT,
            blocks=len(blocks),
            pages=sum(len(block.get("ppt_pages") or []) for block in blocks),
            physical_pages=manuscript.page_count,
            pptx_slides=len(slides),
            pptx_notes=len(notes),
            pptx_bytes=len(content),
            pptx_sha256=hashlib.sha256(content).hexdigest(),
            page_errors=sum(len(block.get("ppt_errors") or []) for block in blocks),
            model_calls=model_calls,
            checkpoint_events=checkpoint_events,
            source_grounded_fallback_pages=fallback_pages,
            handout_unchanged=True,
        )
        completed_lessons.append(lesson_id)
    emit(event="isolated_four_lesson_complete", lessons=completed_lessons)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        emit(event="isolated_test_failed", error_type=type(error).__name__, code=str(error)[:1200])
        raise
