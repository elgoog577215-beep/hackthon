"""Notation alignment admits comparison; it never merges knowledge by itself."""
from copy import deepcopy
import json

import pytest

from course_repository import CourseDocumentConflict


def rows():
    return [{'key':'K1','knowledge_id':'p1','name':'加速度是速度对时间的导数','statement':"加速度的定义为a(t)=v'(t)。",
             'conditions':['v 表示速度','t 表示时间'],'atomic_contract':{'subjects':['加速度']}},
            {'key':'K2','knowledge_id':'p2','name':'加速度是速度对时间的导数','statement':"加速度的微分联系为$a(t)=v'(t)$。",
             'conditions':['t表示时间','v(t)表示速度'],'atomic_contract':{'subjects':['加速度']}}]


def test_only_formula_bound_notation_definitions_align_and_conditions_stay_unchanged():
    from knowledge_scope_notation import scope_signature
    points=rows();before=deepcopy(points)
    assert scope_signature(points[0])==scope_signature(points[1])
    assert points==before
    for mutation in ['quantity','argument','domain','case','unbound_call']:
        changed=deepcopy(points[1])
        if mutation=='quantity':changed['conditions'][1]='v(t)表示速率'
        if mutation=='argument':changed['conditions'][1]='v(s)表示速度'
        if mutation=='domain':changed['conditions'].append('t大于零')
        if mutation=='case':changed['conditions'][1]='V(t)表示速度'
        if mutation=='unbound_call':changed['statement']='加速度的定义为A。'
        assert scope_signature(points[0])!=scope_signature(changed),mutation


@pytest.mark.asyncio
@pytest.mark.parametrize('decision',['restatement','different'])
async def test_aligned_scopes_still_require_explicit_bidirectional_pair_confirmation(monkeypatch,decision):
    from knowledge_equivalence_pairs import confirm_pairs
    from knowledge_equivalence import validate_groups,apply_equivalences,catalog_signature
    points=rows();record={'contract':'knowledge_equivalence_v4','status':'requested','proposed_edges':[]};calls=[]
    async def call(*args):
        payload=json.loads(args[-2].split('\nINPUT_JSON:\n')[1]);calls.append(payload)
        return json.dumps({'pair_reviews':{key:{'relation':decision,'forward_reason':'同一公式与符号含义' if decision=='restatement' else '不同检查内容',
            'reverse_reason':'符号说明只是同一速度函数的记号' if decision=='restatement' else '反向不能表达另一检查内容'} for key in payload['pairs']}})
    monkeypatch.setattr('knowledge_atomic.call_stage',call)
    groups=await confirm_pairs(None,'c','j',None,points,[],record,lambda **k:None,lambda:None)
    assert len(calls)==1 and len(groups)==(1 if decision=='restatement' else 0)
    if groups:
        # Frozen old contracts still require exactly matching conditions.
        with pytest.raises(CourseDocumentConflict):validate_groups({'groups':[{k:v for k,v in g.items() if k not in ['semantics_verified','evidence_kind']} for g in groups]},points)
        record.update(status='completed',input_signature=catalog_signature(points),groups=groups)
        merged,_=apply_equivalences(points,record)
        assert len(merged)==1 and merged[0]['conditions']==points[0]['conditions']
        assert merged[0]['semantic_equivalents'][0]['point']['conditions']==points[1]['conditions']


@pytest.mark.asyncio
async def test_completed_discovery_is_reused_only_as_proposals_without_rewriting_its_input(monkeypatch):
    from knowledge_equivalence import review_equivalence,catalog_signature
    points=rows();reviews={p['key']:{'canonical_key':p['key'],'forward_reason':'旧合同条件文字不同','reverse_reason':''} for p in points}
    frozen={'input_signature':catalog_signature(points),'point_reviews':reviews,'raw_response':json.dumps({'point_reviews':reviews}),
            'origin_job_id':'old-job','origin_contract':'knowledge_equivalence_v3'}
    before=deepcopy(frozen);pipeline={'semantic_equivalence_contract':'knowledge_equivalence_v4','frozen_equivalence_discovery':frozen};calls=[]
    async def call(*args):
        assert args[-1]=='semantic_equivalence_pairs';calls.append(args[-1])
        data=json.loads(args[-2].split('\nINPUT_JSON:\n')[1])
        return json.dumps({'pair_reviews':{key:{'relation':'restatement','forward_reason':'同一公式','reverse_reason':'同一速度函数的记号'} for key in data['pairs']}})
    monkeypatch.setattr('knowledge_atomic.call_stage',call)
    await review_equivalence(None,'c','new-job',None,points,pipeline,lambda **k:None,lambda:None)
    assert calls==['semantic_equivalence_pairs'] and frozen==before
    assert pipeline['semantic_equivalence']['discovery_origin_job_id']=='old-job'
    assert len(pipeline['semantic_equivalence']['groups'])==1
