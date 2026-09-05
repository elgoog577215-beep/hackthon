"""L1 覆盖率口径 + H2 题型匹配规则 + L2 干扰项对应关系检查。"""
from __future__ import annotations

from question_distractor_audit import (
    audit_question_bank_distractors,
    audit_question_distractors,
)
from question_form_matching import (
    discouraged_forms,
    evaluate_form_match,
    recommended_forms,
    review_question_form_matches,
)


# --- L1：覆盖率只算学生真正拿得到的题 ---------------------------------------


def _item(**overrides):
    item = {
        "revision_id": "qbr_1",
        "lifecycle_status": "approved",
        "quality_report": {"passed": True},
        "assessment_role": "practice",
        "course_objective_refs": ["obj_1"],
    }
    item.update(overrides)
    return item


def test_only_approved_and_passing_items_count() -> None:
    from question_bank import _counts_towards_coverage

    assert _counts_towards_coverage(_item()) is True
    assert _counts_towards_coverage(
        _item(lifecycle_status="needs_review"),
    ) is False
    assert _counts_towards_coverage(
        _item(quality_report={"passed": False}),
    ) is False


def test_field_complete_but_contract_failing_item_is_not_covered() -> None:
    """L1 的核心：字段完整不等于合同通过。

    V2 题若编译合同校验没过，approved_formal_tasks 会跳过它，学生根本看不到；
    此前覆盖率仍把它算成已覆盖——一个目标显示「有题」，学生打开却是空的。
    """
    from question_bank import _counts_towards_coverage

    failing = _item(
        question_spec={"schema_version": "question_spec_v2"},
        compiled_contract_validation={"passed": False},
    )
    assert _counts_towards_coverage(failing) is False

    passing = _item(
        question_spec={"schema_version": "question_spec_v2"},
        compiled_contract_validation={"passed": True},
    )
    assert _counts_towards_coverage(passing) is True


def test_non_practice_roles_do_not_count() -> None:
    from question_bank import _counts_towards_coverage

    assert _counts_towards_coverage(
        _item(assessment_role="coverage_task"),
    ) is False


def test_coverage_uses_the_same_contract_gate_as_the_student_projection() -> None:
    """覆盖率口径与 approved_formal_tasks 的最后一道过滤保持一致。

    approved_formal_tasks 对 V2 题额外要求 compiled_contract_validation.passed
    （question_bank.py:495-506）——不过就跳过，学生看不到。覆盖率此前没有这一条，
    于是一个目标显示「有题」而学生打开是空的。
    """
    import inspect

    from question_bank import _counts_towards_coverage, approved_formal_tasks

    projection_source = inspect.getsource(approved_formal_tasks)
    coverage_source = inspect.getsource(_counts_towards_coverage)
    for marker in ("question_spec_v2", "compiled_contract_validation"):
        assert marker in projection_source
        assert marker in coverage_source, (
            f"覆盖率口径缺少学生侧投影已有的过滤条件：{marker}"
        )


# --- H2：题型与知识点类型的匹配规则 -----------------------------------------


def test_definition_prefers_discriminating_forms() -> None:
    assert "single_choice" in recommended_forms("definition")
    assert "true_false" in recommended_forms("definition")
    assert "essay" in discouraged_forms("definition")


def test_method_and_procedure_require_actually_doing_it() -> None:
    """方法/步骤不能用选择题考——选择题只能考「认得出」。"""
    for knowledge_type in ("method", "procedure"):
        assert "single_choice" in discouraged_forms(knowledge_type)
        assert "true_false" in discouraged_forms(knowledge_type)


def test_match_verdicts_have_three_levels() -> None:
    """未列入推荐表的不能直接算不合适——表本身不完备。"""
    assert evaluate_form_match(
        knowledge_type="definition", question_form="single_choice",
    )["verdict"] == "match"
    assert evaluate_form_match(
        knowledge_type="definition", question_form="essay",
    )["verdict"] == "mismatch"
    assert evaluate_form_match(
        knowledge_type="definition", question_form="numeric",
    )["verdict"] == "acceptable"


def test_unknown_type_or_form_is_not_judged() -> None:
    assert evaluate_form_match(
        knowledge_type="vibes", question_form="single_choice",
    )["verdict"] == "unknown"
    assert evaluate_form_match(
        knowledge_type="definition", question_form="",
    )["verdict"] == "unknown"


def test_every_verdict_explains_itself() -> None:
    """不匹配时要说得出为什么，不能只给一个判定。"""
    result = evaluate_form_match(
        knowledge_type="method", question_form="single_choice",
    )
    assert result["verdict"] == "mismatch"
    assert result["reason"]
    assert result["recommended_forms"]


def _knowledge_base():
    return {
        "knowledge_points": [
            {"knowledge_id": "ckp_def", "knowledge_type": "definition"},
            {"knowledge_id": "ckp_method", "knowledge_type": "method"},
        ],
        "misconceptions": [
            {"misconception_id": "ckm_1"},
            {"misconception_id": "ckm_2"},
        ],
    }


def test_review_flags_mismatched_questions() -> None:
    review = review_question_form_matches(
        [
            {"revision_id": "q1", "question_form": "single_choice",
             "course_knowledge_refs": ["ckp_def"]},
            {"revision_id": "q2", "question_form": "single_choice",
             "course_knowledge_refs": ["ckp_method"]},
        ],
        _knowledge_base(),
    )
    assert review["counts"]["match"] == 1
    assert review["counts"]["mismatch"] == 1
    assert [entry["revision_id"] for entry in review["mismatches"]] == ["q2"]


def test_review_takes_the_most_permissive_bound_knowledge_point() -> None:
    """一道题绑多个知识点时，不能因为附带绑定而误报不匹配。"""
    review = review_question_form_matches(
        [{"revision_id": "q1", "question_form": "single_choice",
          "course_knowledge_refs": ["ckp_method", "ckp_def"]}],
        _knowledge_base(),
    )
    assert review["counts"]["match"] == 1


def test_unbound_question_is_unknown_not_mismatch() -> None:
    review = review_question_form_matches(
        [{"revision_id": "q1", "question_form": "single_choice"}],
        _knowledge_base(),
    )
    assert review["counts"]["unknown"] == 1
    assert review["mismatches"] == []


# --- L2：干扰项对应易错点（结构性检查，不评价质量） -------------------------


def _choice_item(**overrides):
    item = {
        "revision_id": "qbr_1",
        "options": [
            {"id": "A", "text": "正确项"},
            {"id": "B", "text": "干扰项一", "misconception_ids": ["ckm_1"]},
            {"id": "C", "text": "干扰项二", "misconception_ids": ["ckm_2"]},
        ],
        "answer_spec": {"correct_option_id": "A"},
    }
    item.update(overrides)
    return item


def test_declared_distractors_are_resolvable() -> None:
    audit = audit_question_distractors(_choice_item(), {"ckm_1", "ckm_2"})

    assert audit["distractor_count"] == 2
    assert audit["declared_count"] == 2
    assert audit["resolvable_count"] == 2
    assert audit["undeclared_option_ids"] == []


def test_correct_option_is_not_a_distractor() -> None:
    audit = audit_question_distractors(_choice_item(), {"ckm_1", "ckm_2"})
    assert [entry["option_id"] for entry in audit["distractors"]] == ["B", "C"]


def test_undeclared_distractor_is_listed_for_human_review() -> None:
    item = _choice_item(options=[
        {"id": "A", "text": "正确项"},
        {"id": "B", "text": "干扰项一"},
    ])
    audit = audit_question_distractors(item, {"ckm_1"})

    assert audit["undeclared_option_ids"] == ["B"]
    assert audit["resolvable_count"] == 0


def test_dangling_misconception_is_separated_from_undeclared() -> None:
    """写了但指向不存在的易错点，与没写不是一回事——成因不同。"""
    item = _choice_item(options=[
        {"id": "A", "text": "正确项"},
        {"id": "B", "text": "干扰项", "misconception_ids": ["ckm_missing"]},
    ])
    audit = audit_question_distractors(item, {"ckm_1"})

    assert audit["undeclared_option_ids"] == []
    assert audit["dangling_option_ids"] == ["B"]
    assert audit["resolvable_count"] == 0


def test_bank_audit_lists_questions_needing_human_review() -> None:
    items = [
        _choice_item(revision_id="q1"),
        _choice_item(revision_id="q2", options=[
            {"id": "A", "text": "正确项"},
            {"id": "B", "text": "干扰项"},
        ]),
        # 非选择题不参与
        {"revision_id": "q3", "prompt": "简答题"},
    ]
    report = audit_question_bank_distractors(items, _knowledge_base())

    assert report["question_count"] == 2
    assert report["questions_with_undeclared_distractors"] == ["q2"]
    assert report["declared_ratio"] < 1.0


def test_report_does_not_claim_quality() -> None:
    """L2 的质量必须人工评估——报告不得自称达标。

    这里能证明的只有「字段填了、且指向真实存在的易错点」，证明不了
    「这个干扰项真的对应学生会犯的错」。
    """
    report = audit_question_bank_distractors(
        [_choice_item()], _knowledge_base(),
    )
    # 不得出现质量结论类字段
    for forbidden in ("quality_score", "quality", "score", "passed", "verdict"):
        assert forbidden not in report
    # 必须显式声明需要人工评估
    assert "人工评估" in report["assessment_note"]
    # 即使字段全齐，也只说明齐全度，不代表质量合格
    assert report["declared_ratio"] == 1.0
    assert report["resolvable_ratio"] == 1.0


def test_audit_without_a_knowledge_base_does_not_invent_dangling_refs() -> None:
    """拿不到知识库时不能把所有引用都报成悬空。"""
    audit = audit_question_distractors(_choice_item(), None)
    assert audit["dangling_option_ids"] == []
    assert audit["resolvable_count"] == 2
