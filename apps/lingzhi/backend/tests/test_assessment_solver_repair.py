from copy import deepcopy
import json

import pytest

from assessment_blueprint import compile_course_assessment_blueprint, slot_for
from assessment_contracts import compile_assessment_objectives, compile_course_assessment_profile
from assessment_generation import generate_universal_question_contract
from assessment_generation_policy import resolve_assessment_generation_policy
from assessment_orchestrator import AssessmentGenerationOrchestrator, UniversalAssessmentModel
from backend.tests.test_assessment_generation_orchestrator import RepairingModel, _course, _proposal


@pytest.mark.parametrize('batch', [False, True])
async def test_complete_choice_solution_has_room_for_derivation_and_every_option(monkeypatch, batch):
    monkeypatch.delenv('ASSESSMENT_MIN_OUTPUT_TOKENS', raising=False)
    model = UniversalAssessmentModel()
    calls = []
    async def call(prompt, **kwargs):
        calls.append(kwargs)
        return json.dumps({'answer': 'A', 'solutions': [{'slot_id': 's', 'solution': {'answer': 'A'}}]})
    monkeypatch.setattr(model, '_call_llm', call)
    spec = {'input_contract': {'mode': 'choice'}, 'options': [{'id': k, 'text': k} for k in 'ABCD']}
    policy = resolve_assessment_generation_policy('complete').call_policy('solve', {'question_spec': spec})
    if batch:
        await model.solve_candidate_batch([{'slot_id': 's', 'question_spec': spec}], call_policy=policy)
    else:
        await model.solve_candidate(spec, call_policy=policy)
    assert calls[0]['max_tokens'] >= 6144
    assert calls[0]['reject_truncated'] is True
    assert calls[0]['max_attempts'] == 1


def case():
    course = _course()
    profile = compile_course_assessment_profile(course)
    objective = compile_assessment_objectives(course, profile)[0]
    slot = slot_for(compile_course_assessment_blueprint(course), 'thermo-1', 'concept_check')
    candidate = _proposal(12, {'assessment_slot': slot, 'objective': objective})
    base = generate_universal_question_contract(course, course['nodes'][0], profile=profile,
        objective=objective, slot=slot, practice_level='concept_check', variant_index=0, references=[])
    return base, candidate


async def test_private_answer_repair_reuses_blind_solve_and_revalidates_new_answer():
    base, candidate = case()
    candidate['solution']['canonical_answer'] = 'B'
    model = RepairingModel()
    runner = AssessmentGenerationOrchestrator(model=model)
    audit = {'independent_solution_calls': 0}
    policy = resolve_assessment_generation_policy('complete')
    cache, budget = {}, {'used': 0, 'limit': 2}
    _, validation, _ = await runner._solve_and_build(base, candidate, audit,
        generation_policy=policy, solution_batcher=None, solve_budget=budget, solution_cache=cache)
    assert not validation['passed']
    candidate['solution']['canonical_answer'] = 'A'
    _, validation, _ = await runner._solve_and_build(base, candidate, audit,
        generation_policy=policy, solution_batcher=None, solve_budget=budget, solution_cache=cache)
    assert validation['passed']
    assert model.solve_calls == budget['used'] == 1
    assert audit['independent_solution_reuse_count'] == 1
    assert all('canonical_answer' not in repr(spec) for spec in model.solve_payloads)


@pytest.mark.parametrize('change', ['options', 'feedback'])
async def test_changed_public_question_or_explicit_explanation_retry_needs_a_new_solve(change):
    base, candidate = case()
    model = RepairingModel()
    runner = AssessmentGenerationOrchestrator(model=model)
    audit, cache, budget = {'independent_solution_calls': 0}, {}, {'used': 0, 'limit': 2}
    kwargs = dict(generation_policy=resolve_assessment_generation_policy('complete'),
                  solution_batcher=None, solve_budget=budget, solution_cache=cache)
    await runner._solve_and_build(base, candidate, audit, **kwargs)
    if change == 'options':
        candidate['question_spec']['options'][0]['label'] += '（按本题约定）'
    await runner._solve_and_build(base, candidate, audit,
        solver_feedback=['EXPLANATION_CONTRADICTION'] if change == 'feedback' else None, **kwargs)
    assert model.solve_calls == budget['used'] == 2


async def test_explanation_correction_replaces_the_prior_cached_derivation():
    class RevisedWorkModel(RepairingModel):
        async def solve_candidate(self, spec):
            result = await super().solve_candidate(spec)
            result['summary'] = f'第{self.solve_calls}次独立推导：' + result['summary']
            return result
    base, candidate = case()
    model = RevisedWorkModel()
    runner = AssessmentGenerationOrchestrator(model=model)
    kwargs = dict(generation_policy=resolve_assessment_generation_policy('complete'),
                  solution_batcher=None, solve_budget={'used':0,'limit':2}, solution_cache={})
    audit = {'independent_solution_calls':0}
    await runner._solve_and_build(base, candidate, audit, **kwargs)
    await runner._solve_and_build(base, candidate, audit, solver_feedback=['EXPLANATION_CONTRADICTION'], **kwargs)
    candidate['solution']['rubric'] = ['核对两项正负号约定']
    _, _, independent = await runner._solve_and_build(base, candidate, audit, **kwargs)
    assert model.solve_calls == 2
    assert independent['summary'].startswith('第2次独立推导')


async def test_no_correct_option_repairs_the_options_then_solves_the_changed_question():
    class MissingOptionModel(RepairingModel):
        async def generate_candidate(self, context):
            proposal = await super().generate_candidate(context)
            proposal['question_spec']['task']['rendered_text'] = '根据热力学第一定律，选择该过程内能变化的正确数值。'
            proposal['question_spec']['options'] = [{'id': k, 'text': str(v) + ' kJ'}
                for k, v in zip('ABCD', [10, 14, 20, 8])]
            return proposal

        async def solve_candidate(self, spec):
            self.solve_calls += 1
            right = [o['id'] for o in spec['options'] if o.get('text') == '12 kJ']
            return {'answer': right[0] if right else '无正确选项', 'summary': '内能增加12 kJ。',
                'work': [{'title': '代入', 'explanation': 'ΔU=Q-W=20-8=12 kJ。', 'result': '12 kJ'}],
                'checks': ['ΔU+W=12+8=20 kJ'], 'option_analysis': [
                    {'option_id': o['id'], 'is_correct': o['id'] in right,
                     'explanation': '与20-8=12 kJ的计算结果一致。' if o['id'] in right else '与20-8=12 kJ的计算结果不符。'}
                    for o in spec['options']]}

        async def repair_candidate(self, context, candidate, validation):
            self.repair_calls += 1
            assert 'CHOICE_OPTIONS_INVALID' in context['issue_codes']
            changed = deepcopy(candidate)
            changed['question_spec']['options'][1]['text'] = '12 kJ'
            changed['solution']['canonical_answer'] = 'B'
            return changed

    model = MissingOptionModel()
    prepared = await AssessmentGenerationOrchestrator(model=model).prepare_course(_course(),
        node_ids=['thermo-1'], practice_levels_by_node={'thermo-1': ['concept_check']})
    item = prepared['_assessment_generated_contracts']['thermo-1']['concept_check']
    audit = prepared['_assessment_generation_audit']['items'][0]
    assert item['quality_report'].get('passed'), {k: audit.get(k) for k in ('error_code', 'error_message', 'attempts')}
    assert item['question_spec']['options'][1]['text'] == '12 kJ'
    assert model.solve_calls == 2 and model.repair_calls == 1
