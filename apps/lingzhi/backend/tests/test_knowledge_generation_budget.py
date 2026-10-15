from dataclasses import replace

import pytest

from ai_base import AIRequestBudgetExceeded
from backend.tests.test_knowledge_first import svc
from backend.tests.test_handout_knowledge import handouts
from knowledge_generation_budget import KnowledgeTreeBudget


@pytest.fixture
def budget(monkeypatch):
    for name in ('COURSE_KNOWLEDGE_TREE_MAX_INPUT_TOKENS', 'COURSE_KNOWLEDGE_TREE_MAX_INPUT_CHARS',
                 'COURSE_KNOWLEDGE_TREE_MAX_OUTPUT_TOKENS', 'COURSE_KNOWLEDGE_TREE_REQUEST_TIMEOUT_SECONDS'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('COURSE_GENERATION_CONTEXT_WINDOW_TOKENS', '131072')
    monkeypatch.setenv('COURSE_GENERATION_CONTEXT_RESERVE_TOKENS', '1024')
    return KnowledgeTreeBudget.from_env()


def test_extracting_knowledge_reserves_output_and_ignores_handout_limits(budget, monkeypatch):
    monkeypatch.setenv('COURSE_TEACHER_HANDOUT_MAX_INPUT_TOKENS', '2048')
    monkeypatch.setenv('COURSE_TEACHER_HANDOUT_MAX_INPUT_CHARS', '8000')
    value = KnowledgeTreeBudget.from_env()
    assert value == budget
    assert value.max_input_tokens == 131072 - 32000 - 1024
    assert value.validate('知' * 40000, '') == 48000
    assert value.call_options() == {'max_input_tokens': value.max_input_tokens,
        'max_input_chars': value.max_input_chars, 'max_tokens': 32000, 'request_timeout_seconds': 600}


@pytest.mark.parametrize('input_setting', ['999999999', 'broken'])
def test_input_override_never_consumes_the_output_reservation(budget, monkeypatch, input_setting):
    monkeypatch.setenv('COURSE_KNOWLEDGE_TREE_MAX_INPUT_TOKENS', input_setting)
    value = KnowledgeTreeBudget.from_env()
    assert value.max_input_tokens + value.max_output_tokens + value.context_reserve_tokens <= value.context_window_tokens


def test_exact_input_boundary_includes_both_messages(budget):
    value = replace(budget, max_input_tokens=100, max_input_chars=1000)
    assert value.validate('a' * 317, 'abc') == 100
    with pytest.raises(AIRequestBudgetExceeded):
        value.validate('a' * 318, 'abc')


def test_character_override_is_independent_of_token_estimate(budget, monkeypatch):
    monkeypatch.setenv('COURSE_KNOWLEDGE_TREE_MAX_INPUT_CHARS', '1000')
    value = KnowledgeTreeBudget.from_env()
    with pytest.raises(AIRequestBudgetExceeded, match='char_limit=1000'):
        value.validate('a' * 1001, '')


def test_impossible_context_configuration_stays_blocked(budget, monkeypatch):
    monkeypatch.setenv('COURSE_GENERATION_CONTEXT_WINDOW_TOKENS', '32768')
    value = KnowledgeTreeBudget.from_env()
    with pytest.raises(AIRequestBudgetExceeded):
        value.validate('an input', '')


@pytest.mark.asyncio
async def test_actual_context_overflow_is_recorded_before_constructing_provider(svc, budget, monkeypatch):
    handouts(svc)
    monkeypatch.setenv('COURSE_KNOWLEDGE_TREE_MAX_INPUT_TOKENS', '1')
    svc.provider_factory = lambda: pytest.fail('oversize request constructed a provider')
    view = svc.view('c-pilot', source_mode='handouts')
    job, _ = svc.start('c-pilot', 'tree', 'real-limit', '', view['document_revision'], source_mode='handouts', lesson_id='cpu')
    await svc.run('c-pilot', job['id'])
    saved = svc.authoring.get_job('c-pilot', job['id'])
    assert saved['status'] == 'failed'
    assert saved['error']['model_request_sent'] is False
    assert saved['error']['request_budget'] == saved['request_budget']
    assert saved['request_budget']['estimated_input_tokens'] > saved['request_budget']['max_input_tokens']
    assert not saved.get('partial_text')
    assert saved['request_snapshot'] == job['request_snapshot']
