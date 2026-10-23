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
    profile["knowledge_profile"]["nodes"][0]["evidence"].append({"source_id":"a3","support":"independent","outcome":"passed"})
    assert teaching_design("project",profile=profile,knowledge_refs={"k":"kr"})["focus"]==[]


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

def test_course_source_freezes_own_goal_memory_and_exact_evidence(setup_access,monkeypatch):
    from pathlib import Path
    from backend.tests.test_course_learning_access import bearer
    from course_learning_access import CourseLearningAccess
    from ai_teacher_state import AITeacherRepository
    from companion_learning import CompanionService
    from study.repository import StudyRepository
    from study.service import freeze_request
    import learner_model_service
    client,store,course,student,other=setup_access
    uid=student['user']['id']
    course['course_knowledge_base']={'lifecycle_status':'active','knowledge_points':[{'knowledge_id':'k','revision_id':'kr','status':'active','section_refs':['lecture'],'name':'条件'}]}
    store.save_course_sync('course',course)
    CourseLearningAccess(store).grant(course,uid)
    service=CompanionService(AITeacherRepository(Path(store._data_dir)/'ai_teacher'))
    state=service.command(uid,'course',action='save_goal',expected_revision=1,request_id='goal_request_12345',value={'text':'做一个小项目','purpose':'project'},catalog=[],source_revision=course['current_course_version_id'])
    service.command(uid,'course',action='remember',expected_revision=state['revision'],request_id='memory_request_12345',value={'text':'先给一个提示','kind':'agreement'},catalog=[],source_revision=course['current_course_version_id'])
    monkeypatch.setattr(learner_model_service,'build_current_learner_model',lambda *a,**k:{'model_revision_id':'m','knowledge_profile':{'nodes':[{'knowledge_id':'k','knowledge_revision_id':'kr','name':'条件','evidence':[{'source_id':'a1','outcome':'not_passed','support':'independent'},{'source_id':'a2','outcome':'not_passed','support':'independent'}]}]}})
    response=client.post('/api/study/courses/course/sources',headers=bearer(student),json={'revision_id':course['current_course_version_id']})
    assert response.status_code==200,response.text
    source=response.json()
    from course_repository import CourseDocumentRepository
    monkeypatch.setattr(CourseDocumentRepository,'load_course_view',lambda self,cid:deepcopy(course))
    frozen=freeze_request(StudyRepository(store),uid,request_for(source,'project'))
    assert frozen['source_sections'][0]['source_node_id']=='lecture'
    assert frozen['course_contexts']['course']['goal']['text']=='做一个小项目'
    assert frozen['course_contexts']['course']['memories'][0]['text']=='先给一个提示'
    assert frozen['source_sections'][0]['teaching_design']['focus'][0]['knowledge_id']=='k'
    assert frozen['course_contexts']['course']['model_revision_id']=='m'
    assert service.read(other['user']['id'],'course')['goal'] is None
    CourseLearningAccess(store).revoke(course,uid)
    with pytest.raises(ValueError,match='授权'):
        freeze_request(StudyRepository(store),uid,request_for(source,'project'))

from backend.tests.test_course_learning_access import setup_access
