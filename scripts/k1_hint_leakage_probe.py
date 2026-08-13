#!/usr/bin/env python3
"""K1 acceptance probe: the deepest compile-time hint must not hand over the solution.

`test_hint_leakage.py` pins the metric, but every solution graph it feeds in was
written by hand.  The failure this probe exists to catch only appears with a live
model: `_solution_graph_hint_contract` splices the model's own
`solution_graph.steps[*].action/check` **verbatim** into the level-2 and level-3
hints.  If the model writes the computed result into a step ("配方得 (x-3)^2-4，
最小值为 -4"), that value lands in a hint the student sees before submitting, and
no unit test with hand-written steps will ever show it.

So this probe runs the real production chain — real model → real
`prepare_course` → real `build_question_bank` → real `hint_contract` — and then
checks three things:

  A. real items.  Only items whose contract reached ``generation_status == ready``
     count; a fallback template item proves nothing about the model.  Each is
     judged twice: what the shipped gate says (``leakage_check.passed``) and,
     independently, whether the private final answer is actually readable in the
     hints.  A gate pass with the answer visible is a real gap, not a pass.
  B. gate efficacy, built from the *same* real solutions.  A hint that restates
     every real step plus the real answer must be caught.  Without this, "0 leaks"
     in A could just mean the gate never fired.  The real hint is checked too, so
     an over-tightened gate shows up as a false positive rather than as safety.
  C. the middle ground (``reproduced_step_ratio``) is reported, never judged —
     how much restatement is "too much" is a 教研 call, see NOTES_TO_OWNER.

Needs a configured model (`AI_API_KEY`).  Generates in memory only: writes no
course, no question bank, no `backend/data`.

    backend/.venv/bin/python scripts/k1_hint_leakage_probe.py
    backend/.venv/bin/python scripts/k1_hint_leakage_probe.py --json
    backend/.venv/bin/python scripts/k1_hint_leakage_probe.py --case quadratic

Provider note: `ai_base._thinking_extra_body` sends a top-level `enable_thinking`
flag, which vLLM-hosted qwen ignores — it keeps emitting reasoning tokens until
the caller's `max_tokens` is spent and returns empty content, so every generation
is discarded before a hint is ever built.  With `--suppress-thinking` (default)
the probe sends `chat_template_kwargs.enable_thinking=false` instead, which that
endpoint does honour.  This changes only how the request is transported; the
question, the hints and the gate are all production code.  Use
`--no-suppress-thinking` on providers that honour the top-level flag.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from assessment_orchestrator import (  # noqa: E402
    AssessmentGenerationOrchestrator,
    UniversalAssessmentModel,
)
from hint_leakage import measure_deepest_hint_overlap  # noqa: E402
from question_bank import build_question_bank  # noqa: E402


class _ThinkingSuppressedModel(UniversalAssessmentModel):
    """Send the thinking switch the way vLLM-hosted qwen actually reads it."""

    def _thinking_extra_body(
        self,
        enable_thinking: bool,
        api_base: str | None = None,
    ) -> dict:
        return {"chat_template_kwargs": {"enable_thinking": False}}


def _course(
    case_id: str,
    course_name: str,
    node_name: str,
    node_content: str,
    objective: str,
    key_points: list[str],
    assessment: str,
    pedagogy: str,
) -> dict:
    return {
        "course_id": f"k1-probe-{case_id}",
        "course_name": course_name,
        "course_purpose": "systematic",
        "difficulty": "intermediate",
        "subject_pedagogy_profile": {
            "primary_mode": pedagogy,
            "user_locked": True,
        },
        "generation_request": {
            "course_purpose": "systematic",
            "web_question_enrichment": {"mode": "off"},
        },
        "material_bindings": [],
        "evidence_catalog": [],
        "nodes": [{
            "node_id": f"{case_id}-1",
            "node_level": 2,
            "node_name": node_name,
            "node_content": node_content,
            "learning_objective": objective,
            "key_points": key_points,
            "assessment": [assessment],
            "grounding_contract": {"question_evidence_ids": []},
            "difficulty_contract": {"target_level": "intermediate"},
        }],
    }


# Each case is a subject whose derivation ends in a concrete value — that is the
# shape where a model is most tempted to write the result into a solution step,
# and therefore into the hint compiled from it.
CASES: list[dict] = [
    {
        "case_id": "quadratic",
        "practice_level": "objective_practice",
        "course": _course(
            "quadratic",
            "一元二次函数",
            "配方法求最小值",
            "对二次函数 f(x)=x^2-6x+5，用配方法写成顶点式 f(x)=(x-3)^2-4，"
            "从而读出顶点 (3,-4) 与最小值 -4。配方的关键是把一次项系数折半后"
            "平方，再加减同一个数。",
            "用配方法求二次函数的最小值并说明依据",
            ["配方法", "顶点式", "最小值"],
            "写出配方过程并给出最小值",
            "formal_science",
        ),
    },
    {
        "case_id": "kinematics",
        "practice_level": "objective_practice",
        "course": _course(
            "kinematics",
            "匀变速直线运动",
            "平均速度与位移",
            "汽车以 20 m/s 初速度匀减速，加速度 -2 m/s^2，经 5 s 停止前的位移为 "
            "s = v0·t + a·t^2/2 = 20×5 - 2×25/2 = 75 m，平均速度为 15 m/s。"
            "注意匀变速下平均速度等于首末速度的算术平均。",
            "用运动学公式计算位移与平均速度并核对单位",
            ["匀变速直线运动", "位移公式", "平均速度"],
            "列式计算位移与平均速度并说明单位",
            "natural_science",
        ),
    },
    {
        "case_id": "thermo",
        "practice_level": "concept_check",
        "course": _course(
            "thermo",
            "热力学基础",
            "热力学第一定律",
            "封闭系统吸收热量 Q=20 kJ，同时对外做功 W=8 kJ。由 ΔU=Q-W 得 "
            "ΔU=12 kJ。符号约定是系统吸热 Q 取正、对外做功 W 取正。",
            "使用热力学第一定律计算内能变化",
            ["能量守恒", "符号约定"],
            "列式计算内能变化并核对单位",
            "natural_science",
        ),
    },
    {
        "case_id": "coding",
        "practice_level": "objective_practice",
        "course": _course(
            "coding",
            "Python 基础",
            "列表推导式与筛选",
            "用列表推导式从整数列表中筛出偶数并求和："
            "total = sum(x for x in nums if x % 2 == 0)。"
            "对 nums=[1,2,3,4,5,6] 结果为 12。",
            "用推导式完成筛选与聚合并说明其等价的显式循环",
            ["列表推导式", "取模判断", "聚合"],
            "写出推导式并说明与显式循环的等价性",
            "engineering",
        ),
    },
]


def _normalize(value: object) -> str:
    return "".join(str(value or "").split()).lower()


def _final_answer_texts(envelope: dict) -> list[str]:
    """Every way the private solution states its final answer."""
    candidates = [
        (envelope.get("worked_solution") or {}).get("final_answer"),
        envelope.get("canonical_answer"),
        (envelope.get("legacy_answer_spec") or {}).get("correct_answer"),
        (envelope.get("legacy_answer_spec") or {}).get("canonical_answer"),
        (envelope.get("solution_spec") or {}).get("final_answer"),
    ]
    texts: list[str] = []
    for value in candidates:
        if value is None:
            continue
        text = (
            json.dumps(value, ensure_ascii=False)
            if isinstance(value, (dict, list))
            else str(value)
        )
        if text.strip():
            texts.append(text.strip())
    return texts


_NUMERIC = re.compile(r"-?\d+(?:\.\d+)?")


def _answer_values(answer_texts: list[str]) -> list[str]:
    """Numeric cores of the answer — what a leaked hint would actually give away.

    Two or more characters only: a single-character value collides with step
    numbers and option labels, which is the same trade-off the runtime guard in
    `socratic_guidance` settled on (see NOTES_TO_OWNER, K2).
    """
    values: list[str] = []
    for text in answer_texts:
        for match in _NUMERIC.findall(text):
            if len(match.lstrip("-")) >= 2 or len(match) >= 2:
                values.append(match)
    return sorted(set(values), key=len, reverse=True)


def _value_visible(value: str, text: str) -> bool:
    """Digit-boundary match so -4 does not fire on -42 or on 2024."""
    pattern = re.compile(
        rf"(?<![\d.]){re.escape(value)}(?![\d.])"
    )
    return bool(pattern.search(text))


def _observed_answer_leak(
    levels: list[dict],
    answer_texts: list[str],
) -> dict:
    """Independent read of the hints, not routed through the shipped gate."""
    if not levels:
        return {"checked": False, "reason": "no_hint_levels"}
    deepest = max(levels, key=lambda level: int(level.get("level") or 0))
    deepest_text = str(deepest.get("content") or "")
    all_text = "\n".join(str(level.get("content") or "") for level in levels)

    phrase_hits = [
        text
        for text in answer_texts
        if len(_normalize(text)) >= 4 and _normalize(text) in _normalize(all_text)
    ]
    values = _answer_values(answer_texts)
    value_hits_deepest = [
        value for value in values if _value_visible(value, deepest_text)
    ]
    value_hits_any = [
        value for value in values if _value_visible(value, all_text)
    ]
    return {
        "checked": bool(answer_texts),
        "answer_texts": answer_texts,
        "answer_values": values,
        "phrase_in_any_hint": phrase_hits,
        "value_in_deepest_hint": value_hits_deepest,
        "value_in_any_hint": value_hits_any,
        "leaked": bool(phrase_hits or value_hits_deepest),
    }


def _solution_steps_text(envelope: dict) -> list[str]:
    graph = envelope.get("solution_graph") or {}
    raw = graph.get("steps") if isinstance(graph, dict) else graph
    steps: list[str] = []
    for value in raw or []:
        if isinstance(value, dict):
            text = " ".join(
                str(value.get(field) or "")
                for field in ("action", "check", "instruction", "description")
            ).strip()
        else:
            text = str(value or "").strip()
        if text:
            steps.append(text)
    return steps


async def _run_case(case: dict, *, suppress_thinking: bool) -> dict:
    node_id = f"{case['case_id']}-1"
    model = (
        _ThinkingSuppressedModel()
        if suppress_thinking
        else UniversalAssessmentModel()
    )
    orchestrator = AssessmentGenerationOrchestrator(model=model)
    try:
        prepared = await orchestrator.prepare_course(
            case["course"],
            node_ids=[node_id],
            practice_levels_by_node={node_id: [case["practice_level"]]},
        )
    except Exception as error:  # noqa: BLE001 - a failed run must be reported, not hidden
        return {
            "case_id": case["case_id"],
            "generation_error": f"{type(error).__name__}: {error}",
            "items": [],
        }

    contracts = (prepared.get("_assessment_generated_contracts") or {}).get(
        node_id
    ) or {}
    envelopes: dict[str, dict] = {}
    statuses: dict[str, str] = {}
    for level, contract in contracts.items():
        status = str(contract.get("generation_status") or "")
        statuses[level] = status
        # Only a contract the model produced and that survived validation is
        # evidence about the model.  A discarded slot falls back to a template
        # item, which would otherwise pad the sample with hints no model wrote.
        if status != "ready":
            continue
        envelope = contract.get("solution_envelope") or {}
        revision = str(envelope.get("solution_revision_id") or "")
        if revision:
            envelopes[revision] = envelope

    bundle = build_question_bank(prepared)
    rows: list[dict] = []
    for item in bundle.get("items") or []:
        if item.get("assessment_role") != "practice":
            continue
        # The join back to the model's own solution: an item whose
        # solution_revision_id matches a ready contract's envelope is one the
        # model actually wrote.  Items built from a fallback template carry a
        # revision no ready contract claims, and drop out here.
        revision = str(item.get("solution_revision_id") or "")
        envelope = envelopes.get(revision) or {}
        if not envelope:
            continue
        hint = item.get("hint_contract") or {}
        levels = hint.get("levels") or []
        answer_texts = _final_answer_texts(envelope)
        gate = hint.get("leakage_check") or {}
        rows.append({
            "case_id": case["case_id"],
            "item_id": item.get("item_id"),
            "item_generation_status": item.get("generation_status"),
            "question_type": item.get("question_type"),
            "input_mode": (item.get("input_contract") or {}).get("mode"),
            "prompt": str(item.get("prompt") or "")[:200],
            "hint_generator": hint.get("generator"),
            "hint_levels": [
                {
                    "level": level.get("level"),
                    "content": str(level.get("content") or ""),
                }
                for level in levels
            ],
            "solution_steps": _solution_steps_text(envelope),
            "gate": {
                "passed": bool(gate.get("passed")),
                "overlap": gate.get("deepest_hint_overlap") or {},
            },
            "observed": _observed_answer_leak(levels, answer_texts),
        })
    return {
        "case_id": case["case_id"],
        "generation_status_by_level": statuses,
        "items": rows,
    }


def _gate_efficacy(rows: list[dict]) -> list[dict]:
    """Feed the gate hints built from the real solutions it just cleared.

    Two directions matter equally: a hint that restates the whole real derivation
    plus the real answer must fail, and the real hint must still pass.  A gate
    that catches everything is as unusable as one that catches nothing.
    """
    checks: list[dict] = []
    for row in rows:
        steps = row["solution_steps"]
        answer_texts = row["observed"].get("answer_texts") or []
        if not steps:
            continue
        envelope = {
            "solution_graph": {"steps": [{"action": step} for step in steps]},
            "worked_solution": {
                "final_answer": answer_texts[0] if answer_texts else "",
            },
        }
        leaky_levels = [
            {"level": 1, "content": "先定位题目条件。"},
            {"level": 2, "content": "按方法骨架推进。"},
            {
                "level": 3,
                "content": "完整过程如下：" + "；".join(steps)
                + "。最终答案：" + (answer_texts[0] if answer_texts else ""),
            },
        ]
        leaky = measure_deepest_hint_overlap(leaky_levels, envelope)
        genuine = measure_deepest_hint_overlap(row["hint_levels"], envelope)
        checks.append({
            "case_id": row["case_id"],
            "item_id": row["item_id"],
            "leaky_caught": bool(leaky.get("leaked")),
            "leaky_detail": leaky,
            "genuine_false_positive": bool(genuine.get("leaked")),
            "genuine_detail": genuine,
        })
    return checks


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--case",
        action="append",
        help="Run only these case ids (repeatable).",
    )
    parser.add_argument(
        "--suppress-thinking",
        dest="suppress_thinking",
        action="store_true",
        default=True,
    )
    parser.add_argument(
        "--no-suppress-thinking",
        dest="suppress_thinking",
        action="store_false",
    )
    args = parser.parse_args()

    selected = [
        case
        for case in CASES
        if not args.case or case["case_id"] in set(args.case)
    ]
    if not selected:
        print("no matching case id", file=sys.stderr)
        return 2

    results = []
    for case in selected:
        results.append(
            await _run_case(case, suppress_thinking=args.suppress_thinking)
        )

    rows = [row for result in results for row in result["items"]]
    efficacy = _gate_efficacy(rows)

    gate_leaks = [row for row in rows if not row["gate"]["passed"]]
    observed_leaks = [row for row in rows if row["observed"].get("leaked")]
    silent_leaks = [
        row
        for row in rows
        if row["observed"].get("leaked") and row["gate"]["passed"]
    ]
    efficacy_failures = [
        check
        for check in efficacy
        if not check["leaky_caught"] or check["genuine_false_positive"]
    ]
    generation_errors = [
        result for result in results if result.get("generation_error")
    ]

    # No real items means no evidence.  That is a probe failure, never a pass.
    no_evidence = not rows
    failed = bool(
        no_evidence or observed_leaks or efficacy_failures or gate_leaks
    )

    report = {
        "provider": {
            "api_base": __import__("os").getenv("AI_API_BASE"),
            "model": __import__("os").getenv("AI_MODEL"),
            "thinking_suppressed_by_probe": args.suppress_thinking,
        },
        "cases": results,
        "gate_efficacy": efficacy,
        "summary": {
            "ready_item_count": len(rows),
            "gate_rejected_count": len(gate_leaks),
            "observed_leak_count": len(observed_leaks),
            "silent_leak_count": len(silent_leaks),
            "efficacy_failure_count": len(efficacy_failures),
            "generation_error_count": len(generation_errors),
            "reproduced_step_ratios": [
                row["gate"]["overlap"].get("reproduced_step_ratio")
                for row in rows
            ],
            "passed": not failed,
        },
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if failed else 0

    print("=== A. 真实模型生成 → 真实提示编译 → 真实门禁 ===")
    for result in results:
        if result.get("generation_error"):
            print(f"\n❌ {result['case_id']}: 生成失败 {result['generation_error']}")
            continue
        print(
            f"\n[{result['case_id']}] 生成状态 {result['generation_status_by_level']}"
            f" · 可用条目 {len(result['items'])}"
        )
        for row in result["items"]:
            observed = row["observed"]
            mark = "❌" if observed.get("leaked") else "✅"
            print(f"  {mark} {row['item_id']} ({row['question_type']}/{row['input_mode']})")
            print(f"     题面: {row['prompt'][:80]}")
            for level in row["hint_levels"]:
                print(f"     L{level['level']}: {level['content'][:160]}")
            print(f"     私有答案: {observed.get('answer_texts')}")
            print(
                f"     门禁 passed={row['gate']['passed']} "
                f"reproduced_step_ratio="
                f"{row['gate']['overlap'].get('reproduced_step_ratio')}"
            )
            if observed.get("leaked"):
                print(
                    f"     ⚠ 独立检查发现答案可见: 短语{observed.get('phrase_in_any_hint')} "
                    f"数值(最深层){observed.get('value_in_deepest_hint')}"
                )
            elif observed.get("value_in_any_hint"):
                print(
                    f"     ℹ 非最深层提示出现答案数值 "
                    f"{observed.get('value_in_any_hint')}（未判泄漏，供教研看）"
                )

    print("\n=== B. 门禁有效性（用同一批真实解答构造泄漏提示）===")
    for check in efficacy:
        mark = (
            "✅"
            if check["leaky_caught"] and not check["genuine_false_positive"]
            else "❌"
        )
        print(
            f"{mark} {check['item_id']}: 泄漏提示被拦={check['leaky_caught']} "
            f"真实提示误伤={check['genuine_false_positive']}"
        )
    if not efficacy:
        print("（无可用真实解答，未能检验门禁有效性）")

    print("\n=== C. 中间地带计量（如实报告，不判失败）===")
    print(f"reproduced_step_ratio: {report['summary']['reproduced_step_ratios']}")
    print("阈值属教研口径，本探针不下结论（见 NOTES_TO_OWNER · K1 中间地带阈值）。")

    print(
        f"\n可用条目 {len(rows)} | 门禁拒绝 {len(gate_leaks)} | 实测泄漏 "
        f"{len(observed_leaks)}（其中门禁漏放 {len(silent_leaks)}）| "
        f"门禁失效 {len(efficacy_failures)} | 生成失败 {len(generation_errors)}"
    )
    if no_evidence:
        print("❌ 没有取到任何 ready 条目——没有真机证据，不算通过。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
