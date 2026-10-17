from copy import deepcopy

import pytest
from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course,inventory,atomic_answer
from course_repository import CourseDocumentConflict

V3='knowledge_inventory_passages_v3'
ATOM3='knowledge_atomic_bindings_v3'


def ctx(svc):return svc._context(svc.repository.load_raw('c-pilot'),'handouts','cpu')


def test_passages_preserve_every_character_and_stable_offsets(svc,monkeypatch):
    from knowledge_compact import passage_catalog
    setup_course(svc,monkeypatch);context=ctx(svc)
    source='定义与公式：\\Phi(s)=2m-n。\n\n'+('连续内容；'*400)+'\n'+('示例代码\n'*100)
    context['evidence_package']['units'][0]['source_text']=source
    rows=passage_catalog(context,['S1'])
    assert ''.join(row['text'] for row in rows)==source
    assert all(source[row['start']:row['end']]==row['text'] for row in rows)
    assert rows==passage_catalog(context,['S1']) and len(rows)>1


def test_model_passage_references_bind_exact_original_quotes(svc,monkeypatch):
    from knowledge_compact import passage_catalog
    from knowledge_atomic import compile_inventory
    setup_course(svc,monkeypatch);context=ctx(svc);passage=passage_catalog(context,['S1'])[0]
    items=inventory()['items']
    for item in items:item['source_passage_keys']=[passage['key']];item.pop('sources')
    result={'response_contract':V3,'items':items,'unassigned_passages':[],'source_issues':[]}
    saved,coverage=compile_inventory(result,context,['S1'],1)
    assert saved[0]['sources'][0]['quote']==passage['text']
    assert saved[0]['sources'][0]['key']=='S1' and coverage[0]['passage_keys']==[passage['key']]


def test_tail_passages_cannot_be_hidden_by_an_earlier_reference_to_same_source(svc,monkeypatch):
    from knowledge_compact import passage_catalog
    from knowledge_atomic import compile_inventory
    setup_course(svc,monkeypatch);context=ctx(svc)
    context['evidence_package']['units'][0]['source_text']='入栈将元素插入栈顶。'+('独立的后续内容。'*400)
    rows=passage_catalog(context,['S1']);item=deepcopy(inventory()['items'][0]);item.pop('sources');item['source_passage_keys']=[rows[0]['key']]
    response={'response_contract':V3,'items':[item],'unassigned_passages':[],'source_issues':[]}
    with pytest.raises(CourseDocumentConflict,match='片段'):compile_inventory(response,context,['S1'],1)


def test_atomic_binding_uses_frozen_inventory_evidence_instead_of_model_recopied_quotes(svc,monkeypatch):
    from knowledge_atomic import compile_inventory,compile_batch
    setup_course(svc,monkeypatch);context=ctx(svc);items,_=compile_inventory(inventory(),context,['S1'],1)
    result=atomic_answer(items)
    for p in result['points']:p.pop('sources')
    result.update(response_contract=ATOM3,context_items=[])
    result.pop('coverage');result.pop('question_coverage')
    tree,report=compile_batch(svc.repository.load_raw('c-pilot'),context,items,result)
    assert report['ready_for_adoption'] and tree['knowledge_points'][0]['source_quotes'][0]['quote']==items[0]['sources'][0]['quote']
    assert tree['knowledge_points'][0]['source_binding_origin']=='frozen_inventory_passage'


def test_cross_group_dedup_keeps_nested_passage_references_resolvable():
    from knowledge_compact import remap_coverage_keys
    pipeline={'inventory_batches':[{'source_coverage':[{'item_keys':['I2_I1'],'passage_coverage':[{'item_keys':['I2_I1'],'passage_key':'S8.1'}]}]}]}
    remap_coverage_keys(pipeline,{'I2_I1':'I1_I1'})
    row=pipeline['inventory_batches'][0]['source_coverage'][0]
    assert row['item_keys']==row['passage_coverage'][0]['item_keys']==['I1_I1']
