from collections import Counter
from copy import deepcopy

import pytest

from assessment_blueprint import compile_course_assessment_blueprint
from backend.tests.test_atomic_assessment import atomic_course
from backend.tests.test_assessment_measurement_design import context, plan
from backend.tests.test_knowledge_mastery import attempt, project


def test_default_atomic_plan_has_three_stable_distinct_variants():
    course = atomic_course()
    course.pop('assessment_variant_count', None)
    slots = compile_course_assessment_blueprint(course)['nodes'][0]['slots']
    assert len(slots) == 6
    assert Counter(s['primary_knowledge_ids'][0] for s in slots) == {'division': 3, 'conversion': 3}
    assert len({s['generation_key'] for s in slots}) == 6
    assert {s['variant_role'] for s in slots} == {'direct', 'contrast', 'transfer'}
    previous = deepcopy(course)
    previous['assessment_variant_count'] = 1
    old = compile_course_assessment_blueprint(previous)['nodes'][0]['slots']
    assert [s['generation_key'] for s in slots if s['variant_index'] == 0] == [s['generation_key'] for s in old]
    course['course_knowledge_base']['knowledge_points'][0]['revision_id'] = 'new'
    assert [s['generation_key'] for s in compile_course_assessment_blueprint(course)['nodes'][0]['slots']] == [s['generation_key'] for s in slots]


@pytest.mark.parametrize('count', [0, 4, True, '3'])
def test_variant_count_rejects_invalid_budget(count):
    course = atomic_course()
    course['assessment_variant_count'] = count
    with pytest.raises(ValueError, match='assessment_variant_count'):
        compile_course_assessment_blueprint(course)


def test_balanced_choice_positions_ignore_model_bias_and_preserve_option_meanings():
    from assessment_variants import ChoicePositionAllocator
    from assessment_measurement_design import candidate_from_measurement_design
    allocator = ChoicePositionAllocator()
    answers = []
    for n in range(27):
        c = {**context(f'slot-{n}'), 'private_measurement_design': plan()}
        before = deepcopy(c)
        q = candidate_from_measurement_design(c, position_allocator=allocator)
        answer = q['solution']['canonical_answer']
        assert next(o['text'] for o in q['question_spec']['options'] if o['id'] == answer) == '2'
        answers.append(answer)
        assert c == before
    counts = Counter(answers)
    assert set(counts) == {'A', 'B'}
    assert abs(counts['A'] - counts['B']) == 1


def test_same_variant_new_revision_is_one_evidence_but_distinct_variants_accumulate():
    rows = [attempt(i, assessment_evidence_key='variant-1') for i in range(1, 4)]
    node = project(rows)['nodes'][0]
    assert node['independent_count'] == 1
    assert node['mastery'] == 66.7
    rows += [attempt(4, assessment_evidence_key='variant-2'), attempt(5, assessment_evidence_key='variant-3')]
    assert project(rows)['nodes'][0]['independent_count'] == 3
    assert project(rows)['nodes'][0]['mastery'] == 80
    rows += [attempt(6, False, assessment_evidence_key='variant-2')]
    assert project(rows)['nodes'][0]['mastery'] == 60


def test_variant_identity_is_frozen_in_repository(tmp_path):
    from practice_attempts import PracticeAttemptRepository
    repo = PracticeAttemptRepository(tmp_path)
    saved, _ = repo.create_once('u', 'c', {'task_revision_id': 'q', 'assessment_evidence_key': 'variant-2'})
    assert repo.get('u', 'c', saved['attempt_id'])['assessment_evidence_key'] == 'variant-2'


def test_variant_prompt_changes_observation_instead_of_only_numbers():
    from assessment_measurement_design import measurement_design_prompt
    c = context()
    c['assessment_slot'].update(variant_role='contrast', variant_index=1)
    prompt = measurement_design_prompt([c])
    assert 'contrast' in prompt
    assert '不能仅' in prompt
