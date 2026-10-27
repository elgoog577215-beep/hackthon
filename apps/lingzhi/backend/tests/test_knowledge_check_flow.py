from copy import deepcopy
import json
import pytest
from practice_grading import PracticeGrader
from practice_attempts import PracticeAttemptRepository
from knowledge_check_measurement import summarize_check,POLICY


def fixture():
    criterion={'criterion_id':'C','revision_id':'CR','contract':'knowledge_teaching_structures_v1',
        'knowledge_ids':['K'],'knowledge_revision_refs':{'K':'KR'},'name':'区分两种变化',
        'observable_performance':'分别说明两个量的变化','verification_method':'根据给出的图像说明变化',
        'controlled_conditions':['提供图像'],'checkpoints':[{'checkpoint_id':'A','label':'分别判断','pass_condition':'分别判断两个量'},
            {'checkpoint_id':'B','label':'说明依据','pass_condition':'根据图像说明理由'}],
        'scoring':{'max_score':2,'pass_score':2},'evidence_policy':POLICY,'readiness':'ready','review_status':'owner_accepted',
        'assessment_bindings':['T1','T2','T3']}
    course={'course_id':'c','current_course_version_id':'cv','course_knowledge_base':{'status':'accepted','revision_id':'kb',
        'knowledge_points':[{'knowledge_id':'K','revision_id':'KR','name':'变化','statement':'完整知识','section_refs':['L1']}],
        'mastery_criteria':[criterion]}}
    task={'revision_id':'T1','task_revision_id':'T1','node_id':'L1','question_type':'short_answer','prompt':'分别说明两个量的变化及依据',
        'concept_ids':['K'],'knowledge_revision_refs':{'K':'KR'},'review_status':'approved','quality_status':'passed',
        'answer_spec':{'canonical_answer':'参考结论和依据'},'validation_policy':{'mastery_eligible':True,'max_support_level_for_mastery':0}}
    return course,criterion,task


def test_resolve_requires_adopted_reviewed_current_exact_binding():
    from knowledge_check_flow import task_criterion
    course,c,t=fixture()
    assert task_criterion(course,t)['criterion_id']=='C'
    for field,value in [('readiness','needs_teaching_review'),('review_status','draft')]:
        wrong=deepcopy(course);wrong['course_knowledge_base']['mastery_criteria'][0][field]=value
        assert task_criterion(wrong,t) is None
    stale=deepcopy(t);stale['knowledge_revision_refs']['K']='old'
    assert task_criterion(course,stale) is None
    course['course_knowledge_base']['status']='candidate'
    assert task_criterion(course,t) is None


@pytest.mark.asyncio
async def test_checkpoint_grade_uses_each_verdict_and_real_evidence_not_model_score(monkeypatch,tmp_path):
    from knowledge_check_flow import grade_checkpoints
    course,c,t=fixture();grader=PracticeGrader();grader.client=object()
    async def model(*args,**kwargs):
        return json.dumps({'checks':{'A':{'met':True,'evidence_refs':['answer-1'],'feedback':'判断完整'},
            'B':{'met':False,'evidence_refs':['answer-1'],'feedback':'需要说明理由'}},'confidence':.95})
    monkeypatch.setattr(grader,'_call_llm',model)
    attempt={'answer_payload':{'text':'我能分别说明，但是没有依据'}}
    result=await grade_checkpoints(grader,t,c,attempt)
    assert result['criterion_results']=={'C':{'A':True,'B':False}}
    assert result['score']==50 and result['passed'] is False
    assert result['checkpoint_feedback'][0]['evidence']=='我能分别说明，但是没有依据'
    # Same original attempt repository; a reopening retains rubric identity/results.
    repo=PracticeAttemptRepository(tmp_path/'attempts')
    a,_=repo.create_once('u','c',{'task_revision_id':'T1','course_version_id':'cv','concept_ids':['K'],
        'knowledge_revision_refs':{'K':'KR'},'criterion_revision_refs':{'C':'CR'},'assessment_evidence_key':'e1'})
    a,_=repo.submit('u','c',a['attempt_id'],expected_revision=a['revision'],request_id='submit-1',answer_payload=attempt['answer_payload'],active_seconds=0)
    a=repo.apply_grade('u','c',a['attempt_id'],expected_revision=a['revision'],result=result)
    reread=PracticeAttemptRepository(tmp_path/'attempts').get('u','c',a['attempt_id'])
    assert reread['criterion_revision_refs']=={'C':'CR'} and reread['result']['criterion_results']==result['criterion_results']
    assert summarize_check(c,[reread],user_id='u',course_id='c',course_version_id='cv')['status']=='needs_more_evidence'


@pytest.mark.asyncio
async def test_missing_uncertain_or_invented_checkpoint_evidence_stays_pending(monkeypatch):
    from knowledge_check_flow import grade_checkpoints
    _,c,t=fixture();grader=PracticeGrader();grader.client=object()
    for checks in [{'A':{'met':True,'evidence_refs':['answer-1'],'feedback':'满足'}},
                   {'A':{'met':True,'evidence_refs':['unknown'],'feedback':'满足'},'B':{'met':True,'evidence_refs':['answer-1'],'feedback':'满足'}}]:
        async def model(*args,**kwargs):return json.dumps({'checks':checks,'confidence':.95})
        monkeypatch.setattr(grader,'_call_llm',model)
        result=await grade_checkpoints(grader,t,c,{'answer_payload':{'text':'原句'}})
        assert result['status']=='pending_review' and result['score'] is None


def test_target_only_selects_unused_approved_task_and_view_does_not_leak_answers():
    from knowledge_check_flow import check_view,select_task
    course,c,t=fixture();other={**t,'revision_id':'T2','task_revision_id':'T2'}
    attempts=[{'task_revision_id':'T1'}]
    assert select_task(course,[t,other],attempts,'C','CR')['task_revision_id']=='T2'
    view=check_view(course,[t,other],[],'K','KR','u')
    assert view['criteria'][0]['measurement']['status']=='unassessed'
    assert 'canonical_answer' not in json.dumps(view) and 'assessment_bindings' not in json.dumps(view)
    assert select_task(course,[t],attempts,'C','CR') is None


@pytest.mark.asyncio
async def test_practice_grading_consumes_bound_criterion_and_freezes_attempt_refs(monkeypatch):
    from routers import practice as routes
    course,c,t=fixture()
    seen=[]
    async def grade(task,attempt):
        seen.append(task)
        return {'status':'graded','score':100,'passed':True}
    monkeypatch.setattr(routes.practice_grader,'grade',grade)
    await routes._grade_task(course,'u',t,{'criterion_revision_refs':{'C':'CR'}})
    assert seen[0]['_knowledge_criterion']['criterion_id']=='C'
    result=await routes._grade_task(course,'u',t,{'criterion_revision_refs':{'C':'old'}})
    assert result['status']=='pending_review' and len(seen)==1


def test_authenticated_check_api_returns_current_criteria_and_never_reads_preview_identity(monkeypatch,tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock
    from routers import companion_learning as routes,practice
    from study.auth import study_identity
    course,c,t=fixture()
    monkeypatch.setattr(routes,'read_learning_course',AsyncMock(return_value=course))
    monkeypatch.setattr(practice,'_questions',lambda *a,**k:[t])
    repo=PracticeAttemptRepository(tmp_path/'attempts');monkeypatch.setattr(practice,'practice_attempt_repository',repo)
    app=FastAPI();app.include_router(routes.router,prefix='/api');app.dependency_overrides[study_identity]=lambda:{'id':'u'}
    client=TestClient(app)
    url='/api/courses/c/learning-records/knowledge-checks'
    response=client.get(url,params={'knowledge_id':'K','knowledge_revision':'KR'})
    assert response.status_code==200 and response.json()['criteria'][0]['criterion_id']=='C'
    selected=client.post(url+'/target',json={'knowledge_id':'K','knowledge_revision':'KR','criterion_id':'C','criterion_revision':'CR'})
    assert selected.status_code==200 and 'canonical_answer'not in selected.text
    bad=client.post(url+'/target',json={'knowledge_id':'K','knowledge_revision':'old','criterion_id':'C','criterion_revision':'CR'})
    assert bad.status_code==409
    app.dependency_overrides.clear()
    assert client.get(url,params={'knowledge_id':'K','knowledge_revision':'KR'},headers={'X-User-Id':'u'}).status_code in {401,403}


def test_model_exposes_checkpoint_evidence_without_conflating_it_with_mastery():
    from knowledge_mastery import build_knowledge_profile
    course,c,t=fixture();base=course['course_knowledge_base'];base['lifecycle_status']='active'
    base['knowledge_points'][0].update(status='active',granularity_status='atomic')
    profile=build_knowledge_profile(base,course_id='c',course_version_id='cv',user_id='u',attempts=[],events=[])
    assert profile['nodes'][0]['check_measurements'][0]['measurement']['latest_score']is None
    assert profile['nodes'][0]['mastery']is None


def test_unfinished_current_task_can_be_resumed_without_manufacturing_new_checks():
    from knowledge_check_flow import select_task
    course,c,t=fixture()
    a={'task_revision_id':'T1','status':'in_progress','course_version_id':'cv','criterion_revision_refs':{'C':'CR'}}
    assert select_task(course,[t],[a],'C','CR')['task_revision_id']=='T1'
    a['criterion_revision_refs']['C']='old'
    assert select_task(course,[t],[a],'C','CR')is None


def test_help_consumes_only_reviewed_shared_objects_at_current_knowledge_revision():
    from knowledge_check_flow import shared_help
    course,c,t=fixture();c['misconception_ids']=['M']
    row={'misconception_id':'M','revision_id':'MR','knowledge_ids':['K'],'knowledge_revision_refs':{'K':'KR'},
        'readiness':'ready','review_status':'owner_accepted','discrimination':'分别观察两个量','repair_strategy':'对照两种判断依据'}
    course['course_knowledge_base']['misconceptions']=[row]
    assert shared_help(course,t)[0]['revision_id']=='MR'
    row['review_status']='draft';assert shared_help(course,t)==[]
    row['review_status']='owner_accepted';row['knowledge_revision_refs']['K']='old';assert shared_help(course,t)==[]


def test_reading_back_feedback_is_current_private_and_does_not_expose_reference_answers():
    from knowledge_check_flow import check_view
    course,c,t=fixture()
    t['input_contract']={'mode':'rich_text','fields':[{'field_id':'text','kind':'rich_text','required':True}]}
    a={'attempt_id':'A','revision':3,'user_id':'u','course_id':'c','course_version_id':'cv','status':'graded',
        'task_revision_id':'T1','criterion_revision_refs':{'C':'CR'},'knowledge_revision_refs':{'K':'KR'},
        'answer_payload':{'text':'自己的回答'},'result':{'status':'graded','passed':False,'support_level':0,
            'checkpoint_feedback':[{'checkpoint_id':'A','label':'判断','met':False,'feedback':'分别判断'}],'canonical_answer':'private answer'}}
    view=check_view(course,[t],[a],'K','KR','u')
    assert view['last_check']['result']['checkpoint_feedback'][0]['feedback']=='分别判断'
    assert view['last_check']['task']['question']['input_contract']==t['input_contract']
    assert 'private answer'not in json.dumps(view)
    assert check_view(course,[t],[a],'K','KR','other')['last_check']is None
    a['criterion_revision_refs']['C']='old'
    assert check_view(course,[t],[a],'K','KR','u')['last_check']is None


def test_unsupported_choice_and_runner_tasks_keep_their_original_grading_path():
    from knowledge_check_flow import task_criterion
    course,c,t=fixture()
    for kind in ['single_choice','code']:
        assert task_criterion(course,{**t,'question_type':kind})is None
