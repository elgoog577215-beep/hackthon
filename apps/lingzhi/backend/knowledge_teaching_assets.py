"""Compile shared teaching objects into the original course knowledge payload."""
from copy import deepcopy
from course_document import stable_hash
from knowledge_check_measurement import POLICY
from knowledge_teaching_contract import CONTRACT,obj,text
from knowledge_registry_contract import render
from jsonschema import Draft202012Validator

COLLECTIONS={'mistake':('misconceptions','misconception_id'),'criterion':('mastery_criteria','criterion_id'),
             'extension':('extensions','extension_id')}


def drafts_for(batches):
    result=[]
    for batch in sorted(batches,key=lambda b:b['id']):
        value=batch['result']
        for kind,field in [('mistake','mistakes'),('extension','extensions')]:
            result.extend({'key':batch['id']+':'+row['key'],'kind':kind,'body':deepcopy(row)}for row in value[field])
    return result


def existing_catalog(tree):
    return [{'key':f'E{i}','kind':kind,'record':deepcopy(row)}for i,(kind,row)in enumerate(
        [(kind,row)for kind in ['mistake','extension']for row in tree.get(COLLECTIONS[kind][0],[])],1)]


def identity_schema(keys,targets,kinds=None):
    keep=obj({'action':{'enum':['keep']},'reason':text(200)})
    rows={}
    for key in keys:
        allowed=[t for t in targets if t!=key and (not kinds or kinds[t]==kinds[key])]
        match=obj({'action':{'enum':['match']},'target':{'enum':allowed},'same_content':{'const':True},
                   'same_scope':{'const':True},'same_discrimination':{'const':True},'reason':text(200)})
        rows[key]={'anyOf':[keep,match]} if allowed else keep
    return obj({'decisions':obj(rows)})


def identity_prompt(drafts,existing):
    return render('只核对教学对象身份，不改知识或删除检查标准。为每个candidate key给keep或match。'
        '相同易错对象必须错误假设、适用范围和区分方式一致；相同错答但可能原因不同不能合并。'
        '相同拓展须学习内容、前置范围和完成依据一致；不能仅按标题相似合并，不能跨kind合并。'
        '一个对象关联多个知识时保留一个对象并汇集关联。优先复用已有E对象，不改已有正文或合并多个已有身份。'
        '无法确认等价就keep。match必须给target、same_content/same_scope/same_discrimination均true、reason。'
        'keep只含action与reason。输出{"decisions":{"候选key":{"action":"keep","reason":"依据"}}}。',
        {'stage':'candidate_teaching_identity','contract':CONTRACT,'candidates':drafts,'existing':existing})


def resolve_identities(value,drafts,existing):
    by_key={r['key']:r for r in [*drafts,*existing]};keys=[r['key']for r in drafts]
    if list(Draft202012Validator(identity_schema(keys,list(by_key),{k:r['kind']for k,r in by_key.items()})).iter_errors(value)):
        raise ValueError('教学对象身份核对缺失、越界或缺少等价依据')
    parents={k:k for k in by_key}
    def root(k):
        while parents[k]!=k:parents[k]=parents[parents[k]];k=parents[k]
        return k
    for key,row in value['decisions'].items():
        if row['action']=='match':
            target=row['target']
            if key==target or by_key[key]['kind']!=by_key[target]['kind']:raise ValueError('教学身份不能指向自身或混合对象类型')
            parents[root(key)]=root(target)
    groups={}
    for key in keys:groups.setdefault(root(key),[]).append(key)
    result={}
    for canonical,members in groups.items():
        old=[r['key']for r in existing if root(r['key'])==canonical]
        if len(old)>1:raise ValueError('不能自动合并多个已有教学对象身份')
        representative=old[0] if old else sorted(members)[0]
        for key in members:result[key]=representative
    return result


def _revision(record,prefix):
    return stable_hash({k:v for k,v in record.items()if k not in {'revision_id','knowledge_ids','knowledge_revision_refs',
        'primary_knowledge_id','related_knowledge_ids','section_refs','source_refs','name','review_status','status'}},prefix=prefix)


def assemble(tree,batches,identities,existing,course_id,lesson_id,origin_id):
    result=deepcopy(tree);points={p['key']:p for p in tree['knowledge_points']};drafts=drafts_for(batches)
    by_draft={r['key']:r for r in drafts};old={r['key']:r for r in existing};objects={};resolved={}
    for draft in drafts:
        target=identities[draft['key']];kind=draft['kind'];field,id_field=COLLECTIONS[kind]
        if target not in objects:
            if target in old:
                record=deepcopy(old[target]['record'])
                record.setdefault('knowledge_ids',list(dict.fromkeys(k for k in [record.get('primary_knowledge_id'),*record.get('related_knowledge_ids',[])]if k)))
            else:
                source=by_draft[target]['body'];identifier=stable_hash({'course':course_id,'origin':origin_id,'key':target,'kind':kind},prefix='kta_')
                record={id_field:identifier,'course_id':course_id,'name':source['name'],'contract':CONTRACT,
                    'review_status':'draft','status':'candidate','learner_evidence':False,'section_refs':[lesson_id],
                    'knowledge_ids':[],'knowledge_revision_refs':{},'source_refs':[],'readiness':'ready'}
                if kind=='mistake':
                    record.update({k:deepcopy(source[k])for k in ('observable_error_pattern','hypothesis','alternative_explanations','scope','discrimination','repair_strategy','retest')})
                    record.update(skill_ids=[],primary_knowledge_id='',related_knowledge_ids=[])
                else:
                    record.update({k:deepcopy(source[k])for k in ('kind','goal','explanation','prerequisite_notes','task','success_criteria')})
                    record.update(prerequisite_knowledge_refs={points[k]['knowledge_id']:points[k]['revision_id']for k in source['prerequisite_keys']},
                        scope_role='extension',counts_toward_required_mastery=False,resource_refs=[],resource_status='not_provided')
                record['revision_id']=_revision(record,'ktar_')
            objects[target]=(kind,record)
        record=objects[target][1]
        for key in draft['body']['knowledge_keys']:
            point=points[key];kid=point['knowledge_id']
            if kid not in record.setdefault('knowledge_ids',[]):record['knowledge_ids'].append(kid)
            record.setdefault('knowledge_revision_refs',{})[kid]=point['revision_id']
        resolved[draft['key']]=record[id_field]
    criteria=[];point_notes={}
    for batch in batches:
        value=batch['result']
        for key,entry in value['points'].items():
            point=points[key];kid=point['knowledge_id']
            point_notes[kid]={'knowledge_revision':point['revision_id'],**{k:entry[k]for k in ('status','note','no_mistakes','no_extensions')}}
            for index,source in enumerate(entry['criteria'],1):
                cid=stable_hash({'course':course_id,'origin':origin_id,'batch':batch['id'],'point':key,'index':index},prefix='ktc_')
                checks=[{'checkpoint_id':stable_hash({'criterion':cid,'index':i},prefix='kti_'),**deepcopy(c),'max_score':1}
                        for i,c in enumerate(source['checkpoints'],1)]
                row={'criterion_id':cid,'course_id':course_id,'contract':CONTRACT,
                    **{k:deepcopy(source[k])for k in ('name','dimension','observable_performance','verification_method','controlled_conditions')},
                    'knowledge_ids':[kid],'knowledge_revision_refs':{kid:point['revision_id']},'section_refs':[lesson_id],
                    'source_refs':deepcopy(point.get('source_refs',[])),'skill_ids':[],
                    'misconception_ids':[resolved[batch['id']+':'+m]for m in source['mistake_keys']],
                    'checkpoints':checks,'scoring':{'rule':'all_checkpoints','max_score':len(checks),'pass_score':len(checks),'unknown_score':None},
                    'evidence_policy':deepcopy(POLICY),'required_independence':'independent','required_transfer':'transfer' if source['dimension']=='transfer' else 'variation',
                    'required_evidence_types':['graded_response'],'readiness':'ready' if entry['status']=='ready' else 'needs_core_review',
                    'review_status':'draft','status':'candidate','learner_evidence':False}
                row['revision_id']=_revision(row,'ktcr_');criteria.append(row)
    bindings=[]
    for target,(kind,record)in objects.items():
        if target not in old and any(point_notes.get(k,{}).get('status')=='needs_core_review'for k in record['knowledge_ids']):
            record['readiness']='needs_core_review';record['revision_id']=_revision(record,'ktar_')
    for kind,rows in [('criterion',criteria),*[(kind,[record])for kind,record in objects.values()]]:
        collection,id_field=COLLECTIONS[kind]
        for row in rows:
            row['section_refs']=list(dict.fromkeys([*row.get('section_refs',[]),lesson_id]))
            if kind=='mistake':
                row['primary_knowledge_id']=row.get('primary_knowledge_id')or row['knowledge_ids'][0]
                row['related_knowledge_ids']=[k for k in row['knowledge_ids']if k!=row['primary_knowledge_id']]
            for kid in row['knowledge_ids']:
                point=next((p for p in points.values()if p['knowledge_id']==kid),None)
                if point is None:continue
                binding={'binding_id':stable_hash({'course':course_id,'kind':kind,'object':row[id_field],'knowledge':kid,'lesson':lesson_id},prefix='ktb_'),
                    'object_type':kind,'object_id':row[id_field],'object_revision':row['revision_id'],'knowledge_id':kid,
                    'knowledge_revision':point['revision_id'],'scope_lesson_id':lesson_id,'role':'direct','status':'candidate','review_status':'draft'}
                binding['revision_id']=stable_hash(binding,prefix='ktbr_');bindings.append(binding)
            current={r[id_field]:r for r in result.get(collection,[])};current[row[id_field]]=row
            result[collection]=list(current.values())
    current={b['binding_id']:b for b in result.get('teaching_bindings',[])};current.update({b['binding_id']:b for b in bindings})
    result['teaching_bindings']=list(current.values())
    result.setdefault('teaching_coverage',{}).update(point_notes)
    result['teaching_structure_summary']={'contract':CONTRACT,'scope_lesson_id':lesson_id,'knowledge_count':len(point_notes),
        'criteria_covered_count':len({k for c in criteria for k in c['knowledge_ids']}),'ready_count':sum(v['status']=='ready'for v in point_notes.values()),
        'needs_review_count':sum(v['status']!='ready'for v in point_notes.values()),'criterion_count':len(criteria),
        'misconception_count':sum(k=='mistake'for k,r in objects.values()),'extension_count':sum(k=='extension'for k,r in objects.values()),
        'binding_count':len(bindings),'learner_evidence':False}
    return result


def merge_fields(existing,candidate,points):
    """Retain unrelated objects; stale links never acquire new revisions silently."""
    result={};by_id={p['knowledge_id']:p for p in points}
    for collection,id_field in [*COLLECTIONS.values(),('teaching_bindings','binding_id')]:
        rows={r[id_field]:deepcopy(r)for r in existing.get(collection,[])if r.get(id_field)}
        for source in candidate.get(collection,[]):
            if not source.get(id_field):continue
            row=deepcopy(source);previous=rows.get(row[id_field])
            if previous and collection!='teaching_bindings' and previous.get('revision_id')==row.get('revision_id'):
                for field in ('knowledge_ids','section_refs','source_refs'):
                    row[field]=list(dict.fromkeys([*previous.get(field,[]),*row.get(field,[])]))
                row['knowledge_revision_refs']={**previous.get('knowledge_revision_refs',{}),**row.get('knowledge_revision_refs',{})}
                if collection=='misconceptions':
                    row['primary_knowledge_id']=previous.get('primary_knowledge_id')or row.get('primary_knowledge_id')
                    row['related_knowledge_ids']=[k for k in row['knowledge_ids']if k!=row['primary_knowledge_id']]
            rows[row[id_field]]=row
        result[collection]=list(rows.values())
    for binding in result['teaching_bindings']:
        if by_id.get(binding['knowledge_id'],{}).get('revision_id')!=binding['knowledge_revision']:binding['status']='needs_review'
    result['teaching_coverage']={**deepcopy(existing.get('teaching_coverage',{})),**deepcopy(candidate.get('teaching_coverage',{}))}
    return result


def filter_fields(tree,points,*,published=False):
    ids={p['knowledge_id']:p['revision_id']for p in points};result={}
    for collection,id_field in COLLECTIONS.values():
        rows=[]
        for row in tree.get(collection,[]):
            refs=row.get('knowledge_revision_refs')or{}
            keys=set(row.get('knowledge_ids')or [row.get('primary_knowledge_id'),*row.get('related_knowledge_ids',[])])-{None,''}
            if not keys.intersection(ids) or published and not keys<=set(ids):continue
            if refs and any(k in ids and ids[k]!=v for k,v in refs.items()):continue
            if published and any(ids.get(k)!=v for k,v in row.get('prerequisite_knowledge_refs',{}).items()):continue
            if published and row.get('contract')==CONTRACT and (row.get('review_status')!='owner_accepted' or row.get('readiness')!='ready'):continue
            projected=deepcopy(row)
            if not published:
                projected['knowledge_ids']=[k for k in row.get('knowledge_ids',[])if k in ids]
                projected['knowledge_revision_refs']={k:v for k,v in refs.items()if k in ids}
                if collection=='misconceptions' and projected['knowledge_ids']:
                    projected['primary_knowledge_id']=row.get('primary_knowledge_id')if row.get('primary_knowledge_id')in ids else projected['knowledge_ids'][0]
                    projected['related_knowledge_ids']=[k for k in projected['knowledge_ids']if k!=projected['primary_knowledge_id']]
            rows.append(projected)
        result[collection]=rows
    object_ids={r[id_field]for collection,id_field in COLLECTIONS.values()for r in result[collection]}
    result['teaching_bindings']=[deepcopy(b)for b in tree.get('teaching_bindings',[])if b.get('object_id')in object_ids
        and ids.get(b.get('knowledge_id'))==b.get('knowledge_revision') and b.get('status')!='needs_review']
    result['teaching_coverage']={k:deepcopy(v)for k,v in tree.get('teaching_coverage',{}).items()if ids.get(k)==v.get('knowledge_revision') and (not published or v['status']=='ready')}
    return result


def accept(tree):
    for collection,_ in COLLECTIONS.values():
        for row in tree.get(collection,[]):
            if row.get('contract')==CONTRACT and row.get('readiness')=='ready':row.update(status='active',review_status='owner_accepted')
    for row in tree.get('teaching_bindings',[]):
        if row.get('status')=='candidate':row.update(status='active',review_status='owner_accepted')
