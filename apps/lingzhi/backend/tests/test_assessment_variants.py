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


def test_cosmetic_code_variant_is_a_blocking_quality_issue():
    from assessment_quality import evaluate_question_contract_quality
    def question(code, key):
        return {'assessment_binding_schema': 'atomic_assessment_v1', 'primary_knowledge_ids': ['k'],
                'generation_key': key, 'question_spec': {'stimulus': {'rendered_text': code}}}
    first = question('```c\nint a=-7,b=2; int c=a/b;\n```', 'v1')
    second = question('```c\nint x=-9,y=4; int z=x/y; // changed names\n```', 'v2')
    report = evaluate_question_contract_quality(second, objective={}, slot={}, existing_questions=[first])
    assert any(i['code'] == 'COSMETIC_ATOMIC_VARIANT' and i['severity'] == 'critical' for i in report['issues'])


def test_code_variant_fingerprint_preserves_structure_but_ignores_names_comments_numbers():
    from assessment_variants import atomic_material_fingerprint
    def q(code):
        return {'question_spec': {'stimulus': {'rendered_text': '```c\n'+code+'\n```'}}}
    assert atomic_material_fingerprint(q('int a=7; a++;')) == atomic_material_fingerprint(q('int z=8; z++; // comment'))
    assert atomic_material_fingerprint(q('int a=7; a++;')) != atomic_material_fingerprint(q('int a=7; --a;'))
    assert atomic_material_fingerprint(q('int a=7; int b=a;')) != atomic_material_fingerprint(q('int a=7; int b=b;'))


def test_repair_keeps_position_and_each_option_arity_balances():
    from assessment_variants import ChoicePositionAllocator
    allocator = ChoicePositionAllocator()
    for size in (2, 3, 4, 8):
        values = [allocator.allocate(f'q-{i}', size) for i in range(size * 3)]
        assert Counter(values) == {i: 3 for i in range(size)}
        assert allocator.allocate('q-0', size) == values[0]


@pytest.mark.parametrize('kind', ['assignment_sequence', 'conversion_scope', 'syntactic_binding', 'uncontrolled_statement', 'condition_evaluation_trace', 'next_control_action', 'exit_state', 'direct_value'])
def test_semantic_variant_strategies_offer_distinct_instructions(kind):
    from assessment_variants import variant_instruction
    values = [variant_instruction({'variant_role': role}, kind) for role in ('direct', 'contrast', 'transfer')]
    assert len(set(values)) == 3


def test_variant_budget_is_part_of_resume_source_identity():
    from routers.question_bank import _question_source_revision
    course = atomic_course()
    course['assessment_variant_count'] = 1
    old = _question_source_revision(course)
    course['assessment_variant_count'] = 3
    assert _question_source_revision(course) != old


@pytest.mark.asyncio
async def test_orchestrator_plans_all_variants_and_resumes_exactly_one(monkeypatch):
    from assessment_orchestrator import AssessmentGenerationOrchestrator
    from knowledge_question_supply import select_knowledge_slots
    course = atomic_course()
    course['assessment_variant_count'] = 3
    runner = AssessmentGenerationOrchestrator(model=object())
    seen = []
    async def generate(**kw):
        seen.append(kw['objective']['knowledge'])
        return 'concept_check', {'generation_status': 'ready'}, {'final_decision': 'publish'}, None
    monkeypatch.setattr(runner, '_generate_slot_contract', generate)
    blueprint = compile_course_assessment_blueprint(course)
    selection = select_knowledge_slots(blueprint, ['division'], ['types'])
    assert len(selection['types']) == 3
    prepared = await runner.prepare_course(course, node_ids=['types'], practice_levels_by_node=selection)
    contracts = prepared['_assessment_generated_contracts']['types']
    assert set(contracts) == set(selection['types'])
    assert {q['variant_role'] for q in contracts.values()} == {'direct', 'contrast', 'transfer'}
    assert all(q['assessment_evidence_key'] == key for key, q in contracts.items())
    assert len(seen) == 3
    seen.clear()
    await runner.prepare_course(course, node_ids=['types'], practice_levels_by_node={'types': [selection['types'][1]]})
    assert len(seen) == 1


def test_seen_answer_and_hints_do_not_become_independent_variants():
    rows = [attempt(1, assessment_evidence_key='v1'), attempt(2, assessment_evidence_key='v1', solution_revealed=True),
            attempt(3, assessment_evidence_key='v2', revealed_hint_levels=[1]), attempt(4, assessment_evidence_key='v3')]
    node = project(rows)['nodes'][0]
    assert node['independent_count'] == 2
    assert node['status'] != 'supported_mastery'
    assert node['mastery'] == 76.5


def test_attempt_api_freezes_server_variant_key_not_client_input(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import learning_events
    from practice_attempts import PracticeAttemptRepository
    from routers import practice as router
    from backend.tests.test_practice_attempts import _course, MemoryStorage
    course = _course()
    course['learning_assets']['questions'][0]['assessment_evidence_key'] = 'server-variant'
    async def get_course(_):
        return course
    repo = PracticeAttemptRepository(tmp_path)
    monkeypatch.setattr(router, 'get_course_or_404', get_course)
    monkeypatch.setattr(router, 'practice_attempt_repository', repo)
    monkeypatch.setattr(learning_events, 'storage', MemoryStorage())
    app = FastAPI()
    app.include_router(router.router, prefix='/api')
    client = TestClient(app, headers={'X-User-Id': 'u1'})
    response = client.post('/api/courses/c1/practice/attempts', json={
        'question_revision_id': 'qr1', 'assessment_evidence_key': 'forged-new-independent-evidence'})
    assert response.status_code == 200, response.text
    saved = repo.get('u1', 'c1', response.json()['attempt']['attempt_id'])
    assert saved['assessment_evidence_key'] == 'server-variant'


def test_contrast_plan_is_not_collapsed_back_to_single_direct_instance():
    from assessment_measurement_design import attach_measurement_designs
    c = context()
    c['assessment_slot'].update(variant_role='contrast', knowledge=['赋值目标类型不会反向决定运算类型'])
    p = plan()
    p.update(public_material='```c\nint a=7/2; double b=7/2;\n```', ask='a和b的数值依次是多少？')
    rendered = attach_measurement_designs([c], {'plans': [{'slot_id': 'slot-a', 'plan': p}]})
    assert rendered[0]['private_measurement_design'] == p


@pytest.mark.asyncio
async def test_production_renderer_balances_a_provider_that_always_returns_b():
    import json
    from assessment_generation_policy import resolve_assessment_generation_policy
    from assessment_orchestrator import UniversalAssessmentModel
    model = object.__new__(UniversalAssessmentModel)
    calls = []
    async def call(policy, prompt, **kwargs):
        calls.append(policy.stage)
        p = plan()
        p.update(options=['3', '2'], correct_option_index=1)
        return json.dumps({'plans': [{'slot_id': f'slot-{len(calls)}', 'plan': p}]})
    model._assessment_llm_call = call
    answers = []
    for n in range(1, 28):
        c = context(f'slot-{n}')
        candidate = await model.generate_candidate(c, call_policy=resolve_assessment_generation_policy(None).call_policy('generate', c))
        answer = candidate['solution']['canonical_answer']
        assert next(o['text'] for o in candidate['question_spec']['options'] if o['id'] == answer) == '2'
        answers.append(answer)
        assert 'option_position_receipt' not in json.dumps(candidate['question_spec'])
    assert sorted(Counter(answers).values()) == [13, 14]
    assert set(calls) == {'design'}


def test_first_keyed_retry_of_legacy_question_does_not_double_count_old_attempt():
    old = attempt(1, task_revision_id='legacy-q')
    new = attempt(2, task_revision_id='legacy-q', assessment_evidence_key='variant-1')
    node = project([old, new])['nodes'][0]
    assert node['independent_count'] == 1
    assert node['mastery'] == 66.7
    new['result']['passed'] = False
    assert project([old, new])['nodes'][0]['mastery'] == 33.3
