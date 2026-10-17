from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from backend.tests.test_teacher_course_change import context
from course_document import CourseBlock, CourseSection
from course_evolution import CourseEvolutionRepository
from course_evolution.request_routing import resolve_scope, canonical_aliases
from course_evolution.teacher_planning import TeacherCourseChangeUnit, create_teacher_course_change_plan
from course_evolution.scan_previews import content_previews
from course_evolution.semantic_scan import scan_batches

REQUEST = '只给用户画像补充依据，其他不变'


def course():
    ctx = context().model_copy(deep=True)
    ctx.outline = []
    ctx.units = []
    for i, text in enumerate(['用户画像需要证据。', '课程排版保持一致。', '课堂时间安排。'], 1):
        sid = f'L{i}'
        section = CourseSection(section_id=sid, title=f'第{i}讲', position=i)
        ctx.outline.append({'node_id':sid, 'node_name':section.title, 'node_level':1,
                            'parent_node_id':'root', 'section_snapshot':section.model_dump(mode='json')})
        block = CourseBlock(block_id=f'b{i}', section_id=sid, position=0, kind='rich_text', role='concept',
                            payload={'title':f'段落{i}', 'markdown':text})
        ctx.units.append(TeacherCourseChangeUnit(unit_id=f'course_content:b{i}', asset_type='course_content',
            unit_type='course_block', title=section.title, text=text, section_ids=[sid], parent_id=sid,
            role='concept', source_revision=f'r{i}', full_text_fields={'/title':f'段落{i}', '/markdown':text},
            metadata={'course_block':block.model_dump(mode='json'), 'editable_fields':block.payload}))
    first = ctx.units[0]
    ctx.units.append(TeacherCourseChangeUnit(unit_id='script:L1:b1', asset_type='script', unit_type='script_block',
        title='段落1', text=first.text, full_text_fields={'/title':'段落1', '/content':first.text},
        section_ids=['L1'], parent_id='L1', role='concept', source_revision='script-r1', source_state='current'))
    return ctx


def proposal():
    return {'mode':'topics', 'topics':['用户画像'], 'evidence':REQUEST}


def assessment():
    return {'interpreted_goal':REQUEST, 'affected_units':[], 'clarifications':[], 'blocking_questions':[],
            'structure':{'required':False}, 'scope':proposal()}


def test_scope_uses_full_fields_and_preserves_membership_and_explicit_references():
    ctx = course()
    ctx.units[0].text = '摘要中没有主题'
    ctx.units[0].full_text_fields['/markdown'] = '前言。'*500 + '用户画像'
    ctx.units[0].metadata['course_block']['concept_refs'] = ['c1']
    ctx.units[2].metadata['course_block']['concept_refs'] = ['c1']
    result = resolve_scope(ctx, REQUEST, proposal())
    assert set(result['selected_unit_ids']) == {'course_content:b1','script:L1:b1','course_content:b3'}
    assert result['outside_unit_ids'] == ['course_content:b2']


@pytest.mark.parametrize('instruction,scope', [
    ('优化全课表述，尤其是用户画像', {'mode':'topics','topics':['用户画像'],'evidence':'用户画像'}),
    (REQUEST, {'mode':'topics','topics':['虚构主题'],'evidence':REQUEST}),
    (REQUEST, {'mode':'lectures','lecture_ids':['missing'],'evidence':REQUEST}),
    ('只修改第2讲', {'mode':'lectures','lecture_ids':[{'id':'L2'}],'evidence':'只修改第2讲'}),
    ('给“用户画像”和“排版”补充例子', {'mode':'topics','topics':['用户画像'],'evidence':'用户画像'}),
    ('只改不存在主题', {'mode':'topics','topics':['不存在主题'],'evidence':'不存在主题'}),
])
def test_ambiguous_or_incomplete_scope_keeps_the_full_scan(instruction, scope):
    ctx = course()
    assert set(resolve_scope(ctx, instruction, scope)['selected_unit_ids']) == {u.unit_id for u in ctx.units}


def test_explicit_lecture_and_full_override():
    ctx = course()
    scope = {'mode':'lectures','lecture_ids':['L2'],'evidence':'只修改第2讲'}
    assert resolve_scope(ctx, '只修改第2讲', scope)['selected_unit_ids'] == ['course_content:b2']
    assert resolve_scope(ctx, '只修改第2讲', scope, force_full=True)['mode'] == 'full'


def test_shared_text_requires_verified_owner_identity_and_matching_source():
    ctx = course(); ids = {u.unit_id for u in ctx.units}
    assert not canonical_aliases(ctx, ids)
    ctx.canonical_authoring = True
    assert canonical_aliases(ctx, ids) == {'script:L1:b1':'course_content:b1'}
    ctx.units[-1].full_text_fields['/content'] += '独立内容'
    assert not canonical_aliases(ctx, ids)


@pytest.mark.asyncio
async def test_targeted_scan_reuses_verified_alias_and_unchanged_observations(tmp_path):
    ctx = course(); ctx.canonical_authoring = True
    gate = AsyncMock(return_value=assessment())
    calls = []
    async def analyze(overview, batch, instruction):
        calls.append([u['unit_id'] for u in batch])
        return {'affected_units':[{'unit_id':'course_content:b1','disposition':'rewrite_partial',
            'content_patches':[{'field':'markdown','before':'用户画像需要证据。','after':'用户画像需要记录证据来源。'}]}]}
    repo = CourseEvolutionRepository(tmp_path)
    args = dict(context=ctx, user_id='teacher', instruction=REQUEST, repository=repo,
                analyzer=analyze, intent_analyzer=gate, scan_model_identity='local-qwen')
    state = await create_teacher_course_change_plan(**args, request_id='one')
    first = state.change_sets[-1]
    assert calls == [['course_content:b1']]
    c = first.impact_summary['coverage']
    assert c['model_units'] == 1 and c['alias_units'] == 1
    assert c['scanned_units'] == 2 and not c['unscanned_unit_ids']
    assert len(c['outside_unit_ids']) == 2
    assert len(first.operations) == 1
    state = await create_teacher_course_change_plan(**args, request_id='two')
    second = state.change_sets[-1]
    assert len(calls) == 1 and gate.call_count == 1
    assert second.change_set_id != first.change_set_id
    assert second.impact_summary['coverage']['model_units'] == 0
    assert second.impact_summary['coverage']['retained_units'] == 2
    assert 'scope_review' not in second.impact_summary


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['source', 'actor', 'model', 'outline', 'force_full'])
async def test_source_or_request_authority_change_invalidates_cached_judgment(tmp_path, change):
    ctx = course()
    gate = AsyncMock(return_value=assessment())
    scan = AsyncMock(return_value={'affected_units':[]})
    args = dict(user_id='teacher', instruction=REQUEST, repository=CourseEvolutionRepository(tmp_path),
                analyzer=scan, intent_analyzer=gate, scan_model_identity='local-qwen')
    await create_teacher_course_change_plan(context=ctx, **args, request_id='one')
    initial = scan.call_count
    changed = ctx.model_copy(deep=True)
    if change == 'source':
        changed.units[0].full_text_fields['/markdown'] += '新证据。'
    elif change == 'actor':
        args['user_id'] = 'another-teacher'
    elif change == 'model':
        args['scan_model_identity'] = 'different-model-route'
    elif change == 'outline':
        changed.outline[0]['node_name'] += '新结构'
    else:
        args['force_full_scan'] = True
    await create_teacher_course_change_plan(context=changed, **args, request_id='two')
    assert scan.call_count > initial


@pytest.mark.asyncio
async def test_outside_scope_change_keeps_matching_observations(tmp_path):
    ctx = course()
    scan = AsyncMock(return_value={'affected_units':[]})
    args = dict(user_id='teacher', instruction=REQUEST, repository=CourseEvolutionRepository(tmp_path),
                analyzer=scan, intent_analyzer=AsyncMock(return_value=assessment()), scan_model_identity='local-qwen')
    await create_teacher_course_change_plan(context=ctx, **args, request_id='one')
    initial = scan.call_count
    changed = ctx.model_copy(deep=True)
    changed.base_revision_vector = {**changed.base_revision_vector, 'course_document':'outside-edit'}
    changed.units[1].full_text_fields['/markdown'] += '外部排版变化。'
    state = await create_teacher_course_change_plan(context=changed, **args, request_id='two')
    assert scan.call_count == initial
    assert state.change_sets[-1].impact_summary['coverage']['retained_units'] == 2


@pytest.mark.asyncio
async def test_preview_waits_for_all_fragments_and_only_shows_validated_diff():
    ctx = course()
    uid = ctx.units[0].unit_id
    patches = [{'unit_id':uid,'content_patches':[{'field':'markdown','before':'需要证据','after':'需要记录证据来源'}]}]
    events = []
    async def analyze(overview, batch, instruction): return {'affected_units':patches}
    async def progress(detail, saved):
        events.append(content_previews(ctx, saved, set(detail.get('_complete_unit_ids') or [])))
    await scan_batches(overview={}, batches=[[{'unit_id':uid,'part':1,'parts':2}],
        [{'unit_id':uid,'part':2,'parts':2}]], instruction=REQUEST, revisions={}, analyzer=analyze, on_progress=progress)
    assert not any(events[:-1])
    assert events[-1][uid]['before'] == '需要证据'
    assert events[-1][uid]['after'] == '需要记录证据来源'
    invalid = {'results':{'batch':{'affected_units':[{'unit_id':uid,'content_patches':[
        {'field':'markdown','before':'不存在的原文','after':'fake'}]}]}}}
    assert not content_previews(ctx, invalid, {uid})
