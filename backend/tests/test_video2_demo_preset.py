from __future__ import annotations

import json
from pathlib import Path

from course_document import CourseDocument
from video2_demo_preset import (
    COURSE_ID,
    COURSE_TITLE,
    DEMO_USER_ID,
    FIXED_PROMPT,
    PPT_BASELINE_GOAL,
    TARGET_SECTION_ID,
    _is_course_scoped_payload,
    build_video2_course_envelope,
    prepare_video2_demo,
)


def test_video2_course_is_curated_and_keeps_the_growth_gap_open():
    envelope = build_video2_course_envelope()
    document = CourseDocument.model_validate(envelope["course_document"])
    learnable_sections = [section for section in document.sections if section.level == 2]
    target = next(
        section for section in document.sections
        if section.section_id == TARGET_SECTION_ID
    )
    target_blocks = [
        block for block in document.blocks
        if block.section_id == TARGET_SECTION_ID
    ]
    initial_text = "\n".join(
        "\n".join([
            str(block.payload.get("title") or ""),
            str(block.payload.get("markdown") or ""),
        ])
        for block in target_blocks
    )

    assert envelope["course_name"] == COURSE_TITLE
    assert envelope["generation_source"] == "curated_local_preset"
    assert len(learnable_sections) == 12
    assert len(document.blocks) >= 58
    assert target.title == "1.2 矩阵：线性映射与矩阵运算"
    assert target.learning_objective == PPT_BASELINE_GOAL
    assert len(target_blocks) == 7
    assert any(section.title.startswith("3.1 特征向量") for section in learnable_sections)
    assert any(section.title.startswith("4.3 综合项目") for section in learnable_sections)
    assert "矩阵乘法" in initial_text
    assert "不交换" in initial_text
    assert "A(Bv)" not in initial_text
    assert "先右后左" not in initial_text
    assert envelope["demo_metadata"]["fixed_prompt"] == FIXED_PROMPT
    assert envelope["demo_metadata"]["external_model_required"] is False


def test_prepare_video2_demo_resets_only_the_dedicated_course(tmp_path: Path):
    data_dir = tmp_path / "data"
    courses_dir = data_dir / "courses"
    courses_dir.mkdir(parents=True)
    other_course = {"course_id": "other-course", "course_name": "其他课程"}
    (courses_dir / "other-course.json").write_text(
        json.dumps(other_course, ensure_ascii=False),
        encoding="utf-8",
    )
    (courses_dir / f"{COURSE_ID}.json").write_text(
        json.dumps({"course_id": COURSE_ID, "course_name": "旧演示"}),
        encoding="utf-8",
    )
    events = [
        {"event_id": "keep", "course_id": "other-course"},
        {"event_id": "remove", "course_id": COURSE_ID},
    ]
    (data_dir / "learning_events.json").write_text(
        json.dumps(events, ensure_ascii=False),
        encoding="utf-8",
    )

    result = prepare_video2_demo(data_dir)

    assert result["course_id"] == COURSE_ID
    assert result["learner_id"] == DEMO_USER_ID
    assert result["external_model_required"] is False
    assert result["compiled_representation_count"] == 6
    assert result["relative_ppt_url"] == f"/course/{COURSE_ID}/ppt"
    assert result["baseline_goal"] == PPT_BASELINE_GOAL
    assert json.loads(
        (courses_dir / "other-course.json").read_text(encoding="utf-8"),
    ) == other_course
    stored_course = json.loads(
        (courses_dir / f"{COURSE_ID}.json").read_text(encoding="utf-8"),
    )
    assert stored_course["course_schema_version"] == "course_document_v1"
    assert stored_course["course_document_authoritative"] is True
    remaining_events = json.loads(
        (data_dir / "learning_events.json").read_text(encoding="utf-8"),
    )
    assert remaining_events == [{"event_id": "keep", "course_id": "other-course"}]

    asset_pointer = json.loads(
        (
            data_dir
            / "learning_assets"
            / COURSE_ID
            / "current.json"
        ).read_text(encoding="utf-8"),
    )
    bundle_path = (
        data_dir
        / "learning_assets"
        / COURSE_ID
        / "revisions"
        / f"{asset_pointer['bundle_revision_id']}.json"
    )
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    question = bundle["assets"]["validation_questions"][0]
    assert len(bundle["assets"]["questions"]) == 12
    assert question["node_id"] == TARGET_SECTION_ID
    assert "Bv" in question["prompt"]
    assert "A(Bv)" in question["prompt"]


def test_demo_reset_ignores_malformed_mixed_state():
    assert not _is_course_scoped_payload(
        {
            "conversations": None,
            "proposals": "not-a-list",
            "receipts": [{"course_id": "other-course"}],
        },
        COURSE_ID,
    )
