import json
from copy import deepcopy

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course
from backend.tests.test_knowledge_extraction_repair import point, value
from course_repository import CourseDocumentConflict


@pytest.mark.asyncio
@pytest.mark.parametrize('missing', [False, True])
async def test_content_review_accounts_for_every_point_and_keeps_source_warnings(svc, monkeypatch, missing):
    from knowledge_content_review import review_content
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    original = value([point(), point('出栈', value='移除并返回栈顶元素')]); before = deepcopy(original)
    reviews = {'S1.1:0': {'decision': 'keep', 'points': [], 'reason': '原文支持一个操作效果'},
               'S1.1:1': {'decision': 'source_issue', 'points': [], 'reason': '隔离测试的来源疑点'}}
    if missing: reviews.pop('S1.1:0')
    calls = []
    async def call(*args):
        calls.append(args[-1]); return json.dumps({'point_reviews': reviews, 'additions': {'S1.1': []},
            'source_issues': [{'passage_key': 'S1.1', 'kind': 'suspected_error', 'detail': '隔离测试的来源疑点'}]})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    record = {}
    if missing:
        with pytest.raises(CourseDocumentConflict): await review_content(svc, 'c-pilot', 'j', None, raw, context, ['S1'], original, record)
    else:
        reviewed = await review_content(svc, 'c-pilot', 'j', None, raw, context, ['S1'], original, record)
        assert reviewed['passages']['S1.1']['points'] == [original['passages']['S1.1']['points'][0]]
        assert reviewed['source_issues'] and record['status'] == 'completed'
        assert record['semantics_verified'] is False
    assert original == before and calls == ['content_review']


def test_published_projection_does_not_disclose_private_review_notes():
    from handout_knowledge import visible_handout_tree
    tree = {'knowledge_points': [{'knowledge_id': 'k', 'revision_id': 'v', 'parent_id': 'c', 'section_refs': ['l'], 'source_refs': ['e'],
        'source_quotes': [{'evidence_id': 'e', 'quote': '公开正文', 'handout_ref': {'block_id': 'visible', 'lesson_id': 'l', 'script_revision_id': 'r'}}],
        'content_review': {'reason': '私有候选核对笔记'}}], 'categories': [{'id': 'c', 'parent_id': None}],
        'concept_groups': [{'id': 'c'}], 'relations': [], 'lessons': [{'topic': 'l', 'knowledge_ids': ['k']}], 'sources': [{'evidence_id': 'e'}]}
    before = deepcopy(tree)
    visible = visible_handout_tree(tree, {'blocks': [{'block_id': 'visible'}]}, {'l': {'revision_id': 'r'}})
    assert len(visible['knowledge_points']) == 1
    assert 'content_review' not in visible['knowledge_points'][0]
    assert tree == before


def test_repeated_definition_review_uses_only_earlier_related_frozen_questions():
    from knowledge_content_review import prior_question_context
    earlier={'batch_index':1,'knowledge_id':'canonical','subjects':['栈'],'meta_question':'栈的完整定义是什么？','statement':'仅在栈顶操作。'}
    pipeline={'review_reference_catalog':[earlier,{**earlier,'batch_index':6,'knowledge_id':'self'},
        {**earlier,'batch_index':7,'knowledge_id':'later'},{**earlier,'subjects':['队列'],'knowledge_id':'other'}]}
    original=value([point('栈')]);before=deepcopy(pipeline)
    assert prior_question_context(pipeline,6,original)==[earlier]
    assert prior_question_context({},6,original)==[]
    assert pipeline==before


@pytest.mark.asyncio
async def test_cross_batch_reference_is_visible_to_the_model_and_kept_as_unverified_provenance(svc,monkeypatch):
    from knowledge_content_review import review_content
    setup_course(svc,monkeypatch);raw=svc.repository.load_raw('c-pilot');context=svc._context(raw,'handouts','cpu')
    refs=[{'batch_index':1,'knowledge_id':'canonical','subjects':['入栈'],'meta_question':'入栈的操作效果是什么？',
           'statement':'入栈将元素插入栈顶。','conditions':[]}]
    async def call(*args):
        payload=json.loads(args[-2].split('\nINPUT_JSON:\n')[1])
        assert payload['earlier_frozen_questions']==refs
        return json.dumps({'point_reviews':{'S1.1:0':{'decision':'context','points':[],
            'reason':'前批次canonical已有相同操作知识，本块仅重复演示'}},'additions':{'S1.1':[]},'source_issues':[]})
    monkeypatch.setattr('knowledge_atomic.call_stage',call);record={}
    reviewed=await review_content(svc,'c-pilot','j',None,raw,context,['S1'],value([point()]),record,reference_points=refs)
    assert reviewed['passages']['S1.1']['points']==[]
    assert record['earlier_frozen_questions']==refs and record['semantics_verified'] is False
