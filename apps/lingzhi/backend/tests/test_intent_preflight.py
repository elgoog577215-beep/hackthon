from copy import deepcopy
from types import MethodType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.tests.test_teacher_course_change import context
from course_evolution import CourseEvolutionRepository
from course_evolution.teacher_planning import create_teacher_course_change_plan
from course_generation.service import CourseService


def assessment(ambiguous=False):
    return {'interpreted_goal': '确认设计思维流程的修改方式', 'signal_kind': 'semantic',
            'affected_units': [], 'structure': {'required': False},
            'clarifications': [{'question_id': 'action', 'prompt': '希望对流程做什么修改？',
                'response_type': 'single_choice', 'required': True, 'options': [
                    {'option_id': 'overview', 'label': '补充流程概览', 'impact': '完善现有第一讲'},
                    {'option_id': 'reorder', 'label': '调整课程顺序', 'impact': '重排现有讲次'},
                ]}] if ambiguous else [], 'blocking_questions': []}


@pytest.mark.asyncio
async def test_ambiguous_request_clarifies_before_scanning_and_never_claims_coverage(tmp_path):
    scan = AsyncMock()
    gate = AsyncMock(return_value=assessment(True))
    state = await create_teacher_course_change_plan(
        context=context(), user_id='teacher', request_id='unclear', instruction='先将设计思维的一套流程',
        repository=CourseEvolutionRepository(tmp_path), analyzer=scan, intent_analyzer=gate)
    scan.assert_not_called()
    plan = state.change_sets[-1]
    assert plan.teacher_change_planning.status == 'needs_clarification'
    assert len(plan.teacher_change_planning.intent.clarifications) == 1
    assert not plan.teacher_change_planning.intent.system_blockers
    assert not plan.operations
    assert plan.impact_summary['coverage']['scanned_units'] == 0
    assert len(plan.impact_summary['coverage']['unscanned_unit_ids']) == len(context().units)


@pytest.mark.asyncio
async def test_clear_request_caches_intent_and_preserves_full_scan_on_resume(tmp_path):
    gate = AsyncMock(return_value=assessment())
    scan = AsyncMock(return_value={'affected_units': [], 'structure': {'required': False}})
    checkpoints = []
    async def progress(detail, saved):
        checkpoints.append(deepcopy(saved))
    args = dict(context=context(), user_id='teacher', instruction='所有例子补充适用条件',
                repository=CourseEvolutionRepository(tmp_path), analyzer=scan,
                intent_analyzer=gate, on_scan_progress=progress)
    state = await create_teacher_course_change_plan(**args, request_id='clear')
    assert not state.change_sets[-1].impact_summary['coverage']['unscanned_unit_ids']
    assert scan.call_count > 0
    assert all(call.args[0]['intent_assessment']['interpreted_goal'] for call in scan.call_args_list)
    assert checkpoints[-1]['intent_preflight']['result']['interpreted_goal']
    await create_teacher_course_change_plan(**args, request_id='resume', scan_checkpoint=checkpoints[-1])
    assert gate.call_count == 1


@pytest.mark.asyncio
async def test_preflight_failure_is_a_system_error_without_a_fake_question_plan(tmp_path):
    repo = CourseEvolutionRepository(tmp_path)
    with pytest.raises(RuntimeError, match='offline'):
        await create_teacher_course_change_plan(
            context=context(), user_id='teacher', request_id='failure', instruction='详细讲解流程',
            repository=repo, analyzer=AsyncMock(), intent_analyzer=AsyncMock(side_effect=RuntimeError('offline')))
    assert not repo.load('teacher', context().course_id).change_sets


@pytest.mark.asyncio
async def test_intent_model_call_keeps_bounded_output_and_approved_provider_contract():
    call = AsyncMock(return_value='{"interpreted_goal":"补充流程","affected_units":[]}')
    service = SimpleNamespace(_call_llm=call)
    service._extract_json = MethodType(CourseService._extract_json, service)
    result = await CourseService.analyze_teacher_course_change_intent(service, {}, [], '补充流程')
    assert result['interpreted_goal'] == '补充流程'
    assert call.call_args.kwargs['max_tokens'] == 1600
    assert call.call_args.kwargs['model_role'] == 'teacher_course_change_intent'
    assert call.call_args.kwargs['max_attempts'] == 1
    assert call.call_args.kwargs['wait_for_capacity'] is True
