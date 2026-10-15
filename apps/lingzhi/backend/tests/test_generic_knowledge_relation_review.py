from copy import deepcopy
import pytest
from backend.tests.test_knowledge_first import svc
from backend.tests.test_handout_knowledge import handouts, answer
from handout_knowledge import handout_context
from generic_knowledge import compile_tree, validate_relation_revision
from course_document import stable_hash
from knowledge_relations import relation_index
from course_knowledge_commands import build_knowledge_candidate, CourseKnowledgeCommandService, KnowledgeCommandRejected


def prepare(svc):
    handouts(svc)
    raw=svc.repository.load_raw('c-pilot')
    tree=compile_tree(raw,handout_context(raw,svc.authoring.load('c-pilot')),answer())
    tree['status']='accepted'
    svc.storage.update_course_data('c-pilot',lambda c:{**c,'course_knowledge_base':tree})
    proposed=deepcopy(tree)
    a,b=[p['knowledge_id'] for p in tree['knowledge_points']]
    proposed['relations']=[{'id':'relation-reviewed','relation_id':'relation-reviewed','source_id':a,'source_knowledge_id':a,'target_id':b,'target_knowledge_id':b,'type':'contrasts_with','relation_type':'contrasts_with','reason':'比较执行指令与保存数据的职责','conditions':[]}]
    proposed['relation_index']=relation_index(proposed)
    proposed['revision_id']=stable_hash({k:v for k,v in proposed.items() if k!='revision_id'},prefix='kb_')
    return tree,proposed


@pytest.mark.asyncio
async def test_original_knowledge_command_saves_generic_relation_review_without_legacy_role_requirements(svc):
    before,proposed=prepare(svc)
    course=svc.repository.load_course_view('c-pilot')
    candidate=build_knowledge_candidate(course,operation='adjust_relation',proposed_knowledge_base=proposed,reason='核对定义之间的职责区别')
    assert candidate['confirmable'],candidate['blocking_issues']
    command=CourseKnowledgeCommandService(svc.repository)
    receipt=await command.confirm_knowledge_candidate('c-pilot',command_id='manual-relation-review',candidate=candidate,proposed_knowledge_base=proposed,actor='owner')
    saved=svc.repository.load_raw('c-pilot')['course_knowledge_base']
    assert saved['knowledge_points']==before['knowledge_points']
    assert saved['categories']==before['categories']
    assert saved['relations']==proposed['relations']
    assert receipt['knowledge_revision_id']==proposed['revision_id']
    assert (await command.confirm_knowledge_candidate('c-pilot',command_id='manual-relation-review',candidate=candidate,proposed_knowledge_base=proposed,actor='owner'))['command_id']==receipt['command_id']


@pytest.mark.parametrize('mutation',['facts','source','dangling','duplicate','cycle','index','revision','malformed'])
def test_relation_review_refuses_scope_changes_and_broken_graphs(svc,mutation):
    before,proposed=prepare(svc)
    if mutation=='facts':proposed['knowledge_points'][0]['statement']='改变定义'
    elif mutation=='source':proposed['source_handouts']=[]
    elif mutation=='dangling':proposed['relations'][0]['target_id']='foreign'
    elif mutation=='duplicate':proposed['relations'].append({**proposed['relations'][0],'id':'another','relation_id':'another','reason':'换句话重复同一条边'})
    elif mutation=='cycle':
        a,b=[p['knowledge_id'] for p in before['knowledge_points']]
        proposed['relations']=[{**proposed['relations'][0],'id':str(i),'relation_id':str(i),'source_id':x,'source_knowledge_id':x,'target_id':y,'target_knowledge_id':y,'type':'prerequisite','relation_type':'prerequisite'} for i,(x,y) in enumerate([(a,b),(b,a)])]
    elif mutation=='index':proposed['relation_index']={}
    elif mutation=='revision':proposed['revision_id']='old'
    else:proposed['relations']=[{'source_id':[],'target_id':{},'type':None,'id':[]}]
    assert not validate_relation_revision(before,proposed)['passed']


@pytest.mark.asyncio
async def test_relation_confirm_rechecks_payload_after_preview(svc):
    before,proposed=prepare(svc)
    candidate=build_knowledge_candidate(svc.repository.load_course_view('c-pilot'),operation='adjust_relation',proposed_knowledge_base=proposed,reason='核对关系')
    proposed['knowledge_points'][0]['statement']='偷偷改写定义'
    with pytest.raises(KnowledgeCommandRejected):
        await CourseKnowledgeCommandService(svc.repository).confirm_knowledge_candidate('c-pilot',command_id='tampered',candidate=candidate,proposed_knowledge_base=proposed,actor='owner')
    assert svc.repository.load_raw('c-pilot')['course_knowledge_base']==before

@pytest.mark.asyncio
async def test_teacher_projection_relation_command_checks_reading_version_and_keeps_the_canonical_body(svc,monkeypatch):
    from course_document import CourseDocument,CourseSection,refresh_document_revision
    before,proposed=prepare(svc)
    doc=refresh_document_revision(CourseDocument(course_id='c-pilot',title='Computer',sections=[CourseSection(section_id='cpu',title='CPU',position=0),CourseSection(section_id='memory',title='Memory',position=1)]))
    svc.storage.update_course_data('c-pilot',lambda c:{**c,'course_document':doc.model_dump(mode='json'),'course_document_revision':doc.document_revision})
    state=svc.authoring.load('c-pilot')
    for lesson in state['lessons'].values():
        lesson['working_revision_id']='plan'
        for revision in lesson['script_revisions']:
            revision.update(publication_eligible=True,source_lesson_plan_revision_id='plan')
            for section in revision['sections']:
                for block in section['blocks']:block['status']='final'
    svc.authoring._save(state)
    monkeypatch.setattr('dependencies.get_teacher_lesson_authoring_repository',lambda:svc.authoring)
    canonical=deepcopy(svc.repository.load_raw('c-pilot')['course_document'])
    view=svc.repository.load_course_view('c-pilot')
    assert len(view['course_document']['blocks'])==2
    assert view['course_document_revision']!=doc.document_revision
    candidate=build_knowledge_candidate(view,operation='adjust_relation',proposed_knowledge_base=proposed,reason='修正讲义派生关系')
    assert candidate['confirmable']
    await CourseKnowledgeCommandService(svc.repository).confirm_knowledge_candidate('c-pilot',command_id='teacher-reading',candidate=candidate,proposed_knowledge_base=proposed,actor='owner')
    assert svc.repository.load_raw('c-pilot')['course_document']==canonical
    assert svc.authoring.load('c-pilot')['lessons']==state['lessons']
