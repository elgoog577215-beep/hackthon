import json
from pathlib import Path

from course_document import CourseDocument
from teaching_representations import TeachingRepresentationRepository
from video1_demo_preset import (
    BASELINE_GOAL,
    COURSE_ID,
    COURSE_TITLE,
    FOLLOWUP_GOAL,
    TARGET_GOAL,
    TARGET_SECTION_ID,
    build_video1_course_envelope,
    prepare_video1_demo,
)


def test_video1_course_is_a_twenty_lesson_ai_literacy_course():
    envelope = build_video1_course_envelope()
    document = CourseDocument.model_validate(envelope["course_document"])
    target = next(section for section in document.sections if section.section_id == TARGET_SECTION_ID)

    assert COURSE_ID == "demo-ai-literacy-update-v1"
    assert COURSE_TITLE == "人工智能通识课"
    assert len(document.sections) == 20
    assert target.position == 16
    assert target.title == "第17讲 DeepSeek 核心能力与应用"
    assert target.learning_objective == BASELINE_GOAL
    assert target.attributes["demo_target_goal"] == TARGET_GOAL
    assert target.attributes["demo_followup_goal"] == FOLLOWUP_GOAL
    assert envelope["demo_metadata"]["external_model_required"] is False
    blocks_by_section = {
        section.section_id: [
            block for block in document.blocks if block.section_id == section.section_id
        ]
        for section in document.sections
    }
    assert len(blocks_by_section[TARGET_SECTION_ID]) >= 12
    assert all(
        len(blocks) == 2
        for section_id, blocks in blocks_by_section.items()
        if section_id != TARGET_SECTION_ID
    )
    assert any(
        "AI 论文助手" in str(block.payload.get("title") or "")
        for block in blocks_by_section[TARGET_SECTION_ID]
    )


def test_prepare_video1_demo_builds_ready_slide_and_resets_only_owned_state(tmp_path: Path):
    data_dir = tmp_path / "data"
    other = {"course_id": "real-course", "course_name": "real"}
    _write_json(data_dir / "courses" / "real-course.json", other)
    _write_json(data_dir / "courses" / f"{COURSE_ID}.json", {"course_id": COURSE_ID})
    _write_json(data_dir / "teaching_representations" / "old-demo.json", {"course_id": COURSE_ID})
    _write_json(data_dir / "teaching_representations" / "real.json", {"course_id": "real-course"})
    _write_json(data_dir / "change_proposals" / "cps_demo.json", {"course_id": COURSE_ID})
    _write_json(data_dir / "change_proposals" / "cps_real.json", {"course_id": "real-course"})
    _write_json(data_dir / "course_versions" / COURSE_ID / "mutated.json", {"course_id": COURSE_ID})

    result = prepare_video1_demo(data_dir)

    assert result["lesson_count"] == 20
    assert result["baseline_goal"] == BASELINE_GOAL
    assert result["target_goal"] == TARGET_GOAL
    assert result["followup_goal"] == FOLLOWUP_GOAL
    assert result["target_slide_number"] > 0
    assert result["compiled_representation_count"] == 6
    assert (data_dir / "courses" / "real-course.json").exists()
    assert (data_dir / "teaching_representations" / "real.json").exists()
    assert (data_dir / "change_proposals" / "cps_real.json").exists()
    assert not (data_dir / "change_proposals" / "cps_demo.json").exists()

    registry = TeachingRepresentationRepository(data_dir / "teaching_representations").load(COURSE_ID)
    slide_representation = next(
        item for item in registry.representations if item.representation_type == "slide_deck"
    )
    slide_spec = next(item for item in registry.specs if item.spec_id == slide_representation.spec_id)
    target_slide = next(
        slide
        for slide in slide_spec.payload["content"]["slides"]
        if slide.get("section_id") == TARGET_SECTION_ID
    )
    assert target_slide["key_message"] == BASELINE_GOAL


def test_prepare_video1_demo_is_repeatable_after_demo_mutation(tmp_path: Path):
    data_dir = tmp_path / "data"
    first = prepare_video1_demo(data_dir)
    course_path = Path(first["course_file"])
    mutated = json.loads(course_path.read_text(encoding="utf-8"))
    mutated["course_name"] = "被修改的课程"
    _write_json(course_path, mutated)

    second = prepare_video1_demo(data_dir)
    restored = json.loads(course_path.read_text(encoding="utf-8"))
    assert first["course_revision"] == second["course_revision"]
    assert restored["course_name"] == COURSE_TITLE


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
