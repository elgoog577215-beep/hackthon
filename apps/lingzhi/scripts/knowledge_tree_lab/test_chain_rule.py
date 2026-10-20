"""A finite diagnostic sample must distinguish evidence, not guess beliefs."""
from copy import deepcopy

import pytest


def lab():
    from . import chain_rule
    return chain_rule


def observation(check, answer, *, key=None, **extra):
    bundle = lab().build_bundle()
    return {'event_id': key or check, 'activity_id': key or check, 'check_id': check,
            'user_id': 'sample-student', 'course_id': 'chain-sample',
            'knowledge_revision': bundle['revision'], 'response': answer,
            'passed': lab().grade_fixture(check, answer), 'support_level': 0,
            'answer_revealed': False, 'phase': 'diagnostic', **extra}


def correct(*keys):
    pack = lab().build_bundle()
    return [observation(key, pack['checks'][key]['accepted_answers'][0]) for key in keys]


def wrong(*keys):
    pack = lab().build_bundle()
    return [observation(key, pack['checks'][key]['wrong_answers'][0]) for key in keys]


@pytest.mark.parametrize('cause', ['structure', 'power', 'trig', 'evaluation', 'combination', 'transfer'])
def test_same_wrong_derivative_can_lead_to_different_limited_candidates(cause):
    module = lab()
    pack = module.build_bundle()
    rule = pack['hypotheses'][cause]
    events = wrong('trigger', *rule['fail_checks']) + correct(*rule['controls'])
    before = deepcopy(events)
    result = module.replay(events)
    assert result['candidate_ids'] == [cause]
    assert result['status'] == 'candidate'
    assert result['help']['target'] == cause
    assert result['help']['explanation']
    assert not result['mastery_updated'] and not result['diagnosis_confirmed']
    assert events == before


def test_original_error_alone_and_unknown_answer_are_insufficient():
    module = lab()
    result = module.replay(wrong('trigger'))
    assert result['status'] == 'insufficient' and result['candidate_ids'] == []
    assert result['next_checks'] == ['structure-1']
    assert module.grade_fixture('power-1', '这段话不能可靠判分') is None
    assert module.replay([observation('power-1', '不知道')])['status'] == 'insufficient'
    assert module.grade_fixture('combination-1', '5') is None
    assert module.grade_fixture('combination-2', '2') is None
    assert module.grade_fixture('combination-1', '我认为最终式子就是5，不需要其他因子') is False


def test_multiple_gaps_and_contradicting_checks_are_not_forced_to_one_cause():
    module = lab()
    result = module.replay(wrong('structure-1', 'structure-2', 'power-1', 'power-2'))
    assert set(result['candidate_ids']) == {'structure', 'power'}
    assert result['status'] == 'multiple_candidates'
    conflict = wrong('structure-1', 'structure-2') + [
        observation('structure-1', '内层x^2，外层sin(u)', key='different-activity')]
    result = module.replay(conflict)
    assert result['status'] == 'insufficient'
    assert result['check_states']['structure-1'] == 'conflicting'


@pytest.mark.parametrize('change', [
    {'support_level': 1}, {'answer_revealed': True},
    {'knowledge_revision': 'old-revision'}, {'user_id': 'someone-else'},
    {'course_id': 'other-course'}, {'check_id': 'unknown-check'},
    {'teacher_preview': True},
])
def test_help_exposure_and_wrong_scope_cannot_supply_independent_evidence(change):
    events = [dict(item, **change) for item in wrong('structure-1', 'structure-2')]
    result = lab().replay(events)
    assert result['candidate_ids'] == [] and result['excluded']


def test_duplicate_source_corrections_and_conflicting_copies_preserve_history():
    module = lab()
    first = wrong('structure-1')[0]
    duplicate = {**first, 'event_id': 'note-reference'}
    result = module.replay([first, duplicate])
    assert result['independent_activity_count'] == 1
    assert result['candidate_ids'] == []
    correction = {**first, 'event_id': 'grading-correction', 'passed': True,
                  'supersedes': first['event_id'], 'response': '内层x^2，外层sin(u)',
                  'correction_reason': '复核发现先前转录了另一份答案，保留原记录并更正解释'}
    result = module.replay([first, correction, *wrong('structure-2')])
    assert result['check_states']['structure-1'] == 'pass'
    assert result['history_event_count'] == 3
    conflicting_copy = {**duplicate, 'passed': True}
    result = module.replay([first, conflicting_copy, *wrong('structure-2')])
    assert result['candidate_ids'] == []
    assert any(item['reason'] == 'conflicting_activity' for item in result['excluded'])


def test_public_checks_do_not_disclose_answers_or_remediation():
    module = lab()
    pack = module.build_bundle()
    public = module.public_bundle()
    assert len(pack['knowledge']) == 5
    assert len(pack['checks']) >= 16
    for key, check in public['checks'].items():
        assert set(check) == {'check_id', 'prompt', 'knowledge_ids', 'dimension', 'context', 'role'}
        assert 'accepted_answers' not in check and 'wrong_answers' not in check
    assert 'hypotheses' not in public and 'help' not in public


def test_guided_success_and_unobserved_time_do_not_prove_help_effect():
    module = lab()
    guided = [dict(item, phase='verification', help_id='help-1', support_level=1)
              for item in correct('verify-1', 'verify-2')]
    result = module.help_effect(guided, help_id='help-1')
    assert result['status'] == 'pending'
    assert result['retention'] == 'not_observed'
    good = [dict(item, phase='verification', help_id='help-1')
            for item in correct('verify-1', 'verify-2')]
    assert module.help_effect(good, help_id='help-1')['status'] == 'short_term_independent_pass'
    bad = [dict(item, phase='verification', help_id='help-1')
           for item in wrong('verify-1', 'verify-2')]
    assert module.help_effect(bad, help_id='help-1')['status'] == 'no_clear_improvement'


def test_conflicting_verification_does_not_become_success_by_input_order():
    module = lab()
    good = [dict(item, phase='verification', help_id='help-1')
            for item in correct('verify-1', 'verify-2')]
    bad = dict(wrong('verify-1')[0], event_id='later-fail', activity_id='later-fail',
               phase='verification', help_id='help-1')
    for events in [good + [bad], [bad] + good]:
        assert module.help_effect(events, help_id='help-1')['status'] == 'pending'


@pytest.mark.parametrize('target', ['missing-event', 'correction', 'structure-1'])
def test_unexplained_or_invalid_correction_cannot_erase_evidence(target):
    first = wrong('structure-1')[0]
    correction = {**first, 'event_id': 'correction', 'passed': True, 'supersedes': target}
    result = lab().replay([first, correction, *wrong('structure-2')])
    assert result['candidate_ids'] == ['structure']
    assert any(item['reason'] == 'invalid_correction' for item in result['excluded'])
