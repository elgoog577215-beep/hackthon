import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from course_document import stable_hash
from ppt_teaching_content import PagePresentationV1
from ppt_teaching_manuscript import refresh_manuscript, resolve_manuscript_page
from routers import teacher_lesson_authoring as routes
from teacher_lesson_authoring import TeacherLessonAuthoringRepository, TeacherLessonAuthoringError, validate_teacher_lesson_plan
from .test_teacher_lesson_authoring import standard_lesson_plan
from .test_ppt_teaching_content import compiled_manuscript
from .test_ppt_pacing import progressive_comparison


def test_budget_edit_is_reviewable_confirm_gate_and_last_good_are_preserved(tmp_path, monkeypatch):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    plan = standard_lesson_plan()
    lesson = repo.save_plan_revision("course", "L1-1", plan, source_outline_revision_id="outline", quality_report=validate_teacher_lesson_plan(plan))
    plan_revision = lesson["working_revision_id"]
    lesson = repo.save_script_revision("course", "L1-1", [{"section_node_id": "L2-1-1", "title": "比较", "content": "执行方式"}], source_lesson_plan_revision_id=plan_revision)
    value, _ = progressive_comparison()
    doc, _, template, manuscript = compiled_manuscript(value)
    manuscript.pages[0].teaching.presentation = PagePresentationV1(mode="key_steps", checkpoints=[{"state_id": s.state_id, "reason": "观察执行差异"} for s in manuscript.pages[0].teaching.states])
    resolve_manuscript_page(manuscript.pages[0], template, doc.document_revision)
    manuscript = refresh_manuscript(manuscript)
    saved = repo.save_v6_ppt_manuscript("course", "L1-1", source_lesson_plan_revision_id=plan_revision,
        source_script_revision_id=lesson["working_script_revision_id"], source_material_revision=stable_hash([], prefix="pptrefs_"), task_id="task",
        mode="teaching", theme=template.theme_id, template_id=template.template_id, template_version=template.template_version,
        template_digest=template.template_digest, manuscript=manuscript.model_dump(mode="json"))
    repo.confirm_v6_ppt_manuscript_draft("course", "L1-1", manuscript_revision=saved["revision"])
    monkeypatch.setattr(routes, "_teacher_v6_source", lambda *_: (doc, {}, "synthetic", lesson, plan))
    monkeypatch.setattr(routes, "_ppt_material_bundle", lambda *_: ([], []))
    monkeypatch.setattr(routes, "_resolve_locked_teacher_v6_template", lambda *_: template)
    monkeypatch.setattr("ppt_teaching_manuscript.template_for_manuscript", lambda _: template)
    request = Request({"type": "http", "headers": []})

    def save(revision, updates=None, pacing=None):
        return asyncio.run(routes.update_teacher_lesson_v6_manuscript_draft("course", "L1-1",
            routes.UpdateTeacherLessonPptManuscriptRequest(expected_manuscript_revision=revision, page_updates=updates or [], pacing=pacing),
            request, tm=None, repository=repo))["ppt_manuscript_state"]

    blocked = save(saved["revision"], pacing={"max_physical_pages": 2, "rationale": "留出独立练习时间"})
    assert blocked["status"] == "draft" and not blocked["confirmable"]
    assert blocked["manuscript"]["quality_issues"][0]["code"] == "ppt_pacing_budget_exceeded"
    current = repo.current_v6_ppt_manuscript("course", "L1-1")
    assert current["last_confirmed_manuscript"]["manuscript_revision"] == saved["revision"]
    with pytest.raises(TeacherLessonAuthoringError, match="请先处理"):
        repo.confirm_v6_ppt_manuscript_draft("course", "L1-1", manuscript_revision=blocked["revision"])
    with pytest.raises(HTTPException) as conflict:
        save(saved["revision"], pacing={"max_physical_pages": 4, "rationale": "有更多停顿"})
    assert conflict.value.status_code == 409
    content = blocked["manuscript"]["pages"][0]["teaching"]
    content["presentation"] = {"mode": "complete"}
    fixed = save(blocked["revision"], [{"page_id": "p1", "teaching": content}])
    assert fixed["confirmable"] and fixed["manuscript"]["page_count"] == 1
    content.pop("presentation")
    with pytest.raises(HTTPException) as downgrade:
        save(fixed["revision"], [{"page_id": "p1", "teaching": content}])
    assert downgrade.value.status_code == 422
    assert downgrade.value.detail["code"] == "presentation_policy_required"
