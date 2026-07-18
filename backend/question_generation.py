"""Cross-subject structured question generation and domain validation.

The module deliberately generates a typed question specification before any
student-facing prose.  Subject adapters own stimulus construction, answer
contracts, and validation.  Unknown domains remain teacher-review candidates
instead of falling back to an unrelated generic prompt.
"""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable


QUESTION_SPEC_SCHEMA = "question_spec_v1"

PRACTICE_LABELS = {
    "concept_check": "概念辨析",
    "objective_practice": "情境应用",
    "mastery_check": "独立达标",
    "final_assessment": "综合测评",
}

STIMULUS_KIND_BY_ADAPTER = {
    "computer_science.graph_traversal": "graph",
    "computer_science.hashing": "hash_table",
    "computer_science.heap": "heap_operations",
    "computer_science.avl_tree": "tree_operations",
    "programming.system_design": "system_requirements",
    "programming.data_processing": "programming_case",
    "math.quantitative_reasoning": "quantitative_problem",
    "science.controlled_experiment": "controlled_experiment",
    "life_science.mechanism_case": "mechanism_case",
    "humanities.evidence_argument": "source_set",
    "language.contextual_production": "language_context",
    "business.constrained_decision": "decision_case",
    "cross_subject.integrated_performance": "multi_source_case",
    "fallback.teacher_review": "unstructured_context",
}


@dataclass(frozen=True)
class AdapterContext:
    course_data: dict[str, Any]
    node: dict[str, Any]
    practice_level: str
    variant_index: int
    subject_family: str
    topic_text: str
    objective: str
    key_points: list[str]
    assessments: list[str]


AdapterBuilder = Callable[[AdapterContext], dict[str, Any]]


def generate_question_contract(
    course_data: dict[str, Any],
    node: dict[str, Any],
    practice_level: str,
    variant_index: int,
) -> dict[str, Any]:
    """Build, validate, and render one cross-subject question contract."""
    context = _adapter_context(
        course_data,
        node,
        practice_level,
        variant_index,
    )
    adapter_id, builder = _select_adapter(context)
    payload = builder(context)
    source_records = _course_document_source_records(
        course_data,
        str(node.get("node_id") or ""),
    )
    risk_flags = list(payload.get("risk_flags") or [])
    if adapter_id == "fallback.teacher_review":
        risk_flags.append("adapter_unavailable")
    if context.subject_family == "life_medical":
        risk_flags.append("high_stakes_domain")
    risk_flags = _unique(risk_flags)

    question_spec = {
        "schema_version": QUESTION_SPEC_SCHEMA,
        "adapter_id": adapter_id,
        "subject_family": context.subject_family,
        "archetype_id": str(payload["archetype_id"]),
        "node_id": str(node.get("node_id") or ""),
        "practice_level": practice_level,
        "target": {
            "objective": context.objective,
            "knowledge_points": context.key_points,
            "assessment_actions": context.assessments,
        },
        "stimulus": deepcopy(payload["stimulus"]),
        "task": deepcopy(payload["task"]),
        "constraints": list(payload["constraints"]),
        "response_contract": deepcopy(payload["response_contract"]),
        "answer_spec": deepcopy(payload["answer_spec"]),
        "result_checks": list(payload["result_checks"]),
        "provenance": {
            "course_id": str(course_data.get("course_id") or ""),
            "source_priority": (
                "course_document"
                if source_records
                else "course_knowledge_contract"
            ),
            "source_refs": deepcopy(source_records),
        },
        "risk": {
            "flags": risk_flags,
            "requires_review": bool(
                payload.get("review_required")
                or adapter_id == "fallback.teacher_review"
                or context.subject_family == "life_medical"
            ),
        },
    }
    validation = validate_question_spec(question_spec)
    presentation = _render_question(context, question_spec)
    return {
        **presentation,
        "question_spec": question_spec,
        "domain_validation": validation,
        "answer_spec": deepcopy(question_spec["answer_spec"]),
        "risk_flags": risk_flags,
        "review_required": bool(
            question_spec["risk"]["requires_review"]
            or validation["status"] != "passed"
        ),
        "source_records": source_records,
    }


def validate_question_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Recompute domain compatibility and answer executability."""
    issues: list[dict[str, str]] = []
    adapter_id = str(spec.get("adapter_id") or "")
    stimulus = spec.get("stimulus") or {}
    task = spec.get("task") or {}
    answer_spec = spec.get("answer_spec") or {}
    target = spec.get("target") or {}

    if spec.get("schema_version") != QUESTION_SPEC_SCHEMA:
        issues.append(_issue("question:spec_schema_invalid", "critical"))
    if not adapter_id or adapter_id not in STIMULUS_KIND_BY_ADAPTER:
        issues.append(_issue("question:adapter_unavailable", "major"))
    expected_kind = STIMULUS_KIND_BY_ADAPTER.get(adapter_id)
    if expected_kind and stimulus.get("kind") != expected_kind:
        issues.append(_issue("question:input_task_incompatible", "critical"))
    if not str(target.get("objective") or "").strip():
        issues.append(_issue("question:target_missing", "critical"))
    if not str(stimulus.get("rendered_text") or "").strip():
        issues.append(_issue("question:input_material_missing", "critical"))
    if not str(task.get("rendered_text") or "").strip():
        issues.append(_issue("question:task_missing", "critical"))
    if not (answer_spec.get("criteria") or answer_spec.get("canonical_answer") is not None):
        issues.append(_issue("question:answer_not_executable", "critical"))

    adapter_validator = {
        "computer_science.graph_traversal": _validate_graph_spec,
        "computer_science.hashing": _validate_hashing_spec,
        "computer_science.heap": _validate_heap_spec,
        "computer_science.avl_tree": _validate_tree_spec,
        "programming.system_design": _validate_rubric_spec,
        "programming.data_processing": _validate_programming_spec,
        "math.quantitative_reasoning": _validate_math_spec,
        "science.controlled_experiment": _validate_science_spec,
        "life_science.mechanism_case": _validate_rubric_spec,
        "humanities.evidence_argument": _validate_humanities_spec,
        "language.contextual_production": _validate_language_spec,
        "business.constrained_decision": _validate_business_spec,
        "cross_subject.integrated_performance": _validate_integrated_spec,
        "fallback.teacher_review": _validate_fallback_spec,
    }.get(adapter_id)
    if adapter_validator:
        issues.extend(adapter_validator(spec))

    issues = _deduplicate_issues(issues)
    critical = any(issue["severity"] == "critical" for issue in issues)
    major = any(issue["severity"] == "major" for issue in issues)
    return {
        "schema_version": "question_domain_validation_v1",
        "passed": not critical,
        "status": "failed" if critical else ("needs_review" if major else "passed"),
        "adapter_id": adapter_id,
        "validation_mode": str(answer_spec.get("validation_mode") or "rubric"),
        "issues": issues,
        "checks": {
            "schema": not any(
                issue["code"] == "question:spec_schema_invalid"
                for issue in issues
            ),
            "input_completeness": not any(
                issue["code"] in {
                    "question:input_material_missing",
                    "question:graph_input_incomplete",
                    "question:experiment_input_incomplete",
                    "question:source_set_incomplete",
                }
                for issue in issues
            ),
            "input_task_compatibility": not any(
                issue["code"] == "question:input_task_incompatible"
                for issue in issues
            ),
            "answer_executable": not any(
                issue["code"] in {
                    "question:answer_not_executable",
                    "question:canonical_answer_mismatch",
                }
                for issue in issues
            ),
            "semantic_alignment": not critical,
        },
    }


def generate_cross_chapter_contract(
    course_data: dict[str, Any],
    nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a concrete, teacher-reviewed cross-chapter performance task."""
    component_contracts = [
        generate_question_contract(
            course_data,
            node,
            "mastery_check",
            index + 5,
        )
        for index, node in enumerate(nodes[:4])
    ]
    subject_family = str(
        (course_data.get("subject_pedagogy_profile") or {}).get(
            "primary_mode"
        )
        or "general"
    )
    objectives = [
        str(node.get("learning_objective") or node.get("node_name") or "")
        for node in nodes[:4]
    ]
    knowledge_points = _unique([
        str(point)
        for node in nodes[:4]
        for point in node.get("key_points") or []
        if str(point).strip()
    ])
    component_materials = [
        str(contract["input_materials"][0])
        for contract in component_contracts
    ]
    rendered_material = "\n".join(
        f"材料{index}：{material}"
        for index, material in enumerate(component_materials, start=1)
    )
    question_spec = {
        "schema_version": QUESTION_SPEC_SCHEMA,
        "adapter_id": "cross_subject.integrated_performance",
        "subject_family": subject_family,
        "archetype_id": "multi_objective_integrated_performance",
        "node_id": "",
        "practice_level": "final_assessment",
        "target": {
            "objective": "综合运用多个课程目标完成可复核成果",
            "knowledge_points": knowledge_points,
            "assessment_actions": objectives,
        },
        "stimulus": {
            "kind": "multi_source_case",
            "data": {
                "component_specs": [
                    deepcopy(contract["question_spec"])
                    for contract in component_contracts
                ],
                "required_objectives": objectives,
            },
            "rendered_text": rendered_material,
        },
        "task": {
            "action": "integrate_and_validate",
            "rendered_text": (
                "完成一份综合解决方案：先分别处理各材料，再明确说明至少两处"
                "跨目标连接，并对最终结果执行一致性检查"
            ),
            "deliverable": "分项结果、跨目标连接、完整推理过程和一致性验证",
        },
        "constraints": [
            "每个必需目标至少形成一项可检查结果",
            "至少建立两处跨目标连接",
            "不得省略关键假设",
        ],
        "response_contract": {
            "format": "integrated_performance",
            "required_parts": [
                "component_results",
                "cross_objective_connections",
                "reasoning",
                "consistency_check",
            ],
        },
        "answer_spec": {
            "type": "structured_rubric",
            "validation_mode": "teacher_reviewed_integrated_rubric",
            "criteria": [
                "每个材料均形成可复核结果",
                "课程概念之间的连接准确且有依据",
                "推理过程完整并明确关键假设",
                "一致性检查能够发现或排除结果冲突",
            ],
            "expected_keywords": knowledge_points[:12],
            "max_score": 100,
            "pass_score": 70,
        },
        "result_checks": [
            "逐项核对目标覆盖",
            "复核跨目标连接依据",
            "检查分项结果是否相互冲突",
        ],
        "provenance": {
            "course_id": str(course_data.get("course_id") or ""),
            "source_priority": "course_question_contracts",
            "source_refs": [
                source
                for contract in component_contracts
                for source in contract.get("source_records") or []
            ],
        },
        "risk": {
            "flags": ["comprehensive_task"],
            "requires_review": True,
        },
    }
    validation = validate_question_spec(question_spec)
    prompt = (
        f"跨章节综合任务｜连接{'、'.join(objectives)}\n"
        f"输入材料：{rendered_material}\n"
        f"任务：{question_spec['task']['rendered_text']}\n"
        f"限制条件：{'；'.join(question_spec['constraints'])}。\n"
        f"输出要求：{question_spec['task']['deliverable']}。"
    )
    return {
        "prompt": prompt,
        "deliverable": question_spec["task"]["deliverable"],
        "input_materials": component_materials,
        "constraints": list(question_spec["constraints"]),
        "result_checks": list(question_spec["result_checks"]),
        "question_type": "scenario_deliverable",
        "estimated_minutes": 45,
        "answer_spec": deepcopy(question_spec["answer_spec"]),
        "question_spec": question_spec,
        "domain_validation": validation,
        "risk_flags": ["comprehensive_task"],
        "review_required": True,
        "source_records": deepcopy(
            question_spec["provenance"]["source_refs"]
        ),
    }


def _adapter_context(
    course_data: dict[str, Any],
    node: dict[str, Any],
    practice_level: str,
    variant_index: int,
) -> AdapterContext:
    profile = course_data.get("subject_pedagogy_profile") or {}
    mode = str(profile.get("primary_mode") or "general")
    key_points = [
        str(value).strip()
        for value in node.get("key_points") or []
        if str(value).strip()
    ] or [str(node.get("node_name") or "当前知识点")]
    assessments = [
        str(value).strip()
        for value in node.get("assessment") or []
        if str(value).strip()
    ] or [str(node.get("learning_objective") or "完成当前任务")]
    topic_text = " ".join([
        str(course_data.get("course_name") or ""),
        str(node.get("node_name") or ""),
        str(node.get("learning_objective") or ""),
        *key_points,
        *assessments,
    ])
    if mode == "general":
        mode = _infer_subject_family(topic_text)
    return AdapterContext(
        course_data=course_data,
        node=node,
        practice_level=practice_level,
        variant_index=variant_index,
        subject_family=mode,
        topic_text=topic_text,
        objective=str(
            node.get("learning_objective")
            or node.get("node_name")
            or "完成当前学习目标"
        ),
        key_points=key_points,
        assessments=assessments,
    )


def _select_adapter(context: AdapterContext) -> tuple[str, AdapterBuilder]:
    topic = context.topic_text.lower()
    if any(marker in topic for marker in (
        "bfs", "dfs", "图遍历", "图算法", "广度优先", "深度优先",
    )):
        return "computer_science.graph_traversal", _build_graph_spec
    if any(marker in topic for marker in ("哈希", "散列表", "hash table", "hashing")):
        return "computer_science.hashing", _build_hashing_spec
    if any(marker in topic for marker in ("二叉堆", "最小堆", "最大堆", "优先队列", "堆操作")):
        return "computer_science.heap", _build_heap_spec
    if any(marker in topic for marker in ("avl", "平衡二叉", "二叉搜索树", "bst", "树旋转")):
        return "computer_science.avl_tree", _build_tree_spec
    if context.subject_family == "math_formal":
        return "math.quantitative_reasoning", _build_math_spec
    if context.subject_family == "programming_engineering":
        if any(marker in topic for marker in ("系统", "架构", "项目设计", "需求定义")):
            return "programming.system_design", _build_system_design_spec
        return "programming.data_processing", _build_programming_spec
    if context.subject_family == "natural_science":
        return "science.controlled_experiment", _build_science_spec
    if context.subject_family == "life_medical":
        return "life_science.mechanism_case", _build_life_science_spec
    if context.subject_family == "humanities_social":
        return "humanities.evidence_argument", _build_humanities_spec
    if context.subject_family == "language_learning":
        return "language.contextual_production", _build_language_spec
    if context.subject_family == "business_career":
        return "business.constrained_decision", _build_business_spec
    return "fallback.teacher_review", _build_fallback_spec


def _infer_subject_family(topic: str) -> str:
    lowered = topic.lower()
    if any(marker in lowered for marker in (
        "矩阵", "方程", "函数", "概率", "几何", "微积分", "行列式",
    )):
        return "math_formal"
    if any(marker in lowered for marker in (
        "算法", "编程", "代码", "数据结构", "python", "java",
    )):
        return "programming_engineering"
    return "general"


def _base_answer_spec(
    context: AdapterContext,
    criteria: list[str],
    *,
    validation_mode: str,
    canonical_answer: Any = None,
    solution_trace: list[str] | None = None,
) -> dict[str, Any]:
    answer = {
        "type": "structured_rubric",
        "validation_mode": validation_mode,
        "criteria": criteria,
        "expected_keywords": context.key_points[:8],
        "max_score": 100,
        "pass_score": 70,
    }
    if canonical_answer is not None:
        answer["canonical_answer"] = canonical_answer
    if solution_trace:
        answer["solution_trace"] = solution_trace
    return answer


def _build_graph_spec(context: AdapterContext) -> dict[str, Any]:
    variants = [
        {
            "vertices": ["A", "B", "C", "D", "E"],
            "edges": [["A", "B"], ["A", "C"], ["B", "D"], ["C", "E"]],
            "start_vertex": "A",
        },
        {
            "vertices": ["P", "Q", "R", "S", "T", "U"],
            "edges": [
                ["P", "Q"], ["P", "R"], ["Q", "S"],
                ["Q", "T"], ["R", "U"], ["T", "U"],
            ],
            "start_vertex": "P",
        },
        {
            "vertices": ["1", "2", "3", "4", "5", "6"],
            "edges": [
                ["1", "2"], ["1", "3"], ["2", "4"],
                ["3", "4"], ["3", "5"], ["5", "6"],
            ],
            "start_vertex": "1",
        },
    ]
    data = {
        **deepcopy(variants[context.variant_index % len(variants)]),
        "directed": False,
        "neighbor_order": "ascending",
        "disconnected_policy": "只遍历起点可达的顶点",
    }
    canonical = _solve_graph(data)
    data["adjacency_list"] = canonical["adjacency_list"]
    input_text = (
        f"给定无向图 V={{{'、'.join(data['vertices'])}}}，"
        f"E={_format_edges(data['edges'])}；从顶点 {data['start_vertex']} 开始，"
        "访问相邻顶点时按名称升序，只遍历起点可达部分。"
    )
    task_by_level = {
        "concept_check": "分别写出BFS和DFS访问顺序，并说明队列与栈如何影响顺序",
        "objective_practice": "执行BFS和DFS，记录每一步队列或栈的变化及访问顺序",
        "mastery_check": "实现BFS和DFS并输出访问顺序，用轨迹检查每个顶点只访问一次",
    }
    criteria = [
        "BFS访问顺序与给定邻接顺序一致",
        "DFS访问顺序与给定邻接顺序一致",
        "过程轨迹能够解释队列或栈的变化",
        "每个可达顶点恰好访问一次",
    ]
    return {
        "archetype_id": "graph_traversal_with_fixed_neighbor_order",
        "stimulus": {
            "kind": "graph",
            "data": data,
            "rendered_text": input_text,
        },
        "task": {
            "action": "execute_and_compare",
            "rendered_text": task_by_level.get(
                context.practice_level,
                task_by_level["mastery_check"],
            ),
            "deliverable": "BFS顺序、DFS顺序以及可复核的遍历轨迹",
        },
        "constraints": [
            "BFS在顶点入队时标记已发现",
            "DFS按相邻顶点升序选择下一顶点",
            "不得省略起点和访问标记",
        ],
        "response_contract": {
            "format": "structured_trace",
            "required_parts": ["bfs_order", "dfs_order", "trace", "result_check"],
        },
        "answer_spec": _base_answer_spec(
            context,
            criteria,
            validation_mode="deterministic_solver",
            canonical_answer={
                "bfs_order": canonical["bfs_order"],
                "dfs_order": canonical["dfs_order"],
            },
            solution_trace=canonical["trace"],
        ),
        "result_checks": [
            "BFS同层顶点先于下一层顶点",
            "DFS沿当前分支深入后再回溯",
            "访问集合等于起点可达顶点集合",
        ],
    }


def _build_hashing_spec(context: AdapterContext) -> dict[str, Any]:
    variants = [
        {
            "capacity": 11,
            "hash_expression": "k mod 11",
            "hash_a": 1,
            "hash_b": 0,
            "keys": [22, 31, 43, 56, 70],
            "collision_policy": "标记冲突，不执行插入",
        },
        {
            "capacity": 10,
            "hash_expression": "(3k+1) mod 10",
            "hash_a": 3,
            "hash_b": 1,
            "keys": [12, 22, 32, 42],
            "collision_policy": "线性探测，步长为1",
        },
        {
            "capacity": 13,
            "hash_expression": "k mod 13",
            "hash_a": 1,
            "hash_b": 0,
            "keys": [18, 31, 44, 57, 29, 42, 71],
            "collision_policy": "链地址法，桶内保持插入顺序",
        },
    ]
    data = deepcopy(variants[context.variant_index % len(variants)])
    canonical = _solve_hashing(data)
    input_text = (
        f"散列表容量 m={data['capacity']}，h(k)={data['hash_expression']}；"
        f"依次处理键 {data['keys']}；冲突规则为{data['collision_policy']}。"
    )
    task_by_level = {
        "concept_check": "计算每个键的初始哈希地址，标出冲突并解释产生原因",
        "objective_practice": "完成全部插入并写出最终槽位或桶内容，同时记录探测过程",
        "mastery_check": "给出各桶内容、指定键的查询路径和负载因子，并验证查询结果",
    }
    criteria = [
        "初始哈希地址计算正确",
        "冲突处理严格遵守给定规则",
        "最终表结构与处理过程一致",
        "查询或负载因子检查可复核",
    ]
    return {
        "archetype_id": "hash_table_trace",
        "stimulus": {
            "kind": "hash_table",
            "data": data,
            "rendered_text": input_text,
        },
        "task": {
            "action": "execute_hash_operations",
            "rendered_text": task_by_level.get(
                context.practice_level,
                task_by_level["mastery_check"],
            ),
            "deliverable": "哈希地址、冲突轨迹和最终表结构",
        },
        "constraints": [
            f"必须采用{data['collision_policy']}",
            "所有地址必须满足0≤h(k)<m",
            "处理顺序不得调整",
        ],
        "response_contract": {
            "format": "hash_trace",
            "required_parts": ["initial_addresses", "collision_trace", "final_table"],
        },
        "answer_spec": _base_answer_spec(
            context,
            criteria,
            validation_mode="deterministic_solver",
            canonical_answer=canonical,
        ),
        "result_checks": [
            "每个键均可按相同规则定位",
            "冲突次数与轨迹一致",
            "负载因子不超过1",
        ],
    }


def _build_heap_spec(context: AdapterContext) -> dict[str, Any]:
    seed = context.variant_index + 2
    values = [7 + seed, 3, 11 + seed, 5, 2 + seed, 9]
    operations = [
        {"op": "build_min_heap", "values": values},
        {"op": "insert", "value": 1 + seed},
        {"op": "delete_min"},
    ]
    canonical = _solve_heap(operations)
    input_text = (
        f"初始序列为 {values}。先建最小堆，再插入 {1 + seed}，"
        "最后执行一次删除最小值；使用数组下标从0开始的完全二叉树表示。"
    )
    return {
        "archetype_id": "binary_heap_operation_trace",
        "stimulus": {
            "kind": "heap_operations",
            "data": {"heap_type": "min", "operations": operations},
            "rendered_text": input_text,
        },
        "task": {
            "action": "execute_heap_operations",
            "rendered_text": "写出建堆、插入和删除后的数组，并标明每次上浮或下沉交换",
            "deliverable": "三个阶段的堆数组、交换轨迹和性质检查",
        },
        "constraints": [
            "父节点下标为(i-1)//2",
            "左右孩子下标分别为2i+1和2i+2",
            "每一步都必须保持最小堆性质",
        ],
        "response_contract": {
            "format": "operation_trace",
            "required_parts": ["heap_states", "swap_trace", "property_check"],
        },
        "answer_spec": _base_answer_spec(
            context,
            [
                "各阶段堆数组正确",
                "上浮和下沉轨迹完整",
                "所有父节点均不大于子节点",
            ],
            validation_mode="deterministic_solver",
            canonical_answer=canonical,
        ),
        "result_checks": ["数组满足完全二叉树位置关系", "最终根节点为当前最小值"],
    }


def _build_tree_spec(context: AdapterContext) -> dict[str, Any]:
    variants = [
        [30, 20, 10, 25, 40, 50],
        [50, 30, 70, 20, 40, 35],
        [40, 20, 60, 10, 30, 25],
    ]
    keys = variants[context.variant_index % len(variants)]
    canonical = _solve_avl(keys)
    input_text = (
        f"向空AVL树依次插入键 {keys}；平衡因子定义为左子树高度减右子树高度，"
        "重复键不插入。"
    )
    return {
        "archetype_id": "avl_insertion_and_rotation",
        "stimulus": {
            "kind": "tree_operations",
            "data": {"tree_type": "AVL", "insert_keys": keys},
            "rendered_text": input_text,
        },
        "task": {
            "action": "execute_balanced_tree_insertions",
            "rendered_text": "逐键插入，标出首次失衡节点、旋转类型，并给出最终树的先序和中序序列",
            "deliverable": "旋转轨迹、最终树遍历序列和高度检查",
        },
        "constraints": ["每次插入后立即恢复平衡", "中序序列必须严格递增"],
        "response_contract": {
            "format": "tree_trace",
            "required_parts": ["rotation_trace", "preorder", "inorder", "height_check"],
        },
        "answer_spec": _base_answer_spec(
            context,
            [
                "失衡节点和旋转类型判断正确",
                "最终先序和中序遍历正确",
                "所有节点平衡因子绝对值不超过1",
            ],
            validation_mode="deterministic_solver",
            canonical_answer=canonical,
        ),
        "result_checks": ["中序序列递增", "每个节点平衡因子绝对值不超过1"],
    }


def _build_math_spec(context: AdapterContext) -> dict[str, Any]:
    seed = context.variant_index + 2
    topic = context.topic_text.lower()
    focus = context.key_points[0]
    assessments = "；".join(context.assessments)
    level_action = {
        "concept_check": "准确辨析",
        "objective_practice": "准确应用",
        "mastery_check": "独立运用",
    }.get(context.practice_level, "准确运用")
    criteria = [
        f"{level_action}“{focus}”完成给定任务",
        "说明所用定义或方法依据",
        "给出可复核的计算或推理过程",
        "检查结果并说明适用边界",
    ]
    task_text = (
        f"完成目标任务：{assessments}。"
        f"评分检查点：{'；'.join(criteria)}"
    )
    if "向量" in topic:
        left = [seed, seed + 1]
        right = [2, -1]
        data = {
            "case_kind": "vector_operations",
            "left": left,
            "right": right,
        }
        canonical: dict[str, Any] | None = {
            "sum": [left[0] + right[0], left[1] + right[1]],
            "dot_product": left[0] * right[0] + left[1] * right[1],
            "left_norm_squared": left[0] ** 2 + left[1] ** 2,
        }
        input_text = (
            f"给定二维向量 u={tuple(left)}、v={tuple(right)}，"
            "坐标均在标准正交基下表示。"
        )
        archetype = "vector_operations_and_boundary_check"
        deliverable = "向量运算结果、使用依据、完整过程和几何或代数检查"
    elif "矩阵" in topic and "方程" not in topic:
        left = [[seed, 1], [2, seed + 1]]
        right = [[1, 2], [0, 1]]
        product = [
            [
                left[row][0] * right[0][column]
                + left[row][1] * right[1][column]
                for column in range(2)
            ]
            for row in range(2)
        ]
        data = {
            "case_kind": "matrix_operations",
            "left": left,
            "right": right,
        }
        canonical = {
            "product": product,
            "left_determinant": left[0][0] * left[1][1] - left[0][1] * left[1][0],
        }
        input_text = f"给定矩阵 A={left}、B={right}，两者均为2×2实矩阵。"
        archetype = "matrix_product_and_determinant"
        deliverable = "矩阵乘积、行列式、逐项计算过程和维度检查"
    elif any(marker in topic for marker in ("线性空间", "向量空间", "基与坐标", "线性组合")):
        basis = [[1, 0], [1, 1]]
        target = [seed, seed + 1]
        data = {
            "case_kind": "basis_coordinates",
            "basis": basis,
            "target": target,
        }
        canonical = {
            "coefficients": [target[0] - target[1], target[1]],
            "reconstructed": target,
        }
        input_text = (
            f"在 R² 中给定有序基 B=({tuple(basis[0])},{tuple(basis[1])})，"
            f"目标向量 w={tuple(target)}。"
        )
        archetype = "basis_coordinate_reconstruction"
        deliverable = "基下坐标、线性组合过程和重构检查"
    elif any(marker in topic for marker in ("方程", "消元", "线性系统")):
        x_value = seed
        y_value = seed + 1
        equations = [
            {"a": 1, "b": 1, "c": x_value + y_value},
            {"a": 2, "b": -1, "c": 2 * x_value - y_value},
        ]
        data = {
            "case_kind": "linear_system",
            "variables": ["x", "y"],
            "domain": "real",
            "equations": equations,
        }
        canonical = {"x": x_value, "y": y_value}
        input_text = (
            f"方程组为 x+y={equations[0]['c']}，"
            f"2x-y={equations[1]['c']}；变量限定为实数。"
        )
        archetype = "two_variable_linear_system"
        deliverable = "方程组的解、关键推导和代回验算"
    else:
        data = {
            "case_kind": "topic_reasoning",
            "topic_focus": focus,
            "given_value": seed * 2,
            "boundary_value": seed * 2 + 1,
        }
        canonical = None
        input_text = (
            f"围绕“{focus}”比较案例值 {data['given_value']} 与边界值"
            f" {data['boundary_value']}，并严格使用课程给出的定义与条件。"
        )
        archetype = "topic_aligned_mathematical_reasoning"
        deliverable = "结论、定义或方法依据、完整推理过程和边界检查"
    return {
        "archetype_id": archetype,
        "stimulus": {
            "kind": "quantitative_problem",
            "data": data,
            "rendered_text": input_text,
        },
        "task": {
            "action": "solve_and_verify",
            "rendered_text": task_text,
            "deliverable": deliverable,
        },
        "constraints": [
            "不得只写最终结论",
            "必须写出依据与关键过程",
            "必须执行至少一项结果或边界检查",
        ],
        "response_contract": {
            "format": "worked_solution",
            "required_parts": ["method", "steps", "answer", "verification"],
        },
        "answer_spec": _base_answer_spec(
            context,
            criteria,
            validation_mode=(
                "deterministic_solver"
                if canonical is not None
                else "teacher_reviewed_mathematical_rubric"
            ),
            canonical_answer=canonical,
        ),
        "result_checks": [
            f"结果能够回应“{focus}”",
            "关键步骤可由输入数据复算",
            "结论未超出题目给定条件",
        ],
    }


def _build_programming_spec(context: AdapterContext) -> dict[str, Any]:
    seed = context.variant_index + 2
    focus = context.key_points[0]
    assessments = "；".join(context.assessments)
    output_topic = any(
        marker in context.topic_text.lower()
        for marker in ("print", "标准输出", "输出副作用", "返回值")
    )
    if output_topic:
        value = seed + 2
        code = (
            f"value = {value}\n"
            "result = print(f\"value:{value}\")\n"
            "print(result is None)"
        )
        data = {
            "case_kind": "stdout_trace",
            "language": "python",
            "code": code,
            "expected_stdout": [f"value:{value}", "True"],
            "expected_return_value": None,
        }
        input_text = (
            "在 Python 中运行以下代码，并分别记录标准输出与 print 调用的返回值：\n"
            f"{code}"
        )
        canonical_answer: dict[str, Any] | None = {
            "stdout": list(data["expected_stdout"]),
            "print_return_value": None,
        }
        action = "execute_explain_and_modify"
        deliverable = "运行结果、标准输出与返回值的区别，以及一处可运行修改"
    else:
        sample_id = f"CASE-{seed:02d}"
        data = {
            "case_kind": "topic_implementation",
            "topic_focus": focus,
            "sample_input": {
                "case_id": sample_id,
                "value": seed * 3,
                "enabled": context.variant_index % 2 == 0,
            },
            "requirements": list(context.assessments),
        }
        input_text = (
            f"围绕“{focus}”处理输入 {data['sample_input']}。"
            f"必须完成课程要求：{assessments}；并为正常、边界和异常输入各设计一个测试。"
        )
        canonical_answer = None
        action = "implement_explain_and_test"
        deliverable = "可运行实现、给定输入的结果、关键过程说明和三类测试"
    level_action = {
        "concept_check": "准确辨析",
        "objective_practice": "准确应用",
        "mastery_check": "独立运用",
    }.get(context.practice_level, "准确运用")
    criteria = [
        f"{level_action}“{focus}”完成给定任务",
        "说明实现方法与选择依据",
        "展示可复核的运行过程",
        "检查结果、边界与异常处理",
    ]
    task_text = (
        f"完成目标任务：{assessments}。"
        f"评分检查点：{'；'.join(criteria)}"
    )
    return {
        "archetype_id": (
            "stdout_and_return_value_trace"
            if output_topic
            else "topic_aligned_implementation"
        ),
        "stimulus": {
            "kind": "programming_case",
            "data": data,
            "rendered_text": input_text,
        },
        "task": {
            "action": action,
            "rendered_text": task_text,
            "deliverable": deliverable,
        },
        "constraints": [
            "必须使用题目给定的输入",
            "不得省略运行结果",
            "至少包含一个边界或反例检查",
        ],
        "response_contract": {
            "format": "code_and_test",
            "required_parts": ["implementation", "observed_output", "tests", "explanation"],
        },
        "answer_spec": _base_answer_spec(
            context,
            criteria,
            validation_mode=(
                "deterministic_code_trace"
                if output_topic
                else "executable_test_rubric"
            ),
            canonical_answer=canonical_answer,
        ),
        "result_checks": [
            "运行结果与给定输入一致",
            f"结果能够证明“{focus}”已被正确使用",
            "边界或异常测试得到预期结果",
        ],
    }


def _build_system_design_spec(context: AdapterContext) -> dict[str, Any]:
    seed = context.variant_index + 2
    input_text = (
        f"系统每天接收{seed * 1000}条记录，单条不超过4KB；"
        f"查询P95需小于{100 + seed * 10}ms，服务重启后数据不可丢失，"
        "并要求支持重复请求幂等处理。"
    )
    return {
        "archetype_id": "bounded_system_design",
        "stimulus": {
            "kind": "system_requirements",
            "data": {
                "daily_records": seed * 1000,
                "max_record_kb": 4,
                "p95_latency_ms": 100 + seed * 10,
                "durability_required": True,
                "idempotency_required": True,
            },
            "rendered_text": input_text,
        },
        "task": {
            "action": "design_and_justify",
            "rendered_text": (
                f"围绕“{context.objective}”给出组件划分、数据流、失败处理和验收测试"
            ),
            "deliverable": "架构图文字说明、关键接口、失败策略和验收用例",
        },
        "constraints": ["设计必须满足全部量化约束", "必须说明至少一个取舍"],
        "response_contract": {
            "format": "design_document",
            "required_parts": ["components", "data_flow", "failure_handling", "tests"],
        },
        "answer_spec": _base_answer_spec(
            context,
            [
                "组件职责和数据流完整",
                "容量与时延约束有明确对应措施",
                "持久化与幂等策略可执行",
                "验收测试能够验证关键需求",
            ],
            validation_mode="rubric_with_constraints",
        ),
        "result_checks": ["逐项映射需求与设计", "失败恢复后数据和请求结果一致"],
    }


def _build_science_spec(context: AdapterContext) -> dict[str, Any]:
    seed = context.variant_index + 2
    control = [10 + seed, 11 + seed, 10 + seed]
    treatment = [14 + seed, 16 + seed, 15 + seed]
    control_mean = round(sum(control) / len(control), 2)
    treatment_mean = round(sum(treatment) / len(treatment), 2)
    input_text = (
        f"对照组读数为{control}，处理组读数为{treatment}；"
        "两组除处理因素外条件相同，仪器单次误差为±1。"
    )
    return {
        "archetype_id": "controlled_experiment_analysis",
        "stimulus": {
            "kind": "controlled_experiment",
            "data": {
                "control_values": control,
                "treatment_values": treatment,
                "measurement_error": 1,
                "controlled_variables": ["样本量", "测量时长", "仪器"],
            },
            "rendered_text": input_text,
        },
        "task": {
            "action": "analyze_evidence",
            "rendered_text": "计算两组均值与差值，判断数据支持什么结论，并说明误差限制",
            "deliverable": "计算结果、证据结论和实验局限",
        },
        "constraints": ["结论不得超出当前数据", "必须考虑测量误差"],
        "response_contract": {
            "format": "evidence_analysis",
            "required_parts": ["calculation", "claim", "evidence", "limitations"],
        },
        "answer_spec": _base_answer_spec(
            context,
            [
                "两组均值和差值计算正确",
                "结论与数据方向一致",
                "能够说明误差和控制变量的影响",
            ],
            validation_mode="calculation_plus_rubric",
            canonical_answer={
                "control_mean": control_mean,
                "treatment_mean": treatment_mean,
                "difference": round(treatment_mean - control_mean, 2),
            },
        ),
        "result_checks": ["重复计算均值", "结论强度不超过证据范围"],
    }


def _build_life_science_spec(context: AdapterContext) -> dict[str, Any]:
    input_text = (
        "教学案例：受试对象进食后血糖短时升高，随后逐步回落至基线附近；"
        "题目只讨论正常生理调节机制，不用于个人诊断或治疗建议。"
    )
    return {
        "archetype_id": "bounded_mechanism_explanation",
        "stimulus": {
            "kind": "mechanism_case",
            "data": {
                "observations": ["进食后升高", "随后回落"],
                "scope": "normal_physiology_education",
                "excluded_use": ["diagnosis", "treatment"],
            },
            "rendered_text": input_text,
        },
        "task": {
            "action": "explain_mechanism",
            "rendered_text": f"使用{_join(context.key_points)}解释观察到的变化并标明反馈环节",
            "deliverable": "刺激、调节信号、靶作用和反馈结果的机制链",
        },
        "constraints": ["不得给出诊断或治疗建议", "不得推断案例未提供的信息"],
        "response_contract": {
            "format": "mechanism_chain",
            "required_parts": ["stimulus", "signal", "target", "effect", "feedback"],
        },
        "answer_spec": _base_answer_spec(
            context,
            [
                "机制链条与正常生理过程一致",
                "明确说明负反馈如何恢复稳态",
                "没有越界形成诊断或治疗建议",
            ],
            validation_mode="rubric_with_expert_review",
        ),
        "result_checks": ["机制各环节因果方向一致", "结论保持在教学案例范围内"],
        "review_required": True,
        "risk_flags": ["high_stakes_domain"],
    }


def _build_humanities_spec(context: AdapterContext) -> dict[str, Any]:
    seed = context.variant_index + 1
    source_a = (
        f"材料A（同时期工厂调查节选）：样本城市中工厂就业人数在{10 + seed}年间增加，"
        "但工作时长和居住拥挤问题同时受到记录。"
    )
    source_b = (
        f"材料B（后来的统计研究摘要）：实际工资指数由100升至{106 + seed}，"
        "地区与行业之间差异明显。"
    )
    input_text = f"{source_a}\n{source_b}"
    return {
        "archetype_id": "two_source_evidence_argument",
        "stimulus": {
            "kind": "source_set",
            "data": {
                "sources": [
                    {"source_id": "A", "text": source_a, "perspective": "contemporary"},
                    {"source_id": "B", "text": source_b, "perspective": "retrospective"},
                ],
                "source_scope": "synthetic_course_case",
            },
            "rendered_text": input_text,
        },
        "task": {
            "action": "construct_evidence_argument",
            "rendered_text": (
                f"围绕“{context.objective}”提出一个有限结论，引用两则材料并讨论一项局限"
            ),
            "deliverable": "论点、两条材料证据、推理连接和局限说明",
        },
        "constraints": ["必须区分材料陈述与自己的推断", "不得超出材料时间和样本范围"],
        "response_contract": {
            "format": "evidence_argument",
            "required_parts": ["claim", "evidence_a", "evidence_b", "reasoning", "limitation"],
        },
        "answer_spec": _base_answer_spec(
            context,
            [
                "论点回应任务且范围适当",
                "准确引用并解释两则材料",
                "证据与结论之间有明确推理",
                "能够识别材料的样本或视角局限",
            ],
            validation_mode="evidence_rubric",
        ),
        "result_checks": ["每个主要结论均有材料支持", "至少说明一项来源局限"],
    }


def _build_language_spec(context: AdapterContext) -> dict[str, Any]:
    input_text = (
        "语境：你到达车站时，列车已经离开；此前你收到过临时改点通知，"
        "但没有及时看到。请给同学写一段英文说明事情先后。"
    )
    return {
        "archetype_id": "constrained_contextual_writing",
        "stimulus": {
            "kind": "language_context",
            "data": {
                "events": [
                    {"event": "train_departed", "order": 2},
                    {"event": "arrived_station", "order": 3},
                    {"event": "notice_received", "order": 1},
                ],
                "language": "English",
            },
            "rendered_text": input_text,
        },
        "task": {
            "action": "produce_contextual_language",
            "rendered_text": "写80—100词英文说明，至少两次使用过去完成时并清楚表达时间顺序",
            "deliverable": "符合语境、语法目标和字数限制的英文短文",
        },
        "constraints": ["80—100词", "至少两处过去完成时", "不得改变事件先后"],
        "response_contract": {
            "format": "language_response",
            "required_parts": ["response_text", "target_form_highlights"],
        },
        "answer_spec": _base_answer_spec(
            context,
            [
                "事件先后与语境一致",
                "至少两处过去完成时形式正确",
                "衔接清楚且字数符合要求",
                "表达能够被目标读者理解",
            ],
            validation_mode="language_rubric",
        ),
        "result_checks": ["核对词数", "标出过去完成时", "逐项核对事件顺序"],
    }


def _build_business_spec(context: AdapterContext) -> dict[str, Any]:
    seed = context.variant_index + 1
    options = [
        {"id": "A", "cost": 70 + seed, "weeks": 6, "benefit": 86, "risk": 3},
        {"id": "B", "cost": 60 + seed, "weeks": 8, "benefit": 80, "risk": 2},
        {"id": "C", "cost": 82 + seed, "weeks": 5, "benefit": 92, "risk": 4},
    ]
    budget = 75 + seed
    deadline = 7
    feasible = [
        option
        for option in options
        if option["cost"] <= budget and option["weeks"] <= deadline
    ]
    recommended = max(
        feasible,
        key=lambda option: option["benefit"] - 3 * option["risk"],
    )
    input_text = (
        f"预算上限{budget}万元、工期上限{deadline}周。"
        f"方案数据为{options}；在可行方案中按“收益-3×风险”比较。"
    )
    return {
        "archetype_id": "constrained_option_decision",
        "stimulus": {
            "kind": "decision_case",
            "data": {
                "options": options,
                "budget_limit": budget,
                "deadline_weeks": deadline,
                "decision_rule": "benefit - 3 * risk",
            },
            "rendered_text": input_text,
        },
        "task": {
            "action": "evaluate_and_recommend",
            "rendered_text": "先筛除不可行方案，再计算评分并提出建议，同时说明一个未量化风险",
            "deliverable": "可行性表、评分、推荐方案和风险说明",
        },
        "constraints": ["预算和工期均为硬约束", "推荐必须基于给定评分规则"],
        "response_contract": {
            "format": "decision_memo",
            "required_parts": ["feasibility", "scores", "recommendation", "risk_note"],
        },
        "answer_spec": _base_answer_spec(
            context,
            [
                "可行方案筛选正确",
                "评分计算正确",
                "推荐与规则一致",
                "能够说明一个合理的未量化风险",
            ],
            validation_mode="calculation_plus_rubric",
            canonical_answer={
                "feasible_options": [option["id"] for option in feasible],
                "recommended_option": recommended["id"],
            },
        ),
        "result_checks": ["推荐方案同时满足预算和工期", "评分可由原始数据复算"],
    }


def _build_fallback_spec(context: AdapterContext) -> dict[str, Any]:
    input_text = (
        f"当前目标为“{context.objective}”，相关知识点为{_join(context.key_points)}；"
        "系统尚无可验证的专属题型契约。"
    )
    return {
        "archetype_id": "teacher_authored_candidate",
        "stimulus": {
            "kind": "unstructured_context",
            "data": {
                "objective": context.objective,
                "knowledge_points": context.key_points,
            },
            "rendered_text": input_text,
        },
        "task": {
            "action": "teacher_define_task",
            "rendered_text": "请教师补充可作答材料、明确输出要求和评分依据后再发布",
            "deliverable": "待教师完善的候选题",
        },
        "constraints": ["不得自动发布", "必须补充学科专属验证方式"],
        "response_contract": {
            "format": "teacher_review_candidate",
            "required_parts": ["input", "task", "answer_or_rubric"],
        },
        "answer_spec": _base_answer_spec(
            context,
            ["输入足以完成任务", "评分标准能够区分答案质量"],
            validation_mode="teacher_review_only",
        ),
        "result_checks": ["教师确认学科适配器", "教师确认答案或量规"],
        "review_required": True,
        "risk_flags": ["adapter_unavailable"],
    }


def _render_question(
    context: AdapterContext,
    spec: dict[str, Any],
) -> dict[str, Any]:
    stimulus_text = str(spec["stimulus"]["rendered_text"])
    task_text = str(spec["task"]["rendered_text"])
    constraints = [str(value) for value in spec["constraints"]]
    label = PRACTICE_LABELS.get(context.practice_level, "目标练习")
    prompt = (
        f"{label}｜{context.node.get('node_name') or context.node.get('node_id')}\n"
        f"输入材料：{stimulus_text}\n"
        f"任务：{task_text}\n"
        f"限制条件：{'；'.join(constraints)}。\n"
        f"输出要求：{spec['task']['deliverable']}。"
    )
    return {
        "prompt": prompt,
        "deliverable": str(spec["task"]["deliverable"]),
        "input_materials": [stimulus_text],
        "constraints": constraints,
        "result_checks": [str(value) for value in spec["result_checks"]],
        "question_type": _question_type_for_spec(spec),
        "estimated_minutes": (
            8
            if context.practice_level == "concept_check"
            else (15 if context.practice_level == "objective_practice" else 22)
        ),
    }


def _question_type_for_spec(spec: dict[str, Any]) -> str:
    adapter_id = str(spec.get("adapter_id") or "")
    return {
        "computer_science.graph_traversal": "implementation_task",
        "computer_science.hashing": "worked_solution",
        "computer_science.heap": "worked_solution",
        "computer_science.avl_tree": "worked_solution",
        "programming.system_design": "scenario_deliverable",
        "programming.data_processing": "implementation_task",
        "math.quantitative_reasoning": "worked_solution",
        "science.controlled_experiment": "evidence_analysis",
        "life_science.mechanism_case": "mechanism_explanation",
        "humanities.evidence_argument": "source_argument",
        "language.contextual_production": "language_production",
        "business.constrained_decision": "scenario_deliverable",
        "cross_subject.integrated_performance": "scenario_deliverable",
        "fallback.teacher_review": "short_answer",
    }.get(adapter_id, "short_answer")


def _course_document_source_records(
    course_data: dict[str, Any],
    node_id: str,
) -> list[dict[str, Any]]:
    document = course_data.get("course_document") or {}
    blocks = document.get("blocks") or []
    records: list[dict[str, Any]] = []
    for block in blocks:
        if str(block.get("section_id") or "") != node_id:
            continue
        if str(block.get("role") or "") not in {
            "checkpoint", "exercise", "example", "application",
        }:
            continue
        payload = block.get("payload") or {}
        excerpt = str(
            payload.get("markdown")
            or payload.get("summary")
            or payload.get("text")
            or ""
        ).strip()
        if not excerpt:
            continue
        records.append({
            "source_type": "course_document",
            "course_id": str(course_data.get("course_id") or ""),
            "node_id": node_id,
            "block_id": str(block.get("block_id") or ""),
            "block_role": str(block.get("role") or ""),
            "content_excerpt": excerpt[:1200],
            "rights_basis": "course_owned",
            "reuse_policy": "reference_only",
        })
        if len(records) >= 2:
            break
    return records


def _validate_graph_spec(spec: dict[str, Any]) -> list[dict[str, str]]:
    data = (spec.get("stimulus") or {}).get("data") or {}
    vertices = data.get("vertices") or []
    edges = data.get("edges") or []
    start = data.get("start_vertex")
    if (
        len(vertices) < 3
        or not edges
        or start not in vertices
        or not data.get("neighbor_order")
    ):
        return [_issue("question:graph_input_incomplete", "critical")]
    if any(
        not isinstance(edge, list)
        or len(edge) != 2
        or edge[0] not in vertices
        or edge[1] not in vertices
        for edge in edges
    ):
        return [_issue("question:graph_input_incomplete", "critical")]
    expected = _solve_graph(data)
    canonical = (spec.get("answer_spec") or {}).get("canonical_answer") or {}
    if (
        canonical.get("bfs_order") != expected["bfs_order"]
        or canonical.get("dfs_order") != expected["dfs_order"]
    ):
        return [_issue("question:canonical_answer_mismatch", "critical")]
    return []


def _validate_hashing_spec(spec: dict[str, Any]) -> list[dict[str, str]]:
    data = (spec.get("stimulus") or {}).get("data") or {}
    if (
        int(data.get("capacity") or 0) <= 0
        or not data.get("keys")
        or not data.get("collision_policy")
    ):
        return [_issue("question:input_material_missing", "critical")]
    expected = _solve_hashing(data)
    canonical = (spec.get("answer_spec") or {}).get("canonical_answer")
    return (
        []
        if canonical == expected
        else [_issue("question:canonical_answer_mismatch", "critical")]
    )


def _validate_heap_spec(spec: dict[str, Any]) -> list[dict[str, str]]:
    data = (spec.get("stimulus") or {}).get("data") or {}
    operations = data.get("operations") or []
    if not operations:
        return [_issue("question:input_material_missing", "critical")]
    expected = _solve_heap(operations)
    canonical = (spec.get("answer_spec") or {}).get("canonical_answer")
    return (
        []
        if canonical == expected
        else [_issue("question:canonical_answer_mismatch", "critical")]
    )


def _validate_tree_spec(spec: dict[str, Any]) -> list[dict[str, str]]:
    data = (spec.get("stimulus") or {}).get("data") or {}
    keys = data.get("insert_keys") or []
    if not keys:
        return [_issue("question:input_material_missing", "critical")]
    expected = _solve_avl([int(value) for value in keys])
    canonical = (spec.get("answer_spec") or {}).get("canonical_answer")
    return (
        []
        if canonical == expected
        else [_issue("question:canonical_answer_mismatch", "critical")]
    )


def _validate_programming_spec(spec: dict[str, Any]) -> list[dict[str, str]]:
    data = (spec.get("stimulus") or {}).get("data") or {}
    case_kind = str(data.get("case_kind") or "")
    if case_kind == "stdout_trace":
        canonical = (spec.get("answer_spec") or {}).get("canonical_answer") or {}
        if (
            not str(data.get("code") or "").strip()
            or canonical.get("stdout") != data.get("expected_stdout")
            or "print_return_value" not in canonical
        ):
            return [_issue("question:canonical_answer_mismatch", "critical")]
        return []
    if case_kind == "topic_implementation":
        if (
            not str(data.get("topic_focus") or "").strip()
            or not data.get("sample_input")
            or not data.get("requirements")
        ):
            return [_issue("question:input_material_missing", "critical")]
        return _validate_rubric_spec(spec)
    if "records" not in data or "limit" not in data:
        return [_issue("question:input_material_missing", "critical")]
    expected = _normalize_records(data["records"], int(data["limit"]))
    canonical = (spec.get("answer_spec") or {}).get("canonical_answer") or {}
    if canonical.get("output") != expected:
        return [_issue("question:canonical_answer_mismatch", "critical")]
    return []


def _validate_math_spec(spec: dict[str, Any]) -> list[dict[str, str]]:
    data = (spec.get("stimulus") or {}).get("data") or {}
    case_kind = str(data.get("case_kind") or "")
    canonical = (spec.get("answer_spec") or {}).get("canonical_answer") or {}
    if case_kind == "vector_operations":
        left = data.get("left") or []
        right = data.get("right") or []
        if len(left) != 2 or len(right) != 2:
            return [_issue("question:input_material_missing", "critical")]
        expected = {
            "sum": [left[0] + right[0], left[1] + right[1]],
            "dot_product": left[0] * right[0] + left[1] * right[1],
            "left_norm_squared": left[0] ** 2 + left[1] ** 2,
        }
        return (
            []
            if canonical == expected
            else [_issue("question:canonical_answer_mismatch", "critical")]
        )
    if case_kind == "matrix_operations":
        left = data.get("left") or []
        right = data.get("right") or []
        if (
            len(left) != 2
            or len(right) != 2
            or any(len(row) != 2 for row in [*left, *right])
        ):
            return [_issue("question:input_material_missing", "critical")]
        expected = {
            "product": [
                [
                    left[row][0] * right[0][column]
                    + left[row][1] * right[1][column]
                    for column in range(2)
                ]
                for row in range(2)
            ],
            "left_determinant": left[0][0] * left[1][1] - left[0][1] * left[1][0],
        }
        return (
            []
            if canonical == expected
            else [_issue("question:canonical_answer_mismatch", "critical")]
        )
    if case_kind == "basis_coordinates":
        basis = data.get("basis") or []
        target = data.get("target") or []
        if basis != [[1, 0], [1, 1]] or len(target) != 2:
            return [_issue("question:input_material_missing", "critical")]
        expected = {
            "coefficients": [target[0] - target[1], target[1]],
            "reconstructed": target,
        }
        return (
            []
            if canonical == expected
            else [_issue("question:canonical_answer_mismatch", "critical")]
        )
    if case_kind == "topic_reasoning":
        if not str(data.get("topic_focus") or "").strip():
            return [_issue("question:input_material_missing", "critical")]
        return _validate_rubric_spec(spec)
    equations = data.get("equations") or []
    if len(equations) != 2 or not {"x", "y"} <= set(canonical):
        return [_issue("question:input_material_missing", "critical")]
    x_value = canonical["x"]
    y_value = canonical["y"]
    if any(
        equation["a"] * x_value + equation["b"] * y_value != equation["c"]
        for equation in equations
    ):
        return [_issue("question:canonical_answer_mismatch", "critical")]
    determinant = (
        equations[0]["a"] * equations[1]["b"]
        - equations[1]["a"] * equations[0]["b"]
    )
    if determinant == 0:
        return [_issue("question:answer_not_determinate", "critical")]
    return []


def _validate_science_spec(spec: dict[str, Any]) -> list[dict[str, str]]:
    data = (spec.get("stimulus") or {}).get("data") or {}
    control = data.get("control_values") or []
    treatment = data.get("treatment_values") or []
    if len(control) < 2 or len(treatment) < 2:
        return [_issue("question:experiment_input_incomplete", "critical")]
    canonical = (spec.get("answer_spec") or {}).get("canonical_answer") or {}
    if not {"control_mean", "treatment_mean", "difference"} <= set(canonical):
        return [_issue("question:answer_not_executable", "critical")]
    return []


def _validate_humanities_spec(spec: dict[str, Any]) -> list[dict[str, str]]:
    sources = (
        ((spec.get("stimulus") or {}).get("data") or {}).get("sources")
        or []
    )
    if len(sources) < 2 or any(not source.get("text") for source in sources):
        return [_issue("question:source_set_incomplete", "critical")]
    return _validate_rubric_spec(spec)


def _validate_language_spec(spec: dict[str, Any]) -> list[dict[str, str]]:
    data = (spec.get("stimulus") or {}).get("data") or {}
    if len(data.get("events") or []) < 2 or not data.get("language"):
        return [_issue("question:input_material_missing", "critical")]
    return _validate_rubric_spec(spec)


def _validate_business_spec(spec: dict[str, Any]) -> list[dict[str, str]]:
    data = (spec.get("stimulus") or {}).get("data") or {}
    options = data.get("options") or []
    canonical = (spec.get("answer_spec") or {}).get("canonical_answer") or {}
    if len(options) < 2 or not canonical.get("recommended_option"):
        return [_issue("question:input_material_missing", "critical")]
    feasible_ids = {
        option["id"]
        for option in options
        if option["cost"] <= data["budget_limit"]
        and option["weeks"] <= data["deadline_weeks"]
    }
    if canonical["recommended_option"] not in feasible_ids:
        return [_issue("question:canonical_answer_mismatch", "critical")]
    return []


def _validate_integrated_spec(spec: dict[str, Any]) -> list[dict[str, str]]:
    data = (spec.get("stimulus") or {}).get("data") or {}
    component_specs = data.get("component_specs") or []
    objectives = data.get("required_objectives") or []
    if len(component_specs) < 2 or len(objectives) < 2:
        return [_issue("question:input_material_missing", "critical")]
    component_failures = [
        validation
        for component in component_specs
        if (validation := validate_question_spec(component))["passed"] is False
    ]
    if component_failures:
        return [_issue("question:component_validation_failed", "critical")]
    return _validate_rubric_spec(spec)


def _validate_rubric_spec(spec: dict[str, Any]) -> list[dict[str, str]]:
    answer = spec.get("answer_spec") or {}
    response = spec.get("response_contract") or {}
    if len(answer.get("criteria") or []) < 2:
        return [_issue("question:rubric_not_discriminating", "critical")]
    if len(response.get("required_parts") or []) < 2:
        return [_issue("question:response_contract_incomplete", "critical")]
    return []


def _validate_fallback_spec(spec: dict[str, Any]) -> list[dict[str, str]]:
    return [_issue("question:adapter_unavailable", "major")]


def _solve_graph(data: dict[str, Any]) -> dict[str, Any]:
    vertices = [str(value) for value in data.get("vertices") or []]
    adjacency: dict[str, list[str]] = {vertex: [] for vertex in vertices}
    directed = bool(data.get("directed"))
    for left, right in data.get("edges") or []:
        left = str(left)
        right = str(right)
        adjacency[left].append(right)
        if not directed:
            adjacency[right].append(left)
    reverse = data.get("neighbor_order") == "descending"
    for vertex in adjacency:
        adjacency[vertex] = sorted(adjacency[vertex], reverse=reverse)

    start = str(data.get("start_vertex") or "")
    queue: deque[str] = deque([start])
    discovered = {start}
    bfs_order: list[str] = []
    bfs_trace: list[str] = []
    while queue:
        current = queue.popleft()
        bfs_order.append(current)
        enqueued: list[str] = []
        for neighbor in adjacency[current]:
            if neighbor in discovered:
                continue
            discovered.add(neighbor)
            queue.append(neighbor)
            enqueued.append(neighbor)
        bfs_trace.append(
            f"BFS访问{current}，新入队{enqueued}，队列={list(queue)}"
        )

    dfs_order: list[str] = []
    dfs_trace: list[str] = []
    visited: set[str] = set()

    def visit(vertex: str) -> None:
        visited.add(vertex)
        dfs_order.append(vertex)
        dfs_trace.append(f"DFS进入{vertex}")
        for neighbor in adjacency[vertex]:
            if neighbor not in visited:
                visit(neighbor)
        dfs_trace.append(f"DFS离开{vertex}")

    visit(start)
    return {
        "adjacency_list": adjacency,
        "bfs_order": bfs_order,
        "dfs_order": dfs_order,
        "trace": [*bfs_trace, *dfs_trace],
    }


def _solve_hashing(data: dict[str, Any]) -> dict[str, Any]:
    capacity = int(data["capacity"])
    a_value = int(data.get("hash_a") or 1)
    b_value = int(data.get("hash_b") or 0)
    keys = [int(value) for value in data.get("keys") or []]
    addresses = {
        str(key): (a_value * key + b_value) % capacity
        for key in keys
    }
    policy = str(data.get("collision_policy") or "")
    collisions: list[dict[str, Any]] = []
    if "链地址" in policy:
        buckets: list[list[int]] = [[] for _ in range(capacity)]
        for key in keys:
            address = addresses[str(key)]
            if buckets[address]:
                collisions.append({"key": key, "address": address})
            buckets[address].append(key)
        return {
            "initial_addresses": addresses,
            "collisions": collisions,
            "buckets": buckets,
            "load_factor": round(len(keys) / capacity, 4),
        }
    table: list[int | None] = [None] * capacity
    probe_counts: dict[str, int] = {}
    for key in keys:
        address = addresses[str(key)]
        probes = 1
        if table[address] is not None:
            collisions.append({"key": key, "address": address})
        if "线性探测" in policy:
            while table[address] is not None and probes <= capacity:
                address = (address + 1) % capacity
                probes += 1
        if table[address] is None:
            table[address] = key
        probe_counts[str(key)] = probes
    return {
        "initial_addresses": addresses,
        "collisions": collisions,
        "table": table,
        "probe_counts": probe_counts,
        "load_factor": round(
            sum(value is not None for value in table) / capacity,
            4,
        ),
    }


def _solve_heap(operations: list[dict[str, Any]]) -> dict[str, Any]:
    heap: list[int] = []
    states: list[list[int]] = []
    removed: list[int] = []
    for operation in operations:
        if operation["op"] == "build_min_heap":
            heap = []
            for value in operation.get("values") or []:
                _heap_push(heap, int(value))
        elif operation["op"] == "insert":
            _heap_push(heap, int(operation["value"]))
        elif operation["op"] == "delete_min":
            removed.append(_heap_pop(heap))
        states.append(list(heap))
    return {"heap_states": states, "removed_values": removed}


def _heap_push(heap: list[int], value: int) -> None:
    heap.append(value)
    index = len(heap) - 1
    while index > 0:
        parent = (index - 1) // 2
        if heap[parent] <= heap[index]:
            break
        heap[parent], heap[index] = heap[index], heap[parent]
        index = parent


def _heap_pop(heap: list[int]) -> int:
    if not heap:
        raise ValueError("cannot delete from an empty heap")
    root = heap[0]
    last = heap.pop()
    if not heap:
        return root
    heap[0] = last
    index = 0
    while True:
        left = 2 * index + 1
        right = left + 1
        smallest = index
        if left < len(heap) and heap[left] < heap[smallest]:
            smallest = left
        if right < len(heap) and heap[right] < heap[smallest]:
            smallest = right
        if smallest == index:
            break
        heap[index], heap[smallest] = heap[smallest], heap[index]
        index = smallest
    return root


def _solve_avl(keys: list[int]) -> dict[str, Any]:
    root: dict[str, Any] | None = None
    rotations: list[str] = []
    for key in keys:
        root = _avl_insert(root, key, rotations)
    preorder: list[int] = []
    inorder: list[int] = []
    balance_factors: dict[str, int] = {}

    def traverse(node: dict[str, Any] | None) -> None:
        if not node:
            return
        preorder.append(node["key"])
        traverse(node["left"])
        inorder.append(node["key"])
        traverse(node["right"])
        balance_factors[str(node["key"])] = (
            _tree_height(node["left"]) - _tree_height(node["right"])
        )

    traverse(root)
    return {
        "preorder": preorder,
        "inorder": inorder,
        "rotations": rotations,
        "height": _tree_height(root),
        "balance_factors": balance_factors,
    }


def _avl_insert(
    node: dict[str, Any] | None,
    key: int,
    rotations: list[str],
) -> dict[str, Any]:
    if node is None:
        return {"key": key, "left": None, "right": None, "height": 1}
    if key < node["key"]:
        node["left"] = _avl_insert(node["left"], key, rotations)
    elif key > node["key"]:
        node["right"] = _avl_insert(node["right"], key, rotations)
    else:
        return node
    _refresh_tree_height(node)
    balance = _tree_height(node["left"]) - _tree_height(node["right"])
    if balance > 1 and key < node["left"]["key"]:
        rotations.append(f"在{node['key']}执行LL右旋")
        return _rotate_right(node)
    if balance < -1 and key > node["right"]["key"]:
        rotations.append(f"在{node['key']}执行RR左旋")
        return _rotate_left(node)
    if balance > 1 and key > node["left"]["key"]:
        rotations.append(f"在{node['key']}执行LR双旋")
        node["left"] = _rotate_left(node["left"])
        return _rotate_right(node)
    if balance < -1 and key < node["right"]["key"]:
        rotations.append(f"在{node['key']}执行RL双旋")
        node["right"] = _rotate_right(node["right"])
        return _rotate_left(node)
    return node


def _tree_height(node: dict[str, Any] | None) -> int:
    return int((node or {}).get("height") or 0)


def _refresh_tree_height(node: dict[str, Any]) -> None:
    node["height"] = 1 + max(
        _tree_height(node["left"]),
        _tree_height(node["right"]),
    )


def _rotate_left(node: dict[str, Any]) -> dict[str, Any]:
    pivot = node["right"]
    transferred = pivot["left"]
    pivot["left"] = node
    node["right"] = transferred
    _refresh_tree_height(node)
    _refresh_tree_height(pivot)
    return pivot


def _rotate_right(node: dict[str, Any]) -> dict[str, Any]:
    pivot = node["left"]
    transferred = pivot["right"]
    pivot["right"] = node
    node["left"] = transferred
    _refresh_tree_height(node)
    _refresh_tree_height(pivot)
    return pivot


def _normalize_records(records: list[Any], limit: int) -> list[Any]:
    if limit < 0:
        raise ValueError("limit must be non-negative")
    result: list[Any] = []
    for value in records:
        if value is None or value in result:
            continue
        result.append(value)
        if len(result) >= limit:
            break
    return result


def _format_edges(edges: list[list[str]]) -> str:
    return "{" + "、".join(f"{left}-{right}" for left, right in edges) + "}"


def _join(values: list[str]) -> str:
    return "、".join(str(value) for value in values if str(value).strip())


def _issue(code: str, severity: str) -> dict[str, str]:
    return {"code": code, "severity": severity}


def _deduplicate_issues(
    issues: list[dict[str, str]],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for issue in issues:
        key = (issue["code"], issue["severity"])
        if key in seen:
            continue
        seen.add(key)
        result.append(issue)
    return result


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


__all__ = [
    "QUESTION_SPEC_SCHEMA",
    "generate_cross_chapter_contract",
    "generate_question_contract",
    "validate_question_spec",
]
