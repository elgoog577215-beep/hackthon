from copy import deepcopy
import pytest
from .test_foundation_round import sample
from .foundation_round import assemble
from .refine_foundation import apply_patch_plan,FIELDS,edit
from .pipeline import digest


def inputs():
    c,i,a,t=sample()
    c['scope_quote']=c['profile']
    c['profile']+='；使用图示核验'
    c['materials'][0]['text']+='仅用于列表。'
    i['claims'].append({'key':'C3','kind':'scope','claim':'只在列表范围','source_ref':'M1','quote':'仅用于列表。'})
    a['dispositions'].append({'claim_key':'C3','role':'scope','point_keys':['P1'],'reason':'范围'})
    tree=assemble(c,i,a,t)
    plan={'edits':[edit('P1a',list(FIELDS),'部分一','P1'),edit('P1b',list(FIELDS),'部分二','P1')],
          'retire':{'P1':'split'},'placements':{'P1a':'G1','P1b':'G1'},'category_changes':{},'new_categories':[]}
    patch={'revisions':[{'key':k,'changes':{f:deepcopy(a['points'][0][f]) for f in FIELDS}} for k in ('P1a','P1b')]}
    return c,i,a,tree,plan,patch


def test_split_has_new_identity_and_every_leaf_inherits_source_scope():
    args=inputs();before=deepcopy(args);atoms,tree=apply_patch_plan(*args,digest(args[2]))
    assert args==before
    assert {p['key'] for p in tree['points']}=={'P1a','P1b'}
    assert all(p['knowledge_id']!=args[3]['points'][0]['knowledge_id'] for p in tree['points'])
    assert all('仅用于列表。' in p['effective_conditions'] for p in tree['points'])
    assert all('使用图示核验' not in '；'.join(p['effective_conditions']) for p in tree['points'])
    assert all(p['scope_revision']==tree['scope_revision'] for p in tree['points'])
    assert tree['lineage'][0]['new_keys']==['P1a','P1b']
    assert all(p['attachments'] for p in tree['points'])


@pytest.mark.parametrize('mutation',['missing_slot','extra_field','foreign_ref','stale'])
def test_patch_is_rejected_atomically(mutation):
    c,i,a,t,p,patch=inputs();before=deepcopy(a);revision=digest(a)
    if mutation=='missing_slot':patch['revisions'].pop()
    if mutation=='extra_field':patch['revisions'][0]['changes']['knowledge_id']='forged'
    if mutation=='foreign_ref':patch['revisions'][0]['changes']['claim_refs']=['NO_SOURCE']
    if mutation=='stale':revision='stale'
    with pytest.raises(ValueError):apply_patch_plan(c,i,a,t,p,patch,revision)
    assert a==before


def test_rewording_keeps_identity_and_untargeted_fields():
    c,i,a,t,_,_=inputs()
    plan={'edits':[edit('P1',['conditions'],'澄清条件')],'retire':{},'placements':{},'category_changes':{},'new_categories':[]}
    patch={'revisions':[{'key':'P1','changes':{'conditions':['a为普通列表']}}]}
    _,result=apply_patch_plan(c,i,a,t,plan,patch,digest(a))
    point=result['points'][0]
    assert point['knowledge_id']==t['points'][0]['knowledge_id']
    assert point['statement']==a['points'][0]['statement']
    assert point['meta_answer']==a['points'][0]['meta_answer']


def test_scope_leaf_retires_to_inherited_metadata_without_losing_source():
    c,i,a,_,_,_=inputs()
    a['points'].append({'key':'P0','name':'范围','statement':'仅用于列表','conditions':[],
        'boundaries':[],'meta_question':'范围','meta_answer':'列表','claim_refs':['C3']})
    a['dispositions'][-1]['point_keys']=['P0']
    old=assemble(c,i,a,{'categories':[{'key':'G1','name':'知识','parent_key':None},{'key':'G0','name':'范围','parent_key':None}],
                         'placements':[{'point_key':'P1','parent_key':'G1'},{'point_key':'P0','parent_key':'G0'}]})
    plan={'edits':[],'retire':{'P0':'scope'},'remove_categories':['G0'],'placements':{},'category_changes':{},'new_categories':[]}
    _,tree=apply_patch_plan(c,i,a,old,plan,{'revisions':[]},digest(a))
    assert [p['key'] for p in tree['points']]==['P1']
    assert '仅用于列表。' in tree['points'][0]['effective_conditions']
    assert next(x for x in tree['lineage'] if x['old_key']=='P0')['status']=='scope'
    assert len(tree['categories'])==1
