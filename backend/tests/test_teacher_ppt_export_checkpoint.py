import asyncio
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from routers import teacher_lesson_authoring as routes
from .test_ppt_teaching_content import compiled_manuscript


@pytest.mark.parametrize("resume_id", ["", "interrupted-export"])
def test_new_confirmed_export_does_not_resume_its_planning_checkpoint(tmp_path, monkeypatch, resume_id):
    doc, _, template, manuscript = compiled_manuscript()
    state = {"task_id": "content-planning", "manuscript": manuscript.model_dump(mode="json")}
    repo = SimpleNamespace(
        root=tmp_path,
        current_imported_ppt_review=lambda *_: None,
        current_v6_ppt_manuscript=lambda *_: state,
        create_job=lambda *_, **__: {"id": "new-export"},
        update_job=lambda *_, **__: {"id": "new-export"},
    )
    monkeypatch.setattr(routes, "_teacher_v6_source", lambda *_: (doc, {}, "synthetic", {}, {}))
    monkeypatch.setattr(routes, "_ppt_material_bundle", lambda *_: ([], []))
    monkeypatch.setattr(routes, "_ppt_manuscript_state_payload", lambda *_, **__: {**state, "can_generate_ppt": True})
    monkeypatch.setattr(routes, "_resolve_locked_teacher_v6_template", lambda *_: template)
    monkeypatch.setattr(routes, "_teacher_ppt_resume_job_id", lambda *_, **__: resume_id)
    monkeypatch.setattr(routes, "_capture_generation_source_snapshot", lambda **_: None)
    monkeypatch.setattr(routes, "build_ai_base_story_planner_v6", lambda: None)
    monkeypatch.setattr(routes, "build_ai_base_visual_planner_v2", lambda: None)
    clones = []
    monkeypatch.setattr(routes.SlideDeckV6CandidateRepository, "clone_checkpoint", lambda self, source, target: clones.append((source, target)))
    result = asyncio.run(routes.build_teacher_lesson_v6(
        "course", "lesson", routes.TeacherLessonV6BuildRequest(resume_task_id=resume_id),
        Request({"type": "http", "headers": []}), tm=None, repository=repo))
    assert result.status_code == 200
    assert clones == ([(resume_id, "new-export")] if resume_id else [])
