"""Criterion planning and bindings inside the existing question-bank pipeline."""
from copy import deepcopy
from course_versioning import stable_hash
from knowledge_criterion_binding import BINDING, criterion_signature, content_signature, valid_binding

CONTRACT='knowledge_criterion_generation_v1'


class PreparationRequired(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def generation_readiness(course):
    base=course.get('course_knowledge_base')or{}
    if not base.get('revision_id') or not (base.get('status')=='accepted' or base.get('lifecycle_status')=='active'):
        return {'ready':False,'code':'knowledge_baseline_required','reviewed_criterion_count':0}
    from knowledge_check_flow import criteria
    catalog=criteria(course)
    return {'ready':bool(catalog),'code':'' if catalog else 'reviewed_criteria_required',
            'knowledge_baseline_revision':base['revision_id'],'reviewed_criterion_count':len(catalog)}


def request_plan(course, *, node_ids, request_id, knowledge_ids=None, criterion_revision_refs=None, prior_plan=None):
    """Resolve every new authoring entry against the same reviewed catalog."""
    if prior_plan:
        try:
            validate_plan(course, prior_plan)
        except (ValueError, KeyError) as exc:
            raise PreparationRequired('question_plan_changed', '知识或检查标准已变化，原任务结果保留，请重新规划。') from exc
        if not set(node_ids).issubset(prior_plan['node_ids']):
            raise PreparationRequired('question_plan_scope_changed', '重试范围不属于原出题计划。')
        return deepcopy(prior_plan)
    base = course.get('course_knowledge_base') or {}
    if not base.get('revision_id') or not (base.get('status') == 'accepted' or base.get('lifecycle_status') == 'active'):
        raise PreparationRequired('knowledge_baseline_required', '知识树尚未确认，暂不能生成可用于检查的题目；已有题目保留。')
    from knowledge_check_flow import criteria
    selected = set(knowledge_ids or [])
    points = {p['knowledge_id']:p for p in base.get('knowledge_points', [])}
    eligible = [c for c in criteria(course) if (not selected or c['knowledge_ids'][0] in selected)
                and any(n in node_ids for n in points[c['knowledge_ids'][0]].get('section_refs', []))]
    refs = dict(criterion_revision_refs or {c['criterion_id']:c['revision_id'] for c in eligible})
    if not refs:
        raise PreparationRequired('reviewed_criteria_required', '所选范围尚无已审阅、可用的检查标准，请先准备检查标准；已有题目保留。')
    chosen = [c for c in eligible if c['criterion_id'] in refs]
    try:
        result = plan(course, refs, sorted(selected or {c['knowledge_ids'][0] for c in chosen}), node_ids, request_id)
    except (ValueError, KeyError) as exc:
        raise PreparationRequired('reviewed_criteria_required', str(exc)) from exc
    result.update(entrypoint='standard' if criterion_revision_refs else 'lecture', default_count=3)
    return result


def authoring_directive():
    return ('有criterion_target时，目标是其criterion的完整检查标准。逐项让学生作答产生checkpoints要求的证据；'
        'controlled_conditions必须落实为题面已知条件或明确的作答环境，以排除其他能力干扰，不能变成额外的学生计算任务。'
        '给定数据和定义不等于泄漏目标结论；不得给出目标的答案或推理规则。'
        '允许同一目标下的关联小问，不强制改成选择题、代码或单个数值；各判据必须能独立评分。')


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
    if any(frozen.get(key)!=value for key,value in current.items()):raise ValueError('课程、知识或检查标准已变化，本次出题结果保留待核对')


FORMATS = {
    'short_answer': ('rich_text', 'short_answer', 'expert_rubric_validator', 'evidence_argument'),
    'single_choice': ('choice', 'selected_response', 'exact_validator', 'concept_classification'),
    'numeric_response': ('numeric_unit', 'numeric_response', 'numeric_unit_validator', 'numeric_application'),
}


def criterion_slots(course, objective, recipe):
    """Build exact slots for adopted generic knowledge without changing its granularity."""
    frozen = course.get('_criterion_generation_plan')
    if not frozen:
        return None
    base = course['course_knowledge_base']
    points = {p['knowledge_id']:p for p in base.get('knowledge_points', [])}
    source_rows = base.get('sources') or []
    if isinstance(source_rows, dict):
        source_rows = [s for t in source_rows.get('topics', []) for s in t.get('sources', [])]
    source_rows = [*source_rows, *(course.get('evidence_catalog') or [])]
    sources = {str(s.get('source_id') or s.get('id') or s.get('evidence_id')):s for s in source_rows if isinstance(s,dict)}
    slots = []
    for target in frozen['targets']:
        if target['node_id'] != objective.get('node_id'):
            continue
        kid = target['knowledge_id']; point = points[kid]; criterion = target['criterion']
        form = criterion.get('assessment_format') or 'short_answer'
        if form not in FORMATS:
            raise PreparationRequired('criterion_format_unsupported', '该检查标准的作答形式尚未接通。')
        if form!='short_answer' and len(criterion['checkpoints'])!=1:
            raise PreparationRequired('criterion_format_mismatch', '数值或单选结果只能直接检查一条判据；多项判据需要可分别作答的形式。')
        mode, question_type, validator, archetype = FORMATS[form]
        evidence = [{'reference_id':ref,'source_type':'course_material',
                     'reference_excerpt':str(sources[ref].get('text') or sources[ref].get('source_text') or sources[ref].get('excerpt') or ''),
                     'reuse_policy':'course_grounding'} for ref in point.get('source_refs', []) if ref in sources]
        if not evidence:
            evidence = [{'reference_id':kid,'source_type':'course_knowledge','reference_excerpt':point['statement'],'reuse_policy':'course_grounding'}]
        key = stable_hash({'batch':frozen['batch_id'],'criterion':criterion['criterion_id'],'revision':criterion['revision_id']},prefix='kcslot_')
        performance = criterion['observable_performance']
        target_objective = {**deepcopy(objective),'objective':performance,'knowledge':[point['statement']],
            'skills':[performance],'misconceptions':[],'observable_evidence':[p['pass_condition']for p in criterion['checkpoints']],
            'source_refs':[e['reference_id']for e in evidence],'source_excerpt':'\n'.join(e['reference_excerpt']for e in evidence),
            'source_sufficiency':'sufficient','generation_status':'ready'}
        slots.append({**deepcopy(recipe),'slot_id':key,'generation_key':key,'assessment_binding_schema':'atomic_assessment_v1',
            'assessment_purpose':'criterion_check','primary_knowledge_ids':[kid],
            'prerequisite_knowledge_ids':deepcopy(point.get('prerequisite_ids')or []),
            'knowledge_revision_refs':{kid:point['revision_id']},'knowledge_baseline_revision':base['revision_id'],
            'target_objective':target_objective,'knowledge':[point['statement']],'skills':[performance],'misconceptions':[],
            'source_refs':target_objective['source_refs'],'conditions':deepcopy(point.get('conditions')or []),
            'target_content_evidence':evidence,'input_mode':mode,'question_type':question_type,'question_form':form,
            'validation_mode':validator,'archetype_id':archetype,'practice_level':'mastery_check',
            'observable_evidence':target_objective['observable_evidence'],'criterion_target':deepcopy(target)})
    if frozen.get('replacement_slots'):
        replacements=[]
        for original in frozen['replacement_slots']:
            cid=original['criterion_target']['criterion']['criterion_id']
            target=next((s for s in slots if s['criterion_target']['criterion']['criterion_id']==cid),None)
            if target:
                replacements.append({**deepcopy(original),**deepcopy(target),
                    'slot_id':original['slot_id'],'generation_key':original['generation_key']})
        return replacements
    return slots


def configure(course,refs,knowledge_ids,node_ids,request_id):
    if not refs:return course
    value=deepcopy(course);value['_criterion_generation_plan']=plan(course,refs,knowledge_ids,node_ids,request_id)
    return value


def decorate_slots(slots,course):
    frozen=course.get('_criterion_generation_plan')
    if not frozen:return slots
    output=[]
    for slot in slots:
        if not any(slot.get('primary_knowledge_ids')==[t['knowledge_id']]for t in frozen['targets']):
            output.append(deepcopy(slot));continue
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


def seal_binding(q,target,report):
    verified=enforce_alignment(report,{'criterion_target':target})
    c=target['criterion']
    return {'contract':BINDING,'criterion_id':c['criterion_id'],'criterion_revision':c['revision_id'],
        'knowledge_revision_refs':deepcopy(c['knowledge_revision_refs']),'checkpoint_ids':[p['checkpoint_id']for p in c['checkpoints']],
        'criterion_signature':target['criterion_signature'],'content_signature':content_signature(q),
        'reviewed':verified.get('passed')is True and verified.get('solution_consistent')is True,
        'alignment':deepcopy(verified.get('criterion_alignment')or{})}


