import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course, inventory, atomic_answer, start, provider
from course_repository import CourseDocumentConflict

INVENTORY='knowledge_inventory_compact_v2'
ATOMIC='knowledge_atomic_compact_v2'


def context(svc):return svc._context(svc.repository.load_raw('c-pilot'),'handouts','cpu')


def compact_inventory():
    return {'response_contract':INVENTORY,'items':inventory()['items'],'source_notes':[],'source_issues':[]}


def compact_atoms(items):
    value=atomic_answer(items)
    return {'response_contract':ATOMIC,'categories':value['categories'],'points':value['points'],'context_items':[],'gaps':[]}


def test_inventory_prompt_does_not_seed_an_empty_output_list(svc,monkeypatch):
    from knowledge_atomic import stage_prompt
    setup_course(svc,monkeypatch);data=json.loads(stage_prompt(svc.repository.load_raw('c-pilot'),context(svc),'inventory',source_keys=['S1']).split('\nINPUT_JSON:\n')[1])
    assert 'items' not in data
    assert data['required_source_keys']==['S1']


def test_compact_inventory_derives_only_explicit_source_bindings(svc,monkeypatch):
    from knowledge_atomic import compile_inventory
    setup_course(svc,monkeypatch)
    items,coverage=compile_inventory(compact_inventory(),context(svc),['S1'],1)
    assert len(items)==2 and coverage[0]['item_keys']==[i['key'] for i in items]
    assert coverage[0]['mapping_origin']=='program_validated_bindings'


def test_compact_inventory_may_not_silently_skip_a_source(svc,monkeypatch):
    from knowledge_atomic import compile_inventory
    setup_course(svc,monkeypatch);result=compact_inventory();result['items']=[]
    with pytest.raises(CourseDocumentConflict):compile_inventory(result,context(svc),['S1'],1)


def test_compact_background_requires_an_explicit_reason(svc,monkeypatch):
    from knowledge_atomic import compile_inventory
    setup_course(svc,monkeypatch);result=compact_inventory();result['items']=[]
    result['source_notes']=[{'source_key':'S1','handling':'context','reason':'仅作背景'}]
    items,coverage=compile_inventory(result,context(svc),['S1'],1)
    assert not items and coverage[0]['handling']=='context'


@pytest.mark.parametrize('fault',['none','wrong_question','missing_point','lost_condition','coarse'])
def test_compact_question_mapping_keeps_all_existing_quality_guards(svc,monkeypatch,fault):
    from knowledge_atomic import compile_inventory,compile_batch
    setup_course(svc,monkeypatch);ctx=context(svc);items,_=compile_inventory(inventory(),ctx,['S1'],1)
    if fault=='lost_condition':items[0]['conditions']=['栈未满']
    result=compact_atoms(items)
    if fault=='wrong_question':result['points'][0]['meta_question']='出栈是什么？'
    if fault=='missing_point':result['points']=result['points'][:1]
    if fault=='coarse':
        result['points']=result['points'][:1];result['points'][0]['inventory_keys']=[i['key'] for i in items]
    _,report=compile_batch(svc.repository.load_raw('c-pilot'),ctx,items,result)
    assert report['ready_for_adoption']==(fault=='none')
    assert report['semantics_verified'] is False
    assert report['mapping_origin']=='program_validated_bindings'


@pytest.mark.asyncio
async def test_structured_json_single_attempt_and_per_stage_metrics_are_persisted(svc,monkeypatch):
    setup_course(svc,monkeypatch);calls=[]
    async def call(prompt,**kwargs):
        data=json.loads(prompt.split('\nINPUT_JSON:\n')[1]);calls.append(kwargs)
        assert kwargs['json_mode'] is True and kwargs['json_schema']['type']=='object'
        assert kwargs['max_attempts']==1
        value=compact_inventory() if data['stage']=='inventory' else compact_atoms(data['items'])
        output=json.dumps(value,ensure_ascii=False);kwargs['on_content_delta'](output)
        kwargs['telemetry_sink']({'model_id':'test-qwen','status':'completed','duration_ms':25,'input_tokens':120,'output_tokens':80,'tokens_source':'provider','physical_request_count':1})
        return output
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=call,model_smart='test-qwen',client=None)
    job=start(svc);await svc.run('c-pilot',job['id']);saved=svc.authoring.get_job('c-pilot',job['id'])
    assert saved['status']=='completed',saved.get('error')
    assert len(calls)==3 and len(saved['stage_observations'])==3
    row=saved['stage_observations'][0]
    assert row['stage']=='inventory' and row['input_tokens']==120 and row['tokens_source']=='provider'
    assert row['first_content_seconds'] is not None and row['seconds']>=0
    status=svc.status('c-pilot');assert 'stage_observations' not in json.dumps(status)


@pytest.mark.asyncio
async def test_source_issues_preserve_exact_quotes_and_require_owner_review(svc,monkeypatch):
    setup_course(svc,monkeypatch)
    def issue(data,result):
        if data['stage']=='inventory':result['source_issues']=[{'source_key':'S1','kind':'suspected_error','quote':'入栈将元素插入栈顶。','detail':'来源表述需要进一步核对。'}]
    provider(svc,mutate=issue);job=start(svc);await svc.run('c-pilot',job['id'])
    candidate=svc.authoring.get_job('c-pilot',job['id'])['checkpoint']['candidate']
    assert candidate['atomic_assessment']['source_issues'][0]['quote']=='入栈将元素插入栈顶。'
    view=svc.view('c-pilot')
    with pytest.raises(CourseDocumentConflict):svc.adopt('c-pilot',job['id'],'',view['document_revision'])


@pytest.mark.asyncio
async def test_exact_regeneration_preserves_existing_manual_aliases(svc,monkeypatch):
    setup_course(svc,monkeypatch);provider(svc);first=start(svc);await svc.run('c-pilot',first['id'])
    tree=deepcopy(svc.authoring.get_job('c-pilot',first['id'])['checkpoint']['candidate']);tree.update(status='accepted',revision_id='existing')
    tree['knowledge_points'][0]['aliases']=['已有手工别名']
    svc.storage.update_course_data('c-pilot',lambda r:{**r,'course_knowledge_base':tree,'knowledge_first_history':{'existing':tree}})
    provider(svc);second=start(svc,'regenerate');await svc.run('c-pilot',second['id'])
    candidate=svc.authoring.get_job('c-pilot',second['id'])['checkpoint']['candidate']
    assert candidate['knowledge_points'][0]['knowledge_id']==tree['knowledge_points'][0]['knowledge_id']
    assert '已有手工别名' in candidate['knowledge_points'][0]['aliases']
