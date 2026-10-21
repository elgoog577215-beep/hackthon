from copy import deepcopy

import pytest


def unit(statement='常数函数的导数为零', focus='线性法则'):
    return {'statement': statement, 'branch': '求导法则', 'knowledge_type': 'rule',
            'profile_focus': focus, 'check_intent': '在新的常数函数上独立求导'}


def point(statement='常数函数的导数为零'):
    return {'statement': statement, 'knowledge_type': 'rule', 'conditions': [],
            'symbol_definitions': [], 'teaching_context': [], 'examples': []}


def test_coverage_units_are_separate_from_material_wording_and_all_get_a_disposition():
    from knowledge_coverage import parse_plan, parse_unit_points, coverage_report
    units = parse_plan({'units':[unit(),unit('常数倍求导时系数保持不变')]},['线性法则'])
    rows = parse_unit_points({'points':{'U1':[point()],'U2':[point('常数因子可提出导数运算')]}},units,['S1'])
    assert rows[0]['coverage_unit_ids']==['U1'] and rows[1]['coverage_unit_ids']==['U2']
    assert coverage_report(units,rows)['missing_unit_ids']==[]
    assert coverage_report(units,rows[:1])['missing_unit_ids']==['U2']
    with pytest.raises(ValueError):
        parse_unit_points({'points':{'U1':[point()]}},units,['S1'])


def test_bound_checks_are_accounted_without_becoming_knowledge_leaves():
    from knowledge_coverage import coverage_report
    record={'disposition':'check','coverage_unit_ids':['U2'],'reason':'只检查规则应用','knowledge_id':'k'}
    points=[{'knowledge_id':'k','coverage_unit_ids':['U1']}]
    report=coverage_report([{'key':'U1'},{'key':'U2'}],points,[record])
    assert report['covered_unit_count']==1 and report['accounted_unit_count']==2
    assert report['unit_dispositions']['U2']['disposition']=='check'
    record['knowledge_id']='missing'
    with pytest.raises(ValueError):coverage_report([{'key':'U1'},{'key':'U2'}],points,[record])


def test_distinct_learning_units_cannot_be_lost_by_equivalence_flags():
    from knowledge_registry_identity import apply_decisions
    rows=[{**point(text),'key':key,'input_material_keys':['S1'],'coverage_unit_ids':[uid]}
          for text,key,uid in [('常数导数为0','P1','U1'),('常数倍求导保持系数','P2','U2')]]
    with pytest.raises(ValueError,match='命题、范围'):
        apply_decisions(rows,[],{'P1':{'action':'keep','reason':'保留'},
            'P2':{'action':'match','target':'P1','same_claim':False,'same_scope':True,'same_symbols':True,'reason':'都是线性但不同知识'}})
    kept=apply_decisions(rows,[],{key:{'action':'keep','reason':'独立'} for key in ['P1','P2']})
    assert [p['coverage_unit_ids'] for p in kept['points']]==[['U1'],['U2']]


def test_upstream_grouping_sampling_and_schema_are_callable():
    from third_party.learningmap.kc import group_questions_by_route, sample_questions, KCSkill
    grouped=group_questions_by_route({'q1':{'kc_routes':['kp1','kp2'],'type':'choice'},
                                      'q2':{'kc_routes':['kp1'],'type':'calculation'}})
    assert len(grouped['kp1'])==2 and len(grouped['kp2'])==1
    assert sample_questions(grouped['kp1'],cap=12)==grouped['kp1']
    assert set(KCSkill.model_fields)=={'description','assessment_focus','assessment_format','common_mistakes','difficulty_cues'}


def test_sampling_reserves_each_check_angle_before_proportional_sampling():
    from knowledge_kc_profiles import select_samples
    rows=[{'id':str(i),'type':'calculation','check_angle':'routine'} for i in range(99)]
    rows.append({'id':'99','type':'choice','check_angle':'boundary'})
    result=select_samples(rows,cap=12)
    assert len(result)==12 and any(p['id']=='99' for p in result)
    assert len({p['id'] for p in result})==12


def test_profile_is_revision_bound_and_does_not_create_learner_facts():
    from knowledge_kc_profiles import compile_profiles, profile_context
    from third_party.learningmap.kc import KCSkill
    p={**point(),'key':'K1','knowledge_id':'kp1','revision_id':'rev1'}
    before=deepcopy(p)
    skill={key:'教学说明' for key in KCSkill.model_fields}
    profiles=compile_profiles({'profiles':{'K1':skill}},[p],{})
    profile=profiles['kp1']
    assert profile['basis']=='knowledge_draft' and profile['sampled_question_refs']==[]
    assert profile['review_status']=='draft' and not profile['learner_evidence']
    p['kc_skill_profile']=profile
    assert '教学说明' in profile_context(p)
    p['revision_id']='rev2'
    assert profile_context(p)==''
    assert before['statement']==p['statement']
    with pytest.raises(ValueError):
        compile_profiles({'profiles':{'UNKNOWN':skill}},[p],{})


def test_reused_registered_point_does_not_inherit_an_old_plan_unit():
    from knowledge_registry_identity import apply_decisions
    old={**point(),'key':'E1','knowledge_id':'kid','revision_id':'old','name':'常数的导数为零',
         'coverage_unit_ids':['U99'],'profile_focus':'','check_intents':['旧检查']}
    new={**point(),'key':'P1','input_material_keys':['S1'],'coverage_unit_ids':['U1'],'profile_focus':'线性法则','check_intents':['新检查']}
    result=apply_decisions([new],[old],{'P1':{'action':'reuse','target':'E1','same_claim':True,'same_scope':True,'same_symbols':True,'reason':'同一知识'}})
    assert result['points'][0]['coverage_unit_ids']==['U1']
    assert result['points'][0]['profile_focus']=='线性法则'
    assert old['coverage_unit_ids']==['U99']


def test_question_samples_require_approved_current_complete_bindings():
    from knowledge_kc_profiles import eligible_questions
    tree={'revision_id':'base','knowledge_points':[{'knowledge_id':'kp1','revision_id':'r1'}]}
    item={'revision_id':'q1','review_status':'approved','prompt':'求常数的导数','knowledge_binding':{'status':'bound','knowledge_ids':['kp1'],'knowledge_revision_refs':{'kp1':'r1'},'knowledge_baseline_revision':'base'}}
    assert eligible_questions(tree,{'items':[item]})['kp1'][0]['id']=='q1'
    for change in [{'review_status':'needs_review'},{'lifecycle_status':'retired'},
                   {'knowledge_binding':{**item['knowledge_binding'],'knowledge_revision_refs':{'kp1':'old'}}},
                   {'knowledge_binding':{**item['knowledge_binding'],'knowledge_ids':['kp1','missing']}}]:
        assert not eligible_questions(tree,{'items':[{**item,**change}]})


def test_handout_consumes_only_matching_profile_revision():
    from generic_knowledge import handout_prompt
    from knowledge_kc_profiles import compile_profiles
    from third_party.learningmap.kc import KCSkill
    p={**point(),'key':'K1','knowledge_id':'kp1','revision_id':'r1'}
    p['kc_skill_profile']=compile_profiles({'profiles':{'K1':{key:'教学草稿内容' for key in KCSkill.model_fields}}},[p],{})['kp1']
    lesson={'knowledge_ids':['kp1'],'title':'常数'}
    assert '教学草稿内容' in handout_prompt({'knowledge_points':[p]},lesson)
    p['revision_id']='r2'
    assert '教学草稿内容' not in handout_prompt({'knowledge_points':[p]},lesson)










def test_true_synonyms_from_different_units_merge_without_losing_coverage():
    from knowledge_registry_identity import apply_decisions
    rows=[{**point(),'key':key,'input_material_keys':['S1'],'coverage_unit_ids':[uid]} for key,uid in [('P1','U1'),('P2','U2')]]
    result=apply_decisions(rows,[],{'P1':{'action':'keep','reason':'完整知识'},'P2':{'action':'match','target':'P1','same_claim':True,'same_scope':True,'same_symbols':True,'reason':'同一常数求导规则'}})
    assert len(result['points'])==1 and result['points'][0]['coverage_unit_ids']==['U1','U2']
