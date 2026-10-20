"""Knowledge extraction observes complete saved blocks, not evidence fragments."""
from copy import deepcopy
import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course, start


def test_projection_keeps_diagram_and_definition_whole_without_changing_input_identity(svc,monkeypatch):
    from knowledge_handout_projection import project_complete_blocks
    setup_course(svc,monkeypatch)
    raw=svc.repository.load_raw('c-pilot');state=deepcopy(svc.authoring.load('c-pilot'))
    lesson=state['lessons']['cpu'];rid=lesson['working_script_revision_id']
    revision=next(r for r in lesson['script_revisions'] if r['revision_id']==rid)
    body='完整方法定义。\n```lingzhi-diagram\n'+('说明。'*500)+'\n```\n最后成功判据。'
    revision['sections'][0]['blocks'][0]['content']=body
    from handout_knowledge import handout_context
    old=handout_context(raw,state,'cpu');before=deepcopy(old)
    projected=project_complete_blocks(raw,state,old,'cpu')
    units=projected['evidence_package']['units']
    assert len(units)==1 and units[0]['source_text']==body
    assert projected['revision_id']==old['revision_id']
    assert projected['source_unit_contract']=='complete_handout_blocks_v1'
    assert projected['evidence_package']['package_revision_id']!=old['evidence_package']['package_revision_id']
    assert old==before


def test_new_attempt_freezes_complete_block_projection_and_legacy_context_stays_readable(svc,monkeypatch):
    setup_course(svc,monkeypatch);raw=svc.repository.load_raw('c-pilot')
    old=svc._context(raw,'handouts','cpu')
    job=start(svc,extraction_mode='single_pass_v1')
    frozen=job['request_snapshot']['knowledge_generation_context']
    assert frozen['source_unit_contract']=='complete_handout_blocks_v1'
    assert frozen['revision_id']==old['revision_id']
    assert 'source_unit_contract' not in svc._context(raw,'handouts','cpu')


def test_shortening_subject_preserves_only_source_bound_conditional_scope():
    from knowledge_correction_protocol import subject_scope
    assert subject_scope('函数$f(x)$在$x=a$处不连续','$f(x)$','若$f(x)$在$x=a$处不连续，则导数不存在。')==['在$x=a$处不连续']
    assert subject_scope('函数$f(x)$在$x=a$处不连续','$f(x)$','函数$f(x)$可导。')==[]
    assert subject_scope('导数定义式','定义式','导数的定义式可改写为增量形式。')==[]


@pytest.mark.asyncio
@pytest.mark.parametrize('change',[False,True])
async def test_adoption_compares_the_same_projection_and_still_protects_handout_changes(svc,monkeypatch,change):
    from backend.tests.test_knowledge_tree_relations import fake_provider
    setup_course(svc,monkeypatch);fake_provider(svc)
    job=start(svc,extraction_mode='single_pass_v1');await svc.run('c-pilot',job['id'])
    view=svc.view('c-pilot',source_mode='handouts')
    if change:
        from course_repository import CourseDocumentConflict
        state=svc.authoring.load('c-pilot')
        state['lessons']['cpu']['script_revisions'][0]['sections'][0]['blocks'][0]['content']+='正文变化。'
        svc.authoring._save(state)
        with pytest.raises(CourseDocumentConflict,match='变化'):
            svc.adopt('c-pilot',job['id'],'',view['document_revision'],confirm_atomic_review=True,confirm_relations=True)
        return
    svc.adopt('c-pilot',job['id'],'',view['document_revision'],confirm_atomic_review=True,confirm_relations=True)
    assert svc.repository.load_raw('c-pilot')['course_knowledge_base']['generation_job_id']==job['id']
