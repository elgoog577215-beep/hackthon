from copy import deepcopy
import pytest
from backend.tests.test_personal_study import setup_study, account, add_source, request_for
from study.teaching import teaching_design


def test_exam_and_project_are_distinct_teaching_sequences_without_fabricated_mastery():
    exam = teaching_design("exam_prep")
    project = teaching_design("project")
    assert [s["role"] for s in exam["sequence"]] != [s["role"] for s in project["sequence"]]
    assert "independent_check" in [s["role"] for s in exam["sequence"]]
    assert "deliverable" in [s["role"] for s in project["sequence"]]
    assert exam["mastery_write"] is False and project["mastery_write"] is False
    assert "exam_frequency" not in exam


def test_only_exact_current_formal_evidence_can_change_the_focus():
    profile = {
        "model_revision_id": "m1",
        "knowledge_profile": {
            "nodes": [
                {
                    "knowledge_id": "k",
                    "knowledge_revision_id": "kr",
                    "name": "边界条件",
                    "evidence": [
                        {"source_id": "a1", "outcome": "not_passed", "support": "independent"},
                        {"source_id": "a2", "outcome": "not_passed", "support": "independent"},
                    ],
                },
                {
                    "knowledge_id": "old",
                    "knowledge_revision_id": "old-rev",
                    "evidence": [{"outcome": "not_passed", "support": "independent"}],
                },
            ]
        },
    }
    before = deepcopy(profile)
    result = teaching_design("project", profile=profile, knowledge_refs={"k": "kr", "old": "new-rev"})
    assert result["focus"][0]["knowledge_id"] == "k"
    assert result["focus"][0]["reason"] == "repeated_independent_difficulty"
    assert len(result["focus"]) == 1 and profile == before
    assert teaching_design("project", profile=profile, knowledge_refs={"k": "changed"})["focus"] == []


@pytest.mark.asyncio
async def test_project_generation_is_owned_source_bound_and_uses_the_existing_writer(setup_study):
    client, manager, repo, writer = setup_study
    owner, headers = account(client)
    source = add_source(client, headers)
    body = request_for(source, "project")
    response = client.post("/api/study/materials", headers=headers, json=body)
    assert response.status_code == 200, response.text
    item = response.json()
    frozen = repo.get(owner, item["id"])["request"]
    assert frozen["teaching_design"]["purpose"] == "project"
    from study.service import run_personal_handout

    await run_personal_handout(manager, item["task_id"])
    calls = [call[1] for call in writer.calls if call[0] != "scope"]
    assert "可检查的产出" in calls[0]["requirements"]
    assert "teaching_design" in calls[0]["lesson_context"]
    assert repo.get(owner, item["id"])["status"] == "completed"
    assert client.get("/api/study/materials/" + item["id"], headers={"X-User-Id": owner}).status_code == 401
