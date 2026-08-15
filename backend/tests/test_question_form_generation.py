"""生成端产出多选 / 判断 / 填空（H1a、H1b 的生成侧接入）。

这些用例全部离线，不碰 provider。真机取证由
`scripts/question_form_generation_audit.py` 负责。
"""
from __future__ import annotations

from copy import deepcopy

from assessment_blueprint import (
    compile_course_assessment_blueprint,
    input_contract_for_slot,
    resolve_slot_question_form,
)


def _node(node_id: str, **extra) -> dict:
    node = {
        "node_id": node_id,
        "node_level": 2,
        "node_name": "热力学第一定律",
        "learning_objective": "使用热力学第一定律计算内能变化",
        "key_points": ["能量守恒"],
        "assessment": ["列式计算内能变化"],
        "node_content": "封闭系统 ΔU=Q-W；吸热为正、对外做功为正。" * 3,
        "difficulty_contract": {"target_level": "intermediate"},
        "grounding_contract": {"question_evidence_ids": []},
    }
    node.update(extra)
    return node


def _course(*, knowledge_type: str | None = None, **node_extra) -> dict:
    course = {
        "course_id": "c1",
        "course_purpose": "systematic",
        "difficulty": "intermediate",
        "nodes": [_node("L2-1-1", **node_extra)],
    }
    if knowledge_type:
        course["course_knowledge_base"] = {
            "schema_version": "course_knowledge_base_v1",
            "course_id": "c1",
            "knowledge_points": [{
                "knowledge_id": "ckp_1",
                "knowledge_type": knowledge_type,
                "name": "知识点",
                "section_refs": ["L2-1-1"],
            }],
        }
    return course


# --- 回归护栏：没有知识库时产物零变化（最重要的一条） ----------------------


def test_without_a_knowledge_base_the_choice_contract_is_unchanged() -> None:
    """既有课程的 blueprint_revision_id 不能因为本次改动而漂移。

    blueprint_revision_id 是对整个 blueprint 的 stable_hash，input_contract
    多一个键就会让所有既有课程的修订 ID 变化。绝大多数既有测试与线上课程都
    没有课程知识库，走的正是这条回落路径。
    """
    blueprint = compile_course_assessment_blueprint(_course())
    slot = blueprint["nodes"][0]["slots"][0]

    assert slot["input_mode"] == "choice"
    assert slot["question_form"] == "single_choice"
    # 逐字节：只有 multiple 一个键，值为 False
    assert slot["input_contract"]["selection"] == {"multiple": False}


def test_form_selection_is_deterministic() -> None:
    """选型必须是纯函数，否则 blueprint 不再可复现。"""
    course = _course(knowledge_type="condition")
    first = compile_course_assessment_blueprint(course)
    second = compile_course_assessment_blueprint(deepcopy(course))
    assert first["blueprint_revision_id"] == second["blueprint_revision_id"]


def test_unknown_knowledge_type_falls_back_to_the_default_form() -> None:
    blueprint = compile_course_assessment_blueprint(
        _course(knowledge_type="vibes"),
    )
    assert blueprint["nodes"][0]["slots"][0]["question_form"] == "single_choice"


# --- H2 按知识点类型选型 ----------------------------------------------------


def test_condition_and_rule_select_true_false() -> None:
    for knowledge_type in ("condition", "rule"):
        blueprint = compile_course_assessment_blueprint(
            _course(knowledge_type=knowledge_type),
        )
        slot = blueprint["nodes"][0]["slots"][0]
        assert slot["question_form"] == "true_false", knowledge_type
        assert slot["input_contract"]["selection"]["true_false"] is True


def test_representation_selects_fill_blank_and_switches_input_mode() -> None:
    """填空要连输入模式与验证器一起换。

    只改形态不改验证器，填空题会拿着选择题的 exact_validator 去比对整段文本。
    """
    blueprint = compile_course_assessment_blueprint(
        _course(knowledge_type="representation"),
    )
    slot = blueprint["nodes"][0]["slots"][0]

    assert slot["question_form"] == "fill_blank"
    assert slot["input_mode"] == "short_text"
    assert slot["input_contract"]["blanks"] == []
    # 作答载体仍要有落点
    assert slot["input_contract"]["fields"]


def test_a_node_can_request_a_form_explicitly() -> None:
    """H2 的推荐表里没有任何知识点类型把 multiple_choice 排第一。

    与其为了凑出多选去改教研判断表（那是把工具改成迎合结论），不如给一个
    显式入口。
    """
    blueprint = compile_course_assessment_blueprint(
        _course(
            knowledge_type="definition",
            preferred_question_form="multiple_choice",
        ),
    )
    slot = blueprint["nodes"][0]["slots"][0]
    assert slot["question_form"] == "multiple_choice"
    assert slot["input_contract"]["selection"] == {
        "multiple": True,
        "partial_credit": False,
    }


def test_an_impossible_requested_form_is_ignored() -> None:
    """choice 槽位要不到 coding，请求无效时回落而不是硬塞。"""
    blueprint = compile_course_assessment_blueprint(
        _course(knowledge_type="definition", preferred_question_form="coding"),
    )
    assert blueprint["nodes"][0]["slots"][0]["question_form"] == "single_choice"


def test_slots_in_one_node_do_not_collapse_into_one_form() -> None:
    course = _course(knowledge_type="condition")
    course["course_knowledge_base"]["knowledge_points"].extend([
        {
            "knowledge_id": "ckp_2",
            "knowledge_type": "representation",
            "name": "k2",
            "section_refs": ["L2-1-1"],
        },
        {
            "knowledge_id": "ckp_3",
            "knowledge_type": "definition",
            "name": "k3",
            "section_refs": ["L2-1-1"],
        },
    ])
    blueprint = compile_course_assessment_blueprint(course)
    forms = {slot["question_form"] for slot in blueprint["nodes"][0]["slots"]}
    assert len(forms) > 1


# --- input_contract 分支 ----------------------------------------------------


def test_input_contract_branches_by_form() -> None:
    base = {"input_mode": "choice", "question_type": "selected_response"}

    single = input_contract_for_slot(
        {**base, "question_form": "single_choice"}, family="general",
    )
    assert single["selection"] == {"multiple": False}

    multi = input_contract_for_slot(
        {**base, "question_form": "multiple_choice"}, family="general",
    )
    assert multi["selection"]["multiple"] is True
    # 部分给分默认关闭——口径已定，引擎不替所有题决定
    assert multi["selection"]["partial_credit"] is False


def test_resolver_returns_default_for_modes_without_alternatives() -> None:
    for mode, expected in (
        ("code", "coding"),
        ("rich_text", "essay"),
        ("numeric_unit", "numeric"),
        ("structured_fields", "structured"),
    ):
        assert resolve_slot_question_form(
            {}, node_id="x", input_mode=mode, practice_level="concept_check",
        ) == expected


# --- prompt 按题型下发 ------------------------------------------------------


def test_single_choice_prompt_wording_is_unchanged() -> None:
    """默认路径的 prompt 一变，既有题目的生成结果就不可比。"""
    from assessment_orchestrator import _form_directive

    assert _form_directive("single_choice") == (
        "选择题必须提供至少两个唯一 options，标准答案必须对应"
        "一个 option id。"
    )
    assert _form_directive("") == _form_directive("single_choice")


def test_new_forms_get_specific_directives() -> None:
    from assessment_orchestrator import _form_directive

    multi = _form_directive("multiple_choice")
    assert "两个或以上" in multi
    assert "JSON 数组" in multi
    assert "misconception_rules" in multi, "干扰项要对应易错点（喂给 L2）"

    true_false = _form_directive("true_false")
    assert "恰好两个" in true_false
    # 词表必须逐字列出——_looks_like_true_false 按精确文本匹配
    assert "正确/错误" in true_false

    fill_blank = _form_directive("fill_blank")
    assert "{{1}}" in fill_blank
    assert "solution.blanks" in fill_blank


def test_batch_prompt_sends_per_item_directives_when_forms_differ() -> None:
    from assessment_orchestrator import _batch_generation_prompt

    def context(form: str, index: int) -> dict:
        return {
            "assessment_slot": {
                "slot_id": f"slot-{index}",
                "question_form": form,
                "input_mode": "choice",
                "validation_mode": "exact_validator",
            },
        }

    mixed = _batch_generation_prompt([
        context("multiple_choice", 1),
        context("true_false", 2),
    ])
    assert "slot-1：" in mixed and "slot-2：" in mixed

    uniform = _batch_generation_prompt([
        context("single_choice", 1), context("single_choice", 2),
    ])
    assert "标准答案必须对应一个 option id" in uniform


def test_blanks_schema_only_appears_for_fill_blank() -> None:
    from assessment_orchestrator import _generation_prompt_v2

    fill_blank = {
        "assessment_slot": {
            "question_form": "fill_blank",
            "input_mode": "short_text",
            "validation_mode": "exact_validator",
        },
    }
    single = {
        "assessment_slot": {
            "question_form": "single_choice",
            "input_mode": "choice",
            "validation_mode": "exact_validator",
        },
    }
    assert '"blanks"' in _generation_prompt_v2(fill_blank)
    # 留在 schema 里模型会照着填一个空壳
    assert '"blanks"' not in _generation_prompt_v2(single)


# --- 语义义务按题型覆盖 -----------------------------------------------------


def test_multiple_choice_semantics_no_longer_demand_exactly_one() -> None:
    from assessment_semantics import (
        _semantics_for_question_form,
        semantics_for_question_type,
    )

    base = semantics_for_question_type("selected_response")
    multi = _semantics_for_question_form(base, "multiple_choice")

    assert any("Two or more" in text for text in multi["semantic_obligations"])
    assert not any(
        "Exactly one option" in text for text in multi["semantic_obligations"]
    )
    # 注册表本身不得被污染——它按 question_type 组织，与 question_form 是两个维度
    assert any(
        "Exactly one option" in text
        for text in semantics_for_question_type(
            "selected_response",
        )["semantic_obligations"]
    )


# --- 独立求解比较：顺序与文本 -----------------------------------------------


def test_solver_answer_order_does_not_break_multi_answer_validation() -> None:
    from assessment_orchestrator import _resolve_option_ids

    options = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
    assert sorted(_resolve_option_ids(["C", "A"], options)) == ["A", "C"]


def test_solver_answering_with_option_text_is_resolved() -> None:
    """判断题上模型常直接回「正确」而不是「A」。"""
    from assessment_orchestrator import _resolve_option_ids

    options = [{"id": "A", "text": "正确"}, {"id": "B", "text": "错误"}]
    assert _resolve_option_ids("正确", options) == {"A"}
    assert _resolve_option_ids("错误", options) == {"B"}
    # 对不上的原样保留，仍会判不一致——这不是放宽判定
    assert _resolve_option_ids("香蕉", options) == {"香蕉"}


def test_fill_blank_contract_passes_the_input_contract_gate() -> None:
    """填空的作答单元是空位不是字段；不认这条会在硬门上反复失败。"""
    from assessment_blueprint import INPUT_CONTRACT_SCHEMA
    from assessment_quality import _valid_input_contract

    assert _valid_input_contract({
        "schema_version": INPUT_CONTRACT_SCHEMA,
        "mode": "short_text",
        "blanks": [],
        "fields": [],
    }) is True
    # 普通短文本没有字段仍然不合法
    assert _valid_input_contract({
        "schema_version": INPUT_CONTRACT_SCHEMA,
        "mode": "short_text",
        "fields": [],
    }) is False


# --- 落库分类认合同声明 -----------------------------------------------------


def test_v2_items_are_classified_from_the_selection_contract() -> None:
    """V2 题落库时 answer_spec 被置空，只看答案永远判不出多选。"""
    from question_forms import classify_question_form

    v2_multi = {
        "question_spec": {
            "input_contract": {
                "mode": "choice",
                "selection": {"multiple": True},
            },
        },
        "options": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        "answer_spec": {},
    }
    assert classify_question_form(v2_multi) == "multiple_choice"

    v2_tf = deepcopy(v2_multi)
    v2_tf["question_spec"]["input_contract"]["selection"] = {
        "multiple": False, "true_false": True,
    }
    assert classify_question_form(v2_tf) == "true_false"


def test_multi_answer_question_survives_bank_alignment() -> None:
    """最危险的一条：合法多选此前会被静默改写成单选。"""
    from question_bank import _align_generated_contract_to_slot

    options = [
        {"id": "A", "text": "能量守恒"},
        {"id": "B", "text": "熵必减"},
        {"id": "C", "text": "ΔU=Q-W"},
    ]
    contract = {
        "prompt": "选出全部正确项。",
        "question_spec": {
            "schema_version": "question_spec_v2",
            "input_contract": {
                "mode": "choice",
                "selection": {"multiple": True},
            },
            "options": deepcopy(options),
            "task": {"rendered_text": "选出全部正确项"},
        },
        "solution_envelope": {
            "canonical_answer": ["A", "C"],
            "validation_mode": "exact_validator",
        },
        "options": deepcopy(options),
    }
    aligned = _align_generated_contract_to_slot(
        contract,
        {"input_mode": "choice", "question_type": "selected_response"},
        misconception_labels=["符号弄反"],
        variant_index=0,
    )
    spec = aligned["question_spec"]

    assert [o["id"] for o in spec["options"]] == ["A", "B", "C"], "选项被替换了"
    assert spec["task"]["rendered_text"] == "选出全部正确项", "题干被改写了"
    assert spec["presentation_contract"]["mode"] == "multiple_choice"
    assert spec["presentation_contract"]["selection_limit"] == 2
    assert spec["response_contract"]["required_parts"] == ["selected_option_ids"]


# --- 本地解题器的适用范围（M1 打开后暴露的真实故障） ----------------------


def test_local_solver_is_not_used_for_choice_questions() -> None:
    """拿一把算数值的尺子去量选择题，永远量不对。

    真机实测：模型给一道判断题也写了 solver_contract，本地解题器算出
    {"value": -90, "unit": "J"}，而该题标准答案是选项 id "A"。数值不可能等于
    选项 id，于是 VALIDATION_FAILED + PROMPT_SOLUTION_CONTRADICTION，四轮
    修复全废后丢弃——三类新题型的失败几乎全部是这一条。
    """
    from assessment_orchestrator import _local_solver_applicable

    assert _local_solver_applicable({
        "input_contract": {"mode": "choice"},
        "solver_contract": {"kind": "numeric_expression", "expression": "20-8"},
    }) is False


def test_local_solver_is_not_used_for_fill_blank() -> None:
    """填空的答案是逐空对照，本地解题器只产出单个值。"""
    from assessment_orchestrator import _local_solver_applicable

    assert _local_solver_applicable({
        "input_contract": {"mode": "short_text", "blanks": []},
    }) is False


def test_local_solver_still_applies_to_numeric_questions() -> None:
    """M1 的收益不能被这道闸门抹掉：数值题仍然走本地求解。"""
    from assessment_orchestrator import _local_solver_applicable

    assert _local_solver_applicable({
        "input_contract": {"mode": "numeric_unit"},
        "solver_contract": {"kind": "numeric_expression", "expression": "20-8"},
    }) is True
    assert _local_solver_applicable({
        "input_contract": {"mode": "structured_fields"},
    }) is True


# --- 跨线核查：lz-course-gen 报的三条契约缺陷 ------------------------------


def test_multi_answer_item_is_not_blocked_as_unexecutable() -> None:
    """多选的正确答案是复数键，只认单数键会把合法多选题硬阻断。

    V2 题因为能读到 canonical_answer 而侥幸逃过（这就是我的多选生成率能到
    10/10 的原因），但**非 V2 的多选题（旧题、教师导入）会被直接误杀**。
    """
    from question_bank import evaluate_question_item_quality

    legacy_multi = {
        "prompt": "下列关于热力学第一定律的说法中，选出全部成立的项并说明依据。",
        "options": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        "answer_spec": {"type": "choice", "correct_option_ids": ["A", "C"]},
        "source_type": "generated",
        "course_knowledge_refs": ["ckp_1"],
        "source_records": [{"source_type": "course_knowledge_base"}],
    }
    codes = [
        issue["code"]
        for issue in evaluate_question_item_quality(legacy_multi).get("issues", [])
    ]
    assert "question:answer_not_executable" not in codes


def test_answerless_item_is_still_blocked() -> None:
    """放宽是为了认复数键，不是把这道门关掉。"""
    from question_bank import evaluate_question_item_quality

    codes = [
        issue["code"]
        for issue in evaluate_question_item_quality({
            "prompt": "下列关于热力学第一定律的说法中，选出全部成立的项。",
            "options": [{"id": "A"}, {"id": "B"}],
            "answer_spec": {"type": "choice"},
            "source_type": "generated",
            "course_knowledge_refs": ["ckp_1"],
            "source_records": [{"source_type": "course_knowledge_base"}],
        }).get("issues", [])
    ]
    assert "question:answer_not_executable" in codes


def test_new_forms_do_not_degrade_to_rich_text_without_a_contract() -> None:
    """没带 input_contract 的多选/判断会退化成 rich_text——学生看到文本框而非选项。

    静默降级，不报错。practice_contracts.INPUT_MODES 是
    「question_type -> 输入模式」的映射，三个新形态此前不在里面。
    """
    from practice_contracts import (
        INPUT_MODE_BY_QUESTION_TYPE,
        enrich_question_contract,
    )

    assert INPUT_MODE_BY_QUESTION_TYPE["multiple_choice"] == "choice"
    assert INPUT_MODE_BY_QUESTION_TYPE["true_false"] == "choice"
    assert INPUT_MODE_BY_QUESTION_TYPE["fill_blank"] == "short_text"

    enriched = enrich_question_contract({
        "question_type": "multiple_choice",
        "prompt": "选出全部正确项",
        "answer_spec": {"correct_option_ids": ["A", "C"]},
        "options": [{"id": "A"}, {"id": "B"}],
    })
    assert enriched["input_contract"]["mode"] == "choice"


def test_input_modes_has_exactly_one_source_of_truth() -> None:
    """E2：`INPUT_MODES` 曾在三个文件各有一份且内容不同。

    前两处是同一个概念的两份副本却内容不一致，导致同一道题在不同门得到相反
    结论（详见下一条用例）。现在两处都指向 `assessment_input_modes` 的同一个
    对象——用 `is` 断言，改回各自定义会立刻失败。
    """
    from assessment_blueprint import INPUT_MODES as blueprint_modes
    from assessment_compiler import INPUT_MODES as compiler_modes
    from assessment_input_modes import INPUT_MODES as canonical

    assert blueprint_modes is canonical
    assert compiler_modes is canonical


def test_question_type_mapping_is_a_different_concept_and_stays_in_range() -> None:
    """第三处是「题型 -> 模式」的映射，不是模式集合，不能合并进来。

    但它的**值域**必须落在唯一真源里——否则又会产出没人认识的模式。
    """
    from assessment_input_modes import INPUT_MODES as canonical
    from practice_contracts import INPUT_MODE_BY_QUESTION_TYPE as mapping

    assert isinstance(mapping, dict)
    assert set(mapping.values()) <= canonical


def test_every_mapped_question_type_passes_the_input_contract_gate() -> None:
    """合并前的真实缺陷：6 种题型的作答模式被质量门判为非法。

    `practice_contracts` 为 implementation_task / evidence_analysis /
    mechanism_explanation / source_argument / language_production /
    scenario_deliverable 产出 structured_text / code_and_text /
    language_response，而质量门校验的是蓝图侧那份只有 6 项的集合——
    于是这些题的输入合同当场判 INPUT_CONTRACT_MISMATCH。
    """
    from assessment_blueprint import INPUT_CONTRACT_SCHEMA
    from assessment_quality import _valid_input_contract
    from practice_contracts import INPUT_MODE_BY_QUESTION_TYPE as mapping

    rejected = [
        question_type
        for question_type, mode in mapping.items()
        if not _valid_input_contract({
            "schema_version": INPUT_CONTRACT_SCHEMA,
            "mode": mode,
            "fields": [{"field_id": "answer", "required": True}],
        })
    ]
    assert rejected == [], f"这些题型的作答模式过不了质量门：{rejected}"
