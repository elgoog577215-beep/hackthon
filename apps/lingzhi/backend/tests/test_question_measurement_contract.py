from question_measurement_contract import measurement_findings, review_witness_issues


def sample():
    return {
        "prompt": '在C17中，循环结束后变量i的值是多少？\n```c\nint i; for(i=0;i<5;i++){if(i==2)break;} printf("%d",i);\n```',
        "question_spec": {"options": [{"id": "A", "text": "2"}, {"id": "B", "text": "3"}]},
        "solution_envelope": {"canonical_answer": "A", "worked_solution": {"summary": "i为2时退出循环。"}},
        "design_brief": {
            "primary_knowledge": "break退出for时不执行更新表达式。",
            "language_contract": {"language_standard": "C17"},
        },
    }


def witness():
    return {
        "option_audit": [
            {
                "option_id": "A",
                "meaning": "整数2",
                "is_correct": True,
                "reason": "i等于2时执行break，退出前不执行更新。",
            },
            {
                "option_id": "B",
                "meaning": "整数3",
                "is_correct": False,
                "reason": "把退出前仍执行一次i++作为错误规则才会得到3。",
            },
        ],
        "observation_test": {
            "target_statement": "break退出for时不执行更新表达式。",
            "observed_quantity": "循环后的i",
            "public_anchor": 'printf("%d",i)',
            "incorrect_rule": "break退出前仍执行一次更新表达式，其余行为不变",
            "correct_prediction": "2",
            "incorrect_prediction": "3",
            "trace": "i=0,1完成迭代；i=2时break；错误规则先更新到3再退出。",
        },
        "unsupported_assumptions": [],
    }


def test_value_options_reject_bare_arithmetic_expressions():
    c = sample()
    c["question_spec"]["options"][1]["text"] = "7/2"
    assert "AMBIGUOUS_VALUE_OPTION" in {i["code"] for i in measurement_findings(c)}


def test_equivalent_numeric_alternatives_are_not_distinct_answers():
    c = sample()
    c["question_spec"]["options"][1]["text"] = "2.00"
    assert "EQUIVALENT_NUMERIC_OPTIONS" in {i["code"] for i in measurement_findings(c)}


def test_literal_output_does_not_collapse_different_formatting():
    c = sample()
    c["prompt"] = "请选择程序打印的完整输出。"
    c["question_spec"]["options"][1]["text"] = "2.0"
    assert not measurement_findings(c)


def test_false_additive_explanation_is_detected_without_evaluating_model_code():
    c = sample()
    c["solution_envelope"]["worked_solution"]["summary"] = "这些整数之和为1+2+3+4=9。"
    assert "EXPLANATION_ARITHMETIC_ERROR" in {i["code"] for i in measurement_findings(c)}
    c["solution_envelope"]["worked_solution"]["summary"] = "这些整数之和为1+2+3+4=10。"
    assert not measurement_findings(c)


def test_complete_grounded_witness_is_accepted():
    assert not review_witness_issues(sample(), witness())


def test_same_prediction_cannot_demonstrate_target_rule():
    w = witness()
    w["observation_test"]["incorrect_prediction"] = "2.0"
    assert "OBSERVATION_NOT_DISCRIMINATING" in {i["code"] for i in review_witness_issues(sample(), w)}


def test_observation_must_exist_in_public_question():
    w = witness()
    w["observation_test"]["public_anchor"] = 'printf("%d",hidden_counter)'
    assert "OBSERVATION_ANCHOR_MISSING" in {i["code"] for i in review_witness_issues(sample(), w)}


def test_review_must_examine_every_actual_option_and_agree_on_correct_ids():
    w = witness()
    w["option_audit"][1]["is_correct"] = True
    assert "OPTION_REASONING_CONTRADICTION" in {i["code"] for i in review_witness_issues(sample(), w)}
    w = witness()
    w["option_audit"].pop()
    assert "OPTION_AUDIT_INCOMPLETE" in {i["code"] for i in review_witness_issues(sample(), w)}


def test_assertions_of_quality_do_not_substitute_for_a_witness():
    assert review_witness_issues(sample(), {})
    w = witness()
    w["unsupported_assumptions"] = ["假定未声明的变量初始为0"]
    assert "UNSUPPORTED_REASONING_ASSUMPTION" in {i["code"] for i in review_witness_issues(sample(), w)}


def test_precise_standard_citation_needs_source_support():
    c = sample()
    c["solution_envelope"]["worked_solution"]["summary"] = "根据C17标准第6.5.5节第5段。"
    assert "UNSUPPORTED_PRECISE_CITATION" in {i["code"] for i in measurement_findings(c)}


def test_previous_round_ambiguous_value_option_is_blocked():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    rows = json.loads((root / "docs/研究/C17单点出题千问修复轮样题-2026-10-11.json").read_text(encoding="utf-8"))[
        "questions"
    ]
    row = next(q for q in rows if q["key"] == "K-T08")
    c = {
        "prompt": row["prompt"],
        "options": row["options"],
        "solution_envelope": {"worked_solution": row["worked_solution"]},
    }
    assert "AMBIGUOUS_VALUE_OPTION" in {i["code"] for i in measurement_findings(c)}


def test_string_false_is_not_a_positive_semantic_review():
    from assessment_orchestrator import _normalize_semantic_report

    report = _normalize_semantic_report({"passed": "false", "solution_consistent": "true"})
    assert report["passed"] is False and report["solution_consistent"] is False


def test_asking_output_value_does_not_silently_switch_to_string_semantics():
    c = sample()
    c["prompt"] = "printf将输出什么数值？"
    c["question_spec"]["options"][1]["text"] = "2.0"
    assert "EQUIVALENT_NUMERIC_OPTIONS" in {i["code"] for i in measurement_findings(c)}


def test_passive_condition_and_branch_body_observation_cannot_measure_evaluation():
    c = sample()
    c["design_brief"]["primary_knowledge"] = "首个命中分支之后不再求值后续分支条件。"
    c["prompt"] = "```c\nint x=1,y=1,z=1;if(x){z=10;}else if(y){z=20;}\n```\nz的最终值是多少？"
    assert "UNOBSERVABLE_CONDITION_EVALUATION" in {i["code"] for i in measurement_findings(c)}
    c["prompt"] = "```c\nint x=1,y=1,z=0;if(x){}else if((z++,y)){}\n```\nz的最终值是多少？"
    assert "UNOBSERVABLE_CONDITION_EVALUATION" not in {i["code"] for i in measurement_findings(c)}


def test_direct_question_about_condition_evaluation_is_not_a_proxy_observation():
    c = sample()
    c["design_brief"]["primary_knowledge"] = "首个命中分支之后不再求值后续分支条件。"
    c["prompt"] = "```c\nint x=1,y=1;if(x){}else if(y){}\n```\n条件y还会被求值吗？"
    assert not measurement_findings(c)


def test_review_cannot_add_ungrounded_clause_numbers_either():
    w = witness()
    w["option_audit"][0]["reason"] = "C17 6.5.16规定这个规则。"
    assert "UNSUPPORTED_PRECISE_CITATION" in {i["code"] for i in review_witness_issues(sample(), w)}


def test_misplaced_candidate_fields_can_be_moved_without_changing_content():
    from assessment_orchestrator import _normalize_candidate_layout

    original = {
        "question_spec": {
            "stimulus": {"rendered_text": "code"},
            "task": {"rendered_text": "question", "options": [{"id": "A", "text": "1"}]},
            "solution": {"canonical_answer": "A", "validation_mode": "exact_validator"},
        }
    }
    normalized, receipt = _normalize_candidate_layout(original)
    assert normalized["solution"]["canonical_answer"] == "A"
    assert normalized["question_spec"]["options"] == [{"id": "A", "text": "1"}]
    assert "solution" not in normalized["question_spec"] and "options" not in normalized["question_spec"]["task"]
    assert "solution" in original["question_spec"] and len(receipt) == 2


def test_counterfactual_cannot_change_a_read_only_public_input():
    from question_measurement_contract import fixed_input_witness_issues

    prompt = "```c\nint x=15;int y=0;if(x>10); y=20;\n```\ny的值是多少？"
    w = {
        "observation_test": {
            "correct_prediction": "x=15时y=20",
            "incorrect_prediction": "x=5时y=0",
            "trace": "比较两种规则。",
        }
    }
    assert fixed_input_witness_issues(prompt, w)
    w["observation_test"]["incorrect_prediction"] = "x=15时y=20"
    assert not fixed_input_witness_issues(prompt, w)


def test_mutated_program_state_is_not_misclassified_as_fixed_input():
    from question_measurement_contract import fixed_input_witness_issues

    prompt = "```c\nint i=0;for(;i<5;i++){if(i==2)break;}\n```"
    w = {
        "observation_test": {
            "correct_prediction": "i=2",
            "incorrect_prediction": "i=3",
            "trace": "错误规则额外更新一次。",
        }
    }
    assert not fixed_input_witness_issues(prompt, w)


def test_conflicting_candidate_layout_is_not_guessed():
    import pytest

    from ai_base import AIProviderRequestError
    from assessment_orchestrator import _normalize_candidate_layout

    with pytest.raises(AIProviderRequestError, match="layout_conflict"):
        _normalize_candidate_layout(
            {"solution": {"canonical_answer": "A"}, "question_spec": {"solution": {"canonical_answer": "B"}}}
        )


def test_c_binary_division_cannot_be_described_as_postfix_operator():
    c = sample()
    c["solution_envelope"]["worked_solution"]["summary"] = "由于 `/` 是后置运算符（中缀），所以如此。"
    assert "OPERATOR_FIXITY_CONTRADICTION" in {i["code"] for i in measurement_findings(c)}
    c["solution_envelope"]["worked_solution"]["summary"] = "除法 / 是二元中缀运算符，后缀递增 i++ 则不同。"
    assert not measurement_findings(c)


def test_trace_cannot_silently_change_else_binding_with_added_braces():
    c = sample()
    c["prompt"] = "```c\nif(a) if(b) x=1; else x=2;\n```\nelse属于哪个if？"
    w = witness()
    w["observation_test"]["trace"] = "解析语句流：if(a){if(b)x=1;}else x=2; 因此else属于if(b)。"
    assert "TRACE_CONTROL_STRUCTURE_CHANGED" in {i["code"] for i in review_witness_issues(c, w)}
    w["observation_test"]["trace"] = "解析语句流：if(a){if(b)x=1;else x=2;} 因此else属于if(b)。"
    assert "TRACE_CONTROL_STRUCTURE_CHANGED" not in {i["code"] for i in review_witness_issues(c, w)}


def test_existing_admission_is_rechecked_with_private_explanation_without_mutating_history():
    from question_evidence_guard import (
        CHECKS,
        EVIDENCE_SCHEMA,
        evidence_content_revision,
        revalidate_evidence_admission,
    )

    c = sample()
    c["assessment_binding_schema"] = "atomic_assessment_v1"
    c["evidence_admission"] = {
        "schema_version": EVIDENCE_SCHEMA,
        "eligible": True,
        "checks": {k: True for k in CHECKS},
        "witness_verified": True,
        "review_witness": witness(),
        "content_revision": evidence_content_revision(c),
    }
    sol = {"canonical_answer": "A", "worked_solution": {"summary": "计算1+2+3=9。"}}
    result = revalidate_evidence_admission(c, sol)
    assert result["eligible"] is False
    assert "EXPLANATION_ARITHMETIC_ERROR" in {i["code"] for i in result["local_issues"]}
    assert c["evidence_admission"]["eligible"] is True


def test_missing_private_answer_is_unknown_not_an_answer_disagreement():
    from question_evidence_guard import revalidate_evidence_admission
    c=sample();c['evidence_admission']={'review_witness':witness()}
    issues=revalidate_evidence_admission(c,{})['local_issues']
    assert 'PRIVATE_SOLUTION_UNAVAILABLE' in {i['code'] for i in issues}
    assert 'OPTION_REASONING_CONTRADICTION' not in {i['code'] for i in issues}


def test_assessable_coverage_requires_private_solution_revalidation():
    from question_evidence_guard import CHECKS, EVIDENCE_SCHEMA, evidence_content_revision
    from question_knowledge_binding import knowledge_point_coverage

    c = sample()
    c.update(
        assessment_binding_schema="atomic_assessment_v1",
        primary_knowledge_ids=["k"],
        course_knowledge_refs=["k"],
        knowledge_revision_refs={"k": "kv"},
        knowledge_baseline_revision="b",
        solution_revision_id="s",
        lifecycle_status="approved",
        quality_report={"passed": True},
    )
    c["evidence_admission"] = {
        "schema_version": EVIDENCE_SCHEMA,
        "eligible": True,
        "checks": {k: True for k in CHECKS},
        "witness_verified": True,
        "review_witness": witness(),
        "content_revision": evidence_content_revision(c),
    }
    course = {
        "course_knowledge_base": {"revision_id": "b", "knowledge_points": [{"knowledge_id": "k", "revision_id": "kv"}]}
    }
    bad = {"canonical_answer": "A", "worked_solution": {"summary": "1+2+3=9"}}
    assert knowledge_point_coverage(course, [c], solutions={"s": bad})["assessable_knowledge_point_count"] == 0
    assert (
        knowledge_point_coverage(course, [c], solutions={"s": c["solution_envelope"]})[
            "assessable_knowledge_point_count"
        ]
        == 1
    )
