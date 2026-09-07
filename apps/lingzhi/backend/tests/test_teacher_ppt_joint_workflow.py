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
from teacher_script import compile_teacher_script_module_contract
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


def generate(client):
    response = client.post("/api/teacher/courses/course-1/lessons/L1-1/script/generate", json={"request_id": "joint-test"})
    assert response.status_code == 202, response.text
    job_id = response.json()["job"]["id"]
    for _ in range(300):
        job = client.get(f"/api/teacher/courses/course-1/lesson-jobs/{job_id}").json()["job"]
        if job["status"] not in {"pending", "running"}:
            break
        time.sleep(.01)
    assert job["status"] == "completed", job.get("error")
    return job


def test_joint_route_saves_real_revision_and_preview_edit_use_no_model(workflow):
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
    assert len(calls) == 1
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
    assert len(calls) == 1
    assert not repository.lesson("course-1", "L1-1").get("ppt_assets")
    assert job["bundle_blocks"]


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
