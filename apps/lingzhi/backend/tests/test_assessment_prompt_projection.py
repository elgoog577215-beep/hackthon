"""Model inputs keep facts and constraints without duplicating backend contracts."""
from copy import deepcopy

from assessment_orchestrator import UniversalAssessmentModel, _prompt_generation_context, _batch_generation_prompt


def test_projection_preserves_evidence_and_does_not_mutate_validation_contracts():
    evidence = '源教材：队列删除空队列必须报错。' * 500
    validation = {'input_mode': 'structured_fields', 'validation_mode': 'state_trace_validator', 'input_contract': {'fields': [{'field_id': 'trace', 'required': True}]}}
    difficulty = {'target_level': 'intermediate', 'expected_reasoning_steps': [2, 3]}
    context = {
        'assessment_slot': {**deepcopy(validation), 'slot_id': 's1', 'knowledge': ['队列'], 'difficulty_contract': difficulty},
        'objective': {'difficulty_contract': deepcopy(difficulty), 'objective': '追踪队列'},
        'question_design_brief': {'primary_skill': '追踪队列', 'primary_knowledge': '队列', 'validation_contract': deepcopy(validation), 'assessment_scope_contract': {'learner_action_limit': 2}, 'answer_fact_contract': {'fact_basis': ['独有事实必须保留']}, 'material_contract': {'maximum_effective_code_lines': 20}},
        'untrusted_source_package': {'source_excerpt': evidence, 'source_refs': ['source-1']},
        'content_evidence': [{'reference_id': 'source-2', 'fact_excerpt': '另一个独立来源'}],
        'teacher_authoring_instruction': '包含空队列边界',
    }
    before = deepcopy(context)
    projected = _prompt_generation_context(context)
    assert context == before
    assert projected['untrusted_source_package'] == before['untrusted_source_package']
    assert projected['content_evidence'] == before['content_evidence']
    assert projected['assessment_slot']['input_contract'] == validation['input_contract']
    assert projected['assessment_slot']['difficulty_contract'] == difficulty
    assert projected['question_design_brief']['assessment_scope_contract']['learner_action_limit'] == 2
    assert projected['question_design_brief']['answer_fact_contract']['fact_basis'] == ['独有事实必须保留']
    assert projected['teacher_authoring_instruction'] == '包含空队列边界'
    assert 'validation_contract' not in projected['question_design_brief']
    assert 'difficulty_contract' not in projected['objective']
    prompt = _batch_generation_prompt([context, {**context, 'assessment_slot': {**context['assessment_slot'], 'slot_id': 's2'}}], compact=True)
    assert prompt.count(evidence) == 1
    assert 's1' in prompt and 's2' in prompt


def test_assessment_uses_lossless_plain_text_for_long_requests():
    prompt = 'Python 输入和边界条件\n' * 2000
    messages = UniversalAssessmentModel._request_messages(prompt=prompt, system_prompt='只输出JSON', model_id='qwen3.8-27b')
    assert messages == [{'role': 'system', 'content': '只输出JSON'}, {'role': 'user', 'content': prompt}]


def test_code_batch_schema_and_repair_include_hidden_test_contract():
    import json
    from assessment_orchestrator import _batch_repair_prompt, _generation_prompt_v2, _repair_prompt_v2

    context = {'assessment_slot': {'slot_id': 'code-1', 'input_mode': 'code', 'validation_mode': 'code_validator'}}
    prompt = _batch_generation_prompt([context], compact=True)
    schema = json.loads(prompt.split('<REQUIRED_OUTPUT_ENVELOPE>\n')[1].split('\n</REQUIRED_OUTPUT_ENVELOPE>')[0])
    tests = schema['candidates'][0]['candidate']['solution']['hidden_tests']
    assert set(tests[0]) == {'test_id', 'stdin', 'expected_output'}
    single = _generation_prompt_v2(context, compact=True)
    assert '"hidden_tests": [{' in single
    for repair in [_repair_prompt_v2(context, {}, {}), _batch_repair_prompt([{'slot_id': 'code-1', 'context': context}])]:
        assert 'test_id、stdin、expected_output' in repair


def test_batch_solver_requests_complete_choice_explanation():
    from assessment_orchestrator import _batch_solution_prompt
    prompt = _batch_solution_prompt([{'slot_id': 'choice-1', 'question_spec': {'input_contract': {'mode': 'choice'}}}])
    assert 'option_analysis必须逐项填写所有选项' in prompt


def test_missing_code_tests_can_be_repaired_without_replacing_existing_tests():
    from assessment_orchestrator import _apply_targeted_repair_candidate
    tests = [{'test_id': 'zero', 'stdin': '0', 'expected_output': '0'}]
    original = {'question_spec': {}, 'solution': {'validation_mode': 'code_validator'}}
    proposed = deepcopy(original)
    proposed['solution']['hidden_tests'] = tests
    repaired, _ = _apply_targeted_repair_candidate(original, proposed, issue_codes=['MATERIAL_BINDING_INVALID'])
    assert repaired['solution']['hidden_tests'] == tests
    proposed['solution']['hidden_tests'] = [{'test_id': 'changed', 'stdin': '1', 'expected_output': 'wrong'}]
    preserved, _ = _apply_targeted_repair_candidate(repaired, proposed, issue_codes=['MATERIAL_BINDING_INVALID'])
    assert preserved['solution']['hidden_tests'] == tests
