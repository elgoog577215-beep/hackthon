"""Criterion planning and bindings inside the existing question-bank pipeline."""
from copy import deepcopy
from course_versioning import stable_hash

CONTRACT='knowledge_criterion_generation_v1'
BINDING='knowledge_criterion_binding_v1'


def criterion_signature(c):
    return stable_hash({k:deepcopy(c.get(k))for k in ('criterion_id','revision_id','knowledge_ids','knowledge_revision_refs',
        'dimension','observable_performance','verification_method','controlled_conditions','checkpoints','scoring','evidence_policy')},prefix='kcgs_')


def plan(course,refs,knowledge_ids,node_ids,request_id):
    from knowledge_check_flow import criteria
    if not refs or not request_id or len(refs)>50:raise ValueError('缺少检查标准、请求身份或超出范围')
    catalog={c['criterion_id']:c for c in criteria(course)}
    base=course.get('course_knowledge_base')or{};points={p['knowledge_id']:p for p in base.get('knowledge_points',[])}
    nodes={n['node_id']for n in course.get('nodes',[])if int(n.get('node_level')or 1)==2}
    targets=[]
    for cid,revision in sorted(refs.items()):
        c=catalog.get(cid)
        if not c or c['revision_id']!=revision:raise ValueError('检查标准未审阅、已变化或不可用于出题')
        kid=c['knowledge_ids'][0];p=points[kid]
        owner=next((n for n in p.get('section_refs',[])if n in nodes),None)
        if not owner or owner not in node_ids:raise ValueError('检查标准不属于所选讲次')
        snapshot={k:deepcopy(v)for k,v in c.items()if k not in {'assessment_bindings','source_refs'}}
        targets.append({'criterion':snapshot,'criterion_signature':criterion_signature(c),'knowledge_id':kid,
            'knowledge_revision':p['revision_id'],'node_id':owner})
    if {t['knowledge_id']for t in targets}!=set(knowledge_ids) or {t['node_id']for t in targets}!=set(node_ids):
        raise ValueError('检查标准与知识、讲次范围不一致')
    return {'contract':CONTRACT,'course_id':course['course_id'],'owner_id':course.get('owner_id'),
        'knowledge_baseline_revision':base.get('revision_id'),'criterion_revision_refs':deepcopy(refs),
        'knowledge_ids':sorted(knowledge_ids),'node_ids':sorted(node_ids),'request_id':request_id,
        'batch_id':stable_hash({'course':course['course_id'],'request':request_id,'criteria':refs},prefix='kcgb_'),'targets':targets}


def validate_plan(course,frozen):
    current=plan(course,frozen['criterion_revision_refs'],frozen['knowledge_ids'],frozen['node_ids'],frozen['request_id'])
    if current!=frozen:raise ValueError('课程、知识或检查标准已变化，本次出题结果保留待核对')


def configure(course,refs,knowledge_ids,node_ids,request_id):
    if not refs:return course
    value=deepcopy(course);value['_criterion_generation_plan']=plan(course,refs,knowledge_ids,node_ids,request_id)
    return value


def decorate_slots(slots,course):
    frozen=course.get('_criterion_generation_plan')
    if not frozen:return slots
    output=[]
    for slot in slots:
        for target in frozen['targets']:
            if slot.get('primary_knowledge_ids')!=[target['knowledge_id']]:continue
            c=target['criterion'];key=stable_hash({'batch':frozen['batch_id'],'criterion':c['criterion_id'],'revision':c['revision_id']},prefix='kcslot_')
            objective={**deepcopy(slot.get('target_objective')or{}),'objective':c['observable_performance'],
                'skills':[c['observable_performance']],'observable_evidence':[p['pass_condition']for p in c['checkpoints']]}
            output.append({**deepcopy(slot),'slot_id':key,'generation_key':key,'archetype_id':'evidence_argument',
                'input_mode':'rich_text','question_type':'short_answer','question_form':'short_answer','practice_level':'mastery_check',
                'validation_mode':'expert_rubric_validator','target_objective':objective,'skills':[c['observable_performance']],
                'observable_evidence':objective['observable_evidence'],'criterion_target':deepcopy(target)})
    return output


def review_schema(slot):
    target=slot.get('criterion_target')
    return {'criterion_alignment':{'checkpoints':{p['checkpoint_id']:True for p in target['criterion']['checkpoints']},
        'conditions_controlled':True,'reason':'分别说明题面如何检查每条判据，并控制已声明的其他知识干扰'}}if target else{}


def enforce_alignment(report,slot):
    if not slot.get('criterion_target'):return report
    r=deepcopy(report);a=r.get('criterion_alignment')or{}
    ids={p['checkpoint_id']for p in slot['criterion_target']['criterion']['checkpoints']}
    if (set(a.get('checkpoints',{}))!=ids or any(v is not True for v in a.get('checkpoints',{}).values())
        or a.get('conditions_controlled')is not True or not str(a.get('reason')or'').strip()
        or r.get('confidence',0)<.72 or r.get('reviewer_triggered')is not True):
        r['passed']=False;r.setdefault('issues',[]).append({'code':'CRITERION_ALIGNMENT_INCOMPLETE','severity':'critical',
            'message':'题目尚未覆盖全部检查判据，或未控制声明的干扰条件'})
    return r


def content_signature(q):
    return stable_hash({'prompt':q.get('prompt'),'spec':q.get('question_spec'),'solution':q.get('solution_revision_id')},prefix='kcqcontent_')


def seal_binding(q,target,report):
    verified=enforce_alignment(report,{'criterion_target':target})
    c=target['criterion']
    return {'contract':BINDING,'criterion_id':c['criterion_id'],'criterion_revision':c['revision_id'],
        'knowledge_revision_refs':deepcopy(c['knowledge_revision_refs']),'checkpoint_ids':[p['checkpoint_id']for p in c['checkpoints']],
        'criterion_signature':target['criterion_signature'],'content_signature':content_signature(q),
        'reviewed':verified.get('passed')is True and verified.get('solution_consistent')is True,
        'alignment':deepcopy(verified.get('criterion_alignment')or{})}


def valid_binding(q,c):
    b=q.get('criterion_binding')or{}
    return bool(b.get('contract')==BINDING and b.get('reviewed')is True
        and b.get('criterion_id')==c['criterion_id'] and b.get('criterion_revision')==c['revision_id']
        and b.get('criterion_signature')==criterion_signature(c) and b.get('knowledge_revision_refs')==c['knowledge_revision_refs']
        and b.get('checkpoint_ids')==[p['checkpoint_id']for p in c['checkpoints']]
        and b.get('content_signature')==content_signature(q))
