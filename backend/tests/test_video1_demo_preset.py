from __future__ import annotations
import json
from pathlib import Path
from course_document import CourseDocument
from teaching_representations import TeachingRepresentationRepository
from video1_demo_preset import BASELINE_GOAL, COURSE_ID, TARGET_GOAL, TARGET_SECTION_ID, build_video1_course_envelope, prepare_video1_demo

def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

def test_video1_course_uses_the_shared_video2_identity_and_fixed_goal_pair():
    envelope = build_video1_course_envelope()
    document = CourseDocument.model_validate(envelope["course_document"])
    target = next(section for section in document.sections if section.section_id == TARGET_SECTION_ID)
    assert COURSE_ID == "demo-matrix-growth-v2"
    assert envelope["course_id"] == document.course_id == COURSE_ID
    assert target.learning_objective == BASELINE_GOAL
    assert target.attributes["demo_target_goal"] == TARGET_GOAL
    assert envelope["demo_metadata"]["external_model_required"] is False

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
    assert result["compiled_representation_count"] == 6
    assert result["relative_url"] == f"/course/{COURSE_ID}/ppt"
    assert not (data_dir / "change_proposals" / "cps_demo.json").exists()
    assert not (data_dir / "course_versions" / COURSE_ID).exists()
    assert json.loads((data_dir / "courses" / "real-course.json").read_text(encoding="utf-8")) == other
    assert (data_dir / "teaching_representations" / "real.json").exists()
    assert (data_dir / "change_proposals" / "cps_real.json").exists()
    registry = TeachingRepresentationRepository(data_dir / "teaching_representations").load(COURSE_ID)
    reps = {item.representation_type: item for item in registry.representations}
    assert set(reps) == {"outline", "lesson_plan", "handout", "practice_sheet", "slide_deck", "diagram"}
    assert reps["slide_deck"].status == "ready"
    spec = next(item for item in registry.specs if item.spec_id == reps["slide_deck"].spec_id)
    target = next(slide for slide in spec.payload["content"]["slides"] if slide.get("section_id") == TARGET_SECTION_ID)
    assert target["key_message"] == BASELINE_GOAL

def test_prepare_video1_demo_is_repeatable_after_demo_mutation(tmp_path: Path):
    data_dir = tmp_path / "data"
    first = prepare_video1_demo(data_dir)
    path = data_dir / "courses" / f"{COURSE_ID}.json"
    mutated = json.loads(path.read_text(encoding="utf-8"))
    mutated["course_operation_log"] = [{"command_id": "take-1"}]
    _write_json(path, mutated)
    _write_json(data_dir / "change_proposals" / "cps_take_1.json", {"course_id": COURSE_ID})
    second = prepare_video1_demo(data_dir)
    restored = json.loads(path.read_text(encoding="utf-8"))
    assert first["course_revision"] == second["course_revision"]
    assert restored["course_operation_log"] == []
    assert not (data_dir / "change_proposals" / "cps_take_1.json").exists()
