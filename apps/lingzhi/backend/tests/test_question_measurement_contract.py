from copy import deepcopy

from question_measurement_contract import measurement_findings, review_witness_issues


def sample():
    return {
        'prompt': '在C17中，循环结束后变量i的值是多少？\n```c\nint i; for(i=0;i<5;i++){if(i==2)break;} printf("%d",i);\n```',
        'question_spec': {'options': [{'id':'A','text':'2'},{'id':'B','text':'3'}]},
        'solution_envelope': {'canonical_answer':'A','worked_solution':{'summary':'i为2时退出循环。'}},
        'design_brief': {'primary_knowledge':'break退出for时不执行更新表达式。','language_contract':{'language_standard':'C17'}},
    }


def witness():
    return {'option_audit':[
        {'option_id':'A','meaning':'整数2','is_correct':True,'reason':'i等于2时执行break，退出前不执行更新。'},
        {'option_id':'B','meaning':'整数3','is_correct':False,'reason':'把退出前仍执行一次i++作为错误规则才会得到3。'}],
        'observation_test':{'target_statement':'break退出for时不执行更新表达式。',
            'observed_quantity':'循环后的i','public_anchor':'printf("%d",i)',
            'incorrect_rule':'break退出前仍执行一次更新表达式，其余行为不变',
            'correct_prediction':'2','incorrect_prediction':'3','trace':'i=0,1完成迭代；i=2时break；错误规则先更新到3再退出。'},
        'unsupported_assumptions':[]}


def test_value_options_reject_bare_arithmetic_expressions():
    c=sample();c['question_spec']['options'][1]['text']='7/2'
    assert 'AMBIGUOUS_VALUE_OPTION' in {i['code'] for i in measurement_findings(c)}


def test_equivalent_numeric_alternatives_are_not_distinct_answers():
    c=sample();c['question_spec']['options'][1]['text']='2.00'
    assert 'EQUIVALENT_NUMERIC_OPTIONS' in {i['code'] for i in measurement_findings(c)}


def test_literal_output_does_not_collapse_different_formatting():
    c=sample();c['prompt']='请选择程序打印的完整输出。';c['question_spec']['options'][1]['text']='2.0'
    assert not measurement_findings(c)


def test_false_additive_explanation_is_detected_without_evaluating_model_code():
    c=sample();c['solution_envelope']['worked_solution']['summary']='这些整数之和为1+2+3+4=9。'
    assert 'EXPLANATION_ARITHMETIC_ERROR' in {i['code'] for i in measurement_findings(c)}
    c['solution_envelope']['worked_solution']['summary']='这些整数之和为1+2+3+4=10。'
    assert not measurement_findings(c)


def test_complete_grounded_witness_is_accepted():
    assert not review_witness_issues(sample(), witness())


def test_same_prediction_cannot_demonstrate_target_rule():
    w=witness();w['observation_test']['incorrect_prediction']='2.0'
    assert 'OBSERVATION_NOT_DISCRIMINATING' in {i['code'] for i in review_witness_issues(sample(),w)}


def test_observation_must_exist_in_public_question():
    w=witness();w['observation_test']['public_anchor']='printf("%d",hidden_counter)'
    assert 'OBSERVATION_ANCHOR_MISSING' in {i['code'] for i in review_witness_issues(sample(),w)}


def test_review_must_examine_every_actual_option_and_agree_on_correct_ids():
    w=witness();w['option_audit'][1]['is_correct']=True
    assert 'OPTION_REASONING_CONTRADICTION' in {i['code'] for i in review_witness_issues(sample(),w)}
    w=witness();w['option_audit'].pop()
    assert 'OPTION_AUDIT_INCOMPLETE' in {i['code'] for i in review_witness_issues(sample(),w)}


def test_assertions_of_quality_do_not_substitute_for_a_witness():
    assert review_witness_issues(sample(), {})
    w=witness();w['unsupported_assumptions']=['假定未声明的变量初始为0']
    assert 'UNSUPPORTED_REASONING_ASSUMPTION' in {i['code'] for i in review_witness_issues(sample(),w)}


def test_precise_standard_citation_needs_source_support():
    c=sample();c['solution_envelope']['worked_solution']['summary']='根据C17标准第6.5.5节第5段。'
    assert 'UNSUPPORTED_PRECISE_CITATION' in {i['code'] for i in measurement_findings(c)}
