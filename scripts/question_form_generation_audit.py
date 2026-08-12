#!/usr/bin/env python3
"""真机出题 + 判分一致性核查（清单 H1a / H1b 的最后一步）。

用真实 provider 各出若干道多选 / 判断 / 填空题，然后用**预先声明的作答用例与
预期分**（`backend/question_grading_perturbations.py`）跑判分器，比对实际输出。

## 指标命名纪律（重要）

产出的指标叫 **预期一致率（expected-agreement）**，衡量的是「判分器是否符合
预先声明的判分意图」。预期分由 AI 编写、**未经教研复核**，因此：

- 不得称为「人工一致率」；
- 清单要求的「判分器与人工判分一致率 > 90%」状态为**待教研复核**，
  不因预期一致率达标而标为通过；
- 本脚本导出的逐条清单就是供教研复核的材料。

用法：

    python scripts/question_form_generation_audit.py --dry-run     # 不联网自检
    python scripts/question_form_generation_audit.py --per-form 1  # 先验证链路
    python scripts/question_form_generation_audit.py --per-form 10 # 正式取证
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# 目标形态 -> 用哪种知识点类型把 H2 引到这个形态上。
# 对应关系来自 question_form_matching._RULES，不是随手编的。
_FORM_BY_KNOWLEDGE_TYPE = {
    "true_false": "condition",
    "fill_blank": "representation",
    "multiple_choice": "rule",
    "single_choice": "definition",
}


def _knowledge_point(index: int, knowledge_type: str, node_id: str) -> dict[str, Any]:
    return {
        "knowledge_id": f"ckp_probe_{index}",
        "course_id": "form-audit",
        "knowledge_type": knowledge_type,
        "name": f"探针知识点{index}",
        "statement": "封闭系统的内能变化等于吸收的热量减去对外做的功。",
        "section_refs": [node_id],
        "objective_refs": [],
        "source_refs": [],
    }


def _course(forms: list[str], per_form: int) -> dict[str, Any]:
    """构造一门探针课程：每个目标形态给 per_form 个小节。"""
    nodes: list[dict[str, Any]] = []
    points: list[dict[str, Any]] = []
    index = 0
    for form in forms:
        knowledge_type = _FORM_BY_KNOWLEDGE_TYPE[form]
        for offset in range(per_form):
            index += 1
            node_id = f"L2-{form}-{offset + 1}"
            nodes.append({
                "node_id": node_id,
                "node_level": 2,
                "node_name": f"热力学第一定律 · {form} · {offset + 1}",
                "learning_objective": "使用热力学第一定律计算封闭系统的内能变化",
                "key_points": ["能量守恒", "热力学第一定律"],
                "assessment": ["列式计算内能变化并核对单位"],
                "node_content": (
                    "封闭系统与外界交换能量时，内能变化 ΔU 等于系统吸收的热量 Q "
                    "减去系统对外做的功 W，即 ΔU = Q - W。规定系统吸热时 Q 取正、"
                    "系统对外做功时 W 取正。例如某封闭系统吸收热量 20 kJ，同时对外"
                    "做功 8 kJ，则 ΔU = 20 kJ - 8 kJ = 12 kJ。所有能量均以 kJ 计，"
                    "计算后应回代检查能量守恒是否成立。"
                ),
                "difficulty_contract": {"target_level": "intermediate"},
                "grounding_contract": {"question_evidence_ids": []},
                # 显式声明目标形态：H2 的推荐表里没有任何知识点类型把
                # multiple_choice 排第一，纯按推荐顺序取不到多选。
                "preferred_question_form": form,
            })
            points.append(_knowledge_point(index, knowledge_type, node_id))
    return {
        "course_id": "form-audit",
        "course_name": "题型生成核查",
        "course_purpose": "systematic",
        "difficulty": "intermediate",
        "subject_pedagogy_profile": {
            "primary_mode": "natural_science",
            "user_locked": True,
        },
        "generation_request": {
            "course_purpose": "systematic",
            "web_question_enrichment": {"mode": "off"},
        },
        "material_bindings": [],
        "evidence_catalog": [],
        "course_knowledge_base": {
            "schema_version": "course_knowledge_base_v1",
            "course_id": "form-audit",
            "knowledge_points": points,
            "skill_units": [],
            "misconceptions": [],
            "mastery_criteria": [],
        },
        "nodes": nodes,
    }


def _private_answer_spec(
    item: dict[str, Any],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    """取这道题的私有答案。

    V2 题落库时 answer_spec 被显式置空（`_stored_formal_task_from_item`），
    真正的标准答案在 bundle 的 solution_envelopes 里按 solution_revision_id
    索引。核查要拿私有答案去构造作答，所以必须从那里读——直接读 item 的
    answer_spec 会永远拿到空字典，一条用例都构造不出来。
    """
    spec = item.get("answer_spec") or {}
    if spec:
        return spec
    envelope = (bundle.get("solution_envelopes") or {}).get(
        str(item.get("solution_revision_id") or "")
    ) or {}
    if not envelope:
        return {}
    from assessment_compiler import solution_answer_spec

    return solution_answer_spec(
        envelope,
        input_mode=str(
            (item.get("input_contract") or {}).get("mode") or "choice"
        ),
        options=item.get("options") or [],
        fallback={},
    )


def _grade_choice_cases(
    item: dict[str, Any],
    bundle: dict[str, Any],
) -> list[dict[str, Any]]:
    from question_choice_grading import correct_option_ids, grade_choice
    from question_grading_perturbations import choice_cases

    answer_spec = _private_answer_spec(item, bundle)
    correct = sorted(correct_option_ids(item, answer_spec))
    results: list[dict[str, Any]] = []
    for case in choice_cases(item, correct):
        graded = grade_choice(item, answer_spec, case["payload"])
        results.append({
            **case,
            "actual_score": graded["score"],
            "actual_passed": graded["passed"],
            "agrees": (
                graded["score"] == case["expected_score"]
                and graded["passed"] == case["expected_passed"]
            ),
        })
    return results


def _grade_fill_blank_cases(contract: dict[str, Any]) -> list[dict[str, Any]]:
    from question_fill_blank import grade_fill_blank
    from question_grading_perturbations import fill_blank_cases

    results: list[dict[str, Any]] = []
    for case in fill_blank_cases(contract):
        graded = grade_fill_blank(contract, case["payload"])
        results.append({
            **case,
            "actual_score": graded["score"],
            "actual_passed": graded["all_correct"],
            "agrees": (
                abs(graded["score"] - float(case["expected_score"])) < 0.01
                and graded["all_correct"] == case["expected_passed"]
            ),
        })
    return results


def _provider_cooldowns() -> int:
    """本轮有没有触发过 provider 熔断/冷却。

    熔断会让调用被跳过而不是真的发出去，跑出来又快又少——那样的数据不能当
    有效样本。
    """
    try:
        from ai_capacity import _CONTROLLERS
    except Exception:  # noqa: BLE001 - 拿不到就报 -1，不假装是 0
        return -1
    total = 0
    for controller in _CONTROLLERS.values():
        models = getattr(controller, "_models", None)
        if not isinstance(models, dict):
            return -1
        for state in models.values():
            total += int(getattr(state, "quota_exhausted", 0) or 0)
    return total


async def _run(forms: list[str], per_form: int, profile: str) -> dict[str, Any]:
    from assessment_orchestrator import AssessmentGenerationOrchestrator
    from question_bank import build_question_bank
    from question_fill_blank import compile_fill_blank_contract
    from question_forms import classify_question_form

    course = _course(forms, per_form)
    started = time.monotonic()
    prepared = await AssessmentGenerationOrchestrator().prepare_course(
        course,
        generation_profile=profile,
        practice_levels_by_node={
            str(node["node_id"]): ["concept_check"]
            for node in course["nodes"]
        },
    )
    elapsed = time.monotonic() - started
    # 记录每个槽位的最终去向与失败原因——生成失败率与失败原因本身就是要如实
    # 报告的结果，不能只报成功的那几道。
    outcomes: dict[str, dict[str, Any]] = {}
    for entry in (
        prepared.get("_assessment_generation_audit") or {}
    ).get("items") or []:
        if str(entry.get("practice_level") or "") != "concept_check":
            continue
        attempts = entry.get("attempts") or []
        codes: list[str] = []
        for attempt in attempts:
            for code in attempt.get("issue_codes") or []:
                if code and code not in codes:
                    codes.append(str(code))
        # 逐轮明细：哪一轮报了什么码、决定做什么。
        # 只有聚合计数时无法回答「这道题为什么没成」——归因必须能落到单题单轮。
        attempt_trail = [
            {
                "attempt": a.get("attempt"),
                "decision": a.get("decision"),
                "issue_codes": list(a.get("issue_codes") or []),
            }
            for a in attempts
        ]
        outcomes[str(entry.get("node_id") or "")] = {
            # 整槽异常（一次 attempt 都没发生）的真实原因就存在这两个字段里。
            # 不采它们，`attempts: []` 的题在报告里只剩一个空壳，看不出为什么。
            "error_code": str(entry.get("error_code") or ""),
            "error_message": str(entry.get("error_message") or "")[:300],
            "attempt_trail": attempt_trail,
            "semantic_preflight_issues": [
                str(i.get("code") or "")
                for i in (entry.get("semantic_preflight") or {}).get("issues") or []
                if i.get("code")
            ],
            "final_decision": str(entry.get("final_decision") or ""),
            "attempt_count": len(attempts),
            "issue_codes": codes,
        }
    bundle = build_question_bank(prepared)
    items = bundle.get("items") or []

    # 只看 concept_check 这一层的正式练习题。
    #
    # build_question_bank 会为每个小节产出多个角色的题（其他练习层级、
    # final_assessment 等）。只按 node_id 归组会把它们一起算进来——第一次真机跑
    # 就是这样，每节请求 1 道却抓到 3-4 条，且多数是别的层级的简答/大题，
    # 于是「声明为多选却分类成 essay」看起来像失败，实际是抓错了对象。
    by_node: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        if str(item.get("assessment_role") or "") != "practice":
            continue
        levels = item.get("practice_levels") or []
        level = str(
            next(iter(levels), item.get("practice_level") or "")
        )
        if level != "concept_check":
            continue
        node_id = str(item.get("node_id") or "")
        by_node.setdefault(node_id, []).append(item)

    per_form_report: dict[str, Any] = {}
    checked: list[dict[str, Any]] = []
    for form in forms:
        requested = per_form
        node_ids = [
            str(node["node_id"]) for node in course["nodes"]
            if str(node["node_id"]).startswith(f"L2-{form}-")
        ]
        generated = 0
        classified_ok = 0
        agree_total = 0
        agree_hit = 0
        for node_id in node_ids:
            for item in by_node.get(node_id, []):
                generated += 1
                actual_form = classify_question_form(item)
                if actual_form == form:
                    classified_ok += 1
                cases: list[dict[str, Any]] = []
                if form == "fill_blank":
                    blanks = (
                        _private_answer_spec(item, bundle).get("blanks")
                        or (
                            (bundle.get("solution_envelopes") or {}).get(
                                str(item.get("solution_revision_id") or "")
                            ) or {}
                        ).get("blanks")
                        or []
                    )
                    if blanks:
                        try:
                            contract = compile_fill_blank_contract(
                                prompt=str(item.get("prompt") or ""),
                                blanks=blanks,
                            )
                            cases = _grade_fill_blank_cases(contract)
                        except ValueError as error:
                            cases = [{
                                "case_id": "contract_invalid",
                                "description": "填空契约结构非法",
                                "expected_score": None,
                                "actual_score": None,
                                "agrees": False,
                                "rationale": str(error),
                            }]
                else:
                    cases = _grade_choice_cases(item, bundle)
                for case in cases:
                    agree_total += 1
                    if case.get("agrees"):
                        agree_hit += 1
                checked.append({
                    "form": form,
                    "node_id": node_id,
                    "revision_id": str(item.get("revision_id") or ""),
                    "declared_form": form,
                    "classified_form": actual_form,
                    "prompt": str(item.get("prompt") or "")[:400],
                    "options": [
                        {"id": o.get("id"), "text": o.get("text")}
                        for o in item.get("options") or []
                    ],
                    "answer_spec": deepcopy(item.get("answer_spec") or {}),
                    "input_contract": deepcopy(item.get("input_contract") or {}),
                    "cases": cases,
                })
        form_outcomes = [
            {"node_id": node_id, **outcomes[node_id]}
            for node_id in node_ids
            if node_id in outcomes
        ]
        discarded = [
            entry for entry in form_outcomes
            if entry["final_decision"] != "publish"
        ]
        failure_codes: dict[str, int] = {}
        for entry in discarded:
            for code in entry["issue_codes"]:
                failure_codes[code] = failure_codes.get(code, 0) + 1
        per_form_report[form] = {
            "requested": requested,
            "generated": generated,
            "discarded": len(discarded),
            # 逐条失败明细，供归因用
            "discarded_detail": deepcopy(discarded),
            "failure_issue_codes": dict(
                sorted(failure_codes.items(), key=lambda kv: -kv[1])
            ),
            "classified_as_declared": classified_ok,
            "graded_case_count": agree_total,
            "expected_agreement_hits": agree_hit,
            "expected_agreement_rate": (
                round(agree_hit / agree_total, 4) if agree_total else None
            ),
        }

    # 熔断判据所需的运行体征。
    #
    # lz-web-search 独立复核给出的口径：健康运行 250-315 秒 / 92-103 次调用 /
    # 0 熔断；出现「100 秒出头、20 多次调用」就是熔断了，那一轮数据必须作废。
    # 我前五轮只记了耗时，调用数这一维无法回查——补上，让判据两个轴都能核。
    gen_audit = prepared.get("_assessment_generation_audit") or {}
    vitals: dict[str, Any] = {
        "logical_call_count": int(gen_audit.get("logical_call_count") or 0),
        "physical_model_call_count": int(
            gen_audit.get("physical_model_call_count") or 0
        ),
        "provider_attempt_count": int(
            gen_audit.get("provider_attempt_count") or 0
        ),
        "generation_calls": int(gen_audit.get("generation_calls") or 0),
        "repair_calls": int(gen_audit.get("repair_calls") or 0),
        "independent_solution_calls": int(
            gen_audit.get("independent_solution_calls") or 0
        ),
        "semantic_evaluation_calls": int(
            gen_audit.get("semantic_evaluation_calls") or 0
        ),
        "provider_cooldowns": _provider_cooldowns(),
    }
    # 产出量必须与耗时/调用数一起看。
    #
    # 实测踩到过一次反例：修完缺陷后的运行 214.9 秒 / 82 次调用，两项都**低于**
    # lz-web-search 给的健康区间（250-315 秒 / 92-103 次），按「快 = 熔断」会被
    # 误判作废——但那一轮产出 27/30 道，是历轮最高。原因是修复减少了失败重试，
    # 「更快更少」在这里是修好了的信号，不是熔断。
    # 熔断的真正特征是「快 + 少 + 产出也少」，三者要一起看。
    vitals["generated_total"] = sum(
        int(v.get("generated") or 0) for v in per_form_report.values()
    )
    vitals["requested_total"] = sum(
        int(v.get("requested") or 0) for v in per_form_report.values()
    )

    return {
        "schema_version": "question_form_generation_audit_v2",
        "run_vitals": vitals,
        "metric_name": "expected_agreement",
        "metric_disclaimer": (
            "预期一致率：预期分由 AI 编写、未经教研复核，"
            "不等于人工判分一致率；清单 H1a/H1b 的人工一致率一条仍为待教研复核。"
        ),
        "generation_profile": profile,
        "elapsed_seconds": round(elapsed, 1),
        "per_form": per_form_report,
        "items": checked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-form", type=int, default=1)
    parser.add_argument(
        "--forms",
        default="multiple_choice,true_false,fill_blank",
    )
    parser.add_argument("--profile", default="deliberate")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    forms = [value.strip() for value in args.forms.split(",") if value.strip()]
    unknown = [form for form in forms if form not in _FORM_BY_KNOWLEDGE_TYPE]
    if unknown:
        print(f"unsupported forms: {unknown}", file=sys.stderr)
        return 2

    if args.dry_run:
        course = _course(forms, args.per_form)
        from assessment_blueprint import compile_course_assessment_blueprint

        blueprint = compile_course_assessment_blueprint(course)
        rows = []
        for node in blueprint.get("nodes") or []:
            slot = next(
                (
                    s for s in node.get("slots") or []
                    if s.get("practice_level") == "concept_check"
                ),
                None,
            )
            if slot:
                rows.append({
                    "node_id": node.get("node_id"),
                    "question_form": slot.get("question_form"),
                    "input_mode": slot.get("input_mode"),
                })
        print(json.dumps({"dry_run": True, "slots": rows}, ensure_ascii=False, indent=2))
        return 0

    with tempfile.TemporaryDirectory(prefix="form-audit-") as tmp:
        os.environ.setdefault("DATA_DIR", tmp)
        report = asyncio.run(_run(forms, args.per_form, args.profile))

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        print(f"written: {args.out}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
