"""Version-bound teaching profiles using vendored LearningMAP components."""
from third_party.learningmap.kc import KCSkill, group_questions_by_route, sample_questions
from third_party.learningmap.prompts.loader import render_kc_skill_block, render_prompt
from knowledge_registry_contract import render

CONTRACT='knowledge_kc_profile_v1'
UPSTREAM='ai-for-edu/LearningMAP@bb17f6a7e8c105248d80126b2bf07ff07209b83f'


def select_samples(rows, cap=12):
    """Reserve each available checking angle, then use upstream proportional sampling."""
    selected={}
    for row in sorted(rows,key=lambda r:str(r['id'])):
        angle=row.get('check_angle') or row['type']
        if angle not in selected and len(selected)<cap:
            selected[angle]=row
    ids={r['id'] for r in selected.values()}
    remaining=[r for r in rows if r['id'] not in ids]
    extra=sample_questions(remaining,cap=cap-len(ids)) if len(ids)<cap else []
    return [*selected.values(),*extra]


def eligible_questions(tree, bundle):
    """Read only explicitly reviewed, current question bindings; never infer admission."""
    by_id={p['knowledge_id']:p for p in tree['knowledge_points']}
    rows={}
    for item in (bundle or {}).get('items',[]):
        binding=item.get('knowledge_binding') or ({'status':'bound','knowledge_ids':item.get('primary_knowledge_ids',[]),
            'knowledge_revision_refs':item.get('knowledge_revision_refs',{}),
            'knowledge_baseline_revision':item.get('knowledge_baseline_revision')}
            if item.get('assessment_binding_schema')=='atomic_assessment_v1' else {})
        # Conservative admission: an unreviewed binding is not a verified question sample.
        if item.get('review_status')!='approved' or item.get('lifecycle_status') in {'retired','rejected','needs_review'} or binding.get('status')!='bound':
            continue
        if binding.get('knowledge_baseline_revision')!=tree.get('revision_id'):
            continue
        refs=binding.get('knowledge_revision_refs') or {}
        ids=binding.get('knowledge_ids',[])
        if not ids or set(ids)!=set(refs) or any(kid not in by_id or refs[kid]!=by_id[kid]['revision_id'] for kid in ids) or not item.get('revision_id'):
            continue
        rows[item['revision_id']]={'type':str(item.get('question_type') or item.get('form') or 'unspecified'),
            'kc_routes':ids,'content':str(item.get('prompt') or ''),'answer':item.get('answer'),
            'analysis':item.get('explanation') or item.get('analysis') or '',
            'check_angle':str(item.get('check_angle') or item.get('question_type') or 'general')}
    return group_questions_by_route(rows)


def profile_prompt(points, groups):
    return render(
        '为冻结知识生成教学档案，不修改知识或条件。逐点按instructions填写五个字符串字段，'
        '不要输出诊断、掌握度或学生记录，不把候选失误说成高频或已发生事实。'
        '输出{"profiles":{"K1":{"description":"适用场景","assessment_focus":"考查重点",'
        '"assessment_format":"题型与问法","common_mistakes":"易错候选","difficulty_cues":"难度变化"}}}。',
        {'stage':'kc_profiles','contract':CONTRACT,'profiles':[
            {'key':p['key'],'instructions':render_prompt('kc_skill_from_bank_zh',point=p,
                samples=select_samples(groups.get(p['knowledge_id'],[])))} for p in points]})


def compile_profiles(value, points, groups):
    rows=value.get('profiles') if isinstance(value,dict) else None
    if not isinstance(rows,dict) or set(rows)!={p['key'] for p in points}:
        raise ValueError('教学档案须恰好对应冻结知识ID')
    result={}
    for p in points:
        row=rows[p['key']]
        if not isinstance(row,dict) or set(row)!=set(KCSkill.model_fields):
            raise ValueError('教学档案仅允许KCSkill五字段')
        skill=KCSkill.model_validate(row)
        if any(not value.strip() or len(value)>1800 for value in skill.model_dump().values()):
            raise ValueError('教学档案字段为空或过长')
        samples=select_samples(groups.get(p['knowledge_id'],[]))
        result[p['knowledge_id']]={'contract':CONTRACT,'upstream':UPSTREAM,
            'knowledge_id':p['knowledge_id'],'knowledge_revision':p['revision_id'],
            'skill':skill.model_dump(),'basis':'question_samples' if samples else 'knowledge_draft',
            'sampled_question_refs':[q['id'] for q in samples],
            'review_status':'draft','semantics_verified':False,'learner_evidence':False}
    return result


def profile_context(point):
    profile=point.get('kc_skill_profile') or {}
    if profile.get('knowledge_id')!=point.get('knowledge_id') or profile.get('knowledge_revision')!=point.get('revision_id'):
        return ''
    return ('以下是教学档案草稿，不是学生学情证据。\n'+render_kc_skill_block(profile.get('skill'))) if profile.get('skill') else ''
