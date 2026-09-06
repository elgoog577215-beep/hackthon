"""J3: 分步作答与分步判定。

现状是学生一次性提交一个 answer_payload，没有分步提交、没有逐步判定。本文件
锁住新增的分步能力，以及三条必须成立的性质：

- **降级路径**：学生不想分步就不分步，整体作答仍然完整可判（任务书硬要求）；
- **不补写**：只判学生实际写下的步骤，不为没写的步骤编造判定（沿用 J2 口径）；
- **证据强度不重复建模**：分步是表达形式而非获得支持，不改变 evidence_strength
  与 support_level（J4 要求复用同一套口径，不新建计量）。
"""

import pytest

from practice_attempts import evidence_strength
from practice_attempts import support_level as _support_level
from practice_grading import PracticeGrader
from stepwise_answers import (
    extract_steps,
    first_flawed_step,
    merged_answer_text,
    normalize_step_judgements,
    reference_steps,
    stepwise_enabled,
    stepwise_summary,
)


def _stepwise_question():
    return {
        "question_type": "short_answer",
        "prompt": "求函数 f(x)=x^2-4x+3 的最小值，并写出推导过程。",
        "input_contract": {"mode": "rich_text", "stepwise": True},
        "answer_spec": {
            "type": "rubric",
            "pass_score": 70,
            "criteria": ["完成配方", "读出顶点", "得出最小值"],
            "solution_spec": {
                "final_answer": "-1",
                "steps": [
                    {"step_id": "s1", "action": "配方为 (x-2)^2-1"},
                    {"step_id": "s2", "action": "顶点为 (2,-1)"},
                    {"step_id": "s3", "action": "开口向上，最小值 -1"},
                ],
            },
        },
    }


def _steps_payload():
    return {
        "steps": [
            {"step_index": 1, "step_id": "s1", "text": "配方得 (x-2)^2-1"},
            {"step_index": 2, "step_id": "s2", "text": "所以顶点是 (2,-1)"},
            {"step_index": 3, "step_id": "s3", "text": "最小值是 -1"},
        ],
    }


# --- 数据结构：加法式扩展，旧数据零迁移 --------------------------------------


def test_payload_without_steps_is_simply_not_stepwise():
    """历史 attempt 没有 steps 键，天然就是"未分步"，不需要任何迁移。"""
    assert extract_steps({"text": "最小值是 -1"}) == []
    assert extract_steps({}) == []
    assert extract_steps({"steps": "not-a-list"}) == []


def test_blank_steps_are_not_treated_as_evidence():
    """空步骤是"这一步还没写"，不是证据，不能变成可判定的步骤。"""
    steps = extract_steps({"steps": [
        {"step_index": 1, "text": "配方得 (x-2)^2-1"},
        {"step_index": 2, "text": "   "},
        {"step_index": 3, "text": ""},
    ]})

    assert [item["step_index"] for item in steps] == [1]


def test_plain_string_steps_are_accepted_and_indexed():
    steps = extract_steps({"steps": ["先配方", "再读顶点"]})

    assert [item["step_index"] for item in steps] == [1, 2]
    assert steps[0]["text"] == "先配方"


def test_merged_answer_text_keeps_every_word_the_student_wrote():
    """整体评分必须看到全部内容，分步不能让一部分作答消失。"""
    merged = merged_answer_text({
        **_steps_payload(),
        "text": "综上，最小值为 -1。",
    })

    assert "配方得 (x-2)^2-1" in merged
    assert "所以顶点是 (2,-1)" in merged
    assert "综上，最小值为 -1。" in merged


def test_stepwise_is_opt_in_per_question():
    """默认关闭：不强制所有题都分步。"""
    assert stepwise_enabled(_stepwise_question()) is True
    assert stepwise_enabled({"input_contract": {"mode": "rich_text"}}) is False
    assert stepwise_enabled({}) is False


def test_reference_steps_read_the_private_derivation():
    assert [item["text"] for item in reference_steps(_stepwise_question())] == [
        "配方为 (x-2)^2-1",
        "顶点为 (2,-1)",
        "开口向上，最小值 -1",
    ]


# --- 分步判定：不为学生没写的步骤编造判定 ------------------------------------


def test_judgements_for_unsubmitted_steps_are_dropped():
    """模型给第 5 步打了分，但学生只写了 2 步——这条判定必须被丢掉。"""
    submitted = extract_steps({"steps": ["先配方", "再读顶点"]})
    judged = normalize_step_judgements(
        [
            {"step_index": 1, "verdict": "correct", "comment": "配方正确"},
            {"step_index": 5, "verdict": "flawed", "comment": "这一步学生根本没写"},
        ],
        submitted,
    )

    assert [item["step_index"] for item in judged] == [1]


def test_unknown_verdict_degrades_to_unclear_not_to_pass():
    """无法识别的判定必须降级为 unclear，绝不能变成"通过"。"""
    submitted = extract_steps({"steps": ["先配方"]})
    judged = normalize_step_judgements(
        [{"step_index": 1, "verdict": "看起来还行", "comment": ""}],
        submitted,
    )

    assert judged[0]["verdict"] == "unclear"


def test_duplicate_judgements_for_one_step_are_collapsed():
    submitted = extract_steps({"steps": ["先配方"]})
    judged = normalize_step_judgements(
        [
            {"step_index": 1, "verdict": "correct"},
            {"step_index": 1, "verdict": "flawed"},
        ],
        submitted,
    )

    assert len(judged) == 1
    assert judged[0]["verdict"] == "correct"


def test_summary_points_at_the_first_broken_step():
    """过程评价的核心：推导是从哪一步开始断的。"""
    submitted = extract_steps({"steps": ["a", "b", "c"]})
    judged = normalize_step_judgements(
        [
            {"step_index": 1, "verdict": "correct"},
            {"step_index": 2, "verdict": "flawed"},
            {"step_index": 3, "verdict": "flawed"},
        ],
        submitted,
    )
    summary = stepwise_summary(submitted, judged)

    assert summary["first_flawed_step_index"] == 2
    assert summary["flawed_step_count"] == 2
    assert summary["correct_step_count"] == 1
    assert summary["submitted_step_count"] == 3
    assert first_flawed_step(judged) == 2


def test_no_flawed_step_reports_none_not_zero():
    """没有出错的步骤时是 None，不能是 0——0 会被误读成"第 0 步错了"。"""
    submitted = extract_steps({"steps": ["a"]})
    judged = normalize_step_judgements(
        [{"step_index": 1, "verdict": "correct"}], submitted
    )

    assert stepwise_summary(submitted, judged)["first_flawed_step_index"] is None


# --- 与评分链路的集成 --------------------------------------------------------


class _FakeGrader(PracticeGrader):
    def __init__(self, response):
        super().__init__()
        self.client = object()
        self._response = response
        self.prompts = []

    async def _call_llm(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs.get("system_prompt") or ""))
        return self._response


@pytest.mark.asyncio
async def test_stepwise_grading_attaches_per_step_verdicts():
    grader = _FakeGrader("""{
        "score": 80, "passed": true, "confidence": 0.9,
        "feedback": "推导基本成立，第二步的依据要写清楚。",
        "rubric_results": [],
        "step_judgements": [
            {"step_index": 1, "verdict": "correct", "comment": "配方正确",
             "evidence": "配方得 (x-2)^2-1"},
            {"step_index": 2, "verdict": "unclear", "comment": "没说明依据",
             "evidence": "所以顶点是 (2,-1)"},
            {"step_index": 3, "verdict": "correct", "comment": "结论正确",
             "evidence": "最小值是 -1"}
        ]
    }""")
    result = await grader.grade(
        _stepwise_question(),
        {"status": "submitted", "submitted_answer_payload": _steps_payload()},
    )

    assert result["status"] == "graded"
    assert result["stepwise"]["judged_step_count"] == 3
    assert result["stepwise"]["unclear_step_count"] == 1
    assert result["stepwise"]["first_flawed_step_index"] is None
    # 学生写的每一步都进了送评 prompt。
    prompt, system_prompt = grader.prompts[0]
    assert "配方得 (x-2)^2-1" in prompt
    assert "student_steps" in prompt
    assert "不得为学生没有写的步骤编造判定" in system_prompt


@pytest.mark.asyncio
async def test_whole_answer_submission_still_works_and_carries_no_stepwise():
    """降级路径：学生不想分步，整体作答照常判，结果里没有 stepwise 字段。"""
    grader = _FakeGrader("""{
        "score": 85, "passed": true, "confidence": 0.9,
        "feedback": "结论正确。", "rubric_results": []
    }""")
    result = await grader.grade(
        _stepwise_question(),
        {
            "status": "submitted",
            "submitted_answer_payload": {"text": "配方后得最小值 -1。"},
        },
    )

    assert result["status"] == "graded"
    assert result["passed"] is True
    assert "stepwise" not in result
    # 未分步时不得给模型塞 student_steps。
    assert "student_steps" not in grader.prompts[0][0]


@pytest.mark.asyncio
async def test_steps_on_a_non_stepwise_question_are_still_graded_as_answer():
    """题目未开分步时，学生写的步骤不能凭空消失，只是不做逐步判定。"""
    question = _stepwise_question()
    question["input_contract"] = {"mode": "rich_text"}
    grader = _FakeGrader("""{
        "score": 80, "passed": true, "confidence": 0.9,
        "feedback": "结论正确。", "rubric_results": []
    }""")
    result = await grader.grade(
        question,
        {"status": "submitted", "submitted_answer_payload": _steps_payload()},
    )

    assert "stepwise" not in result
    # 内容仍然完整送进了评分。
    assert "配方得 (x-2)^2-1" in grader.prompts[0][0]


@pytest.mark.asyncio
async def test_stepwise_does_not_change_evidence_strength_or_support_level():
    """J4 口径：分步是表达形式不是支持，不得因此改变证据强度。"""
    question = _stepwise_question()
    grader = _FakeGrader("""{
        "score": 80, "passed": true, "confidence": 0.9,
        "feedback": "ok", "rubric_results": [],
        "step_judgements": [{"step_index": 1, "verdict": "correct"}]
    }""")
    attempt = {
        "status": "submitted",
        "revealed_hint_levels": [1],
        "ai_support_level": 0,
        "solution_revealed": False,
    }
    stepwise_attempt = {**attempt, "submitted_answer_payload": _steps_payload()}
    whole_attempt = {**attempt, "submitted_answer_payload": {"text": "最小值 -1"}}

    stepwise_result = await grader.grade(question, stepwise_attempt)
    whole_result = await grader.grade(question, whole_attempt)

    assert stepwise_result["evidence_strength"] == whole_result["evidence_strength"]
    assert stepwise_result["support_level"] == whole_result["support_level"]
    # 直接对齐既有口径本身，确认没有第二套计量。
    assert evidence_strength(stepwise_attempt) == "lightly_supported"
    assert _support_level(stepwise_attempt) == 1


@pytest.mark.asyncio
async def test_step_verdicts_survive_into_pending_review():
    """落到人工评阅时，逐步判定必须保留——否则评阅人要重做一遍模型的活。"""
    grader = _FakeGrader("""{
        "score": 71, "passed": true, "confidence": 0.95,
        "feedback": "接近通过线。", "rubric_results": [],
        "step_judgements": [
            {"step_index": 1, "verdict": "flawed", "comment": "配方符号错了"}
        ]
    }""")
    result = await grader.grade(
        _stepwise_question(),
        {"status": "submitted", "submitted_answer_payload": _steps_payload()},
    )

    assert result["status"] == "pending_review"
    assert result["stepwise"]["first_flawed_step_index"] == 1


# --- 编译期能力开关 ----------------------------------------------------------


def test_compiler_offers_stepwise_only_where_a_derivation_exists():
    """分步是"提供"而非"强制"：只在真有多步推导可拆的题上开启。"""
    from assessment_compiler import compile_formal_task_contract

    open_ended = compile_formal_task_contract({
        "question_type": "short_answer",
        "prompt": "求最小值并写出推导过程。",
        "input_contract": {"mode": "rich_text"},
        "answer_spec": {
            "type": "rubric",
            "pass_score": 70,
            "criteria": ["完成配方", "读出顶点", "得出最小值"],
        },
    }, {})
    single_choice = compile_formal_task_contract({
        "question_type": "single_choice",
        "prompt": "下列哪个判断正确？",
        "input_contract": {"mode": "choice"},
        "options": [{"id": "A", "text": "甲"}, {"id": "B", "text": "乙"}],
        "answer_spec": {"criteria": ["判断依据", "比较选项"], "correct_answer": "A"},
    }, {})
    one_step = compile_formal_task_contract({
        "question_type": "short_answer",
        "prompt": "一句话回答。",
        "input_contract": {"mode": "rich_text"},
        "answer_spec": {"criteria": ["答对即可"], "pass_score": 70},
    }, {})

    assert open_ended["input_contract"]["stepwise"] is True
    # 选择题只有一次选择，没有可拆的推导。
    assert single_choice["input_contract"]["stepwise"] is False
    assert one_step["input_contract"]["stepwise"] is False


# --- 提交端点的空答案守门 ----------------------------------------------------


def test_all_blank_steps_do_not_pass_the_empty_answer_guard():
    """只开了分步编辑器但一个字没写，必须被判为空答案而不是"零分作答"。"""
    from routers import practice as practice_router

    assert practice_router._has_answer({"steps": [
        {"step_index": 1, "text": ""},
        {"step_index": 2, "text": "   "},
    ]}) is False
    assert practice_router._has_answer({"steps": [
        {"step_index": 1, "text": "配方得 (x-2)^2-1"},
    ]}) is True
    # 未分步的整体作答不受影响。
    assert practice_router._has_answer({"text": "最小值 -1"}) is True
    assert practice_router._has_answer({"text": ""}) is False


# --- J4：证据强度口径对齐（不重复建模） --------------------------------------


def test_support_level_has_exactly_one_implementation():
    """`support_level` 必须只有一份实现，两个调用方指向同一个函数对象。

    此前评分与路由各有一份**逐字相同**的副本（D7）。两份副本一旦漂移，同一次
    作答会在"判定用的支持等级"和"上报用的支持等级"上给出不同答案，而且不会有
    任何测试报警——这条规则决定作答算不算掌握证据，漂移的后果是静默的。

    合并后不再断言"两份行为一致"（那默许了副本存在），而是直接断言**同一性**：
    任何人再复制一份出来，这条就会失败。
    """
    from practice_attempts import support_level as canonical
    import practice_grading
    from routers import practice as practice_router

    assert practice_grading.support_level is canonical
    assert practice_router.support_level is canonical
    # 模块内不得再出现私有副本
    assert not hasattr(practice_grading, "_support_level")
    assert not hasattr(practice_router, "_support_level")


def test_support_level_reads_all_three_support_signals():
    """合并后的唯一实现仍须覆盖三个支持入口，取其最大值。"""
    from practice_attempts import support_level

    assert support_level({}) == 0
    assert support_level({"ai_support_level": 2}) == 2
    assert support_level({"revealed_hint_levels": [1, 3]}) == 3
    assert support_level({"solution_revealed": True}) == 3
    # 多个入口同时存在时取最大，不是相加也不是最后一个
    assert support_level({
        "ai_support_level": 1,
        "revealed_hint_levels": [2],
        "solution_revealed": False,
    }) == 2
    assert support_level({
        "ai_support_level": 0,
        "revealed_hint_levels": [],
        "solution_revealed": True,
    }) == 3


def test_support_level_and_evidence_strength_agree_on_every_support_source():
    """三个支持入口（提示 / AI 求助 / 看答案）都必须同时影响两套口径。"""
    from practice_attempts import support_level as _support_level

    # 提示与 AI 求助按等级折算。
    assert _support_level({"revealed_hint_levels": [2]}) == 2
    assert evidence_strength({"revealed_hint_levels": [2]}) == "supported"
    assert _support_level({"ai_support_level": 3}) == 3
    assert evidence_strength({"ai_support_level": 3}) == "scaffolded"
    # 看过答案一律降到最低档。
    assert _support_level({"solution_revealed": True}) == 3
    assert evidence_strength({"solution_revealed": True}) == "scaffolded"
    # 作废的作答不产生任何证据。
    assert evidence_strength({"status": "invalidated"}) == "invalid"


def test_legacy_asset_path_also_derives_stepwise():
    """legacy/资产路径必须同样派生分步能力，否则真实课程里 UI 永远不出现。

    真实课程的题目走 learning_assets -> enrich_question_contract 这条路，而不是
    assessment_compiler。第一版只在 compiler 里派生，导致真实数据上
    input_contract.stepwise 恒为空、分步入口在生产里根本不显示。
    """
    from practice_contracts import enrich_question_contract

    # 开放题：_legacy_reasoning_support 会补出多步推导，应提供分步。
    open_ended = enrich_question_contract({
        "asset_id": "q-open",
        "revision_id": "qr-open",
        "node_id": "n1",
        "question_type": "worked_solution",
        "prompt": "把新坐标还原为标准坐标，并逐步解释每一步接收什么输入。",
        "answer_spec": {"type": "rubric", "pass_score": 70},
    }, practice_level="guided_practice")
    # 选择题：一次选择没有可拆的推导，永远不提供。
    choice = enrich_question_contract({
        "asset_id": "q-choice",
        "revision_id": "qr-choice",
        "node_id": "n1",
        "question_type": "single_choice",
        "prompt": "下列哪一个结果正确？",
        "options": [{"id": "A", "text": "甲"}, {"id": "B", "text": "乙"}],
        "answer_spec": {"type": "choice", "correct_option_id": "A",
                        "criteria": ["比较选项", "说明依据"], "pass_score": 70},
    }, practice_level="guided_practice")

    assert open_ended["input_contract"]["stepwise"] is True
    assert choice["input_contract"]["stepwise"] is False


def test_both_contract_paths_share_one_stepwise_rule():
    """两条契约路径必须用同一条规则，不能各判各的。"""
    from assessment_compiler import compile_formal_task_contract
    from practice_contracts import enrich_question_contract
    from stepwise_answers import derive_stepwise_capability

    # 同一条规则的直接断言：选择题永不提供，多步推导才提供。
    assert derive_stepwise_capability(input_mode="choice", reference_step_count=9) is False
    assert derive_stepwise_capability(input_mode="rich_text", reference_step_count=1) is False
    assert derive_stepwise_capability(input_mode="rich_text", reference_step_count=2) is True
    # 作者显式打开时尊重作者意图。
    assert derive_stepwise_capability(
        input_mode="rich_text", reference_step_count=0, existing=True
    ) is True

    compiled = compile_formal_task_contract({
        "question_type": "single_choice",
        "prompt": "选一个。",
        "input_contract": {"mode": "choice"},
        "options": [{"id": "A", "text": "甲"}, {"id": "B", "text": "乙"}],
        "answer_spec": {"criteria": ["a", "b", "c"], "correct_answer": "A"},
    }, {})
    enriched = enrich_question_contract({
        "asset_id": "q-c", "revision_id": "qr-c", "node_id": "n1",
        "question_type": "single_choice", "prompt": "选一个。",
        "options": [{"id": "A", "text": "甲"}, {"id": "B", "text": "乙"}],
        "answer_spec": {"type": "choice", "correct_option_id": "A",
                        "criteria": ["a", "b", "c"], "pass_score": 70},
    })

    assert compiled["input_contract"]["stepwise"] is False
    assert enriched["input_contract"]["stepwise"] is False


# --- 步骤编号必须连续且唯一（代码自查发现的绑定错位） -------------------------


def test_duplicate_client_indices_cannot_misbind_a_verdict():
    """客户端给的 step_index 重号时，逐步判定会绑错步骤——必须重新编号。

    自查复现：`[{step_index:0,text:'甲'},{step_index:1,text:'乙'}]` 里 0 是非正数
    会退回位置 1，于是两步都拿到 index=1；normalize 用字典按 index 收敛，后者
    覆盖前者，模型对"第 1 步"的判定实际落到了'乙'上。**把判定安到学生没写的那
    一步上，正是诚实性红线禁止的事。**
    """
    steps = extract_steps({"steps": [
        {"step_index": 0, "text": "甲"},
        {"step_index": 1, "text": "乙"},
    ]})

    assert [item["step_index"] for item in steps] == [1, 2]
    assert [item["text"] for item in steps] == ["甲", "乙"]

    judged = normalize_step_judgements(
        [{"step_index": 1, "verdict": "flawed", "comment": "第一步错"}], steps
    )
    assert len(judged) == 1
    assert judged[0]["step_index"] == 1  # 明确指向"甲"，不再有歧义


def test_indices_are_renumbered_contiguously_after_dropping_blanks():
    """空步骤被丢掉后，剩余步骤必须重新连号，不能留下空洞。

    留空洞会让"第 3 步"在 UI 上指向实际的第 2 个输入框。
    """
    steps = extract_steps({"steps": [
        {"step_index": 1, "text": "甲"},
        {"step_index": 2, "text": "   "},
        {"step_index": 3, "text": "丙"},
    ]})

    assert [item["step_index"] for item in steps] == [1, 2]
    assert [item["text"] for item in steps] == ["甲", "丙"]


def test_arbitrary_client_indices_are_normalized():
    """跳号（7、9）同样规整为 1、2——位置才是权威，客户端声明不是。"""
    steps = extract_steps({"steps": [
        {"step_index": 7, "text": "甲"},
        {"step_index": 9, "text": "乙"},
    ]})

    assert [item["step_index"] for item in steps] == [1, 2]


def test_malformed_step_payloads_do_not_crash():
    """畸形 payload 只应产生更少的步骤，不应抛异常。"""
    assert extract_steps({"steps": {"a": 1}}) == []
    assert [item["text"] for item in extract_steps({"steps": [None, "有内容", None]})] == ["有内容"]
    assert [item["text"] for item in extract_steps({"steps": [123, "文本"]})] == ["123", "文本"]
    # 上限仍然生效
    assert len(extract_steps({"steps": [f"s{i}" for i in range(200)]})) == 20
    assert len(extract_steps({"steps": [{"step_index": 1, "text": "x" * 99999}]})[0]["text"]) == 5000
