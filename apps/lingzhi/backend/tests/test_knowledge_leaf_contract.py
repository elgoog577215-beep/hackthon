import json
from copy import deepcopy
import pytest
from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course,inventory
from course_repository import CourseDocumentConflict

CONTRACT='knowledge_leaf_claims_v4'


def fixture(svc,monkeypatch):
    from knowledge_atomic import compile_inventory
    setup_course(svc,monkeypatch);ctx=svc._context(svc.repository.load_raw('c-pilot'),'handouts','cpu')
    response=inventory();extra={**deepcopy(response['items'][0]),'key':'I3','kind':'example'}
    response['items'].append(extra);response['source_coverage'][0]['item_keys'].append('I3')
    items,_=compile_inventory(response,ctx,['S1'],1);items[0]['conditions']=['栈未满']
    return ctx,items


def reply(items):
    return {'response_contract':CONTRACT,'categories':[{'key':'C1','name':'栈操作','parent_key':None}],
        'points':[{'inventory_key':i['key'],'attachment_keys':[],'category_key':'C1','name':i['name'],
            'claims':[i['claim']],'meta_question':i['name']+'执行什么操作？','meta_answer':i['claim'],
            'extraction_method':'direct_statement','derivation_note':''} for i in items[:2]],
        'context_items':[{'inventory_key':items[2]['key'],'reason':'本例保留为说明背景。'}],'gaps':[]}


def test_leaf_input_separates_knowledge_from_examples(svc,monkeypatch):
    from knowledge_atomic import stage_prompt
    ctx,items=fixture(svc,monkeypatch)
    payload=json.loads(stage_prompt(svc.repository.load_raw('c-pilot'),ctx,'atomize',source_keys=['S1'],items=items).split('\nINPUT_JSON:\n')[1])
    assert [i['key'] for i in payload['items']]==[i['key'] for i in items[:2]]
    assert payload['attachments'][0]['key']==items[2]['key']


def test_program_assembles_single_claim_and_inherits_frozen_conditions(svc,monkeypatch):
    from knowledge_atomic import compile_batch
    ctx,items=fixture(svc,monkeypatch);tree,report=compile_batch(svc.repository.load_raw('c-pilot'),ctx,items,reply(items))
    assert report['ready_for_adoption']
    assert tree['knowledge_points'][0]['statement']==items[0]['claim']
    assert tree['knowledge_points'][0]['conditions']==['栈未满']
    assert tree['knowledge_points'][0]['source_binding_origin']=='frozen_inventory_passage'


def test_multiple_declared_claims_remain_blocking(svc,monkeypatch):
    from knowledge_atomic import compile_batch
    ctx,items=fixture(svc,monkeypatch);value=reply(items);value['points'][0]['claims']=['入栈插入元素。','出栈移除元素。']
    _,report=compile_batch(svc.repository.load_raw('c-pilot'),ctx,items,value)
    assert not report['ready_for_adoption'] and any(i['code']=='multiple_or_unbound_claims' for i in report['issues'])


def test_example_id_cannot_be_used_as_a_knowledge_leaf(svc,monkeypatch):
    from knowledge_atomic import compile_batch
    ctx,items=fixture(svc,monkeypatch);value=reply(items);value['points'][0]['inventory_key']=items[2]['key']
    with pytest.raises(CourseDocumentConflict):compile_batch(svc.repository.load_raw('c-pilot'),ctx,items,value)


@pytest.mark.asyncio
async def test_rebuild_all_leaves_reuses_inventory_and_keeps_original_attempt(svc,monkeypatch):
    from backend.tests.test_knowledge_atomic import start,provider
    setup_course(svc,monkeypatch);provider(svc);first=start(svc);await svc.run('c-pilot',first['id'])
    old=deepcopy(svc.authoring.get_job('c-pilot',first['id']));calls=provider(svc)
    child=start(svc,'leaves-only',resume_job_id=first['id'],retry_batch_id='all_atoms');await svc.run('c-pilot',child['id'])
    saved=svc.authoring.get_job('c-pilot',child['id'])
    assert len(calls)==2 and all(c['stage']=='atomize' for c in calls)
    assert saved['checkpoint']['atomic_pipeline']['inventory_batches']==old['checkpoint']['atomic_pipeline']['inventory_batches']
    assert svc.authoring.get_job('c-pilot',first['id'])==old
