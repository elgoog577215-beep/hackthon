"""Add version-bound relations and teaching profiles to a frozen knowledge tree."""
import asyncio
from copy import deepcopy

from course_document import stable_hash
from generic_knowledge import require
from knowledge_unified import body_signature, protected_body, validate_core


def progress(pipeline):
    def fraction(stage):
        if stage.get('status')=='completed':return 1
        rows=stage.get('batches',[])
        return sum(b['status']=='completed'for b in rows)/len(rows) if rows else 0
    return int(60+20*fraction(pipeline.get('registry_relations',{}))+15*fraction(pipeline.get('kc_profiles',{})))


async def enrich(svc,course_id,lesson_id,pipeline,request,save,io):
    from knowledge_atomic import run_batches
    from knowledge_registry_relations import prompt as relation_prompt,compile_edges,attach
    from knowledge_kc_profiles import profile_prompt,compile_profiles,eligible_questions,CONTRACT as PROFILE_CONTRACT,READABLE_CONTRACTS,PROFILE_FIELD_MAX_CHARS
    base=deepcopy(pipeline['core_tree']);validate_core(base,lesson_id)
    signature=body_signature(base)
    frozen=protected_body(base)
    # Short keys are transport references, not knowledge identities. Historical
    # per-lesson trees may reuse K1; remap only the model's private catalog.
    catalog=deepcopy(base)
    for index,point in enumerate(catalog['knowledge_points'],1):point['key']=f'K{index}'
    local=[p for p in catalog['knowledge_points']if lesson_id in p.get('section_refs',[])]
    keys=[p['key']for p in local]
    certificate=base.get('enrichment',{}).get('relations',{})
    certified=isinstance(certificate,dict) and certificate.get('status')=='completed' and certificate.get('body_signature')==signature
    relations=pipeline.setdefault('registry_relations',{'status':'completed' if certified else 'pending',
        'body_signature':signature,'batches':[] if certified else [
            {'id':f'relations-{i//6+1}','focus_keys':keys[i:i+6],'status':'pending'} for i in range(0,len(keys),6)]})
    require(relations['body_signature']==signature,'关系任务的冻结知识已变化')
    def current_profile(point):
        profile=point.get('kc_skill_profile') or {}
        fields={'description','assessment_focus','assessment_format','common_mistakes','difficulty_cues'}
        skill=profile.get('skill')
        limit=PROFILE_FIELD_MAX_CHARS if profile.get('contract')==PROFILE_CONTRACT else 1800
        return (profile.get('contract')in READABLE_CONTRACTS and profile.get('knowledge_id')==point['knowledge_id']
            and profile.get('knowledge_revision')==point['revision_id'] and isinstance(skill,dict) and set(skill)==fields
            and all(isinstance(v,str) and v.strip() and len(v)<=limit for v in skill.values()))
    missing=[p for p in local if not current_profile(p)]
    profiles=pipeline.setdefault('kc_profiles',{'status':'pending','body_signature':signature,'batches':[
        {'id':f'profiles-{i//4+1}','point_ids':[p['knowledge_id']for p in missing[i:i+4]],'status':'pending'} for i in range(0,len(missing),4)]})
    require(profiles['body_signature']==signature,'教学档案任务的冻结知识已变化')
    if 'sample_groups'not in profiles:
        def samples():
            raw=svc.repository.load_raw(course_id)
            accepted=raw.get('course_knowledge_base') or {}
            if accepted.get('status')!='accepted':return {}
            from question_bank import QuestionBankRepository
            return eligible_questions(base,QuestionBankRepository().load_bundle(course_id))
        profiles['sample_groups']=await io(samples)
    groups=profiles['sample_groups']
    async def relation_batch(index,batch):
        batch['result']=await request(relation_prompt(catalog,batch['focus_keys']),'candidate_relations',batch.setdefault('request',{}),
            lambda value:compile_edges(value,catalog,batch['focus_keys'],lesson_id))
        batch['status']='completed';await save()
    async def profile_batch(index,batch):
        points=[p for p in local if p['knowledge_id']in batch['point_ids']]
        batch['result']=await request(profile_prompt(points,groups),'kc_profiles',batch.setdefault('request',{}),
            lambda value:compile_profiles(value,points,groups))
        batch['status']='completed';await save()
    async def run_relations():
        if relations['status']!='completed':
            await run_batches(relations['batches'],relation_batch,width=4,stage='candidate_relations')
            relations['status']='completed';await save()
    async def run_profiles():
        if profiles['status']!='completed':
            await run_batches(profiles['batches'],profile_batch,width=3,stage='kc_profiles')
            profiles['status']='completed';await save()
    # Retain all in-flight successes before reporting an error. Cancellation
    # still propagates through the original job control and bounded workers.
    results=await asyncio.gather(run_relations(),run_profiles(),return_exceptions=True)
    for result in results:
        if isinstance(result,BaseException):raise result
    tree=attach(base,relations['batches']) if relations['batches'] else deepcopy(base)
    by_id={p['knowledge_id']:p for p in tree['knowledge_points']}
    for batch in profiles['batches']:
        for kid,profile in batch['result'].items():by_id[kid]['kc_skill_profile']=deepcopy(profile)
    require(protected_body(tree)==frozen,'配套生成不能删除、合并或改写知识主体及覆盖')
    require(all(current_profile(by_id[p['knowledge_id']])for p in local),'本讲教学档案尚未完整覆盖')
    tree['enrichment']={'relations':{'status':'completed','body_signature':signature,'reviewed_knowledge_ids':[p['knowledge_id']for p in local]},
        'kc_profiles':{'status':'completed','body_signature':signature,'knowledge_ids':[p['knowledge_id']for p in local]}}
    tree['kc_profile_summary']={'scope':'all_lesson','profile_count':len(local),'draft_count':len(local),'learner_evidence':False}
    tree['core_reuse']=deepcopy(pipeline.get('core_reuse') or {'origin':'generated','body_signature':signature})
    return tree
