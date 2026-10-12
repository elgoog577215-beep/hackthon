from .independent_answers import literal_prefix,compare


def test_list_parser_checks_value_not_prefix_and_never_executes_code():
    assert literal_prefix('[[10]]。共享对象')==('list',[[10]])
    assert literal_prefix('[[20]]。共享对象')!=literal_prefix('[[10]]')
    assert literal_prefix('[__import__("os").system("echo x")]') is None
    assert literal_prefix('TrueValue') is None
    assert literal_prefix('True。解释')==('bool',True)


def test_disagreement_detected_and_reasoning_not_falsely_certified():
    candidate={'points':[{'key':'P1','check':{'answer':'[[20]]'},'transfer':{'answer':'不能，因为前提不足'}}]}
    audit={'reviews':[{'key':'P1','check_answer':'[[10]]','transfer_answer':'不能，缺少条件'}]}
    rows=compare(candidate,audit)['rows']
    assert rows[0]['status']=='answer_mismatch'
    assert rows[1]['status']=='needs_semantic_review'
    assert not compare(candidate,audit)['ready_for_adoption']
