"""Stop runaway output without rewriting formulas or replaying successful work."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_unified import seed,start,provider,model_reply,body


def payload(text):
    return json.dumps({'profiles':{'K1':{'assessment_focus':text}}},ensure_ascii=False)


def test_repetition_detection_crosses_chunks_but_not_separate_fields():
    from knowledge_output_guard import JsonOutputGuard
    guard=JsonOutputGuard()
    raw=payload('简短说明 '+('aBcD(x+1)/'*80))
    with pytest.raises(ValueError,match='重复'):
        for i in range(0,len(raw),7):guard.feed(raw[i:i+7])
    assert guard.reason=='repetition'
    assert guard.path==('profiles','K1','assessment_focus')
    # Repeated JSON field names and ordinary formula notation across distinct
    # records must not be mistaken for one endlessly expanding string.
    normal=json.dumps({'profiles':{f'K{i}':{'assessment_focus':r'识别 $f^{(n+1)}(x)$ 的阶数与参数。'}for i in range(30)}})
    good=JsonOutputGuard()
    for char in normal:good.feed(char)


def test_field_limit_counts_decoded_unicode_and_escaped_quotes_incrementally():
    from knowledge_output_guard import JsonOutputGuard
    path=('profiles','K1','assessment_focus')
    guard=JsonOutputGuard({path:12})
    text='说明"参数"'+r'\theta'
    raw=json.dumps({'profiles':{'K1':{'assessment_focus':text}}},ensure_ascii=True)
    for char in raw:guard.feed(char)
    with pytest.raises(ValueError,match='过长'):
        JsonOutputGuard({path:12}).feed(payload(text+'额外'))


def test_profile_schema_closes_keys_and_bounds_each_field_before_generation():
    from knowledge_kc_profiles import response_schema,PROFILE_FIELD_MAX_CHARS
    from jsonschema import Draft202012Validator
    schema=response_schema(['K1'])
    fields=schema['properties']['profiles']['properties']['K1']['properties']
    assert len(fields)==5 and all(f['maxLength']==PROFILE_FIELD_MAX_CHARS for f in fields.values())
    value={'profiles':{'K1':{k:'短说明'for k in fields}}}
    assert not list(Draft202012Validator(schema).iter_errors(value))
    value['profiles']['K1']['assessment_focus']='字'*(PROFILE_FIELD_MAX_CHARS+1)
    assert list(Draft202012Validator(schema).iter_errors(value))


@pytest.mark.asyncio
async def test_guard_cancels_provider_even_when_callback_exceptions_would_be_swallowed(svc,monkeypatch):
    from knowledge_atomic import call_stage
    from knowledge_kc_profiles import profile_prompt
    original=await seed(svc,monkeypatch);job=start(svc,'guard-stream',generation_mode='full_v1')
    cancelled=asyncio.Event();calls=[]
    async def stream(prompt,**kwargs):
        calls.append(kwargs)
        try:
            for chunk in ['{"profiles":{"K1":{"assessment_focus":"',*['aBcD(x+1)/']*200]:
                try:kwargs['on_content_delta'](chunk)
                except Exception:pass
                await asyncio.sleep(0)
            await asyncio.sleep(10)
        finally:cancelled.set()
    points=original['checkpoint']['candidate']['knowledge_points']
    with pytest.raises(ValueError,match='重复') as caught:
        await asyncio.wait_for(call_stage(svc,'c-pilot',job['id'],SimpleNamespace(_call_llm=stream),profile_prompt(points,{}),'kc_profiles'),2)
    assert cancelled.is_set() and len(calls)==1
    assert caught.value.partial_response.startswith('{"profiles"')
    assert len(caught.value.partial_response)<2500
    assert calls[0]['json_schema']['additionalProperties'] is False
    assert calls[0]['max_tokens']<14000


@pytest.mark.asyncio
async def test_failed_batch_keeps_its_own_partial_output_after_parallel_success(svc,monkeypatch):
    from ai_base import AIResponseTruncated
    original=await seed(svc,monkeypatch);failed=asyncio.Event();fragment='{"profiles":{"K1":{"assessment_focus":"真实失败片段'
    async def model(prompt,**kwargs):
        p=json.loads(prompt.split('\nINPUT_JSON:\n')[1])
        if p['stage']=='kc_profiles':
            kwargs['on_content_delta'](fragment);failed.set()
            raise AIResponseTruncated('test truncated')
        await failed.wait();await asyncio.sleep(.02)
        text=json.dumps(model_reply(p));kwargs['on_content_delta'](text);return text
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=model,model_smart='test',client=None)
    job=start(svc,'batch-fragment',generation_mode='full_v1');await svc.run('c-pilot',job['id'])
    saved=svc.authoring.get_job('c-pilot',job['id']);assert saved['status']=='failed'
    pipeline=saved['checkpoint']['atomic_pipeline']
    assert pipeline['kc_profiles']['batches'][0]['request']['raw_response']==fragment
    assert pipeline['registry_relations']['status']=='completed'
    assert body(pipeline['core_tree'])==body(original['checkpoint']['candidate'])
    calls=[];provider(svc,calls);resumed=start(svc,'resume-fragment',resume_job_id=job['id'])
    await svc.run('c-pilot',resumed['id'])
    assert svc.authoring.get_job('c-pilot',resumed['id'])['status']=='completed'
    assert [p['stage']for p in calls]==['kc_profiles']


@pytest.mark.asyncio
async def test_final_response_is_guarded_when_provider_does_not_emit_deltas(svc,monkeypatch):
    from knowledge_atomic import call_stage
    from knowledge_kc_profiles import profile_prompt
    original=await seed(svc,monkeypatch);job=start(svc,'final-guard',generation_mode='full_v1')
    async def model(*args,**kwargs):return payload('aBcD(x+1)/'*20)
    with pytest.raises(ValueError,match='重复'):
        await call_stage(svc,'c-pilot',job['id'],SimpleNamespace(_call_llm=model),
            profile_prompt(original['checkpoint']['candidate']['knowledge_points'],{}),'kc_profiles')


@pytest.mark.asyncio
async def test_completed_v1_profiles_are_reused_even_beyond_the_new_output_limit(svc,monkeypatch):
    await seed(svc,monkeypatch);calls=[];provider(svc,calls)
    job=start(svc,'completed-profiles',generation_mode='full_v1');await svc.run('c-pilot',job['id'])
    state=svc.authoring.load('c-pilot');tree=state['jobs'][job['id']]['checkpoint']['candidate']
    for point in tree['knowledge_points']:
        point['kc_skill_profile']['contract']='knowledge_kc_profile_v1'
        point['kc_skill_profile']['skill']['description']='旧说明'*150
    svc.authoring._save(state);calls.clear()
    resumed=start(svc,'reuse-v1-profiles',generation_mode='full_v1',base_job_id=job['id'])
    await svc.run('c-pilot',resumed['id']);saved=svc.authoring.get_job('c-pilot',resumed['id'])
    assert saved['status']=='completed',saved.get('error')
    assert not calls and saved['checkpoint']['candidate']['knowledge_points']==tree['knowledge_points']
