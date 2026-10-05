from copy import deepcopy
from dataclasses import replace
import json

import pytest

from ai_base import AIProviderRequestError
from course_generation.prompts import TEACHER_OUTLINE_COMPLETE_SCHEMA
from course_generation.service import CourseService
from course_generation_budget import CourseGenerationBudgetExceeded
from models import CourseGenerationRequest


def payload(count=2):
    result = deepcopy(TEACHER_OUTLINE_COMPLETE_SCHEMA)
    result['course_title'] = '数据分析方法'
    result['positioning'] = '掌握基础统计方法，进阶建模不在本课范围内'
    result['reference_books'] = []
    result['reference_websites'] = []
    result['assessment_plan'] = [
        {'item': '练习', 'category': 'formative', 'weight_percent': 40, 'criteria': '步骤正确', 'outcome_numbers': [1]},
        {'item': '项目', 'category': 'summative', 'weight_percent': 60, 'criteria': '分析正确', 'outcome_numbers': [1]},
    ]
    result['course_modules'][0]['lecture_numbers'] = list(range(1, count + 1))
    result['outcome_alignment'][0]['lecture_numbers'] = list(range(1, count + 1))
    result['lectures'] = [dict(deepcopy(result['lectures'][0]), lecture_number=n, title=f'数据主题{n}',
                                content_summary=f'学习第{n}个数据分析方法',
                                hour_breakdown={'classroom_lecture': 1, 'classroom_practice': 0, 'online_instruction': 0},
                                extension_resources=[]) for n in range(1, count + 1)]
    return result


async def generate(service, **kwargs):
    return await service.build_course_draft(
        course_id='isolated-outline', topic='数据分析方法',
        teacher_course_brief={'lecture_count': 2, 'total_class_hours': 2, 'course_period_minutes': 45,
                              'target_audience': '本科生', 'teaching_context': 'classroom'},
        stop_after_outline=True, **kwargs,
    )


def test_default_request_is_complete_and_mode_is_validated():
    assert CourseGenerationRequest(subject='数据分析').outline_mode == 'full'
    with pytest.raises(ValueError):
        CourseGenerationRequest(subject='数据分析', outline_mode='batched')


@pytest.mark.asyncio
async def test_complete_outline_one_call_and_resume_save_without_model(monkeypatch):
    service = CourseService()
    calls = []
    async def model(*args, **kwargs):
        calls.append(kwargs)
        return json.dumps(payload(), ensure_ascii=False)
    monkeypatch.setattr(service, '_call_llm', model)
    async def forbidden(**kwargs):
        pytest.fail('No automatic editorial model call')
    monkeypatch.setattr(service, 'propose_outline_adjustment', forbidden)
    checkpoints = []
    result = await generate(service, on_checkpoint=lambda item: checkpoints.append(deepcopy(item)))
    assert len(calls) == 1
    assert calls[0]['max_attempts'] == 1
    assert calls[0]['reject_truncated'] is True
    assert result['outline_generation_status'] == 'completed'
    stage = result['generation_stage_artifacts']['outline']
    assert stage['strategy'] == 'teacher_complete_outline'
    assert stage['model_call_count'] == 1
    assert len(result['course_outline']['chapters']) == 2
    assert not result.get('outline_framework_only')
    # Simulate failure after the final stage checkpoint but before publication.
    persisted = {}
    for checkpoint in checkpoints:
        persisted.update(checkpoint)
        if (checkpoint.get('generation_stage_artifacts') or {}).get('outline', {}).get('status') == 'completed':
            break
    recovered = await generate(service, existing_course_data=persisted)
    assert len(calls) == 1
    assert recovered['course_outline'] == result['course_outline']


@pytest.mark.asyncio
async def test_optional_plan_waits_then_one_complete_call_preserving_titles(monkeypatch):
    service = CourseService()
    calls = []
    async def model(*args, **kwargs):
        calls.append(kwargs)
        return json.dumps(payload(), ensure_ascii=False)
    monkeypatch.setattr(service, '_call_llm', model)
    first = await generate(service, stop_after_skeleton=True)
    assert len(calls) == 1
    assert first['outline_framework_only'] is True
    stage = first['generation_stage_artifacts']['outline']
    stage['shape_confirmed'] = True
    stage['skeleton']['chapters'][0]['title'] = '教师确认的主题'
    second = await generate(service, existing_course_data=first)
    assert len(calls) == 2
    assert second['course_outline']['chapters'][0]['title'] == '教师确认的主题'
    assert second['generation_stage_artifacts']['outline']['model_call_count'] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', ['json', 'missing', 'duplicate'])
async def test_one_structure_repair_and_no_extra_retry(monkeypatch, invalid):
    service = CourseService()
    calls = []
    bad = payload()
    if invalid == 'missing': bad['lectures'].pop()
    if invalid == 'duplicate': bad['lectures'][1]['lecture_number'] = 1
    if invalid == 'hours': bad['lectures'][1]['hour_breakdown']['classroom_lecture'] = 5
    async def model(*args, **kwargs):
        calls.append(kwargs)
        return 'broken json' if invalid == 'json' else json.dumps(bad, ensure_ascii=False)
    monkeypatch.setattr(service, '_call_llm', model)
    with pytest.raises(AIProviderRequestError):
        await generate(service)
    assert len(calls) == 2
    assert all(item['max_attempts'] == 1 for item in calls)


@pytest.mark.asyncio
async def test_provider_failure_preserves_partial_and_does_not_retry(monkeypatch):
    service = CourseService()
    calls = []
    checkpoints = []
    async def model(*args, **kwargs):
        calls.append(kwargs)
        await kwargs['on_content_delta']('{"lectures":[')
        raise AIProviderRequestError('stream interrupted')
    monkeypatch.setattr(service, '_call_llm', model)
    with pytest.raises(AIProviderRequestError):
        await generate(service, on_checkpoint=lambda item: checkpoints.append(deepcopy(item)))
    assert len(calls) == 1
    stage = checkpoints[-1]['generation_stage_artifacts']['outline']
    assert stage['partial_response'] == '{"lectures":['
    assert stage['status'] == 'failed'
    assert stage['model_call_count'] == 1


@pytest.mark.asyncio
async def test_over_budget_never_calls_model_or_silently_compacts(monkeypatch):
    service = CourseService()
    service._generation_budget = replace(service._generation_budget, max_input_chars=50)
    async def forbidden(*args, **kwargs):
        pytest.fail('over-budget request must not reach provider')
    monkeypatch.setattr(service, '_call_llm', forbidden)
    with pytest.raises(CourseGenerationBudgetExceeded):
        await generate(service)


@pytest.mark.asyncio
async def test_hour_arithmetic_is_local_and_budget_includes_output(monkeypatch):
    service = CourseService()
    result = payload()
    result['lectures'][0]['hour_breakdown']['classroom_practice'] = 0.5
    calls = []
    async def model(*args, **kwargs):
        calls.append(kwargs)
        return json.dumps(result, ensure_ascii=False)
    monkeypatch.setattr(service, '_call_llm', model)
    generated = await generate(service)
    assert len(calls) == 1
    assert sum(c['sections'][0]['planned_hours'] for c in generated['course_outline']['chapters']) == 2
    assert generated['generation_stage_artifacts']['outline']['local_hour_adjustments']
    service._generation_budget = replace(service._generation_budget, context_window_tokens=16384)
    with pytest.raises(CourseGenerationBudgetExceeded):
        await generate(service)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_provider_queue_does_not_consume_active_deadline(monkeypatch):
    import asyncio
    service = CourseService()
    async def model(*args, **kwargs):
        await asyncio.sleep(1.1)
        await kwargs['on_content_reset']()
        await asyncio.sleep(0.1)
        return '{}'
    monkeypatch.setattr(service, '_call_llm', model)
    result = await service._call_llm_with_heartbeat(
        'user', 'system', enable_thinking=False, on_phase=None, phase='outline_generation',
        base_progress=33, stage_timeout_seconds=1, wall_timeout_seconds=1,
        heartbeat_seconds=0.05, start_on_provider_request=True,
    )
    assert result == '{}'


@pytest.mark.asyncio
async def test_default_task_completes_without_framework_wait(tmp_path, monkeypatch):
    from backend.tests.test_generation_version_workflow import MemoryStorage
    from course_repository import CourseDocumentRepository
    from course_versions import CourseVersionRepository
    from generation_workspace import GenerationWorkspaceRepository
    from jobs.manager import TaskManager
    import jobs.manager as module
    monkeypatch.setattr(module, 'TASKS_FILE', tmp_path / 'tasks.json')
    service = CourseService()
    calls = []
    async def model(*args, **kwargs):
        calls.append(kwargs)
        return json.dumps(payload(), ensure_ascii=False)
    monkeypatch.setattr(service, '_call_llm', model)
    storage = MemoryStorage()
    manager = TaskManager(storage, service, None,
        version_repository=CourseVersionRepository(tmp_path / 'versions'),
        workspace_repository=GenerationWorkspaceRepository(tmp_path / 'workspaces'),
        document_repository=CourseDocumentRepository(storage))
    job = await manager._create_generation_job({'subject':'数据分析方法',
        'teacher_authoring_mode':'lesson_assets_v1',
        'teacher_course_brief':{'lecture_count':2,'total_class_hours':2,'teaching_context':'classroom'}})
    assert await manager._task_queue.get() == job['job_id']
    await manager._process_task(job['job_id'])
    assert manager.tasks[job['job_id']]['status'] == 'completed'
    assert manager.tasks[job['job_id']]['phase'] == 'teacher_outline_ready'
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_outline_repair_budget_includes_previous_output_but_keeps_context_limit(monkeypatch):
    service = CourseService()
    bad = payload()
    bad['lectures'].pop()
    bad['positioning'] = '用于验证完整响应计入结构修复预算。' * 800
    calls = []
    async def model(*args, **kwargs):
        calls.append(kwargs)
        return json.dumps(bad if len(calls) == 1 else payload(), ensure_ascii=False)
    monkeypatch.setattr(service, '_call_llm', model)
    result = await generate(service)
    assert result['outline_generation_status'] == 'completed'
    assert len(calls) == 2
    assert calls[1]['max_input_tokens'] > calls[0]['max_input_tokens']
    assert calls[1]['max_input_chars'] > calls[0]['max_input_chars']

    constrained = CourseService()
    constrained._generation_budget = replace(constrained._generation_budget, context_window_tokens=25000)
    calls.clear()
    monkeypatch.setattr(constrained, '_call_llm', model)
    with pytest.raises(CourseGenerationBudgetExceeded):
        await generate(constrained)
    assert len(calls) == 1
