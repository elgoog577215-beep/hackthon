"""Incremental structured teaching within the existing knowledge task."""
from copy import deepcopy
from course_document import stable_hash
from generic_knowledge import require
from knowledge_teaching_contract import CONTRACT,PROMPT_REVISION,prompt,compile_batch
from knowledge_teaching_assets import drafts_for,existing_catalog,identity_prompt,resolve_identities,assemble
from knowledge_unified import protected_body,body_signature


def input_signature(tree,lesson_id):
    return stable_hash({'contract':CONTRACT,'prompt_revision':PROMPT_REVISION,'lesson':lesson_id,'points':[
        {k:p.get(k)for k in ('knowledge_id','revision_id','statement','conditions','symbol_definitions','check_intents','kc_skill_profile')}
        for p in tree['knowledge_points']if lesson_id in p.get('section_refs',[])]},prefix='kti_')


def asset_signature(tree,ids):
    from knowledge_teaching_assets import COLLECTIONS
    rows=[]
    for collection,id_field in [*COLLECTIONS.values(),('teaching_bindings','binding_id')]:
        ignored={'status','review_status','name'}
        if collection in {'misconceptions','extensions'}:ignored.update({'knowledge_ids','knowledge_revision_refs','primary_knowledge_id','related_knowledge_ids','section_refs','source_refs'})
        rows.extend({k:deepcopy(v)for k,v in row.items()if k not in ignored}
                    for row in tree.get(collection,[])if row.get(id_field)in ids)
    return stable_hash(sorted(rows,key=lambda row:str(sorted(row.items()))),prefix='ktassets_')


def partition_failed_batches(state):
    """On explicit resume, reduce only a failed request's transport scope."""
    batches=[]
    for batch in state['batches']:
        if batch.get('status')!='completed' and len(batch['keys'])>1 and batch.get('request',{}).get('validation_error'):
            state.setdefault('superseded_batches',[]).append(deepcopy(batch))
            batches.extend({'id':f"{batch['id']}.{i}",'keys':[key],'status':'pending'}for i,key in enumerate(batch['keys'],1))
        else:batches.append(batch)
    state['batches']=batches


async def run(svc,course_id,lesson_id,tree,pipeline,request,save):
    from knowledge_atomic import run_batches
    frozen=protected_body(tree);signature=input_signature(tree,lesson_id)
    certificates=tree.get('enrichment',{}).get('teaching_structures',{})
    cert=certificates.get(lesson_id,{}) if isinstance(certificates,dict)else{}
    if (cert.get('contract')==CONTRACT and cert.get('input_signature')==signature
        and cert.get('asset_signature')==asset_signature(tree,cert.get('asset_ids',[]))):return tree
    catalog=deepcopy(tree)
    for i,p in enumerate(catalog['knowledge_points'],1):p['key']=f'K{i}'
    local=[p for p in catalog['knowledge_points']if lesson_id in p.get('section_refs',[])]
    state=pipeline.get('teaching_structures',{})
    if state.get('input_signature')!=signature:
        state={'contract':CONTRACT,'input_signature':signature,'body_signature':body_signature(tree),
            'identity_origin':pipeline['identity_job_id'],'status':'pending','batches':[
                {'id':f'teaching-{i//3+1}','keys':[p['key']for p in local[i:i+3]],'status':'pending'}for i in range(0,len(local),3)]}
        pipeline['teaching_structures']=state
    else:partition_failed_batches(state)
    async def batch_run(index,batch):
        focus=[p for p in local if p['key']in batch['keys']]
        batch['result']=await request(prompt(catalog,focus),'candidate_teaching_structures',batch.setdefault('request',{}),
            lambda value:compile_batch(value,focus,catalog['knowledge_points'],batch['id']))
        batch['status']='completed';await save()
    await run_batches(state['batches'],batch_run,width=3,stage='candidate_teaching_structures')
    drafts=drafts_for(state['batches']);existing=existing_catalog(tree)
    if len(drafts)>1 or drafts and existing:
        identities=await request(identity_prompt(drafts,existing),'candidate_teaching_identity',state.setdefault('identity',{}),
            lambda value:resolve_identities(value,drafts,existing))
    else:identities={p['key']:p['key']for p in drafts}
    result=assemble(catalog,state['batches'],identities,existing,course_id,lesson_id,state['identity_origin'])
    # The transport catalog must not rename any frozen point's short key.
    result['knowledge_points']=deepcopy(tree['knowledge_points'])
    require(protected_body(result)==frozen,'教学结构不能改写知识主体、分类或覆盖清单')
    from knowledge_teaching_assets import COLLECTIONS
    scope_ids=sorted({key for b in result.get('teaching_bindings',[])if b['scope_lesson_id']==lesson_id
        for key in (b['binding_id'],b['object_id'])})
    result.setdefault('enrichment',{}).setdefault('teaching_structures',{})[lesson_id]={
        'contract':CONTRACT,'status':'completed','input_signature':signature,'asset_ids':scope_ids,
        'asset_signature':asset_signature(result,scope_ids)}
    state.update(status='completed',result_summary=deepcopy(result['teaching_structure_summary']))
    await save()
    return result
