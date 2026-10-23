"""Bounded lesson-core generation within the existing authoring job/store."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone

from course_document import stable_hash
from generic_knowledge import sources, require
from knowledge_core_contract import CONTRACT, KNOWLEDGE_TYPES, group_materials, extraction_prompt, parse_extraction, review_prompt, compile_review, compile_fragment
from knowledge_core_contract import parse_core_response as parse_json
from knowledge_registry_identity import existing_catalog
from knowledge_registry_projection import build_tree
from knowledge_transport import REQUEST_SCOPE
from teacher_lesson_authoring import TeacherLessonAuthoringService, generation_failure


def initial_pipeline(raw,context,job_id):
    materials=[{'key':key,'text':unit['source_text']} for key,unit in sources(context).items()]
    return {'schema_version':'inventory_atomic_v1','generation_contract':CONTRACT,'prompt_contract':CONTRACT,
        'processing_contract':CONTRACT,'generation_mode':'core_v1','revision':0,'identity_job_id':job_id,
        'organize_hierarchy':True,'include_relations':False,'items':[],'batches':[],
        'inventory_batches':[{'id':f'core-{i}','source_keys':[m['key'] for m in group],'status':'pending'}
            for i,group in enumerate(group_materials(materials),1)],'names':{'result':{}},'catalog':existing_catalog(raw)}


def hierarchy_for(points, paths, raw, context):
    from knowledge_hierarchy import compile_hierarchy
    title=context['handout_lessons'][0]['title']
    categories=[{'key':'root','name':title,'parent_key':None}]
    prefixes={(): 'root'};assignments=[]
    for index,point in enumerate(points,1):
        prefix=()
        for label in paths[point['key']]:
            if label.strip()==title.strip() or prefix and label.strip()==prefix[-1]:continue
            parent=prefix;prefix=(*prefix,label.strip())
            if prefix not in prefixes:
                key=f'C{len(prefixes)}';prefixes[prefix]=key
                categories.append({'key':key,'name':label.strip(),'parent_key':prefixes[parent]})
        assignments.append({'point_key':f'K{index}','category_key':prefixes[prefix]})
    return compile_hierarchy({'categories':categories,'assignments':assignments},
        [{'key':f'K{i}'} for i in range(1,len(points)+1)],raw['course_id'],context['scope_lesson_id'])


def compile_tree(raw, context, pipeline, job_id, *, preview):
    candidates=(pipeline.get('registry') or {}).get('points') or [p for b in pipeline['inventory_batches'] for p in b.get('points',[])]
    if preview:
        candidates=[p for p in candidates if p['knowledge_type'] in KNOWLEDGE_TYPES]
    paths=pipeline.get('paths') or {p['key']:p['branch_path'] for p in candidates}
    hierarchy=hierarchy_for(candidates,paths,raw,context) if candidates else None
    display={**pipeline,'registry':{**(pipeline.get('registry') or {}),'points':candidates}}
    tree=build_tree(raw,context,display,job_id,hierarchy=hierarchy,preview=preview)
    tree.update(generation_contract=CONTRACT,generation_mode='core_v1',
                enrichment={'relations':'not_requested','kc_profiles':'not_requested'})
    tree['atomic_assessment']['schema_version']=CONTRACT
    if pipeline.get('core_review',{}).get('status')!='completed':
        tree['atomic_assessment']['ready_for_adoption']=False
    tree['revision_id']=stable_hash({k:v for k,v in tree.items() if k!='revision_id'},prefix='kb_')
    return tree


async def run(svc, course_id, job_id):
    from knowledge_first import knowledge_revision, now
    from knowledge_atomic import call_stage, run_batches
    io=TeacherLessonAuthoringService(svc.authoring)._authoring_io
    job=await io(svc._active,course_id,job_id)
    raw=await io(svc.repository.load_raw,course_id)
    context=job['request_snapshot']['knowledge_generation_context']
    materials=[{'key':key,'text':unit['source_text']} for key,unit in sources(context).items()]
    pipeline=deepcopy((job.get('checkpoint') or {}).get('atomic_pipeline'))
    if not pipeline or pipeline.get('generation_contract')!=CONTRACT:
        pipeline=initial_pipeline(raw,context,job_id)
    provider=None
    def validate_version():
        svc._active(course_id,job_id)
        fresh=svc.repository.load_raw(course_id)
        require(fresh.get('owner_id')==job.get('actor') and knowledge_revision(fresh)==job['source_knowledge_revision']
            and fresh.get('course_document_revision')==job['source_document_revision']
            and svc._context(fresh,'handouts',job['knowledge_lesson_id'])['revision_id']==context['revision_id'],
            '课程、知识或讲义版本已变化，保留本次结果')
    save_lock=asyncio.Lock()
    async def save(*,durable=False):
        async with save_lock:
            await io(validate_version)
            pipeline['revision']+=1
            if any(b.get('points') for b in pipeline['inventory_batches']):
                pipeline['preview_tree']=compile_tree(raw,context,pipeline,job_id,preview=True)
            snapshot=deepcopy(pipeline)
            progress=65*sum(b['status']=='completed' for b in snapshot['inventory_batches'])//len(snapshot['inventory_batches'])
            progress+=30*len(snapshot.get('core_review',{}).get('completed_groups',[]))//len(snapshot['inventory_batches'])
            await io(svc.authoring.update_job if durable else svc.authoring.update_job_live,
                course_id,job_id,checkpoint={'atomic_pipeline':snapshot},progress=progress)
            if not durable:await io(svc.authoring.publish_knowledge_preview,course_id)
    async def request(prompt,stage,record,compile_result):
        request_key=stable_hash({'contract':'knowledge_core_transport_v2','prompt':prompt,'epoch':record.get('response_epoch',0)},prefix='kreq_')
        if record.get('status')=='completed' and record.get('response_attachment')==request_key:
            return compile_result(deepcopy(record['response']))
        await io(validate_version)
        if record.get('status')!='failed':
            cached=await io(svc.authoring.read_knowledge_response,course_id,job_id,pipeline['identity_job_id'],request_key)
            if cached is not None:
                value=parse_json(cached);result=compile_result(value)
                record.update(status='completed',response=value,response_attachment=request_key,validation_origin='saved_response')
                return result
        record.update(status='requested');record.pop('validation_error',None)
        try:
            response=await call_stage(svc,course_id,job_id,provider,prompt,stage)
            record['raw_response']=response
            value=parse_json(response);result=compile_result(value)
            await io(svc.authoring.save_knowledge_response,course_id,job_id,pipeline['identity_job_id'],request_key,response)
            record.update(status='completed',response=value,response_attachment=request_key)
            return result
        except Exception as error:
            record.update(status='failed',validation_error=str(error))
            raise
    token=REQUEST_SCOPE.set({'validate_source':validate_version,'retry_budget':{'used':0,'active':{}}})
    try:
        await io(validate_version)
        await io(svc.authoring.update_job_live,course_id,job_id,status='running',generation_started_at=now(),
            phase='preparing',progress=0,checkpoint={'atomic_pipeline':deepcopy(pipeline)})
        if svc.provider_factory:provider=svc.provider_factory()
        else:
            from ai_base import AIBase
            provider=AIBase()
        async def extract(index,batch):
            selected=[m for m in materials if m['key'] in batch['source_keys']]
            batch['points']=await request(extraction_prompt(raw,context,selected),'candidate_core_extract',
                batch.setdefault('request',{}),lambda value:parse_extraction(value,batch['id'],batch['source_keys']))
            batch['status']='completed'
            pipeline['names']['result'].update({p['key']:{'name':p['short_name'],'meta_question':'请解释：'+p['statement']} for p in batch['points']})
            await save()
        review=pipeline.get('core_review',{})
        if review.get('contract')!='knowledge_core_review_v3':
            review={'contract':'knowledge_core_review_v3','status':'pending','batches':[],'completed_groups':[]};pipeline['core_review']=review
        async def review_batch(index,batch,group):
            focus=[p for p in group['points'] if p['key'] in batch['keys']]
            references=[p for p in group['points'] if p['key'] not in batch['keys']]
            selected=[m for m in materials if m['key'] in batch['source_keys']]
            coverage=[m for m in materials if m['key'] in batch['coverage_keys']]
            batch['result']=await request(review_prompt(raw,context,selected,focus,pipeline['catalog'],references=references,coverage_materials=coverage),
                'candidate_core_review',batch.setdefault('request',{}),lambda value:compile_fragment(value,focus,coverage,pipeline['catalog'],references))
            batch['status']='completed';await save()
        async def extract_and_review(index,work):
            group=work['group']
            if group['status']!='completed':await extract(index,group)
            for offset in range(0,max(1,len(group['points'])),12):
                batch_id=f"review-{group['id']}-{offset//12+1}"
                batch=next((b for b in review['batches'] if b['id']==batch_id),None)
                if batch is None:
                    batch={'id':batch_id,'status':'pending','keys':[p['key'] for p in group['points'][offset:offset+12]],
                        'source_keys':group['source_keys'],'coverage_keys':group['source_keys'] if offset==0 else []}
                    review['batches'].append(batch)
                if batch['status']!='completed':await review_batch(index,batch,group)
            if group['id'] not in review['completed_groups']:review['completed_groups'].append(group['id'])
            work['status']='completed';await save()
        work=[{'id':group['id'],'status':'pending','group':group} for group in pipeline['inventory_batches']]
        await run_batches(work,extract_and_review,width=8,stage='candidate_core_extract')
        candidates=[p for b in pipeline['inventory_batches'] for p in b['points']]
        require(bool(candidates) and len(candidates)<=160,'本讲独立知识为空或超过单讲容量')
        combined={'decisions':{},'add':[],'coverage':{}}
        for batch in review['batches']:
            fragment=batch['result']['response']
            combined['decisions'].update(fragment['decisions']);combined['add'].extend(fragment['add']);combined['coverage'].update(fragment['coverage'])
        try:
            result=compile_review(combined,candidates,pipeline['catalog'],materials)
        except ValueError:
            for batch in review['batches']:
                batch['status']='pending';record=batch['request'];record['status']='failed';record['response_epoch']=record.get('response_epoch',0)+1
            review['status']='failed'
            raise
        review['status']='completed'
        from knowledge_core_identity import catalog_prompt,apply_catalog
        if len(result['registry']['points'])>1:
            await io(svc.authoring.update_job_live,course_id,job_id,progress=96)
            result=await request(catalog_prompt(result),'candidate_core_identity_catalog',pipeline.setdefault('core_identity',{}),
                lambda value:apply_catalog(result,value,pipeline['catalog']))
        pipeline.update({k:deepcopy(v) for k,v in result.items() if k not in {'names','coverage'}})
        pipeline['names']={'status':'completed','result':result['names']}
        pipeline['hierarchy']={'status':'completed','result':{'schema_version':'knowledge_hierarchy_v5'}}
        tree=compile_tree(raw,context,pipeline,job_id,preview=False)
        await io(validate_version)
        elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(job['created_at'])).total_seconds()
        tree.update(source_context_revision=context['revision_id'],source_scope_revision=context['scope_contract']['revision_id'],
            generation_job_id=job_id,model=provider.model_smart,
            performance={'target_seconds':60,'candidate_compiled_seconds':round(elapsed,3),
                         'completion_measurement':'client_observed_durable_result'})
        tree['revision_id']=stable_hash({k:v for k,v in tree.items() if k!='revision_id'},prefix='kb_')
        await io(svc.authoring.update_job,course_id,job_id,status='completed',phase='completed',progress=100,
            checkpoint={'atomic_pipeline':deepcopy(pipeline),'candidate':tree},raw_response='',partial_text='',
            stream_complete=True,message='基础知识树已生成，关系与教学档案可另行补充')
    except asyncio.CancelledError:raise
    except Exception as error:
        current=await io(svc.authoring.get_job,course_id,job_id)
        if current['status'] in {'pending','running'}:
            await io(svc.authoring.update_job,course_id,job_id,status='failed',phase='failed',
                checkpoint={'atomic_pipeline':deepcopy(pipeline)},error=generation_failure(error,type(error).__name__),
                stream_complete=True,message='已保留完成批次与本次预览，可继续未完成阶段')
    finally:
        REQUEST_SCOPE.reset(token)
        if provider and getattr(provider,'client',None):await provider.client.close()
