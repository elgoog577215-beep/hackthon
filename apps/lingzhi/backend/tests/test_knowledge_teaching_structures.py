"""Shared teaching objects and measurable checks are not learner evidence."""
from copy import deepcopy
import json
import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_unified import seed,start,provider,model_reply,body


def teaching_reply(payload):
    keys=[p['key']for p in payload['focus']]
    return {'points':{key:{'status':'ready','note':'','criteria':[{
        'name':'独立说明操作位置','dimension':'understanding','observable_performance':'指出该操作发生的位置并说明理由',
        'verification_method':'给出一个操作前后的示意，说明新元素的位置。','controlled_conditions':['提供操作前的状态'],
        'checkpoints':[{'label':'位置判断','pass_condition':'新元素位于规则指定的位置'},
                       {'label':'理由说明','pass_condition':'理由与操作定义一致'}],
        'mistake_keys':['M1']}],'no_mistakes':'','no_extensions':''}for key in keys},
        'mistakes':[{'key':'M1','name':'把操作位置认反','observable_error_pattern':'把新元素放到另一端',
            'hypothesis':'可能混淆两个端点的含义','alternative_explanations':['可能只是读图方向失误'],
            'scope':'判断操作位置时','discrimination':'先标出两个端点，再说明新元素的位置',
            'repair_strategy':'对照操作前后示意，明确端点含义','retest':'换一个初始状态独立判断',
            'knowledge_keys':keys}],
        'extensions':[{'key':'X1','name':'操作在组合流程中的应用','kind':'application','knowledge_keys':keys,
            'goal':'解释连续操作产生的状态变化','explanation':'组合流程可以用逐次更新状态的方式分析。',
            'prerequisite_keys':keys,'prerequisite_notes':'','task':'比较两种不同操作顺序的最终状态',
            'success_criteria':['每一步符合对应操作规则','能够解释最终状态差异']} ]}


def identity_reply(payload):
    return {'decisions':{p['key']:{'action':'keep','reason':'没有确认等价对象'}for p in payload['candidates']}}


@pytest.mark.asyncio
async def test_structuring_reuses_core_profiles_and_relations_without_learner_writes(svc,monkeypatch):
    await seed(svc,monkeypatch);calls=[];provider(svc,calls)
    prior=start(svc,'old-complete',generation_mode='full_v1');await svc.run('c-pilot',prior['id'])
    original=svc.authoring.get_job('c-pilot',prior['id']);before=deepcopy(svc.repository.load_raw('c-pilot'))
    async def reply(payload):
        if payload['stage']=='candidate_teaching_structures':return teaching_reply(payload)
        if payload['stage']=='candidate_teaching_identity':return identity_reply(payload)
        raise AssertionError('completed work was repeated: '+payload['stage'])
    calls.clear();provider(svc,calls,reply)
    job=start(svc,'structured',generation_mode='full_v1',include_teaching_structures=True,base_job_id=prior['id'])
    await svc.run('c-pilot',job['id']);saved=svc.authoring.get_job('c-pilot',job['id'])
    assert saved['status']=='completed',saved.get('error')
    tree=saved['checkpoint']['candidate']
    assert body(tree)==body(original['checkpoint']['candidate'])
    assert len(tree['misconceptions'])==1 and len(tree['mastery_criteria'])==2 and len(tree['extensions'])==1
    assert len(tree['misconceptions'][0]['knowledge_ids'])==2
    assert all(c['scoring']['pass_score']==len(c['checkpoints'])==2 for c in tree['mastery_criteria'])
    assert all(c['evidence_policy']['min_independent_successes']==2 for c in tree['mastery_criteria'])
    assert all(x['scope_role']=='extension' and not x['counts_toward_required_mastery']for x in tree['extensions'])
    assert svc.repository.load_raw('c-pilot')==before
    calls.clear();again=start(svc,'structured-reuse',generation_mode='full_v1',include_teaching_structures=True)
    await svc.run('c-pilot',again['id']);reused=svc.authoring.get_job('c-pilot',again['id'])
    assert reused['status']=='completed',reused.get('error')
    assert not calls
    assert reused['checkpoint']['candidate']['misconceptions']==tree['misconceptions']


def test_quantified_checks_do_not_turn_no_data_hints_or_duplicate_attempts_into_mastery():
    from knowledge_check_measurement import summarize_check
    criterion={'criterion_id':'C','revision_id':'CR','knowledge_revision_refs':{'K':'KR'},'readiness':'ready',
        'review_status':'owner_accepted','checkpoints':[{'checkpoint_id':'A'},{'checkpoint_id':'B'}],
        'evidence_policy':{'min_independent_successes':2,'min_distinct_variants':2}}
    assert summarize_check(criterion,[],user_id='u',course_id='c')['latest_score'] is None
    def attempt(identity,variant,**changes):
        return {'attempt_id':identity,'user_id':'u','course_id':'c','status':'graded','assessment_evidence_key':variant,
            'task_revision_id':variant,'knowledge_revision_refs':{'K':'KR'},'criterion_revision_refs':{'C':'CR'},
            'result':{'criterion_results':{'C':{'A':True,'B':True}}},**changes}
    rows=[attempt('1','v1'),attempt('2','v1'),attempt('3','v2',support_level=1),attempt('4','v3',solution_revealed=True),
        attempt('5','v4',user_id='other')]
    result=summarize_check(criterion,rows,user_id='u',course_id='c')
    assert result['independent_successes']==1 and result['status']=='needs_more_evidence'
    rows.append(attempt('6','v2'))
    assert summarize_check(criterion,rows,user_id='u',course_id='c')['status']=='check_supported'
    criterion['revision_id']='new-revision'
    assert summarize_check(criterion,rows,user_id='u',course_id='c')['latest_score'] is None


def test_compiler_rejects_foreign_references_and_model_invented_scores():
    from knowledge_teaching_contract import compile_batch
    points=[{'key':'K1','knowledge_id':'kid','revision_id':'rev'}]
    response=teaching_reply({'focus':points})
    response['mistakes'][0]['knowledge_keys']=['unknown']
    with pytest.raises(ValueError):compile_batch(response,points,points,'batch')
    response=teaching_reply({'focus':points});response['points']['K1']['mastery']=100
    with pytest.raises(ValueError):compile_batch(response,points,points,'batch')


def test_teaching_assets_survive_other_lesson_merge_and_do_not_leak_hidden_bindings():
    from handout_knowledge import merge_lesson_tree,slice_lesson_tree,visible_handout_tree
    p={'knowledge_id':'K','revision_id':'KR','key':'K1','name':'已知知识','statement':'完整结论',
        'section_refs':['L1'],'parent_id':'C','source_refs':[],'source_quotes':[]}
    c={'criterion_id':'criterion','knowledge_ids':['K'],'knowledge_revision_refs':{'K':'KR'},'section_refs':['L1'],
        'contract':'knowledge_teaching_structures_v1','readiness':'ready','review_status':'owner_accepted'}
    old={'knowledge_points':[p],'categories':[{'id':'C','name':'主题','parent_id':None}],
        'relations':[],'lessons':[{'topic':'L1'}],'sources':[],'mastery_criteria':[c],
        'teaching_coverage':{'K':{'knowledge_revision':'KR','status':'ready'}}}
    other={'knowledge_points':[{**p,'knowledge_id':'J','revision_id':'JR','section_refs':['L2']}],
        'categories':old['categories'],'relations':[],'lessons':[{'topic':'L2'}],'sources':[],
        'mastery_criteria':[],'revision_id':'new-tree'}
    merged=merge_lesson_tree(old,other,'L2')
    assert merged['mastery_criteria']==[c]
    assert slice_lesson_tree(merged,'L2').get('mastery_criteria')==[]
    public=visible_handout_tree(merged,{'blocks':[]},{})
    assert public.get('mastery_criteria')==[]


def test_stream_limits_cover_array_fields_without_a_discipline_word_patch():
    from knowledge_output_guard import JsonOutputGuard
    guard=JsonOutputGuard({('extensions','*','explanation'):20})
    with pytest.raises(ValueError,match='过长'):
        guard.feed(json.dumps({'extensions':[{'explanation':'独立知识说明超过这个字段长度范围但不修改任何原始知识内容'}]}))
