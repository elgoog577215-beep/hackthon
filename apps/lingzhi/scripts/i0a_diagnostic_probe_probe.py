#!/usr/bin/env python3
"""I0-a acceptance probe: an error-shaped probe must not carry its own answer.

`test_diagnostic_probes.py` covers `build_probe_spec` and `probe_leaks_answer`
with hand-written hypotheses.  What it cannot cover is where the hypothesis text
comes from in production: `diagnostic_hypotheses` lifts `claim` straight out of
the live model's `answer_diagnosis.issues[*].what_happened`, and
`build_probe_spec` splices that claim verbatim into the probe prompt the student
reads.  So the real question is one no fixture can answer — **when a real model
describes what went wrong, does it name the answer while doing so?**

That matters because `probe_leaks_answer` only guards the knowledge-base fields
(`discrimination`, `repair_strategy`).  It never looks at the question's own
correct answer, on the assumption that authored claims do not contain it.  This
probe tests that assumption against real diagnoses.

Three parts:

  A. real diagnosis → real hypotheses → real probes, over question types whose
     answer is a concrete value the diagnosis has every reason to mention.
     Each probe is checked for the correct answer, in phrase and value form.
  B. the existing guard's own red line: forbidden knowledge-base fields must
     never reach a probe, and an injected leak must still be caught — otherwise
     a clean part A says nothing.
  C. category coverage: all four probe shapes must be reachable and pairwise
     distinct on real data, not just in fixtures.

Needs a configured model (`AI_API_KEY`).  Read-only: touches no course data.

    backend/.venv/bin/python scripts/i0a_diagnostic_probe_probe.py
    backend/.venv/bin/python scripts/i0a_diagnostic_probe_probe.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from diagnostic_probes import (  # noqa: E402
    FORBIDDEN_PROBE_FIELDS,
    PROBE_CATEGORIES,
    build_probe_spec,
    probe_leaks_answer,
)
from diagnostic_workflows import (  # noqa: E402
    diagnostic_hypotheses,
    diagnostic_tasks,
)
from practice_analysis import PracticeAnalysisService  # noqa: E402


OBJECTIVE_REVISION = "obj-rev-i0a"


def _course() -> dict:
    """A course whose knowledge base has the misconception fields I0-a reads."""
    return {
        "course_id": "i0a-probe",
        "learning_assets": {
            "diagnostic_templates": [],
            "misconceptions": [{
                "mistake_point_id": "mp-1",
                "objective_revision_id": OBJECTIVE_REVISION,
                "error_pattern": "把顶点式里的常数直接当作最小值的相反数",
                "confused_with": "抛物线的对称轴",
                # These two are the probe's own answer key: a probe that shows
                # them tests nothing, because the student can copy them.
                "discrimination": "对称轴看的是 x 的取值，最小值看的是 f(x) 的取值，二者量纲不同",
                "repair_strategy": "先把式子配成 a(x-h)^2+k，再分别读出 h 与 k 的含义",
            }],
        },
    }


def _task(
    prompt: str,
    objective: str,
    practice_level: str,
    correct_answer: str,
) -> dict:
    return {
        "task_id": "task-i0a",
        "objective_revision_id": OBJECTIVE_REVISION,
        "learning_objective": objective,
        "prompt": prompt,
        "practice_level": practice_level,
        "mistake_point_ids": ["mp-1"],
        # Production tasks carry the graded answer here; this is the same field
        # K2's runtime screen reads (`routers/practice.py` passes the resolved
        # task to both `next_turn` and `advance_workflow_after_grade`).
        "answer_spec": {
            "correct_answer": correct_answer,
            "criteria": ["方法正确", "结果可复核"],
        },
    }


def _question(prompt: str, goal: str, question_type: str = "short_answer") -> dict:
    return {
        "prompt": prompt,
        "question_type": question_type,
        "practice_level": "guided_practice",
        "options": [],
        # diagnose_answer refuses to run on un-preflighted questions; that gate
        # is verified separately (see NOTES_TO_OWNER · J2).
        "question_analysis": {
            "status": "passed",
            "question_understanding": {"task_goal": goal},
        },
        "assessment_intent": {
            "revision_id": "probe-intent",
            "target_knowledge": [{"id": "kp1", "name": "目标知识"}],
            "target_skills": [{"id": "sk1", "name": "目标能力"}],
            "target_misconceptions": [{"id": "mp-1", "name": "典型易错"}],
            "observable_actions": ["完成关键判断并说明依据"],
            "answer_invariants": ["结论有依据支撑"],
        },
    }


# Every case ends in a concrete value, and the student gets it wrong in a way a
# diagnosis naturally describes by naming the right value ("应该是 -4，不是 4").
CASES = [
    {
        "name": "配方法求最小值（答错符号）",
        "practice_level": "mastery_check",
        "objective": "用配方法求二次函数的最小值",
        "question": _question(
            "求 f(x)=x^2-6x+5 的最小值，并写出配方过程。",
            "配方并求最小值",
        ),
        "answer": {"text": "配成 (x-3)^2+4，所以最小值是 4。"},
        "correct_answer": "最小值为 -4",
        "answer_values": ["-4"],
    },
    {
        "name": "平均速度（用错公式）",
        "practice_level": "objective_practice",
        "objective": "计算匀变速运动的平均速度",
        "question": _question(
            "汽车从 20 m/s 匀减速到 10 m/s，求这段时间的平均速度。",
            "求平均速度",
        ),
        "answer": {"text": "平均速度就是末速度，所以是 10 m/s。"},
        "correct_answer": "平均速度为 15 m/s",
        "answer_values": ["15"],
    },
    {
        "name": "热力学第一定律（符号搞反）",
        "practice_level": "concept_check",
        "objective": "用热力学第一定律计算内能变化",
        "question": _question(
            "封闭系统吸热 20 kJ，对外做功 8 kJ，求内能变化。",
            "求内能变化",
        ),
        "answer": {"text": "ΔU = Q + W = 28 kJ。"},
        "correct_answer": "内能变化为 12 kJ",
        "answer_values": ["12"],
    },
]


def _normalize(value: object) -> str:
    return "".join(str(value or "").split()).lower()


def _value_visible(value: str, text: str) -> bool:
    return bool(
        re.search(rf"(?<![\d.]){re.escape(value)}(?![\d.])", text)
    )


def _probe_text(probe_task: dict) -> str:
    parts = [str(probe_task.get("prompt") or "")]
    answer_spec = probe_task.get("answer_spec") or {}
    parts.extend(str(item) for item in answer_spec.get("criteria") or [])
    return "\n".join(parts)


async def _run_case(case: dict) -> dict:
    service = PracticeAnalysisService()
    attempt = {
        "attempt_id": "attempt-i0a",
        "answer_payload": case["answer"],
    }
    diagnosis = await service.diagnose_answer(case["question"], attempt)
    status = str(diagnosis.get("status") or "")
    claims = [
        str(
            (issue or {}).get("what_happened")
            or (issue or {}).get("title")
            or ""
        ).strip()
        for issue in ((diagnosis.get("diagnosis") or {}).get("issues") or [])
    ]

    course = _course()
    task = _task(
        case["question"]["prompt"],
        case["objective"],
        case["practice_level"],
        case["correct_answer"],
    )
    full_attempt = {
        "attempt_id": "attempt-i0a",
        "result": {
            "answer_diagnosis": diagnosis,
            "rubric_results": [
                {"criterion": "结果正确", "met": False},
            ],
        },
    }
    hypotheses = diagnostic_hypotheses(course, task, full_attempt)
    probes = diagnostic_tasks(course, task, hypotheses)

    rows = []
    for hypothesis, probe in zip(hypotheses, probes):
        text = _probe_text(probe)
        phrase_hit = (
            _normalize(case["correct_answer"]) in _normalize(text)
            if len(_normalize(case["correct_answer"])) >= 4
            else False
        )
        value_hits = [
            value
            for value in case["answer_values"]
            if _value_visible(value, text)
        ]
        forbidden_hits = [
            field
            for field in FORBIDDEN_PROBE_FIELDS
            if _normalize(
                (course["learning_assets"]["misconceptions"][0]).get(field)
            )
            in _normalize(text)
        ]
        rows.append({
            "category": hypothesis.get("category"),
            "claim": hypothesis.get("claim"),
            "probe_strategy": probe.get("probe_strategy"),
            "probe_prompt": str(probe.get("prompt") or ""),
            "answer_phrase_in_probe": phrase_hit,
            "answer_values_in_probe": value_hits,
            "forbidden_fields_in_probe": forbidden_hits,
            "leaked": bool(phrase_hit or value_hits or forbidden_hits),
        })
    return {
        "name": case["name"],
        "diagnosis_status": status,
        "diagnosis_unavailable_reason": diagnosis.get("reason"),
        "model_claims": claims,
        "probes": rows,
    }


def _guard_efficacy() -> list[dict]:
    """The guard must still catch what it is supposed to catch."""
    misconception = _course()["learning_assets"]["misconceptions"][0]
    task = _task("题面", "目标", "concept_check", "最小值为 -4")
    checks = []
    for field in FORBIDDEN_PROBE_FIELDS:
        injected = {
            "prompt": f"请回答：{misconception[field]}",
            "criteria": ["说明依据"],
            "probe_strategy": "discriminate_neighbour",
        }
        checks.append({
            "name": f"注入 {field}",
            "caught_field": probe_leaks_answer(injected, misconception, task),
            "expected_field": field,
        })
    # The path this probe found in production: the model's claim names the answer,
    # and build_probe_spec splices the claim into the prompt verbatim.
    checks.append({
        "name": "注入 claim 里的答案数值",
        "caught_field": probe_leaks_answer(
            {
                "prompt": "针对这一点作答：原常数相加应得 -4，学生误算为 +4。",
                "criteria": ["说明依据"],
                "probe_strategy": "redo_single_step",
            },
            misconception,
            task,
        ),
        "expected_field": "answer_value:-4",
    })
    # And the other direction: a probe mentioning a step index must not be blocked.
    checks.append({
        "name": "提到步骤号不被误伤",
        "caught_field": probe_leaks_answer(
            {
                "prompt": "只重做出问题的那一步：第 4 步你用了什么条件？",
                "criteria": ["指明这一步的输入"],
                "probe_strategy": "redo_single_step",
            },
            misconception,
            task,
        ),
        "expected_field": "",
    })
    clean = build_probe_spec(
        {"category": "boundary_confusion", "claim": "学生把两个概念混在一起"},
        task=task,
        misconception=misconception,
    )
    checks.append({
        "name": "正常探针不被误伤",
        "caught_field": probe_leaks_answer(clean, misconception, task),
        "expected_field": "",
    })
    return checks


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = [await _run_case(case) for case in CASES]
    guards = _guard_efficacy()

    all_probes = [probe for result in results for probe in result["probes"]]
    leaks = [probe for probe in all_probes if probe["leaked"]]
    guard_failures = [
        check
        for check in guards
        if check["caught_field"] != check["expected_field"]
    ]
    unavailable = [
        result
        for result in results
        if result["diagnosis_status"] != "completed"
    ]
    categories = sorted({
        str(probe["category"]) for probe in all_probes if probe["category"]
    })
    strategies = {
        str(probe["category"]): probe["probe_strategy"]
        for probe in all_probes
    }
    distinct_shapes = len(set(strategies.values())) == len(strategies)

    # No completed diagnosis means no real claim text, so part A proved nothing.
    no_evidence = not all_probes or len(unavailable) == len(results)
    failed = bool(no_evidence or leaks or guard_failures or not distinct_shapes)

    report = {
        "provider": {
            "api_base": os.getenv("AI_API_BASE"),
            "model": os.getenv("AI_MODEL"),
        },
        "cases": results,
        "guard_efficacy": guards,
        "summary": {
            "probe_count": len(all_probes),
            "leak_count": len(leaks),
            "guard_failure_count": len(guard_failures),
            "diagnosis_unavailable_count": len(unavailable),
            "categories_seen": categories,
            "all_categories_known": all(
                category in PROBE_CATEGORIES for category in categories
            ),
            "shapes_pairwise_distinct": distinct_shapes,
            "passed": not failed,
        },
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if failed else 0

    print("=== A. 真实诊断 → 真实假设 → 真实探针 ===")
    for result in results:
        print(f"\n[{result['name']}] 诊断状态 {result['diagnosis_status']}"
              f" {result.get('diagnosis_unavailable_reason') or ''}")
        for claim in result["model_claims"]:
            print(f"   模型断言: {claim[:120]}")
        for probe in result["probes"]:
            mark = "❌" if probe["leaked"] else "✅"
            print(f"  {mark} [{probe['category']}/{probe['probe_strategy']}]")
            print(f"     探针: {probe['probe_prompt'][:180]}")
            if probe["leaked"]:
                print(
                    f"     ⚠ 探针里出现了答案: 短语={probe['answer_phrase_in_probe']} "
                    f"数值={probe['answer_values_in_probe']} "
                    f"禁用字段={probe['forbidden_fields_in_probe']}"
                )

    print("\n=== B. 守卫有效性（注入必须被抓，正常探针不得误伤）===")
    for check in guards:
        mark = "✅" if check["caught_field"] == check["expected_field"] else "❌"
        print(
            f"{mark} {check['name']}: caught={check['caught_field']!r} "
            f"expected={check['expected_field']!r}"
        )

    print("\n=== C. 四类探针形态覆盖 ===")
    print(f"实际出现的类别: {categories}")
    print(f"类别→形态: {strategies}")
    print(f"形态两两不同: {distinct_shapes}")

    print(
        f"\n探针 {len(all_probes)} 条 | 泄漏 {len(leaks)} | 守卫失效 "
        f"{len(guard_failures)} | 诊断不可用 {len(unavailable)}/{len(results)}"
    )
    if no_evidence:
        print("❌ 没有取到任何真实诊断断言——没有真机证据，不算通过。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
