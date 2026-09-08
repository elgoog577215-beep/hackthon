from copy import deepcopy
import json
import pytest
from inline_editing import inline_text_span, replace_inline_text, outline_inline_target, patch_outline_inline
from course_generation.service import CourseService
from course_versioning import build_blueprint_draft
from backend.tests.test_outline_adjustment_task_manager import _manager, _course


def test_exact_range_preserves_surrounding_markdown_and_rejects_ambiguity():
    source = '前句。使用 **DeepSeek 4.0** 完成任务。后句。'
    assert replace_inline_text(source, 'DeepSeek 4.0', 'DeepSeek 5.0') == source.replace('4.0', '5.0')
    assert replace_inline_text('前句。\n选中  内容。\n后句。', '选中 内容。', '新内容。') == '前句。\n新内容。\n后句。'
    with pytest.raises(ValueError): inline_text_span('重复重复', '重复')
    with pytest.raises(ValueError): replace_inline_text(source, '不存在的内容', '新内容')
    with pytest.raises(ValueError): replace_inline_text(source, 'DeepSeek 4.0', 'DeepSeek 4.0')


@pytest.mark.asyncio
async def test_plan_selection_patches_only_selected_words_and_retains_all_siblings():
    source = {'sections': [{'node_id': 's1', 'teaching_modules': [{'module_id':'m1', 'teacher_activity':'保留前句。使用 DeepSeek 4.0。保留后句。', 'student_activity':'保留学生活动'}]}, {'node_id':'s2','learning_objective':'保留另一小节'}]}
    class Model:
        async def _call_llm(self, prompt, **kwargs):
            assert kwargs['retry_count'] >= 1
            assert '当前值："DeepSeek 4.0"' in prompt
            return json.dumps({'value':'DeepSeek 5.0'})
        def _extract_json(self, value): return json.loads(value)
    result = await CourseService.optimize_teacher_lesson_plan(Model(), plan=source, instruction='更新到 5.0', section_node_id='s1', target_field='teacher_activity',target_item_id='m1', selected_text='DeepSeek 4.0',selection_only=True)
    expected=deepcopy(source)
    expected['sections'][0]['teaching_modules'][0]['teacher_activity']='保留前句。使用 DeepSeek 5.0。保留后句。'
    assert result['plan']==expected
    assert source['sections'][0]['teaching_modules'][0]['teacher_activity'].endswith('4.0。保留后句。')


@pytest.mark.asyncio
async def test_outline_inline_preview_has_single_operation_and_no_source_write(tmp_path, monkeypatch):
    manager, service, storage, versions = _manager(tmp_path, monkeypatch)
    draft=build_blueprint_draft(_course())
    node=next(node for node in draft['nodes'] if node['node_id']=='L2-1-1')
    original=node['learning_objective']
    async def rewrite(**kwargs):
        assert kwargs['selected_text']==original
        return {'replacement_text':original+'并验证结果'}
    service.rewrite_selection=rewrite
    proposal=await manager.preview_outline_adjustment('course-outline', {'request_id':'inline-one','base_blueprint_revision_id':draft['base_blueprint_revision_id'],'expected_draft_revision_id':draft['draft_revision_id'],'instruction':'增加验证要求','inline_target':{'node_id':'L2-1-1','field':'learning_objective','selected_text':original}})
    assert proposal['can_apply']
    assert proposal['operations']==[{'op':'update_node','node_ref':'L2-1-1','learning_objective':original+'并验证结果'}]
    assert proposal['inline_edit']['selected_text']==original
    assert service.calls==[]
    assert versions.load_draft('course-outline') is None
    assert storage.course==_course()


def test_outline_nested_field_keeps_other_items_and_never_edits_ids():
    draft={'nodes':[{'node_id':'n1','node_name':'引言','assessment':['第一个检查','第二个检查']} ]}
    operation,selected,path=outline_inline_target(draft,'第二个检查','n1','assessment')
    changed=patch_outline_inline(operation,path,selected,'修订后的检查')
    assert changed['assessment']==['第一个检查','修订后的检查']
    assert draft['nodes'][0]['assessment'][1]=='第二个检查'
    with pytest.raises(ValueError): outline_inline_target(draft,'n1','n1','node_id')


def test_script_inline_candidate_applies_one_range_and_can_discard_after_conflict(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from dependencies import require_task_manager, get_teacher_lesson_authoring_repository
    from routers import teacher_lesson_authoring as routes
    from teacher_lesson_authoring import TeacherLessonAuthoringRepository
    from teacher_script import compile_teacher_script_module_contract, compile_teacher_script_section
    from backend.tests.test_teacher_lesson_authoring import course_data, standard_lesson_plan
    repository=TeacherLessonAuthoringRepository(tmp_path/'authoring')
    source={**course_data(), 'blueprint_revision_id':'outline-v1'}
    plan=standard_lesson_plan()
    second=deepcopy(plan['sections'][0]);second['node_id']='L2-1-2';plan['sections'].append(second)
    lesson=repository.save_plan_revision('course-1','L1-1',plan,source_outline_revision_id='outline-v1')
    plan_id=lesson['working_revision_id']
    sections=[]
    for item in plan['sections']:
        node=next(n for n in source['nodes'] if n['node_id']==item['node_id'])
        contract=compile_teacher_script_module_contract(node,item)
        text='\n\n'.join(f"## {m['title']}\n\n前句保持。使用 DeepSeek 4.0 解释当前概念的成立条件、适用范围和推理过程。后句保持。" for m in contract['modules'])
        sections.append(compile_teacher_script_section(text,contract))
    saved=repository.save_script_revision('course-1','L1-1',sections,source_lesson_plan_revision_id=plan_id,generation_source='teacher_edit')
    base=saved['working_script_revision_id']
    original=deepcopy(next(r for r in saved['script_revisions'] if r['revision_id']==base)['sections'])
    target=original[0]['blocks'][0]
    calls=[]
    async def rewrite(**kwargs):
        calls.append(kwargs)
        return {'replacement_text':'DeepSeek 5.0'}
    tm=SimpleNamespace(storage=SimpleNamespace(load_course=lambda _: deepcopy(source)),course_service=SimpleNamespace(rewrite_selection=rewrite),get_generation_workspace_course=lambda _:None,get_generation_preview=lambda _:None)
    app=FastAPI();app.include_router(routes.router,prefix='/api')
    app.dependency_overrides[require_task_manager]=lambda:tm
    app.dependency_overrides[get_teacher_lesson_authoring_repository]=lambda:repository
    monkeypatch.setattr(routes,'_course_material_evidence',lambda *_:([],[]))
    prefix='/api/teacher/courses/course-1/lessons/L1-1/script'
    with TestClient(app) as client:
        response=client.post(prefix+'/rewrite-candidate',json={'base_revision_id':base,'section_node_id':original[0]['section_node_id'],'target_block_id':target['block_id'],'selected_text':'DeepSeek 4.0','instruction':'更新版本'})
        assert response.status_code==200,response.text
        candidate=response.json()['candidate']
        assert calls[0]['selected_text']=='DeepSeek 4.0'
        assert calls[0]['node_content']==target['content']
        assert repository.lesson('course-1','L1-1')['working_script_revision_id']==base
        response=client.post(prefix+f"/ai-candidates/{candidate['candidate_id']}/resolve",json={'accept':True})
        assert response.status_code==200,response.text
        now=repository.lesson('course-1','L1-1')
        updated=next(r for r in now['script_revisions'] if r['revision_id']==now['working_script_revision_id'])['sections']
        assert updated[0]['blocks'][0]['content']==target['content'].replace('DeepSeek 4.0','DeepSeek 5.0')
        assert [b['content'] for b in updated[0]['blocks'][1:]]==[b['content'] for b in original[0]['blocks'][1:]]
        assert updated[1]['content']==original[1]['content']
        stale=repository.save_script_ai_candidate('course-1','L1-1',base_revision_id=now['working_script_revision_id'],section_node_id=original[0]['section_node_id'],instruction='再调整',replacement_text='未采用的候选',source_lesson_plan_revision_id=plan_id)
        repository.save_script_revision('course-1','L1-1',updated,source_lesson_plan_revision_id=plan_id,generation_source='teacher_edit')
        response=client.post(prefix+f"/ai-candidates/{stale['candidate_id']}/resolve",json={'accept':False})
        assert response.status_code==200,response.text
        assert response.json()['candidate']['status']=='rejected'
