"""Knowledge-first and legacy handouts share identity, historical sources and coverage."""
from copy import deepcopy
import pytest

from course_teaching_plan_projection import project_course_teaching_plan


def course_fixture():
    tree = {"revision_id": "tree-old", "status": "accepted", "terminology_revision": "terms-old",
        "knowledge_points": [
            {"knowledge_id": "k1", "revision_id": "p1", "name": "同名概念", "statement": "旧规则", "section_refs": ["s1"]},
            {"knowledge_id": "k2", "revision_id": "p2", "name": "同名概念", "statement": "另一规则", "section_refs": ["s1"]},
            {"knowledge_id": "k3", "revision_id": "p3", "name": "尚未讲解", "section_refs": ["s1"]},
            {"knowledge_id": "private", "revision_id": "px", "name": "另一讲", "section_refs": ["s2"]}],
        "relations": [{"source_knowledge_id": "k1", "target_knowledge_id": "k2", "relation_type": "contrasts_with", "reason": "旧区别"}]}
    blocks = [
        {"block_id": "b1", "section_id": "s1", "position": 0, "role": "concept", "kind": "text", "concept_refs": ["k1"],
         "payload": {"markdown": "旧规则的讲解", "content_type": "explanation", "knowledge_refs": [{"knowledge_id": "k1", "revision_id": "p1"}], "source_knowledge_revision": "tree-old"}},
        {"block_id": "b2", "section_id": "s1", "position": 1, "role": "example", "kind": "text", "concept_refs": ["k2"],
         "payload": {"markdown": "例题", "content_type": "example", "knowledge_refs": [{"knowledge_id": "k2", "revision_id": "p2"}], "source_knowledge_revision": "tree-old"}}]
    return {"course_id": "c", "course_name": "课程", "course_knowledge_base": deepcopy(tree),
        "knowledge_first_history": {"tree-old": tree},
        "course_document": {"course_id": "c", "title": "课程", "sections": [{"section_id": "s1", "title": "第一讲", "position": 0}], "blocks": blocks},
        "teacher_handouts": {"s1": {"revision_id": "h1", "source_knowledge_revision": "tree-old"}}}


def test_no_lesson_plan_projects_stable_ids_and_reference_coverage_without_writes():
    raw = course_fixture()
    before = deepcopy(raw)
    sections = project_course_teaching_plan(raw)["sections"]
    assert len(sections) == 1
    section = sections[0]
    points = [p for g in section["knowledge_structure"] for p in g["knowledge_points"]]
    assert [p["knowledge_id"] for p in points] == ["k1", "k2", "k3"]
    assert section["source_knowledge_revision"] == "tree-old"
    assert section["knowledge_source_status"] == "current"
    rows = {r["knowledge_id"]: r for r in section["knowledge_coverage"]["rows"]}
    assert rows["k1"]["explanation_block_ids"] == ["b1"]
    assert rows["k2"]["example_block_ids"] == ["b2"]
    assert rows["k3"]["block_ids"] == []
    assert section["knowledge_coverage"]["semantics_verified"] is False
    assert raw == before


def test_old_handout_uses_old_points_and_edges_after_current_tree_changes():
    raw = course_fixture()
    raw["course_knowledge_base"]["revision_id"] = "tree-new"
    raw["course_knowledge_base"]["knowledge_points"][0]["statement"] = "新规则"
    raw["course_knowledge_base"]["relations"][0]["reason"] = "新区别"
    section = project_course_teaching_plan(raw)["sections"][0]
    assert section["knowledge_source_status"] == "historical"
    assert section["knowledge_structure"][0]["knowledge_points"][0]["statement"] == "旧规则"
    assert section["knowledge_relations"][0]["reason"] == "旧区别"


def test_missing_historical_tree_does_not_substitute_current_graph():
    raw = course_fixture()
    raw["course_knowledge_base"]["revision_id"] = "tree-new"
    raw["knowledge_first_history"] = {}
    section = project_course_teaching_plan(raw)["sections"][0]
    assert section["knowledge_source_status"] == "unavailable"
    assert section["knowledge_structure"] == []
    assert section["knowledge_relations"] == []
    assert section["knowledge_coverage"]["status"] == "unavailable"
    assert section["knowledge_coverage"]["invalid_refs"] == []  # Missing history is not evidence of a bad reference.


def test_mismatched_point_revision_is_not_counted_as_covered():
    raw = course_fixture()
    raw["course_document"]["blocks"][0]["payload"]["knowledge_refs"][0]["revision_id"] = "wrong"
    section = project_course_teaching_plan(raw)["sections"][0]
    coverage = section["knowledge_coverage"]
    assert coverage["rows"][0]["block_ids"] == []
    assert coverage["invalid_refs"] == [{"block_id": "b1", "knowledge_id": "k1", "reason": "revision_mismatch"}]


def test_unversioned_legacy_plan_remains_readable():
    raw = {"course_teaching_plan": {"sections": [{"node_id": "s", "knowledge_structure": [
        {"knowledge_points": [{"name": "旧概念"}]}]}]}}
    result = project_course_teaching_plan(raw)
    assert result["sections"][0]["knowledge_structure"][0]["knowledge_points"][0]["name"] == "旧概念"


def test_normalization_preserves_source_versions_and_ids_for_saved_blocks():
    from teacher_script import normalize_teacher_script_section
    raw = course_fixture()["course_document"]["blocks"][0]
    block = {"block_id": "b1", "role": "concept", "content": "正文", "title": "讲解",
             **{k: v for k, v in raw["payload"].items() if k != "markdown"},
             "source_context_revision": "ctx", "source_evidence_package_revision": "ev", "source_scope_revision": "scope"}
    saved = normalize_teacher_script_section({"section_node_id": "s1", "title": "第一讲", "blocks": [block]})["blocks"][0]
    assert saved["knowledge_refs"] == block["knowledge_refs"]
    assert saved["source_knowledge_revision"] == "tree-old"
    assert saved["source_evidence_package_revision"] == "ev"


@pytest.mark.parametrize("key,value", [
    ("knowledge_refs", [{"knowledge_id": "k1", "revision_id": "p2"}]),
    ("source_knowledge_revision", "tree-new"), ("source_terminology_revision", "terms-new"),
    ("content_type", "example"), ("answer_to", "another-exercise"),
])
def test_reference_or_reading_semantics_change_creates_a_new_handout_revision(key, value):
    from teacher_lesson_authoring import teacher_lesson_script_sections_revision
    section = {"section_node_id": "s1", "title": "讲义", "blocks": [
        {"block_id": "b1", "content": "不变的正文", "role": "concept", "knowledge_refs": [{"knowledge_id": "k1", "revision_id": "p1"}],
         "source_knowledge_revision": "tree-old", "source_terminology_revision": "terms-old", "content_type": "definition"}]}
    before = teacher_lesson_script_sections_revision([section])
    section["blocks"][0][key] = value
    assert teacher_lesson_script_sections_revision([section]) != before


def test_mixed_tree_revisions_show_conflict_and_never_count_references():
    raw = course_fixture()
    raw["course_document"]["blocks"][1]["payload"]["source_knowledge_revision"] = "other"
    section = project_course_teaching_plan(raw)["sections"][0]
    assert section["knowledge_source_status"] == "conflict"
    assert section["knowledge_coverage"]["rows"] == []


def test_trial_coverage_excludes_hidden_blocks_even_in_visible_section():
    from routers.teacher_preview import public_document, public_handout_plan
    raw = course_fixture()
    raw["course_document"]["blocks"][1]["visibility_rule"] = {"audience": "teacher"}
    # Use the actual canonical model's defaults for kind/status, as on reload.
    for b in raw["course_document"]["blocks"]:
        b["kind"] = "rich_text"
    public = public_document(raw)
    plan = public_handout_plan(raw, public)
    rows = {r["knowledge_id"]: r for r in plan["sections"][0]["knowledge_coverage"]["rows"]}
    assert rows["k1"]["block_ids"] == ["b1"]
    assert rows["k2"]["block_ids"] == []
    assert "b2" not in str(plan)


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["teacher", "student"])
async def test_knowledge_first_owner_reload_and_historical_reading(tmp_path, monkeypatch, surface):
    from backend.tests.test_knowledge_first import adopted, generate
    from course_document import CourseDocument, refresh_document_revision
    from course_repository import CourseDocumentRepository
    from knowledge_first import KnowledgeFirstService
    from storage import Storage
    from teacher_lesson_authoring import TeacherLessonAuthoringRepository
    from backend.tests.test_handout_workflow_projection import snapshot
    storage = Storage(str(tmp_path / "data"))
    doc = refresh_document_revision(CourseDocument(course_id="c-pilot", title="C17"))
    storage.save_course_sync("c-pilot", {"course_id": "c-pilot", "course_name": "C17", "owner_id": "owner", "authoring_surface": surface,
        "course_schema_version": "course_document_v1", "course_document": doc.model_dump(mode="json"), "course_document_revision": doc.document_revision})
    repo = CourseDocumentRepository(storage)
    authoring = TeacherLessonAuthoringRepository(tmp_path / "authoring", canonical_storage=storage)
    service = KnowledgeFirstService(repo, authoring)
    await adopted(service)
    await generate(service, "types")
    old_revision = service.view("c-pilot")["knowledge_revision"]
    # Real disk reload, then change the adopted tree while retaining its history.
    fresh = TeacherLessonAuthoringRepository(authoring.root, canonical_storage=storage)
    monkeypatch.setattr("teacher_content_projection.authoring_repository", lambda _: fresh)
    def update(raw):
        raw["course_knowledge_base"]["revision_id"] = "new-baseline"
        raw["course_knowledge_base"]["knowledge_points"][0]["name"] = "新名称"
        return raw
    storage.update_course_data("c-pilot", update)
    before = snapshot(tmp_path)
    envelope = repo.document_envelope("c-pilot")
    section = next(s for s in envelope["teaching_plan"]["sections"] if s["node_id"] == "types")
    assert section["source_knowledge_revision"] == old_revision
    assert section["knowledge_source_status"] == "historical"
    assert len(section["knowledge_coverage"]["rows"]) == 16
    assert all(row["explanation_block_ids"] for row in section["knowledge_coverage"]["rows"])
    assert section["knowledge_coverage"]["invalid_refs"] == []
    assert all(b["payload"]["content_type"] for b in envelope["document"]["blocks"])
    assert snapshot(tmp_path) == before
