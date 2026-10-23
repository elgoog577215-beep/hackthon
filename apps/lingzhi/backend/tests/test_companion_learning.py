from copy import deepcopy
import pytest
from ai_teacher_state import AITeacherRepository, InteractionConflict
from companion_learning import CompanionService, teaching_decision, select_independent_question, help_followups, material_course_context


@pytest.fixture
def service(tmp_path):
    return CompanionService(AITeacherRepository(tmp_path / "interactions"))


CATALOG = [{"id": "n1", "title": "链式法则"}, {"id": "n2", "title": "隐函数求导"}]


def command(service, action, revision=1, user="u", **value):
    return service.command(
        user,
        "c",
        action=action,
        expected_revision=revision,
        request_id=f"request-{revision}-{action}",
        value=value,
        catalog=CATALOG,
        source_revision="cv1",
    )


def test_read_never_creates_files_and_users_are_isolated(service):
    assert service.read("u", "c")["revision"] == 1
    assert not list(service.repository.root.glob("*.json"))
    command(service, "save_goal", purpose="exam", text="两周后考微积分", minutes_per_week=90)
    assert service.read("other", "c")["goal"] is None
    assert service.read("u", "another")["goal"] is None
    reopened = CompanionService(AITeacherRepository(service.repository.root))
    assert reopened.read("u", "c")["goal"]["text"] == "两周后考微积分"

def test_derived_material_inherits_the_same_course_mainline_without_copying_or_overwriting_it(service):
    command(service,'save_goal',text='课程总体目标',purpose='exam')
    material={'request':{'source_sections':[{'course_origin':{'course_id':'c'}}]}}
    inherited=material_course_context(material,'u',service.repository)
    assert inherited['goal']['text']=='课程总体目标'
    assert material_course_context(material,'v',service.repository)['goal'] is None
    command(service,'save_goal',revision=2,text='新的课程目标',purpose='exam')
    assert material_course_context(material,'u',service.repository)['goal']['text']=='新的课程目标'
    assert material_course_context({'request':{'source_sections':[{'course_origin':{'course_id':'c'}},{'course_origin':{'course_id':'other'}}]}},'u',service.repository) is None


def test_goal_idempotency_conflict_and_history(service):
    result = command(service, "save_goal", text="理解课程", purpose="systematic")
    assert command(service, "save_goal", text="理解课程", purpose="systematic") == result
    with pytest.raises(InteractionConflict):
        command(service, "save_goal", text="不同目标", purpose="systematic")
    result = command(service, "save_goal", revision=2, text="准备考试", purpose="exam")
    assert result["goal_history"][0]["text"] == "理解课程"
    assert result["goal"]["revision"] == 2


def test_plan_requires_explicit_adoption_and_preserves_prior_decisions(service):
    command(service, "save_goal", text="理解课程", purpose="systematic")
    proposed = command(service, "propose_plan", revision=2)
    assert proposed["plan"] is None
    assert [s["node_id"] for s in proposed["proposal"]["steps"]] == ["n1", "n2"]
    adopted = command(service, "adopt_plan", revision=3)
    step = adopted["plan"]["steps"][0]["step_id"]
    deferred = command(service, "defer_step", revision=4, step_id=step)
    assert deferred["plan"]["steps"][0]["decision"] == "deferred"
    changed = command(service, "save_goal", revision=5, text="临近考试", purpose="exam")
    assert changed["plan"]["steps"][0]["decision"] == "deferred"
    assert changed["plan"]["status"] == "needs_review"


def test_plan_cannot_adopt_after_source_changed(service):
    command(service, "save_goal", text="理解课程", purpose="systematic")
    command(service, "propose_plan", revision=2)
    with pytest.raises(InteractionConflict):
        service.command(
            "u",
            "c",
            action="adopt_plan",
            expected_revision=3,
            request_id="new-request",
            value={},
            catalog=CATALOG,
            source_revision="cv2",
        )


def test_memory_correction_keeps_history_and_disabled_memory_is_not_prompted(service):
    state = command(service, "remember", text="更喜欢图解", kind="preference")
    mid = state["memories"][0]["memory_id"]
    state = command(service, "correct_memory", revision=2, memory_id=mid, text="更喜欢先看例子")
    assert state["memories"][0]["history"][0]["text"] == "更喜欢图解"
    command(service, "disable_memory", revision=3, memory_id=mid)
    assert "更喜欢先看例子" not in service.prompt("u", "c")


def test_preferences_are_global_per_verified_user_and_survive_reopen(service):
    assert service.preferences("u")["mode"] == "gentle"
    service.set_preferences("u", "on_request", 1, "preference-request")
    reopened = CompanionService(AITeacherRepository(service.repository.root))
    assert reopened.preferences("u")["mode"] == "on_request"
    assert reopened.preferences("v")["mode"] == "gentle"
    assert reopened.read("u", "c")["goal"] is None
    with pytest.raises(InteractionConflict):
        reopened.set_preferences("u", "gentle", 1, "different-request")


@pytest.mark.parametrize(
    "action,value",
    [
        ("remember", {"kind": "mastery", "text": "已经学会"}),
        ("save_goal", {"text": "x", "minutes_per_week": -1}),
        ("defer_step", {"step_id": "not-real"}),
    ],
)
def test_invalid_commands_do_not_mutate_state(service, action, value):
    with pytest.raises(ValueError):
        command(service, action, **value)
    assert service.read("u", "c")["revision"] == 1


def model(evidence, status="checking"):
    return {
        "model_revision_id": "m1",
        "course_version_id": "cv1",
        "knowledge_profile": {
            "nodes": [{"knowledge_id": "k1", "knowledge_revision_id": "kr1", "status": status, "evidence": evidence}]
        },
    }


def test_question_does_not_diagnose_unknown_student():
    d = teaching_decision({}, question="这里是什么意思", knowledge_refs={"k1": "kr1"}, node_id="n1")
    assert d["action"] == "explain" and d["uncertainty"] == "insufficient_evidence"
    assert d["mastery_write"] is False


def test_explicit_request_wins_over_weak_profile():
    d = teaching_decision(
        model([], "needs_review"), question="给我举个例子", knowledge_refs={"k1": "kr1"}, node_id="n1"
    )
    assert d["action"] == "explain" and d["format"] == "example"


@pytest.mark.parametrize(
    "category,action", [("concept_gap", "contrast"), ("boundary_confusion", "contrast"), ("process_error", "step")]
)
def test_only_current_attributed_evidence_drives_specific_teaching(category, action):
    m = model([{"source_id": "a1", "support": "independent", "outcome": "not_passed"}])
    m["mistake_signals"] = [
        {"status": "confirmed", "category": category, "concept_ids": ["k1"], "evidence_refs": [{"source_id": "a1"}]}
    ]
    d = teaching_decision(m, question="帮我看看", knowledge_refs={"k1": "kr1"}, node_id="n1")
    assert d["action"] == action
    assert d["evidence_refs"]
    assert teaching_decision(m, question="帮我看看", knowledge_refs={"k1": "old"}, node_id="n1")["action"] == "explain"


def test_helped_success_invites_independent_check_not_mastery():
    d = teaching_decision(
        model([{"source_id": "a1", "support": "assisted", "outcome": "passed"}]),
        question="我现在会了吗",
        knowledge_refs={"k1": "kr1"},
        node_id="n1",
    )
    assert d["action"] == "verify" and d["requires_qualified_question"]
    assert d["mastery_write"] is False


def test_decision_never_uses_other_knowledge_point():
    m = model([])
    m["mistake_signals"] = [{"status": "confirmed", "category": "process_error", "concept_ids": ["other"]}]
    assert teaching_decision(m, question="帮我", knowledge_refs={"k1": "kr1"}, node_id="n1")["action"] == "explain"


def test_independent_check_requires_current_verified_unused_question_and_never_exposes_answer():
    task = {
        "task_revision_id": "q1",
        "quality_status": "passed",
        "concept_ids": ["k"],
        "knowledge_revision_refs": {"k": "kr"},
        "node_id": "n",
        "answer_spec": {"answer": "private"},
    }
    assert select_independent_question([task], [], "k", "kr") == {"task_revision_id": "q1", "node_id": "n"}
    assert select_independent_question([task], [{"task_revision_id": "q1"}], "k", "kr") is None
    assert select_independent_question([{**task, "quality_status": "runtime_fallback"}], [], "k", "kr") is None
    assert select_independent_question([task], [], "k", "old") is None


def test_help_outcomes_come_from_later_official_attempts_and_keep_uncertainty():
    links = {"q": {"created_at": "2026-10-22T01:00:00+00:00", "course_version_id": "cv", "help_message_id": "help"}}
    attempts = [
        {
            "attempt_id": "a",
            "task_revision_id": "q",
            "course_version_id": "cv",
            "created_at": "2026-10-22T02:00:00+00:00",
            "status": "graded",
            "result": {"passed": True, "grading_confidence": 0.9},
            "ai_support_level": 1,
        }
    ]
    row = help_followups(links, attempts, "cv")[0]
    assert row["status"] == "evidence_available" and row["attempts"][0]["independent"] is False
    assert help_followups(links, attempts, "other")[0]["status"] == "historical"
    assert help_followups(links, [], "cv")[0]["status"] == "verification_requested"

def test_repeated_independent_difficulty_gets_a_bounded_hint_and_later_pass_is_respected():
    evidence=[{'source_id':'a1','support':'independent','outcome':'not_passed'}, {'source_id':'a2','support':'independent','outcome':'not_passed'}]
    result=teaching_decision(model(evidence),question='帮我理一下',knowledge_refs={'k1':'kr1'},node_id='n1')
    assert result['action']=='step'
    assert result['basis']=='repeated_independent_difficulty'
    assert result['mastery_write'] is False
    result=teaching_decision(model(evidence+[{'source_id':'a3','support':'independent','outcome':'passed'}]),question='解释一下',knowledge_refs={'k1':'kr1'},node_id='n1')
    assert result['basis']!='repeated_independent_difficulty'


def test_check_followup_separates_assisted_success_from_independent_result_and_current_profile():
    links={'q':{'created_at':'2026-10-23T01:00:00Z','course_version_id':'cv','help_message_id':'h','knowledge_id':'k','knowledge_revision_id':'kr'}}
    attempt={'attempt_id':'a','task_revision_id':'q','course_version_id':'cv','created_at':'2026-10-23T02:00:00Z','status':'graded','result':{'passed':True,'grading_confidence':.9}}
    profile={'model_revision_id':'m2','knowledge_profile':{'nodes':[{'knowledge_id':'k','knowledge_revision_id':'kr','status':'checking','independent_count':1}]}}
    result=help_followups(links,[attempt],'cv',model=profile)[0]
    assert result['verification_state']=='independent_pass'
    assert result['current_profile']['status']=='checking'
    assert result['current_model_revision_id']=='m2'
    assert result['causal_effect_verified'] is False
    assisted=deepcopy(attempt);assisted['ai_support_level']=1
    assert help_followups(links,[assisted],'cv',model=profile)[0]['verification_state']=='assisted_only'
    uncertain=deepcopy(attempt);uncertain['result']['grading_confidence']=.2
    assert help_followups(links,[uncertain],'cv',model=profile)[0]['verification_state']=='uncertain'
    assert help_followups(links,[],'cv',model=profile)[0]['verification_state']=='awaiting_check'
    assert help_followups(links,[attempt],'new',model=profile)[0]['current_profile'] is None
