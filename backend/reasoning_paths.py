"""Compile subject-neutral reasoning paths into hints and worked solutions.

Question adapters describe concrete inputs and an executable answer contract.
This module turns that structured contract into one shared pedagogical
protocol.  Hints and full solutions therefore come from the same frozen path
instead of unrelated prose templates.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


REASONING_PATH_SCHEMA = "reasoning_path_v1"
SOLUTION_SPEC_SCHEMA = "solution_spec_v1"


_ACTION_FAMILIES = {
    "integrate_and_validate": "integrate_and_validate",
    "execute_and_compare": "execute_and_trace",
    "execute_hash_operations": "execute_and_trace",
    "execute_heap_operations": "execute_and_trace",
    "execute_balanced_tree_insertions": "execute_and_trace",
    "implement_test_and_analyze_avl": "implement_and_test",
    "solve_and_verify": "solve_and_verify",
    "implement_transform_and_test": "implement_and_test",
    "trace_output_and_return": "execute_and_trace",
    "design_and_justify": "design_and_justify",
    "analyze_evidence": "analyze_evidence",
    "explain_mechanism": "explain_mechanism",
    "construct_evidence_argument": "construct_evidence_argument",
    "produce_contextual_language": "produce_constrained_response",
    "evaluate_and_recommend": "evaluate_and_recommend",
    "teacher_define_task": "teacher_review",
}

_FAMILY_METHODS = {
    "integrate_and_validate": (
        "先分别处理每份材料，再写出材料之间的连接，最后检查各部分结论是否一致"
    ),
    "execute_and_trace": (
        "按题目规定的顺序执行操作，每一步都记录当前状态、下一选择和状态变化"
    ),
    "implement_and_test": (
        "先固定输入输出与边界规则，再实现核心处理，并用正常、边界和失败样例验证"
    ),
    "solve_and_verify": (
        "把条件转换为可计算或可推理的关系，保留关键中间结果，再用原条件验证"
    ),
    "design_and_justify": (
        "先分解目标和约束，再设计组件与连接关系，并用失败场景和验收条件检验"
    ),
    "analyze_evidence": (
        "先分别提取或计算每组证据，再比较差异，用误差和局限限定结论"
    ),
    "explain_mechanism": (
        "按刺激、变化、调节信号、作用对象、结果和反馈的顺序建立机制链"
    ),
    "construct_evidence_argument": (
        "先提出范围有限的论点，再逐条连接材料证据、推理依据和可能局限"
    ),
    "produce_constrained_response": (
        "先排列内容顺序和表达要求，再完成草稿，最后逐项核对形式与语义约束"
    ),
    "evaluate_and_recommend": (
        "先按硬约束筛除不可行项，再依规则比较可行项，并说明建议及剩余风险"
    ),
    "structured_performance": (
        "按题目给定的输入、产物和检查条件逐项完成，并保留判断依据"
    ),
    "teacher_review": "等待教师补充可作答材料、明确产物和验证方式",
}

_INPUT_LABELS = {
    "vertices": "顶点集合",
    "edges": "边集合",
    "start_vertex": "起点",
    "directed": "是否有向",
    "neighbor_order": "邻接访问顺序",
    "adjacency_list": "邻接表",
    "records": "记录集合",
    "rules": "处理规则",
    "code": "待分析代码",
    "code_skeleton": "代码骨架",
    "test_cases": "测试用例",
    "groups": "实验分组",
    "measurements": "测量数据",
    "sources": "材料集合",
    "events": "事件序列",
    "options": "候选方案",
    "weights": "评分权重",
    "budget": "预算上限",
    "deadline": "工期上限",
    "basis": "有序基",
    "target": "目标向量",
    "vectors": "向量组",
    "matrix": "矩阵",
    "left": "第一个输入",
    "right": "第二个输入",
    "equations": "方程组",
}

_OUTPUT_LABELS = {
    "method": "方法依据",
    "steps": "关键过程",
    "answer": "任务结果",
    "verification": "结果检验",
    "claim": "有限论点",
    "evidence": "材料证据",
    "reasoning": "证据与论点的连接",
    "limitation": "结论局限",
    "implementation": "可运行实现",
    "tests": "验证用例",
    "bfs_order": "BFS访问顺序",
    "dfs_order": "DFS访问顺序",
    "trace": "过程轨迹",
    "result_check": "结果检查",
}


def compile_reasoning_support(
    payload: dict[str, Any],
    *,
    contrast_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one path plus hints and solution derived from that path."""
    normalized = deepcopy(payload)
    specialized = _math_reasoning_support(normalized)
    if specialized is None:
        path = _generic_reasoning_path(
            normalized,
            contrast_payload=contrast_payload,
        )
        hints = _hints_from_path(
            path,
            explicit_contract=normalized.get("hint_contract"),
        )
        solution = _solution_from_path(
            path,
            normalized.get("answer_spec") or {},
        )
    else:
        path, hints, solution = specialized

    answer_spec = deepcopy(normalized.get("answer_spec") or {})
    existing_solution = answer_spec.get("solution_spec")
    if isinstance(existing_solution, dict) and existing_solution.get("steps"):
        solution = deepcopy(existing_solution)
    answer_spec["solution_spec"] = solution

    return {
        "reasoning_path": path,
        "hint_contract": hints,
        "answer_spec": answer_spec,
        "complete": path.get("completeness") == "complete",
    }


def validate_reasoning_support(spec: dict[str, Any]) -> list[dict[str, str]]:
    """Validate the shared path protocol without trusting generation flags."""
    issues: list[dict[str, str]] = []
    path = spec.get("reasoning_path")
    if not isinstance(path, dict):
        return [{
            "code": "question:reasoning_path_missing",
            "severity": "critical",
        }]
    if path.get("schema_version") != REASONING_PATH_SCHEMA:
        issues.append({
            "code": "question:reasoning_path_schema_invalid",
            "severity": "critical",
        })
    if path.get("completeness") != "complete":
        issues.append({
            "code": "question:semantic_archetype_unavailable",
            "severity": "critical",
        })
    if not path.get("operator_family"):
        issues.append({
            "code": "question:reasoning_operator_missing",
            "severity": "critical",
        })
    if not path.get("input_anchors"):
        issues.append({
            "code": "question:reasoning_inputs_missing",
            "severity": "critical",
        })
    steps = path.get("steps") or []
    if len(steps) < 3 or any(
        not str(step.get("instruction") or "").strip()
        or not str(step.get("check") or "").strip()
        for step in steps
        if isinstance(step, dict)
    ):
        issues.append({
            "code": "question:reasoning_steps_incomplete",
            "severity": "critical",
        })

    hints = spec.get("hint_contract") or {}
    levels = hints.get("levels") or []
    if (
        hints.get("generator") != REASONING_PATH_SCHEMA
        or {int(level.get("level") or 0) for level in levels} != {1, 2, 3}
        or any(
            len(str(level.get("content") or "").strip()) < 12
            or not level.get("step_refs")
            for level in levels
        )
    ):
        issues.append({
            "code": "question:hint_not_path_derived",
            "severity": "critical",
        })

    solution = (spec.get("answer_spec") or {}).get("solution_spec") or {}
    if (
        solution.get("schema_version") != SOLUTION_SPEC_SCHEMA
        or not solution.get("steps")
        or not solution.get("checks")
    ):
        issues.append({
            "code": "question:solution_path_missing",
            "severity": "critical",
        })
    return issues


def _generic_reasoning_path(
    payload: dict[str, Any],
    *,
    contrast_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    stimulus = payload.get("stimulus") or {}
    task = payload.get("task") or {}
    response = payload.get("response_contract") or {}
    answer = payload.get("answer_spec") or {}
    action = str(task.get("action") or "")
    family = _ACTION_FAMILIES.get(action, "structured_performance")
    anchors = _input_anchors(stimulus.get("data"))
    has_structured_anchors = bool(anchors)
    if not anchors:
        rendered_text = str(stimulus.get("rendered_text") or "").strip()
        anchors = [{
            "path": "rendered_text",
            "label": "题目说明",
            "value_preview": rendered_text or "当前冻结任务",
            "value_type": "str",
        }]
    required_parts = [
        str(value).strip()
        for value in response.get("required_parts") or []
        if str(value).strip()
    ]
    criteria = [
        str(value).strip()
        for value in answer.get("criteria") or []
        if str(value).strip()
    ]
    checks = [
        str(value).strip()
        for value in payload.get("result_checks") or []
        if str(value).strip()
    ]
    input_names = [anchor["path"] for anchor in anchors[:4]]
    output_parts = required_parts or criteria[:3] or ["task_result"]
    input_labels = [
        _input_label(value) for value in input_names
    ]
    output_labels = [
        _output_label(value) for value in output_parts
    ]
    primary_check = checks[0] if checks else "结果能够由题目输入复核"
    method = _FAMILY_METHODS[family]
    steps = [
        {
            "step_id": "orient",
            "kind": "orient",
            "instruction": (
                f"从给定材料中定位{_join(input_labels)}，并把它们对应到"
                f"“{task.get('deliverable') or task.get('rendered_text')}”。"
            ),
            "uses_inputs": input_names,
            "produces": ["input_map"],
            "check": "每个待处理对象都能在题目材料中定位",
        },
        {
            "step_id": "transform",
            "kind": "transform",
            "instruction": (
                f"{method}；依次形成{_join(output_labels)}，"
                "每个判断后紧邻写出所用数据、材料或规则。"
            ),
            "uses_inputs": ["input_map"],
            "produces": output_parts,
            "check": criteria[0] if criteria else "过程覆盖题目要求的全部产物",
        },
        {
            "step_id": "verify",
            "kind": "verify",
            "instruction": f"对已得到的产物执行检查：{_join(checks[:3])}。",
            "uses_inputs": output_parts,
            "produces": ["verified_result"],
            "check": primary_check,
        },
    ]
    archetype = str(payload.get("archetype_id") or "")
    complete = (
        family != "teacher_review"
        and archetype != "topic_aligned_mathematical_reasoning"
        and (
            has_structured_anchors
            or str(stimulus.get("kind") or "") == "legacy_question"
        )
    )
    contrast = _contrast_example(contrast_payload, steps[1]["instruction"])
    return {
        "schema_version": REASONING_PATH_SCHEMA,
        "archetype_id": archetype,
        "operator_family": family,
        "goal": {
            "action": action,
            "deliverable": str(task.get("deliverable") or ""),
        },
        "input_anchors": anchors,
        "steps": steps,
        "contrast_example": contrast,
        "completeness": "complete" if complete else "incomplete",
        "derived_from": {
            "stimulus_kind": str(stimulus.get("kind") or ""),
            "response_format": str(response.get("format") or ""),
        },
    }


def _hints_from_path(
    path: dict[str, Any],
    *,
    explicit_contract: Any,
) -> dict[str, Any]:
    explicit_levels = (
        deepcopy(explicit_contract.get("levels") or [])
        if isinstance(explicit_contract, dict)
        else []
    )
    if len(explicit_levels) == 3:
        levels = explicit_levels
        for level, step_id in zip(
            levels,
            ("orient", "transform", "verify"),
            strict=True,
        ):
            level["step_refs"] = [step_id]
    else:
        anchors = path.get("input_anchors") or []
        fallback_anchor = {
            "path": "task",
            "label": "任务要求",
            "value_preview": str(
                (path.get("goal") or {}).get("deliverable")
                or "按当前题目要求完成作答"
            ),
            "value_type": "str",
        }
        first_anchor = anchors[0] if anchors else fallback_anchor
        second_anchor = anchors[1] if len(anchors) > 1 else first_anchor
        steps = path["steps"]
        contrast = path.get("contrast_example") or {}
        levels = [
            {
                "level": 1,
                "kind": "orientation",
                "content": (
                    f"先定位题目中的{first_anchor['label']}="
                    f"{first_anchor['value_preview']}。{steps[0]['instruction']}"
                ),
                "step_refs": ["orient"],
            },
            {
                "level": 2,
                "kind": "method_skeleton",
                "content": (
                    f"下一步使用{second_anchor['label']}="
                    f"{second_anchor['value_preview']}。{steps[1]['instruction']}"
                    f"完成后先检查：{steps[1]['check']}。"
                ),
                "step_refs": ["transform"],
            },
            {
                "level": 3,
                "kind": "local_scaffold",
                "content": (
                    f"对照例：{contrast.get('input') or '使用同结构的另一组材料'}"
                    f"局部示范：{contrast.get('worked_step') or steps[1]['instruction']}"
                ),
                "step_refs": ["transform", "verify"],
            },
        ]
    return {
        "generator": REASONING_PATH_SCHEMA,
        "levels": levels,
        "grounding": {
            "reasoning_path_schema": REASONING_PATH_SCHEMA,
            "input_anchor_paths": [
                anchor["path"] for anchor in path.get("input_anchors") or []
            ],
        },
    }


def _solution_from_path(
    path: dict[str, Any],
    answer_spec: dict[str, Any],
) -> dict[str, Any]:
    final_answer = deepcopy(answer_spec.get("canonical_answer"))
    solution = {
        "schema_version": SOLUTION_SPEC_SCHEMA,
        "summary": (
            f"沿“{path.get('operator_family')}”路径处理输入、形成产物并完成验证。"
        ),
        "steps": [
            str(step.get("instruction") or "")
            for step in path.get("steps") or []
        ],
        "checks": [
            str(step.get("check") or "")
            for step in path.get("steps") or []
            if str(step.get("check") or "").strip()
        ],
        "representation": {
            "kind": "reasoning_path",
            "content": deepcopy(path.get("steps") or []),
        },
    }
    if final_answer is not None:
        solution["final_answer"] = final_answer
    else:
        solution["response_requirements"] = deepcopy(
            answer_spec.get("criteria") or []
        )
    return solution


def _math_reasoning_support(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    stimulus = payload.get("stimulus") or {}
    data = stimulus.get("data") or {}
    case_kind = str(data.get("case_kind") or "")
    archetype = str(payload.get("archetype_id") or "")
    if case_kind == "basis_coordinates":
        return _basis_coordinate_support(payload)
    if case_kind == "linear_system":
        return _linear_system_support(payload)
    if case_kind == "vector_operations":
        return _vector_support(payload)
    if case_kind == "matrix_operations":
        return _matrix_support(payload)
    if archetype == "topic_aligned_mathematical_reasoning":
        return None
    return None


def _basis_coordinate_support(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    data = payload["stimulus"]["data"]
    basis = data["basis"]
    target = data["target"]
    first, second = basis
    x_value, y_value = target
    coefficient_b = y_value
    coefficient_a = x_value - coefficient_b
    equation = (
        f"w=a{_tuple(first)}+b{_tuple(second)}"
    )
    expanded = f"(a+b,b)={_tuple(target)}"
    steps = [
        {
            "step_id": "model",
            "kind": "orient",
            "instruction": f"设未知坐标为(a,b)，按有序基写出 {equation}。",
            "uses_inputs": ["basis", "target"],
            "produces": ["coordinate_equation"],
            "check": "两个系数的顺序与有序基B一致",
        },
        {
            "step_id": "compare",
            "kind": "transform",
            "instruction": (
                f"把线性组合展开并比较分量：{expanded}；"
                "先由第二个分量求b，再由第一个分量求a。"
            ),
            "uses_inputs": ["coordinate_equation"],
            "produces": ["a", "b"],
            "check": "两个分量方程同时成立",
        },
        {
            "step_id": "verify",
            "kind": "verify",
            "instruction": (
                f"将a={coefficient_a}、b={coefficient_b}代回原线性组合，"
                f"重构结果应为{_tuple(target)}。"
            ),
            "uses_inputs": ["a", "b", "basis"],
            "produces": ["reconstructed_vector"],
            "check": "重构向量与目标向量逐分量相等",
        },
    ]
    path = _path_record(payload, "solve_and_verify", steps)
    path["contrast_example"] = {
        "input": (
            f"仍取B=({_tuple(first)},{_tuple(second)})，改取w'=(5,3)。"
        ),
        "worked_step": (
            "写成(a+b,b)=(5,3)，先得b=3，再由a+b=5得a=2；"
            "最后用2(1,0)+3(1,1)重构。"
        ),
        "differs_from_current": target != [5, 3],
    }
    hints = _path_hint_contract(path, [
        (
            f"把未知坐标记为(a,b)，先写 {equation}。"
            "观察哪个分量只含一个未知数。"
        ),
        (
            f"展开后得到 {expanded}。先比较第二个分量求b，"
            "再回代第一个分量求a，暂时不要跳到最终结论。"
        ),
        (
            f"对照例：{path['contrast_example']['input']}"
            f"{path['contrast_example']['worked_step']}"
            "把同样步骤迁移到原题。"
        ),
    ])
    canonical = deepcopy((payload.get("answer_spec") or {}).get("canonical_answer"))
    solution = _math_solution(
        path,
        summary="把目标向量表示为有序基向量的线性组合，再比较分量求系数。",
        steps=[
            f"设w=a{_tuple(first)}+b{_tuple(second)}，展开得到{expanded}。",
            f"由第二个分量得b={coefficient_b}，代入第一个分量得a={coefficient_a}。",
            (
                f"验证：{coefficient_a}{_tuple(first)}+"
                f"{coefficient_b}{_tuple(second)}={_tuple(target)}。"
            ),
        ],
        final_answer=canonical,
    )
    return path, hints, solution


def _linear_system_support(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    data = payload["stimulus"]["data"]
    equations = data["equations"]
    first, second = equations
    first_text = _equation_text(first)
    second_text = _equation_text(second)
    canonical = deepcopy((payload.get("answer_spec") or {}).get("canonical_answer"))
    x_value = canonical["x"]
    y_value = canonical["y"]
    steps = [
        {
            "step_id": "model",
            "kind": "orient",
            "instruction": f"保留方程顺序并标记①{first_text}、②{second_text}。",
            "uses_inputs": ["equations"],
            "produces": ["ordered_equations"],
            "check": "常数项和未知数系数抄写无误",
        },
        {
            "step_id": "eliminate",
            "kind": "transform",
            "instruction": "选择相加或倍乘后相减消去一个未知数，再回代求另一个未知数。",
            "uses_inputs": ["ordered_equations"],
            "produces": ["x", "y"],
            "check": "消元后的等式与原方程组等价",
        },
        {
            "step_id": "verify",
            "kind": "verify",
            "instruction": f"把x={x_value}、y={y_value}分别代回①和②。",
            "uses_inputs": ["x", "y"],
            "produces": ["verified_solution"],
            "check": "两个方程左右两边分别相等",
        },
    ]
    path = _path_record(payload, "solve_and_verify", steps)
    path["contrast_example"] = {
        "input": "方程组x+y=5，2x-y=1。",
        "worked_step": "将两式相加得到3x=6，所以x=2；再回代得到y=3。",
        "differs_from_current": True,
    }
    hints = _path_hint_contract(path, [
        f"先把方程标成①{first_text}、②{second_text}，观察相加后能消去哪一个未知数。",
        "把①与②相加消去y，先求x；再将x代回①求y，并保留等号两侧的运算。",
        "对照例：x+y=5，2x-y=1。两式相加得3x=6，再回代；把这一消元顺序迁移到原题。",
    ])
    solution = _math_solution(
        path,
        summary="通过消元得到一个未知数，再回代并用原方程组验算。",
        steps=[
            f"原方程组为①{first_text}，②{second_text}。",
            f"联立消元并回代得到x={x_value}、y={y_value}。",
            f"将x={x_value}、y={y_value}代回两个原方程，左右两边均相等。",
        ],
        final_answer=canonical,
    )
    return path, hints, solution


def _vector_support(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    data = payload["stimulus"]["data"]
    left = data["left"]
    right = data["right"]
    steps = _calculation_steps(
        "分别按分量计算向量和，按对应分量乘积之和计算点积与范数平方",
        checks=["向量和维度不变", "点积与范数平方为标量"],
    )
    path = _path_record(payload, "solve_and_verify", steps)
    path["contrast_example"] = {
        "input": "取u'=(1,2)、v'=(3,-1)。",
        "worked_step": "先算u'+v'=(1+3,2-1)=(4,1)，其余量仍按对应分量计算。",
        "differs_from_current": True,
    }
    hints = _path_hint_contract(path, [
        f"先并排写出u={_tuple(left)}、v={_tuple(right)}，区分向量结果与标量结果。",
        "向量和逐分量相加；点积把对应分量相乘后求和；‖u‖²只使用u的分量。",
        "对照例：u'=(1,2)、v'=(3,-1)，先得u'+v'=(4,1)；按相同分量对应关系处理原题。",
    ])
    solution = _math_solution_from_answer(path, payload)
    return path, hints, solution


def _matrix_support(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    data = payload["stimulus"]["data"]
    left = data["left"]
    right = data["right"]
    steps = _calculation_steps(
        "用A的每一行与B的每一列做点积得到AB，再用主对角乘积减副对角乘积求det(A)",
        checks=["AB仍为2×2矩阵", "det(A)为标量"],
    )
    path = _path_record(payload, "solve_and_verify", steps)
    path["contrast_example"] = {
        "input": "取A'=[[1,2],[0,1]]、B'=单位矩阵。",
        "worked_step": "第一项由A'第一行与B'第一列点积得到1，且A'B'=A'。",
        "differs_from_current": True,
    }
    hints = _path_hint_contract(path, [
        f"先确认A={_compact(left)}、B={_compact(right)}都是2×2，AB的第(i,j)项来自A第i行与B第j列。",
        "逐项完成四次行列点积；det(A)单独按a₁₁a₂₂-a₁₂a₂₁计算。",
        "对照例：矩阵乘单位矩阵保持不变。先用第一行与第一列验证一个元素，再迁移到原题其余元素。",
    ])
    solution = _math_solution_from_answer(path, payload)
    return path, hints, solution


def _path_record(
    payload: dict[str, Any],
    operator_family: str,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    stimulus = payload.get("stimulus") or {}
    task = payload.get("task") or {}
    return {
        "schema_version": REASONING_PATH_SCHEMA,
        "archetype_id": str(payload.get("archetype_id") or ""),
        "operator_family": operator_family,
        "goal": {
            "action": str(task.get("action") or ""),
            "deliverable": str(task.get("deliverable") or ""),
        },
        "input_anchors": _input_anchors(stimulus.get("data")),
        "steps": steps,
        "contrast_example": {},
        "completeness": "complete",
        "derived_from": {
            "stimulus_kind": str(stimulus.get("kind") or ""),
            "response_format": str(
                (payload.get("response_contract") or {}).get("format") or ""
            ),
        },
    }


def _path_hint_contract(
    path: dict[str, Any],
    contents: list[str],
) -> dict[str, Any]:
    kinds = ("orientation", "method_skeleton", "local_scaffold")
    refs = (["model"], ["compare"], ["compare", "verify"])
    available_ids = {
        str(step.get("step_id") or "") for step in path.get("steps") or []
    }
    fallback_ids = [
        str(step.get("step_id") or "") for step in path.get("steps") or []
    ]
    levels = []
    for index, content in enumerate(contents):
        step_refs = [value for value in refs[index] if value in available_ids]
        if not step_refs:
            step_refs = fallback_ids[min(index, len(fallback_ids) - 1):index + 1]
        levels.append({
            "level": index + 1,
            "kind": kinds[index],
            "content": content,
            "step_refs": step_refs,
        })
    return {
        "generator": REASONING_PATH_SCHEMA,
        "levels": levels,
        "grounding": {
            "reasoning_path_schema": REASONING_PATH_SCHEMA,
            "input_anchor_paths": [
                anchor["path"] for anchor in path.get("input_anchors") or []
            ],
        },
    }


def _math_solution(
    path: dict[str, Any],
    *,
    summary: str,
    steps: list[str],
    final_answer: Any,
) -> dict[str, Any]:
    return {
        "schema_version": SOLUTION_SPEC_SCHEMA,
        "summary": summary,
        "steps": steps,
        "final_answer": deepcopy(final_answer),
        "checks": [
            str(step.get("check") or "")
            for step in path.get("steps") or []
        ],
        "representation": {
            "kind": "reasoning_path",
            "content": deepcopy(path.get("steps") or []),
        },
    }


def _math_solution_from_answer(
    path: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    return _math_solution(
        path,
        summary=str(path["steps"][1]["instruction"]),
        steps=[
            str(step.get("instruction") or "")
            for step in path.get("steps") or []
        ],
        final_answer=deepcopy(
            (payload.get("answer_spec") or {}).get("canonical_answer")
        ),
    )


def _calculation_steps(
    method: str,
    *,
    checks: list[str],
) -> list[dict[str, Any]]:
    return [
        {
            "step_id": "model",
            "kind": "orient",
            "instruction": "标记每个输入对象、维度和待求量，避免混用不同运算。",
            "uses_inputs": ["case_inputs"],
            "produces": ["operation_map"],
            "check": "每个待求量都已对应到具体输入",
        },
        {
            "step_id": "calculate",
            "kind": "transform",
            "instruction": method,
            "uses_inputs": ["operation_map"],
            "produces": ["calculated_results"],
            "check": checks[0],
        },
        {
            "step_id": "verify",
            "kind": "verify",
            "instruction": f"分别检查：{_join(checks)}。",
            "uses_inputs": ["calculated_results"],
            "produces": ["verified_results"],
            "check": checks[-1],
        },
    ]


def _input_anchors(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return [{
            "path": "input",
            "label": "题目输入",
            "value_preview": _compact(value),
            "value_type": type(value).__name__,
        }]
    anchors = []
    for key, nested in value.items():
        if key in {
            "case_kind",
            "expected_stdout",
            "expected_return_value",
            "language",
        } or nested in (None, "", [], {}):
            continue
        anchors.append({
            "path": str(key),
            "label": _input_label(str(key)),
            "value_preview": _compact(nested),
            "value_type": type(nested).__name__,
        })
    return anchors


def _contrast_example(
    payload: dict[str, Any] | None,
    worked_step: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "input": "",
            "worked_step": worked_step,
            "differs_from_current": False,
        }
    rendered = str((payload.get("stimulus") or {}).get("rendered_text") or "")
    anchors = _input_anchors((payload.get("stimulus") or {}).get("data"))
    anchor_instruction = ""
    if anchors:
        anchor_instruction = (
            f"先标出{anchors[0]['label']}={anchors[0]['value_preview']}，"
        )
    return {
        "input": rendered,
        "worked_step": (
            f"{anchor_instruction}再执行局部步骤：{worked_step}"
        ),
        "differs_from_current": True,
    }


def _equation_text(equation: dict[str, Any]) -> str:
    a = equation["a"]
    b = equation["b"]
    sign = "+" if b >= 0 else "-"
    b_abs = abs(b)
    b_term = "y" if b_abs == 1 else f"{b_abs}y"
    a_term = "x" if a == 1 else f"{a}x"
    return f"{a_term}{sign}{b_term}={equation['c']}"


def _tuple(values: list[Any]) -> str:
    return f"({','.join(str(value) for value in values)})"


def _compact(value: Any, limit: int = 180) -> str:
    if isinstance(value, str):
        rendered = " ".join(value.split())
    else:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return rendered if len(rendered) <= limit else f"{rendered[:limit - 1]}…"


def _join(values: list[Any]) -> str:
    normalized = [str(value).strip() for value in values if str(value).strip()]
    return "、".join(normalized) if normalized else "题目输入"


def _input_label(path: str) -> str:
    return _INPUT_LABELS.get(path, path.replace("_", " "))


def _output_label(path: str) -> str:
    return _OUTPUT_LABELS.get(path, path.replace("_", " "))
