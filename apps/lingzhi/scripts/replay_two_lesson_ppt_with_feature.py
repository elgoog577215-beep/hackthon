"""Replay two production PPT checkpoints in memory with the feature branch."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path


COURSE_ID = "2b3f4d8c-2af7-4133-a4f2-1060e8e9f54b"
TARGETS = (
    ("L1-1", "tlj-979b941a22c84c44beb1f07ac2205798", "tlsr-1097b09406b5080ff21e0afd"),
    ("L1-2", "tlj-68760fa978174d4e996b342e583d3e4e", "tlsr-a209b5939e3dba285598986c"),
)
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
    from teacher_script_ppt import (
        RECOVERY_CONTRACT,
        completion_seed_blocks,
        generate_bundle,
        require_valid_bundle_pages,
        validate_block_pages,
    )
    from template_layout_contract import TemplateLayoutPackContractV1

    payload = json.loads(AUTHORING.read_text(encoding="utf-8"))
    service = get_course_service()
    for lesson_id, task_id, script_revision_id in TARGETS:
        lesson = payload["lessons"][lesson_id]
        if lesson.get("working_script_revision_id") != script_revision_id:
            raise ValueError(f"source_revision_changed:{lesson_id}")
        revision = next(
            item
            for item in lesson.get("script_revisions", [])
            if item.get("revision_id") == script_revision_id
        )
        job = payload.get("jobs", {}).get(task_id) or {}
        template_payload = (job.get("request_snapshot") or {}).get("ppt_template")
        if not template_payload:
            raise ValueError(f"template_snapshot_missing:{lesson_id}")
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
        emit(
            event="isolated_lesson_complete",
            lesson_id=lesson_id,
            original_task_id=task_id,
            original_status=job.get("status"),
            source_revision=script_revision_id,
            recovery_contract=RECOVERY_CONTRACT,
            blocks=len(blocks),
            pages=sum(len(block.get("ppt_pages") or []) for block in blocks),
            page_errors=sum(len(block.get("ppt_errors") or []) for block in blocks),
            model_calls=model_calls,
            checkpoint_events=checkpoint_events,
            source_grounded_fallback_pages=fallback_pages,
            handout_unchanged=True,
        )
    emit(event="isolated_two_lesson_complete", lessons=[item[0] for item in TARGETS])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        emit(event="isolated_test_failed", error_type=type(error).__name__, code=str(error)[:1200])
        raise
