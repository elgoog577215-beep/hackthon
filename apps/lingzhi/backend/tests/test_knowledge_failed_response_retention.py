import json

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course, start
from backend.tests.test_knowledge_tree_relations import fake_provider
from course_repository import CourseDocumentConflict


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['extract', 'relations'])
async def test_complete_responses_that_fail_semantic_validation_remain_on_their_own_batch(svc, monkeypatch, stage):
    setup_course(svc, monkeypatch); fake_provider(svc)
    def reject(*args, **kwargs): raise CourseDocumentConflict('明确的语义校验失败')
    monkeypatch.setattr('knowledge_extract.compile_extraction' if stage == 'extract' else 'knowledge_tree_relations.compile_relations', reject)
    job = start(svc, extraction_mode='single_pass_v1', organize_hierarchy=True, include_relations=True)
    await svc.run('c-pilot', job['id'])
    saved = svc.authoring.get_job('c-pilot', job['id'])
    assert saved['status'] == 'failed'
    pipeline = saved['checkpoint']['atomic_pipeline']
    rows = pipeline['inventory_batches'] if stage == 'extract' else pipeline['relations']['batches']
    assert rows[0]['status'] != 'completed'
    assert isinstance(json.loads(rows[0]['raw_response']), dict)
    assert rows[0]['validation_error']['code'] == 'CourseDocumentConflict'
    assert rows[0]['validation_error']['message'] == '明确的语义校验失败'
