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
    task={'revision_id':'T1','task_revision_id':'T1','node_id':'L1','prompt':'分别说明两个量的变化及依据',
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
        return json.dumps({'checks':{'A':{'met':True,'evidence':'分别说明','feedback':'判断完整'},
            'B':{'met':False,'evidence':'没有依据','feedback':'需要说明理由'}},'confidence':.95})
    monkeypatch.setattr(grader,'_call_llm',model)
    attempt={'answer_payload':{'text':'我能分别说明，但是没有依据'}}
    result=await grade_checkpoints(grader,t,c,attempt)
    assert result['criterion_results']=={'C':{'A':True,'B':False}}
    assert result['score']==50 and result['passed'] is False
    # Same original attempt repository; a reopening retains rubric identity/results.
    repo=PracticeAttemptRepository(tmp_path/'attempts')
    a,_=repo.create_once('u','c',{'task_revision_id':'T1','course_version_id':'cv','concept_ids':['K'],
        'knowledge_revision_refs':{'K':'KR'},'criterion_revision_refs':{'C':'CR'},'assessment_evidence_key':'e1'})
    a,_=repo.submit('u','c',a['attempt_id'],expected_revision=a['revision'],request_id='submit-1',answer_payload=attempt['answer_payload'])
    a=repo.apply_grade('u','c',a['attempt_id'],expected_revision=a['revision'],result=result)
    reread=PracticeAttemptRepository(tmp_path/'attempts').get('u','c',a['attempt_id'])
    assert reread['criterion_revision_refs']=={'C':'CR'} and reread['result']['criterion_results']==result['criterion_results']
    assert summarize_check(c,[reread],user_id='u',course_id='c',course_version_id='cv')['status']=='needs_more_evidence'


@pytest.mark.asyncio
async def test_missing_uncertain_or_invented_checkpoint_evidence_stays_pending(monkeypatch):
    from knowledge_check_flow import grade_checkpoints
    _,c,t=fixture();grader=PracticeGrader();grader.client=object()
    for checks in [{'A':{'met':True,'evidence':'原句','feedback':'满足'}},
                   {'A':{'met':True,'evidence':'捏造的句子','feedback':'满足'},'B':{'met':True,'evidence':'原句','feedback':'满足'}}]:
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
