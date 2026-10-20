"""One correction protocol owns prompt shape, decoding and durable subresults."""
from copy import deepcopy
import json

import pytest
from jsonschema import Draft202012Validator

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course, start
from backend.tests.test_knowledge_extraction_repair import point, value
from backend.tests.test_knowledge_validation_pipeline import context_for

CONTRACT = 'knowledge_correction_plan_v4'


def bound_response(context, subject='虚构主体'):
    from knowledge_compact import passage_catalog
    from knowledge_expression import bind_name
    p = point(subject)
    source = passage_catalog({**context,'knowledge_passage_mode':'source_blocks_v1'},['S1'])[0]['text']
    response = value([p]);response['_expression_contract']='knowledge_expression_v1'
    response['_content_review_trace']=[{'expression':bind_name('入栈把元素加入栈顶',p,source)}]
    return response


def test_small_decoder_envelope_requires_names_and_exact_target_keys():
    from knowledge_correction_protocol import envelope_schema
    targets={'S1.1:0':{'correction_plan':{'expression_only':False}}}
    schema=envelope_schema(targets,expression_contract='knowledge_expression_v1')
    good={'repairs':{'S1.1:0':{'handling':'patch','patch':{'subject':'入栈'},'reason':'原文对象'}},
          'short_statements':{'S1.1:0':['入栈把元素加入栈顶']},'source_issues':[]}
    validator=Draft202012Validator(schema);assert validator.is_valid(good)
    missing=deepcopy(good);del missing['short_statements'];assert not validator.is_valid(missing)
    nested=deepcopy(good);nested['repairs']['source_issues']=nested.pop('source_issues');assert not validator.is_valid(nested)
    outside=deepcopy(good);outside['repairs']['S1.1:1']=outside['repairs'].pop('S1.1:0');assert not validator.is_valid(outside)


@pytest.mark.asyncio
async def test_compact_correction_has_one_complete_format_and_no_extraction_or_fragment_hints(svc,monkeypatch):
    from knowledge_extraction_repair import repair_points
    raw,context=context_for(svc,monkeypatch);context['knowledge_correction_contract']=CONTRACT
    original=bound_response(context);record={}
    async def call(*args):
        head,encoded=args[-2].split('\nINPUT_JSON:\n');data=json.loads(encoded)
        assert data['repair_contract']==CONTRACT
        assert 'response_contract' not in head and '名称、命题、答案和元问题由程序' not in head
        assert 'short_statements' in head and '唯一完整响应格式' in head
        assert len(head)<4500
        assert 'literal_subjects' not in data['targets']['S1.1:0']
        return json.dumps({'repairs':{'S1.1:0':{'handling':'patch','patch':{'subject':'入栈'},'reason':'原文对象'}},
            'short_statements':{'S1.1:0':['入栈把元素加入栈顶']},'source_issues':[]})
    monkeypatch.setattr('knowledge_atomic.call_stage',call)
    output=await repair_points(svc,'c-pilot','j',None,raw,context,['S1'],1,original,record)
    assert output['passages']['S1.1']['points'][0]['subject']=='入栈'
    assert record['contract']==CONTRACT


@pytest.mark.asyncio
async def test_second_attempt_keeps_valid_semantic_patch_and_repairs_only_the_name(svc,monkeypatch):
    from knowledge_extraction_repair import correct_points
    from knowledge_extract import compile_extraction
    raw,context=context_for(svc,monkeypatch);context['knowledge_correction_contract']=CONTRACT
    original=bound_response(context);before=deepcopy(original);calls=[];record={}
    async def call(*args):
        data=json.loads(args[-2].split('\nINPUT_JSON:\n')[1]);target=data['targets']['S1.1:0'];calls.append(deepcopy(target))
        if len(calls)==1:
            decision={'handling':'patch','patch':{'subject':'入栈'},'reason':'仅修主体'};name='入栈的操作效果'
        else:
            assert target['point']==point()
            assert target['correction_plan']['expression_only'] is True
            assert target['correction_plan']['editable_fields']==[]
            decision={'handling':'rename','reason':'仅修名称'};name='入栈把元素加入栈顶'
        return json.dumps({'repairs':{'S1.1:0':decision},'short_statements':{'S1.1:0':[name]},'source_issues':[]})
    monkeypatch.setattr('knowledge_atomic.call_stage',call)
    output,result=await correct_points(svc,'c-pilot','j',None,raw,context,['S1'],1,original,record,
        compile_result=lambda response:compile_extraction(raw,context,['S1'],1,response),validate_source=lambda:None,max_attempts=2)
    assert len(calls)==2 and original==before
    assert record['attempts'][0]['validated_semantics_response']['passages']['S1.1']['points']==[point()]
    assert output['passages']['S1.1']['points']==[point()]
    assert result['tree']['knowledge_points'][0]['name']=='入栈把元素加入栈顶'


@pytest.mark.asyncio
async def test_new_jobs_freeze_the_correction_protocol(svc,monkeypatch):
    from backend.tests.test_knowledge_tree_relations import fake_provider
    setup_course(svc,monkeypatch);fake_provider(svc)
    job=start(svc,extraction_mode='single_pass_v1');await svc.run('c-pilot',job['id'])
    saved=svc.authoring.get_job('c-pilot',job['id'])
    assert saved['status']=='completed',saved.get('error')
    assert saved['checkpoint']['atomic_pipeline']['correction_contract']==CONTRACT
