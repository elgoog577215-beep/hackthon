"""Generation -> owner save -> fresh read -> both teacher reading projections."""
from copy import deepcopy
import hashlib
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.tests.test_flexible_handout_blocks import marker
from backend.tests.test_teacher_handout_lecture import fixture, new_job
from backend.tests.test_teacher_lesson_authoring import course_data
from course_document import CourseBlock, CourseDocument, CourseSection, document_from_legacy_course
from course_repository import CourseDocumentRepository
from course_teaching_plan_projection import project_course_teaching_plan
from dependencies import get_teacher_lesson_authoring_repository, require_task_manager
from routers import teacher_preview, tasks
from storage import Storage
from teacher_content_projection import project_teacher_content
from teacher_lesson_authoring import TeacherLessonAuthoringRepository, project_current_teacher_scripts


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


@pytest.mark.asyncio
async def test_generated_handout_survives_owner_reload_and_both_preview_apis(tmp_path, monkeypatch):
    repo, service, kwargs = fixture(tmp_path / "authoring")
    plan = {"schema_version": "course_teaching_plan_v3", "sections": list(deepcopy(kwargs["plan_sections"]).values())}
    relation = {
        "source_name": "核心概念", "target_name": "应用方法", "relation_type": "applies_to",
        "reason": "先检查概念条件，再选用相应方法。", "conditions": ["概念条件满足"],
        "source_refs": [{"filename": "实验资料.md", "locator": "第 2 节"}],
    }
    plan["sections"][0]["knowledge_relations"] = [relation]
    plan["sections"][1]["knowledge_structure"] = [{"knowledge_points": [{"name": "应用方法"}]}]
    plan["sections"][1]["key_points"] = ["应用方法"]
    plan["sections"][1]["teaching_modules"][0]["knowledge_names"] = ["应用方法"]
    saved_plan = repo.save_plan_revision("course-1", "L1-1", plan, source_outline_revision_id="outline-v1")
    kwargs.update(source_plan_revision_id=saved_plan["working_revision_id"],
                  plan_sections={s["node_id"]: s for s in plan["sections"]})
    calls = []

    async def generate(**request):
        calls.append(request)
        chunks = []
        for index, section in enumerate(request["outline_sections"]):
            name = "核心概念" if index == 0 else "应用方法"
            chunks.append("\n".join([
                f'<!-- section:{section["node_id"]} -->',
                marker("定义", name, name + "的条件与适用范围。", key="d", knowledge=[name]),
                marker("练习", "检查条件", "是否满足适用条件？", key="q"),
                marker("解答", "依据定义核对", "先核对条件，然后选择方法。", key="a", answer_to="q"),
            ]))
        text = "\n".join(chunks)
        await request["on_content_delta"](text)
        return {"text": text}

    result = await service.run_script_job(**kwargs, job_id=new_job(repo), generator=generate)
    assert result["status"] == "completed", result.get("error")
    assert len(calls) == 1
    # A fresh repository reads the completed owner's revision, not a live draft.
    fresh = TeacherLessonAuthoringRepository(tmp_path / "authoring")
    storage = Storage(str(tmp_path / "data"))
    raw = course_data()
    raw["nodes"] = [n for n in raw["nodes"] if n["node_id"] in {"L1-1", *kwargs["plan_sections"]}]
    raw.update(authoring_surface="teacher", owner_id="t", teacher_production_schema="unified_teacher_v1",
               teacher_outline_committed=True, course_document=document_from_legacy_course(raw).model_dump(mode="json"))
    storage.save_course_sync("course-1", raw)
    monkeypatch.setattr("teacher_content_projection.authoring_repository", lambda storage: fresh)
    monkeypatch.setattr(teacher_preview, "storage", storage)
    monkeypatch.setattr(teacher_preview, "formal_questions", lambda raw: [])

    legacy = project_current_teacher_scripts({"course_id": "course-1", "nodes": raw["nodes"]}, fresh.view("course-1"))
    envelope = CourseDocumentRepository(storage).document_envelope("course-1")
    app = FastAPI()
    app.include_router(teacher_preview.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")
    app.dependency_overrides[require_task_manager] = lambda: SimpleNamespace(storage=storage)
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: fresh
    client = TestClient(app)
    before = snapshot(tmp_path)
    # Ordinary reads must use the owner's bounded read projection, without
    # copying all historical PPT/model snapshots through load().
    with monkeypatch.context() as reads:
        reads.setattr(fresh, "load", lambda *_: pytest.fail("Full authoring history loaded for a body read"))
        bounded_view = project_teacher_content(storage.load_course("course-1"), storage=storage)
        assert bounded_view["course_document"]["blocks"] == envelope["document"]["blocks"]
    public = client.get("/api/teacher/courses/course-1/preview", headers={"X-User-Id": "t"})
    canonical = client.get("/api/teacher/courses/course-1/generation-preview", headers={"X-User-Id": "t"})
    assert public.status_code == canonical.status_code == 200
    assert client.get("/api/teacher/courses/course-1/preview", headers={"X-User-Id": "other"}).status_code == 404
    assert snapshot(tmp_path) == before
    for view in (envelope, public.json(), canonical.json()):
        blocks = view["document"]["blocks"]
        assert blocks[0]["payload"]["content_type"] == "definition"
        assert blocks[0]["concept_refs"] == ["核心概念"]
        assert blocks[2]["payload"]["answer_to"] == blocks[1]["block_id"]
        assert view["teaching_plan"]["sections"][0]["knowledge_relations"][0] == envelope["teaching_plan"]["sections"][0]["knowledge_relations"][0]
    block = legacy["nodes"][1]["content_blocks"][0]
    assert block["metadata"]["content_type"] == "definition"
    assert block["metadata"]["concept_refs"] == ["核心概念"]
    assert legacy["teaching_plan"]["sections"][0]["knowledge_relations"][0]["source_refs"] == relation["source_refs"]
    assert "course_teaching_plan" not in legacy
    assert "teaching_notes" not in public.json()["teaching_plan"]["sections"][0]

    # A newer plan cannot make old body text appear current or acquire new edges.
    plan["sections"][0]["knowledge_relations"][0]["reason"] = "新教案的理由。"
    fresh.save_plan_revision("course-1", "L1-1", plan, source_outline_revision_id="outline-v1")
    assert project_teacher_content(storage.load_course("course-1"), storage=storage)["course_document"]["blocks"] == []
    assert project_current_teacher_scripts({"course_id": "course-1", "nodes": raw["nodes"]}, fresh.view("course-1"))["teacher_lesson_projection"]["covered_section_count"] == 0


def test_existing_course_graph_is_resolved_and_scoped_without_inventing_edges():
    points = [{"name": name, "knowledge_id": key} for name, key in [("定义", "k1"), ("方法", "k2"), ("无关概念", "k3")]]
    relation = {"source_knowledge_id": "k1", "target_knowledge_id": "k2", "relation_type": "derives",
                "reason": "由定义推出方法。", "derivation_steps": ["展开定义", "整理条件"],
                "source_refs": [{"filename": "教材.pdf", "locator": "第 4 页"}],
                "relation_group_id": "g", "group_operator": "AND"}
    raw = {"course_teaching_plan": {"sections": [
        {"node_id": key, "knowledge_structure": [{"knowledge_points": [point]}], "knowledge_relations": []}
        for key, point in zip(["s1", "s2", "s3"], points)
    ]}, "course_knowledge_base": {"knowledge_points": points, "relations": [relation]}}
    before = deepcopy(raw)
    plan = project_course_teaching_plan(raw)
    assert [len(s["knowledge_relations"]) for s in plan["sections"]] == [1, 1, 0]
    edge = plan["sections"][0]["knowledge_relations"][0]
    assert (edge["source_name"], edge["target_name"]) == ("定义", "方法")
    assert edge["source_refs"] == relation["source_refs"]
    assert edge["group_operator"] == "AND"
    assert raw == before


def test_trial_projection_does_not_disclose_hidden_answer_targets_or_teacher_plan_fields():
    document = CourseDocument(course_id="c", title="课程", sections=[CourseSection(section_id="s", title="概念", position=0)], blocks=[
        CourseBlock(block_id="a", section_id="s", position=0, payload={
            "markdown": "公开说明", "content_type": "answer", "answer_to": "hidden", "private_note": "secret",
        }),
        CourseBlock(block_id="hidden", section_id="s", position=1, payload={"markdown": "secret"}, visibility_rule={"audience": "teacher"}),
    ])
    raw = {"course_document": document.model_dump(mode="json"), "course_teaching_plan": {"sections": [
        {"node_id": "s", "teaching_notes": ["secret"], "knowledge_structure": [{"knowledge_points": [{"name": "概念"}]}]},
        {"node_id": "hidden-section", "knowledge_structure": [{"knowledge_points": [{"name": "隐藏概念"}]}]},
    ]}}
    public = teacher_preview.public_document(raw)
    assert len(public["blocks"]) == 1
    assert public["blocks"][0]["payload"] == {"markdown": "公开说明", "content_type": "answer"}
    plan = teacher_preview.public_handout_plan(raw, public)
    assert [s["node_id"] for s in plan["sections"]] == ["s"]
    assert "teaching_notes" not in plan["sections"][0]
