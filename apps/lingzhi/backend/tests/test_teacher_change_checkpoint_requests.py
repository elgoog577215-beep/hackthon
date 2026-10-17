from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.tests.test_task_manager_runtime_durability import build_manager
from course_evolution.jobs import enqueue_analysis, run_analysis


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['unchanged', 'instruction', 'assets', 'answers', 'confirmed', 'literal', 'force', 'rescan', 'legacy_unverifiable'])
async def test_new_analysis_only_inherits_a_compatible_request_checkpoint(tmp_path, monkeypatch, change):
    manager = build_manager(tmp_path, monkeypatch)
    original = await enqueue_analysis(manager=manager, user_id='teacher', course_id='course-1',
        request_id='old', instruction='先将设计思维的一套流程', asset_types=['script', 'outline'])
    checkpoint = {'results': {'old-batch': {'affected_units': []}}, 'signature': 'legacy-scan'}
    manager.tasks[original['id']].update(status='completed', analysis_checkpoint=deepcopy(checkpoint),
                                        phase_detail={'plan_id': 'legacy-plan'})
    if change == 'legacy_unverifiable': manager.tasks[original['id']].pop('analysis_request_contract')
    manager.save_tasks(strict=True)
    manager.load_tasks()
    assert not manager.tasks[original['id']].get('request_snapshot')
    request = {'instruction': '先将设计思维的一套流程', 'asset_types': ['outline', 'script']}
    if change == 'instruction': request['instruction'] += '放到第一讲开头，保留其他讲次。'
    elif change == 'assets': request['asset_types'] = ['script']
    elif change == 'answers': request.update(clarification_set_id='answer-set', clarification_answers=[{'question_id':'q', 'option_id':'a'}])
    elif change == 'confirmed': request['confirmed_interpretation'] = True
    elif change == 'literal': request['literal_replacement'] = {'before':'原词','after':'新词'}
    elif change == 'force': request['force_full_scan'] = True
    elif change == 'rescan': request['rescan_incomplete_only'] = True
    task = await enqueue_analysis(manager=manager, user_id='teacher', course_id='course-1', request_id='new',
                                  supersedes_plan_id='legacy-plan', **request)
    received = []
    async def create(**kwargs):
        received.append(kwargs['scan_checkpoint'])
        return SimpleNamespace(change_sets=[SimpleNamespace(change_set_id='new-plan', impact_summary={'request_id':'new'})])
    await run_analysis(manager, task['id'], service=SimpleNamespace(create_teacher_plan=create))
    assert manager.tasks[task['id']]['status'] == 'completed'
    assert received == [checkpoint if change in {'unchanged', 'rescan'} else {}]
    assert manager.tasks[original['id']]['analysis_checkpoint'] == checkpoint


@pytest.mark.asyncio
async def test_same_task_resume_preserves_its_own_legacy_checkpoint(tmp_path, monkeypatch):
    manager = build_manager(tmp_path, monkeypatch)
    task = await enqueue_analysis(manager=manager, user_id='teacher', course_id='course-1', request_id='resume', instruction='原要求')
    checkpoint = {'results': {'complete': {'affected_units': []}}, 'signature': 'old-contract'}
    manager.tasks[task['id']]['analysis_checkpoint'] = deepcopy(checkpoint)
    async def create(**kwargs):
        assert kwargs['scan_checkpoint'] == checkpoint
        return SimpleNamespace(change_sets=[SimpleNamespace(change_set_id='resumed-plan', impact_summary={'request_id':'resume'})])
    await run_analysis(manager, task['id'], service=SimpleNamespace(create_teacher_plan=create))
    assert manager.tasks[task['id']]['status'] == 'completed'
