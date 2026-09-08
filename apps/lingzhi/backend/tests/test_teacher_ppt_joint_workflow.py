import asyncio
import json
import time
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import teacher_lesson_authoring as routes
from teacher_lesson_authoring import TeacherLessonAuthoringRepository, TeacherLessonAuthoringError
from teacher_script import compile_teacher_script_module_contract, compile_teacher_script_section
from teacher_script_ppt import generate_bundle, CONTRACT
from template_layout_contract import TemplateLayoutPackContractV1
from backend.tests.test_teacher_lesson_authoring import single_section_course_data, standard_lesson_plan
from backend.tests.test_teacher_script_ppt import TEXT, sample


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    source = {**single_section_course_data(), "blueprint_revision_id": "outline-v1"}
    source["nodes"][1]["module_plan"] = [{"module_id": "core_explanation", "label": "执行方式", "block_role": "concept", "required": True}]
    plan = standard_lesson_plan()
    repository.save_plan_revision("course-1", "L1-1", plan, source_outline_revision_id="outline-v1")
    calls = []

    class Service:
        def register_course_generation_metadata(self, *args):
            pass

        async def generate_teacher_script_section(self, **kwargs):
            contract = compile_teacher_script_module_contract(kwargs["outline_section"], kwargs["current_plan_section"])
            if not kwargs.get("immutable_handout"):
                assert not kwargs.get("ppt_template")
                assert not kwargs.get("generation_contract_version")
                calls.append("handout")
                return compile_teacher_script_section(TEXT, contract)
            template = TemplateLayoutPackContractV1.model_validate(kwargs["ppt_template"])
            async def invoke(prompt, instructions, **options):
                calls.append(prompt)
                blocks = []
                for module in contract["modules"]:
                    page = sample()[2]
                    raw = json.dumps(page, ensure_ascii=False).replace('"block_id": "b"', json.dumps("block_id") + ": " + json.dumps(module["block_id"]))
                    blocks.append({"block_id": module["block_id"], "content": TEXT, "pages": [json.loads(raw)]})
                return json.dumps({"pages": blocks[0]["pages"]} if "修复当前 PPT" in prompt else {"blocks": blocks})
            return await generate_bundle(invoke=invoke, contract=contract, instructions="", template=template,
                seed_blocks=kwargs.get("bundle_seed_blocks"), on_checkpoint=kwargs.get("on_bundle_checkpoint"),
                immutable_handout=kwargs.get("immutable_handout", False))

    tm = SimpleNamespace(storage=SimpleNamespace(load_course=lambda _: deepcopy(source)), course_service=Service(),
        get_generation_workspace_course=lambda _: None, get_generation_preview=lambda _: None)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    app.dependency_overrides[routes.require_task_manager] = lambda: tm
    app.dependency_overrides[routes.get_teacher_lesson_authoring_repository] = lambda: repository
    monkeypatch.setattr(routes, "_course_material_evidence", lambda *args: ([], []))
    monkeypatch.setattr(routes, "_ppt_material_bundle", lambda *args: ([], []))
    with TestClient(app) as client:
        yield client, repository, calls


def generate(client, *, complete_ppt=True):
    response = client.post("/api/teacher/courses/course-1/lessons/L1-1/script/generate", json={"request_id": "joint-test"})
    assert response.status_code == 202, response.text
    job_id = response.json()["job"]["id"]
    for _ in range(300):
        job = client.get(f"/api/teacher/courses/course-1/lesson-jobs/{job_id}").json()["job"]
        if job["status"] not in {"pending", "running"}:
            break
        time.sleep(.01)
    assert job["status"] == "completed", job.get("error")
    assert job["request_snapshot"]["generation_contract_version"] == "handout_prose_v1"
    assert not job.get("bundle_blocks")
    if not complete_ppt:
        return job
    state = client.get("/api/teacher/courses/course-1/lessons/L1-1/ppt-v6/manuscript").json()["ppt_manuscript_state"]
    assert not state.get("manuscript")
    response = client.post("/api/teacher/courses/course-1/lessons/L1-1/ppt-v6/manuscript/complete",
                           json={"source_script_revision_id": state["source_script_revision_id"]})
    assert response.status_code == 202, response.text
    ppt_job_id = response.json()["job"]["id"]
    for _ in range(300):
        ppt_job = client.get(f"/api/teacher/courses/course-1/lesson-jobs/{ppt_job_id}").json()["job"]
        if ppt_job["status"] not in {"pending", "running"}:
            break
        time.sleep(.01)
    assert ppt_job["status"] == "completed", ppt_job.get("error")
    return ppt_job


def test_prose_then_explicit_ppt_saves_real_revision_and_preview_edit_use_no_model(workflow):
    client, repository, calls = workflow
    job = generate(client)
    lesson = repository.lesson("course-1", "L1-1")
    state = lesson["ppt_manuscript"]
    from teacher_lesson_authoring import teacher_lesson_v6_source
    from course_presentation_graph import block_source_text
    document = teacher_lesson_v6_source(single_section_course_data(), lesson_unit_id="L1-1",
        plan_revision=lesson["revisions"][-1], script_revision=lesson["script_revisions"][-1])[0]
    assert block_source_text(document.blocks[0]) == TEXT
    assert next(iter(job["bundle_blocks"])) == document.blocks[0].block_id
    assert state["status"] == "ready", (state.get("page_errors"), lesson["script_revisions"][-1]["sections"])
    assert state["source_script_revision_id"] == lesson["working_script_revision_id"]
    assert state["manuscript"]["source_script_revision_id"] == lesson["working_script_revision_id"]
    assert state["generation_contract_version"] == CONTRACT
    assert len(calls) == 2
    base = "/api/teacher/courses/course-1/lessons/L1-1/ppt-v6"
    page = state["manuscript"]["pages"][0]
    response = client.post(base + "/preview", json={"expected_manuscript_revision": state["revision"], "page_ids": [page["page_id"]]})
    assert response.status_code == 200, response.text
    assert response.json()["deck"]["pages"]
    updated = client.patch(base + "/manuscript", json={"expected_manuscript_revision": state["revision"], "page_updates": [{"page_id": page["page_id"], "title": "串行与并行的选择"}]})
    assert updated.status_code == 200, updated.text
    assert updated.json()["affected_page_ids"] == [page["page_id"]]
    assert updated.json()["ppt_manuscript_state"]["can_export"]
    assert repository.lesson("course-1", "L1-1")["working_script_revision_id"] == lesson["working_script_revision_id"]
    assert client.patch(base + "/manuscript", json={"expected_manuscript_revision": state["revision"], "page_updates": []}).status_code == 409
    assert client.post(base + "/preview", json={"expected_manuscript_revision": state["revision"]}).status_code == 409
    assert len(calls) == 2
    assert not repository.lesson("course-1", "L1-1").get("ppt_assets")
    assert job["bundle_blocks"]


def test_explicit_ppt_reports_source_page_validation_and_save_progress(workflow):
    client, repository, _calls = workflow
    phases = []
    original_update_job = repository.update_job

    def capture_update_job(course_id, job_id, **changes):
        if changes.get("phase"):
            phases.append(changes["phase"])
        return original_update_job(course_id, job_id, **changes)

    repository.update_job = capture_update_job
    generate(client)

    expected = [
        "ppt_source_validation",
        "ppt_page_generation",
        "ppt_page_validation",
        "ppt_manuscript_compiling",
        "ppt_manuscript_saving",
        "ppt_manuscript_complete",
    ]
    positions = [phases.index(phase) for phase in expected]
    assert positions == sorted(positions)


def test_late_bundle_checkpoint_cannot_write_after_stop_or_script_edit(workflow):
    client, repository, _ = workflow
    job = generate(client)
    block = next(iter(job["bundle_blocks"].values()))
    with pytest.raises(asyncio.CancelledError):
        repository.save_script_bundle_checkpoint("course-1", job["id"], block)


def test_sync_candidate_is_reviewed_and_concurrent_edit_is_preserved(workflow):
    client, repository, _ = workflow
    generate(client)
    state = repository.current_v6_ppt_manuscript("course-1", "L1-1")
    candidate = repository.save_ppt_sync_candidate("course-1", "L1-1", expected_revision=state["revision"],
        manuscript=state["manuscript"], source_plan_id=state["source_lesson_plan_revision_id"], source_script_id=state["source_script_revision_id"],
        material_revision=state["source_material_revision"], source_rebase=False, affected_ids=[])
    assert repository.current_v6_ppt_manuscript("course-1", "L1-1")["revision"] == state["revision"]
    repository.update_v6_ppt_manuscript_draft("course-1", "L1-1", expected_manuscript_revision=state["revision"], manuscript={**state["manuscript"], "manuscript_revision": "teacher-new"})
    with pytest.raises(TeacherLessonAuthoringError, match="其他页面修改"):
        repository.resolve_ppt_sync_candidate("course-1", "L1-1", candidate["candidate_id"], accept=True)
    assert repository.current_v6_ppt_manuscript("course-1", "L1-1")["revision"] == "teacher-new"


def test_changed_handout_starts_fresh_ppt_instead_of_reusing_failed_old_pages(workflow):
    client, repository, calls = workflow
    generate(client, complete_ppt=False)
    lesson = repository.lesson("course-1", "L1-1")
    old_script_id = lesson["working_script_revision_id"]
    from ppt_fixed_templates import compile_fixed_template
    from teacher_script_ppt import DEFAULT_THEME
    old = repository.create_job("course-1", "L1-1", job_type="teacher_lesson_ppt_manuscript_generation", request_id="old-ppt")
    repository.bind_ppt_completion("course-1", "L1-1", old["id"], old_script_id,
        lesson["working_revision_id"], compile_fixed_template(DEFAULT_THEME).model_dump(mode="json"))
    repository.update_job("course-1", old["id"], status="failed", error={"message": "old connection stopped"})
    sections = deepcopy(lesson["script_revisions"][-1]["sections"])
    sections[0]["blocks"][0]["content"] += "\n补充新的数值例子。"
    current = repository.save_script_revision("course-1", "L1-1", sections,
        source_lesson_plan_revision_id=lesson["working_revision_id"], generation_source="teacher_edit")
    response = client.post("/api/teacher/courses/course-1/lessons/L1-1/ppt-v6/manuscript/complete",
        json={"source_script_revision_id": current["working_script_revision_id"], "task_id": old["id"]})
    assert response.status_code == 202, response.text
    assert response.json()["job"]["id"] != old["id"]
    assert response.json()["job"]["source_script_revision_id"] == current["working_script_revision_id"]
    assert repository.get_job("course-1", old["id"])["source_script_revision_id"] == old_script_id
    new_job_id = response.json()["job"]["id"]
    for _ in range(300):
        job = client.get(f"/api/teacher/courses/course-1/lesson-jobs/{new_job_id}").json()["job"]
        if job["status"] not in {"pending", "running"}:
            break
        time.sleep(.01)
    assert job["status"] == "completed", job.get("error")
    state = repository.current_v6_ppt_manuscript("course-1", "L1-1")
    assert state["source_script_revision_id"] == current["working_script_revision_id"]
