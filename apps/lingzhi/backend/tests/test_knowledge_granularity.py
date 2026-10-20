"""Granularity is a frozen generation policy, not personal mastery evidence."""
import json
from copy import deepcopy

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course, start
from backend.tests.test_knowledge_tree_relations import fake_provider


POLICY = 'knowledge_granularity_v1'


def payload(prompt):
    return json.loads(prompt.split('\nINPUT_JSON:\n', 1)[1])


def test_extract_policy_preserves_source_and_response_contract(svc, monkeypatch):
    from knowledge_extract import extraction_prompt

    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot')
    context = svc._context(raw, 'handouts', 'cpu')
    before = deepcopy(context)
    old = payload(extraction_prompt(raw, context, ['S1']))
    new = payload(extraction_prompt(raw, {**context, 'granularity_contract': POLICY}, ['S1']))
    policy = new.pop('granularity_policy', None)
    assert policy and policy['contract'] == POLICY
    assert new == old  # Same complete input sources and existing wire protocol.
    assert context == before
    assert {'check_items', 'learner_records'} <= set(policy['not_knowledge'])
    assert policy['split_when'] and policy['keep_together'] and policy['source_boundary']
    assert policy.get('representation', {}).get('rule_form') == 'fact'
    assert policy['representation'].get('rule_preconditions_field') == 'conditions'


def test_unknown_policy_cannot_silently_fall_back(svc, monkeypatch):
    from knowledge_extract import extraction_prompt

    setup_course(svc, monkeypatch)
    context = svc._context(svc.repository.load_raw('c-pilot'), 'handouts', 'cpu')
    with pytest.raises(ValueError, match='颗粒度'):
        extraction_prompt({}, {**context, 'granularity_contract': 'future-unsupported'}, ['S1'])


@pytest.mark.asyncio
@pytest.mark.parametrize('legacy', [False, True])
async def test_new_jobs_freeze_policy_and_old_checkpoints_keep_old_policy(svc, monkeypatch, legacy):
    setup_course(svc, monkeypatch)
    before = deepcopy(svc.repository.load_raw('c-pilot'))
    fake_provider(svc)
    factory = svc.provider_factory
    calls = []

    def recording_provider():
        provider = factory()
        original_call = provider._call_llm

        async def call(prompt, **kwargs):
            data = payload(prompt)
            calls.append((data['stage'], data))
            return await original_call(prompt, **kwargs)

        provider._call_llm = call
        return provider

    svc.provider_factory = recording_provider
    job = start(svc, extraction_mode='single_pass_v1')
    if legacy:
        # A pre-upgrade checkpoint with no policy must not be upgraded on resume.
        from knowledge_extract import extraction_groups
        context = job['request_snapshot']['knowledge_generation_context']
        pipeline = {'schema_version': 'inventory_atomic_v1',
                    'processing_contract': 'knowledge_validation_pipeline_v3',
                    'prompt_contract': 'knowledge_extract_v9', 'revision': 0,
                    'items': [], 'batches': [], 'extraction_mode': 'single_pass_v1',
                    'inventory_batches': [{'id': f'inventory-{i}', 'source_keys': keys, 'status': 'pending'}
                                          for i, keys in enumerate(extraction_groups(context), 1)]}
        svc.authoring.update_job('c-pilot', job['id'], checkpoint={'atomic_pipeline': pipeline})
    await svc.run('c-pilot', job['id'])
    saved = svc.authoring.get_job('c-pilot', job['id'])
    assert saved['status'] == 'completed', saved.get('error')
    pipeline = saved['checkpoint']['atomic_pipeline']
    assert pipeline.get('granularity_contract') == (None if legacy else POLICY)
    for stage, data in calls:
        if stage in {'extract', 'content_review'}:
            assert (data.get('granularity_policy') or {}).get('contract') == (None if legacy else POLICY)
    assert saved['checkpoint']['candidate'].get('granularity_contract') == (None if legacy else POLICY)
    assert pipeline.get('expression_contract') == (None if legacy else 'knowledge_expression_v1')
    assert saved['checkpoint']['candidate'].get('expression_contract') == (None if legacy else 'knowledge_expression_v1')
    assert svc.repository.load_raw('c-pilot') == before


def test_split_proposal_uses_same_content_and_diagnostic_boundaries():
    from course_knowledge_refinement import build_split_prompt

    point = {'name': '链式法则', 'statement': '(f(g(x)))′=f′(g(x))g′(x)',
             'conditions': ['内外函数在对应点可导']}
    before = deepcopy(point)
    prompt = build_split_prompt(point)
    assert 'GRANULARITY_POLICY_JSON:\n' in prompt
    policy = json.loads(prompt.split('GRANULARITY_POLICY_JSON:\n', 1)[1].split('\n', 1)[0])
    assert policy['contract'] == POLICY
    assert {'check_items', 'learner_records'} <= set(policy['not_knowledge'])
    assert point == before


@pytest.mark.asyncio
async def test_review_uses_frozen_policy_without_creating_checks_or_student_records(svc, monkeypatch):
    from knowledge_content_review import review_content
    from backend.tests.test_knowledge_extraction_repair import point, value

    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot')
    context = {**svc._context(raw, 'handouts', 'cpu'), 'granularity_contract': POLICY}
    original = value([point()])
    before = deepcopy(original)
    seen = []

    async def call(*args):
        seen.append(payload(args[-2]))
        return json.dumps({'point_reviews': {'S1.1:0': {'decision': 'keep', 'points': [], 'reason': '完整单一规则'}},
                           'additions': {'S1.1': []}, 'source_issues': []})

    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    record = {}
    reviewed = await review_content(svc, 'c-pilot', 'isolated', None, raw, context, ['S1'], original, record)
    assert seen[0]['granularity_policy']['contract'] == POLICY
    assert reviewed['passages'] == original['passages']
    assert record['granularity_contract'] == POLICY
    assert not record['semantics_verified']
    assert original == before


def test_policy_preserves_legacy_prompt_and_rejects_missing_input():
    from knowledge_granularity import apply_policy, policy_payload

    old = 'frozen old prompt without JSON'
    assert apply_policy(old) == old
    with pytest.raises(ValueError, match='冻结输入'):
        apply_policy(old, POLICY)
    first = policy_payload()
    first['split_when'].clear()
    assert policy_payload()['split_when']  # No shared mutable policy state.
