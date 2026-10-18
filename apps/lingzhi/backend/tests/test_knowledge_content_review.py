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
