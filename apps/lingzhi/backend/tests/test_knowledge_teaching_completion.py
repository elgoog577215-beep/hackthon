from copy import deepcopy
import json
import pytest
from backend.tests.test_knowledge_teaching_structures import teaching_reply,identity_reply


def points():
    return [{'key':f'K{i}','knowledge_id':f'kid-{i}','revision_id':f'rev-{i}','name':f'知识{i}',
             'statement':'完整知识与条件','section_refs':['L']}for i in (1,2)]


def incomplete():
    value=teaching_reply({'focus':points()})
    value['extensions'][0]['knowledge_keys']=['K1']
    return value


def test_optional_gap_is_precise_and_keeps_every_completed_field():
    from knowledge_teaching_contract import compile_batch
    value=incomplete();before=deepcopy(value)
    result=compile_batch(value,points(),points(),'B',allow_incomplete=True)
    assert result['pending_fields']==[{'knowledge_key':'K2','field':'extensions'}]
    assert {k:result[k]for k in value}==before and value==before
    with pytest.raises(ValueError,match='K2'):compile_batch(value,points(),points(),'B')


def test_legacy_failure_is_salvaged_without_splitting_or_overwriting_raw_output():
    from knowledge_teaching import partition_failed_batches
    request={'status':'failed','validation_error':'没有拓展时须说明原因','raw_response':json.dumps(incomplete(),ensure_ascii=False)}
    state={'batches':[{'id':'B','keys':['K1','K2'],'status':'pending','request':deepcopy(request)}]}
    partition_failed_batches(state,catalog={'knowledge_points':points()})
    assert len(state['batches'])==1 and state['batches'][0]['status']=='completed'
    assert state['batches'][0]['request']==request
    assert state['batches'][0]['result']['pending_fields']==[{'knowledge_key':'K2','field':'extensions'}]


def test_additive_patch_cannot_change_existing_criteria_or_foreign_point():
    from knowledge_teaching_completion import compile_completion,merge_completion
    from knowledge_teaching_contract import compile_batch
    result=compile_batch(incomplete(),points(),points(),'B',allow_incomplete=True);before=deepcopy(result)
    obj=teaching_reply({'focus':[points()[1]]})['extensions'][0]
    patch=compile_completion({'objects':[obj],'reason':''},'K2','extensions',points())
    merged=merge_completion(result,'K2','extensions',patch)
    assert merged['points']==before['points'] and merged['extensions'][0]==before['extensions'][0]
    assert len({o['key']for o in merged['extensions']})==2
    assert result==before
    with pytest.raises(ValueError):compile_completion({'objects':[],'reason':''},'K2','extensions',points())
    with pytest.raises(ValueError):compile_completion({'objects':[obj],'reason':'','criteria':[]},'K2','extensions',points())
    obj['knowledge_keys']=['K1']
    with pytest.raises(ValueError):compile_completion({'objects':[obj],'reason':''},'K2','extensions',points())


@pytest.mark.asyncio
async def test_resume_requests_only_the_missing_field_and_preserves_body():
    from knowledge_teaching import run,input_signature
    from knowledge_unified import body_signature
    tree={'knowledge_points':points(),'categories':[],'relations':[],'lessons':[]}
    raw=incomplete();record={'status':'failed','validation_error':'没有拓展时须说明原因','raw_response':json.dumps(raw)}
    state={'input_signature':input_signature(tree,'L'),'body_signature':body_signature(tree),'identity_origin':'origin',
           'status':'pending','batches':[{'id':'B','keys':['K1','K2'],'status':'pending','request':record}]}
    pipeline={'identity_job_id':'origin','teaching_structures':state};calls=[]
    async def request(prompt,stage,record,compile_result):
        payload=json.loads(prompt.split('\nINPUT_JSON:\n')[1]);calls.append((stage,payload))
        if stage=='candidate_teaching_completion':
            assert payload['knowledge_key']=='K2'and payload['field']=='extensions'
            value={'objects':teaching_reply({'focus':[points()[1]]})['extensions'],'reason':''}
        elif stage=='candidate_teaching_identity':value=identity_reply(payload)
        else:raise AssertionError('Repeated completed generation: '+stage)
        record['status']='completed';return compile_result(value)
    async def save():pass
    result=await run(None,'course','L',tree,pipeline,request,save)
    assert result['knowledge_points']==tree['knowledge_points']
    assert len(result['extensions'])==2
    assert pipeline['teaching_structures']['status']=='completed'
    assert [s for s,p in calls].count('candidate_teaching_completion')==1


def test_pending_optional_work_is_retryable_and_status_exposes_field_progress():
    from knowledge_generation_status import job_status
    from teacher_lesson_authoring import generation_failure
    from knowledge_teaching_contract import TeachingDesignInvalid
    error=TeachingDesignInvalid('知识2 缺少拓展');error.code='knowledge_teaching_incomplete'
    assert generation_failure(error,'unknown')['retryable'] is True
    job={'checkpoint':{'atomic_pipeline':{'teaching_structures':{'completion_tasks':[
        {'status':'completed'},{'status':'pending'}]}}}}
    assert job_status(job,'2026-10-30T00:00:00+00:00')['teaching_completion']=={'total':2,'completed':1,'pending':1}


@pytest.mark.asyncio
async def test_invalid_supplement_keeps_partial_preview_and_can_resume_only_the_gap():
    from knowledge_teaching import run,input_signature
    from knowledge_teaching_contract import TeachingDesignInvalid
    from knowledge_unified import body_signature
    tree={'knowledge_points':points(),'categories':[],'relations':[],'lessons':[]}
    state={'input_signature':input_signature(tree,'L'),'body_signature':body_signature(tree),'identity_origin':'origin','status':'pending',
           'batches':[{'id':'B','keys':['K1','K2'],'status':'pending','request':{'raw_response':json.dumps(incomplete())}}]}
    pipeline={'identity_job_id':'origin','teaching_structures':state};calls=[];fixed=False
    async def request(prompt,stage,record,compile_result):
        calls.append(stage)
        payload=json.loads(prompt.split('\nINPUT_JSON:\n')[1])
        if stage=='candidate_teaching_completion':
            value={'objects':teaching_reply({'focus':[points()[1]]})['extensions'],'reason':''}if fixed else {'objects':[],'reason':''}
        elif stage=='candidate_teaching_identity':value=identity_reply(payload)
        else:raise AssertionError('Repeated valid fields')
        return compile_result(value)
    async def save():pass
    with pytest.raises(TeachingDesignInvalid)as caught:await run(None,'c','L',tree,pipeline,request,save)
    assert caught.value.code=='knowledge_teaching_incomplete'
    assert state['status']=='partial'and pipeline['core_tree']['knowledge_points']==tree['knowledge_points']
    assert pipeline['core_tree']['mastery_criteria']and state['batches'][0]['result']['points']['K2']['no_extensions']==''
    calls.clear();fixed=True
    result=await run(None,'c','L',pipeline['core_tree'],pipeline,request,save)
    assert result['knowledge_points']==tree['knowledge_points']and state['status']=='completed'
    assert calls.count('candidate_teaching_completion')==1and 'candidate_teaching_structures'not in calls
