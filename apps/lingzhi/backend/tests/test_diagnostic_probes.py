"""I0-a：把「因错出题」做强——按错误类型出探针题，且探针不得自带答案。

保守路径（不打破"出题不看画像"的既有设计）：诊断→探针题→补救题这条链已存在，
本文件锁住本轮对**探针题生成**的加强：

1. 四种假设类型（概念缺口 / 过程错误 / 迁移缺口 / 边界混淆）产出**形态不同**的
   探针，而不是一个模板套所有；
2. 用���知识库里此前被忽略的易错点字段（`error_pattern` / `confused_with`）来
   框定"要比较什么"；
3. **但绝不放 `discrimination` 与 `repair_strategy` 进探针**——前者就是这道
   探针的答案，后者是补救阶段的教学内容。探针自带答案比没有探针更糟：学生照抄
   即可通过，假设被**错误地否证**，而这个否证看起来还像是证据。
"""

import pytest

from diagnostic_probes import (
    FORBIDDEN_PROBE_FIELDS,
    PROBE_CATEGORIES,
    build_probe_spec,
    find_misconception,
    probe_leaks_answer,
)
from diagnostic_workflows import diagnostic_tasks


def _misconception():
    return {
        "mistake_point_id": "mc-1",
        "name": "把向量与坐标混为一谈",
        "error_pattern": "换基后认为箭头本身也变了",
        "confused_with": "向量的坐标表示",
        # 下面两条是"答案"与"教学内容"，探针里一个字都不该出现
        "discrimination": "箭头是几何对象与基无关，坐标是相对某组基的表示",
        "repair_strategy": "画同一个箭头在两组基下的坐标对照图",
    }


def _course(templates=None):
    return {"learning_assets": {
        "misconceptions": [_misconception()],
        "diagnostic_templates": templates or [],
    }}


def _task():
    return {
        "learning_objective": "区分几何对象与坐标表示",
        "objective_id": "lo1",
        "objective_revision_id": "lor1",
        "node_id": "n1",
        "answer_spec": {"expected_keywords": ["基", "坐标"]},
    }


def _hypothesis(category, *, mistake_ids=("mc-1",)):
    return {
        "hypothesis_id": f"h-{category}",
        "category": category,
        "claim": "换基后误以为箭头本身改变",
        "candidate_mistake_point_ids": list(mistake_ids),
        "concept_ids": [],
        "skill_unit_ids": [],
    }


# --- 按错误类型出不同形态的探针 ----------------------------------------------


@pytest.mark.parametrize("category,strategy", [
    ("concept_gap", "state_conditions"),
    ("process_error", "redo_single_step"),
    ("transfer_gap", "new_context_transfer"),
    ("boundary_confusion", "discriminate_neighbour"),
])
def test_each_error_category_gets_its_own_probe_shape(category, strategy):
    """不同类型的错误需要不同的证据，不能一个模板套所有。"""
    spec = build_probe_spec(
        _hypothesis(category), task=_task(), misconception=_misconception()
    )

    assert spec["probe_strategy"] == strategy
    assert spec["probe_category"] == category
    assert spec["prompt"].strip()
    assert len(spec["criteria"]) >= 3


def test_the_four_probes_are_actually_different():
    """防止"看起来分了类、实际生成同一句话"。"""
    prompts = {
        category: build_probe_spec(
            _hypothesis(category), task=_task(), misconception=_misconception()
        )["prompt"]
        for category in PROBE_CATEGORIES
    }

    assert len(set(prompts.values())) == len(PROBE_CATEGORIES)


def test_unknown_category_degrades_to_process_error_not_crash():
    spec = build_probe_spec(
        _hypothesis("something_new"), task=_task(), misconception=_misconception()
    )

    assert spec["probe_category"] == "process_error"


# --- 探针不得自带答案（本节是重点） ------------------------------------------


@pytest.mark.parametrize("category", PROBE_CATEGORIES)
def test_probe_never_contains_discrimination_or_repair_strategy(category):
    """`discrimination` 就是这道探针的答案；`repair_strategy` 是补救期教学内容。

    探针自带答案比没有探针更糟——学生照抄即可通过，假设被**错误地否证**，
    而这个否证看起来还像是一条证据。
    """
    mistake = _misconception()
    task = diagnostic_tasks(_course(), _task(), [_hypothesis(category)])[0]
    blob = "".join(str(task.get("prompt") or "").split())
    blob += "".join(
        "".join(str(item).split())
        for item in (task.get("answer_spec") or {}).get("criteria") or []
    )

    for field in FORBIDDEN_PROBE_FIELDS:
        forbidden = "".join(mistake[field].split())
        assert forbidden not in blob, (category, field)


def test_boundary_probe_still_uses_the_safe_framing_fields():
    """拦住答案的同时不能把探针做废——`confused_with` 必须还在，否则无从比较。"""
    spec = build_probe_spec(
        _hypothesis("boundary_confusion"),
        task=_task(),
        misconception=_misconception(),
    )

    assert "向量的坐标表示" in spec["prompt"]      # confused_with：安全，指明比什么
    assert "换基后认为箭头本身也变了" in spec["prompt"]  # error_pattern：安全，描述现象
    # 但决定性的判据要学生自己给
    assert "箭头是几何对象与基无关" not in spec["prompt"]


def test_leak_guard_catches_an_injected_answer():
    """守卫本身要有效，否则上面几条"没泄漏"只是碰巧。"""
    mistake = _misconception()
    leaky = {
        "prompt": f"提示：{mistake['discrimination']}，现在请回答。",
        "criteria": [],
        "probe_strategy": "x",
    }
    safe = build_probe_spec(
        _hypothesis("boundary_confusion"), task=_task(), misconception=mistake
    )

    assert probe_leaks_answer(leaky, mistake) == "discrimination"
    assert probe_leaks_answer(safe, mistake) == ""


# --- 假设文本自带答案（真机抽查发现，见 NOTES_TO_OWNER · I0-a 真机取证）------


def _answered_task(correct_answer="最小值为 -4"):
    task = _task()
    task["answer_spec"] = {**task["answer_spec"], "correct_answer": correct_answer}
    return task


def test_guard_catches_the_answer_carried_in_the_hypothesis_claim():
    """claim 来自真实模型的诊断，可能顺手把正确答案说出来。

    这条不是假想：真机抽查里模型写的是
    「原常数 5 与 -9 相加应得 -4，学生误算为 +4」，
    `build_probe_spec` 把 claim 逐字拼进探针，学生就在探针里看到了 -4——
    而他接下来还要在补救链上重做同一道题。手写 fixture 永远暴露不了这条，
    因为人写 claim 时不会去引用答案。
    """
    hypothesis = _hypothesis("process_error")
    hypothesis["claim"] = "原常数 5 与 -9 相加应得 -4，学生误算为 +4"
    spec = build_probe_spec(
        hypothesis, task=_answered_task(), misconception=_misconception()
    )

    # 不传 task 时看不见这条——正是加这个参数的理由
    assert probe_leaks_answer(spec, _misconception()) == ""
    assert probe_leaks_answer(
        spec, _misconception(), _answered_task()
    ) == "answer_value:-4"


def test_claim_carrying_the_answer_is_redacted_not_shown():
    """端到端：带答案的 claim 不得发给学生。

    注意退让的方式：claim 在**进入探针之前**就被改写，所以探针**仍然保持按错误
    类型出题的形态**（这里仍是 `redo_single_step`），只是不再带答案——比整条退回
    通用表述更好。原始 claim 留在假设上作为诊断证据，不给学生看。
    """
    hypothesis = _hypothesis("process_error")
    hypothesis["claim"] = "原常数 5 与 -9 相加应得 -4，学生误算为 +4"
    task = diagnostic_tasks(_course(), _answered_task(), [hypothesis])[0]

    assert "-4" not in str(task.get("prompt"))
    assert "-4" not in str(task.get("answer_spec"))
    assert task.get("probe_strategy") == "redo_single_step"  # 形态未被牺牲
    assert hypothesis["claim"] == "原常数 5 与 -9 相加应得 -4，学生误算为 +4"


def test_safe_claim_is_left_exactly_as_written():
    """不带答案的 claim 一个字都不该被改——重写只针对真泄漏。"""
    hypothesis = _hypothesis("process_error")
    hypothesis["claim"] = "学生跳过了配方中加减同一个数的步骤"
    task = diagnostic_tasks(_course(), _answered_task(), [hypothesis])[0]

    assert "学生跳过了配方中加减同一个数的步骤" in str(task.get("prompt"))


def test_neutral_fallback_also_drops_the_answer():
    """兜底表述同样引用 claim，所以它必须走同一条改写。

    这是修这条时最容易漏的一半：守卫拦下生成的探针后退回"中性提示"，
    而那句中性提示自己就拼了 claim——等于没拦。
    """
    import diagnostic_workflows

    monkey = diagnostic_workflows.build_probe_spec
    try:
        diagnostic_workflows.build_probe_spec = (
            lambda hypothesis, *, task, misconception: {}
        )
        hypothesis = _hypothesis("process_error")
        hypothesis["claim"] = "原常数 5 与 -9 相加应得 -4，学生误算为 +4"
        task = diagnostic_tasks(_course(), _answered_task(), [hypothesis])[0]
    finally:
        diagnostic_workflows.build_probe_spec = monkey

    assert "-4" not in str(task.get("prompt"))
    assert "-4" not in str(task.get("answer_spec"))


def test_guard_does_not_block_step_indices_or_option_labels():
    """另一个方向同样要守：拦得太狠会把探针本身拦死。

    答案是 "1"/"B" 这类单字符时，「第 1 步」「选项 B」是完全正常的探针措辞。
    与 K2 运行时守卫用的是同一套口径（`hint_leakage.mentions_answer_value`），
    不另建第二套。
    """
    probe = {
        "prompt": "只重做出问题的那一步：第 4 步你用了什么条件？选项 B 与 C 差在哪？",
        "criteria": ["指明这一步的输入"],
        "probe_strategy": "redo_single_step",
    }

    assert probe_leaks_answer(probe, _misconception(), _answered_task("B")) == ""
    assert probe_leaks_answer(probe, _misconception(), _answered_task("4")) == ""
    # 两位及以上的裸值照旧拦下
    assert probe_leaks_answer(
        probe, _misconception(), _answered_task("4 步")
    ) == "answer_value:4 步"


def test_guard_is_a_no_op_when_the_task_has_no_stored_answer():
    """开放题没有 correct_answer，守卫不得凭空报错或误报。"""
    probe = build_probe_spec(
        _hypothesis("transfer_gap"), task=_task(), misconception=_misconception()
    )

    assert probe_leaks_answer(probe, _misconception(), _task()) == ""


def test_leaky_probe_falls_back_to_neutral_prompt(monkeypatch):
    """真的漏了就退回中性提示，而不是把带答案的探针发给学生。"""
    import diagnostic_workflows

    monkeypatch.setattr(
        diagnostic_workflows,
        "build_probe_spec",
        lambda hypothesis, *, task, misconception: {
            "prompt": f"答案是：{(misconception or {}).get('discrimination')}",
            "criteria": ["x"],
            "probe_strategy": "leaky",
            "probe_category": "boundary_confusion",
        },
    )
    task = diagnostic_tasks(
        _course(), _task(), [_hypothesis("boundary_confusion")]
    )[0]

    assert "箭头是几何对象与基无关" not in str(task.get("prompt"))
    assert task.get("probe_strategy") is None  # 未采用泄漏的那份


# --- 与既有设计的边界 --------------------------------------------------------


def test_authored_templates_still_win_over_generated_probes():
    """课程里有人工编写的诊断模板时，仍然优先用它——不夺走教研的控制权。"""
    templates = [{
        "objective_revision_id": "lor1",
        "quality_status": "passed",
        "question_type": "short_answer",
        "prompt": "这是教研写好的探针题。",
        "answer_spec": {"type": "rubric", "criteria": ["人工标准"], "pass_score": 70},
        "practice_level": "diagnostic_probe",
    }]
    task = diagnostic_tasks(
        _course(templates), _task(), [_hypothesis("boundary_confusion")]
    )[0]

    assert task["prompt"] == "这是教研写好的探针题。"


def test_probe_works_without_any_misconception_data():
    """知识库没有易错点时不能崩，退回不依赖易错点的表述。"""
    course = {"learning_assets": {"misconceptions": [], "diagnostic_templates": []}}
    task = diagnostic_tasks(
        course, _task(), [_hypothesis("boundary_confusion", mistake_ids=())]
    )[0]

    assert str(task.get("prompt") or "").strip()
    assert task.get("probe_strategy") == "discriminate_neighbour"


def test_find_misconception_matches_by_id_only():
    course = _course()

    assert find_misconception(course, ["mc-1"])["mistake_point_id"] == "mc-1"
    assert find_misconception(course, ["mc-nonexistent"]) == {}
    assert find_misconception(course, []) == {}


def test_outcome_matrix_and_targeting_are_preserved():
    """加强探针内容不能动裁决口径——假设绑定与结论矩阵必须原样保留。"""
    task = diagnostic_tasks(_course(), _task(), [_hypothesis("concept_gap")])[0]

    assert task["target_hypothesis_ids"] == ["h-concept_gap"]
    assert task["outcome_matrix"] == {
        "independent_pass": "evidence_against",
        "independent_fail": "evidence_for",
        "supported_or_pending": "inconclusive",
    }
    assert task["practice_level"] == "diagnostic_probe"
