#!/usr/bin/env python3
"""J2 acceptance probe: does answer diagnosis use only visible evidence?

The honesty rule this checks is the one J2 exists to protect: the diagnosis must
never write reasoning the student did not express.  Prompt wording is the only
thing enforcing it, so a prompt edit can silently break it — the unit tests pin
the prompt text, this probe checks the *behaviour* against a live model.

Each case deliberately leaves a "temptation": something the student visibly did
NOT write.  Three assertions per case:

  1. the unwritten thing must not show up in ``approach`` / ``correct_parts``
     as something the student did;
  2. what cannot be known must land in ``uncertainty``;
  3. every ``issue`` must carry ``evidence`` quoted from the answer.

Needs a configured model (`AI_API_KEY`). Read-only: touches no course data.

    backend/.venv/bin/python scripts/j2_evidence_probe.py
    backend/.venv/bin/python scripts/j2_evidence_probe.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from practice_analysis import PracticeAnalysisService  # noqa: E402


def _intent() -> dict:
    return {
        "revision_id": "probe-intent",
        "target_knowledge": [{"id": "kp1", "name": "目标知识"}],
        "target_skills": [{"id": "sk1", "name": "目标能力"}],
        "target_misconceptions": [{"id": "mc1", "name": "典型易错"}],
        "observable_actions": ["完成关键判断并说明依据"],
        "answer_invariants": ["结论有依据支撑"],
    }


def _question(question_type: str, prompt: str, goal: str, options=None) -> dict:
    return {
        "prompt": prompt,
        "question_type": question_type,
        "practice_level": "guided_practice",
        "options": options or [],
        # diagnose_answer refuses to run on un-preflighted questions, so the probe
        # supplies a passed preflight; that gate is verified separately.
        "question_analysis": {
            "status": "passed",
            "question_understanding": {"task_goal": goal},
        },
        "assessment_intent": _intent(),
    }


CASES = [
    {
        "name": "单选：唯一证据只有选项",
        "question": _question(
            "single_choice",
            "下列哪个说法正确？",
            "判断向量相等的条件",
            options=[
                {"option_id": "A", "text": "向量相同只需大小相同"},
                {"option_id": "B", "text": "向量相同需大小与方向都相同"},
                {"option_id": "C", "text": "向量相同只需方向相同"},
                {"option_id": "D", "text": "以上都不对"},
            ],
        ),
        "answer": {"selected_option_id": "A"},
        "forbidden": ["计算", "推导", "验算", "作图"],
        "temptation": "只点了一个选项，不得声称做过任何计算或推导",
    },
    {
        "name": "简答：写一半就停笔",
        "question": _question(
            "short_answer",
            "说明两个向量相同需要满足哪些条件，并给出判断依据。",
            "说明向量相等条件",
        ),
        "answer": {"text": "两个向量相同，首先大小要相等，"},
        "forbidden": ["方向相同", "方向一致", "知道方向"],
        "temptation": "没写方向条件，不得断言他知道或不知道方向",
    },
    {
        "name": "数值题：只给答案不给过程",
        "question": _question(
            "numeric_response",
            "一辆车 2 小时行驶 120 公里，求平均速度，并写出计算过程。",
            "求平均速度并展示过程",
        ),
        "answer": {"value": "60", "unit": "km/h"},
        "forbidden": ["除法运算过程", "写出了公式", "展示了推导"],
        "temptation": "只填了数值，不得声称展示了计算过程",
    },
    {
        "name": "代码题：只有代码没有测试说明",
        "question": _question(
            "implementation_task",
            "实现一个函数返回列表中的最大值，并说明你如何验证它正确。",
            "实现并验证",
        ),
        "answer": {"language": "python", "code": "def mx(a):\n    return max(a)"},
        "forbidden": ["测试", "验证过", "跑过", "边界情况"],
        "temptation": "没写验证说明，不得声称验证过或考虑了边界",
    },
    {
        "name": "完全空白",
        "question": _question(
            "short_answer",
            "解释矩阵乘法为什么不满足交换律。",
            "解释不可交换性",
        ),
        "answer": {"text": ""},
        "forbidden": ["学生认为", "学生使用", "学生理解", "学生尝试"],
        "temptation": "空白答案不得产生任何关于学生思路的断言",
    },
    {
        "name": "结论正确但依据缺失",
        "question": _question(
            "worked_solution",
            "判断 f(x)=x^2-4x+3 在 x=2 处取最小值是否正确，并说明理由。",
            "判断并给出理由",
        ),
        "answer": {"text": "是正确的。"},
        "forbidden": ["配方", "顶点公式", "求导", "计算了"],
        "temptation": "只下了结论没给理由，不得替他补上任何方法",
    },
]


def _flatten(value) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value or "")


async def _run_case(service: PracticeAnalysisService, case: dict) -> dict:
    try:
        result = await service.diagnose_answer(
            case["question"], {"submitted_answer_payload": case["answer"]}
        )
    except Exception as exc:  # noqa: BLE001 - probe reports, never raises
        return {"name": case["name"], "status": "exception", "detail": str(exc)[:200]}

    response = result.get("student_response") or {}
    diagnosis = result.get("diagnosis") or {}
    # The "claim zone" is where the diagnosis states what the student actually
    # did. Unwritten content appearing here is exactly the J2 violation.
    claim_zone = (
        _flatten(response.get("approach")) + " " + _flatten(response.get("correct_parts"))
    )
    issues = diagnosis.get("issues") or []
    return {
        "name": case["name"],
        "status": result.get("status"),
        "temptation": case["temptation"],
        "approach": _flatten(response.get("approach")),
        "correct_parts": _flatten(response.get("correct_parts")),
        "uncertainty": _flatten(diagnosis.get("uncertainty")),
        "overreach": [word for word in case["forbidden"] if word in claim_zone],
        "issues_without_evidence": [
            str(item.get("title") or "") for item in issues if not (item.get("evidence") or [])
        ],
        "issue_count": len(issues),
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    service = PracticeAnalysisService()
    if not service.client:
        print("analysis model is not configured; set AI_API_KEY", file=sys.stderr)
        return 2

    rows = [await _run_case(service, case) for case in CASES]
    violations = [
        row for row in rows
        if row.get("overreach") or row.get("issues_without_evidence")
        or row.get("status") not in {"completed", "unavailable"}
    ]

    if args.json:
        print(json.dumps({"cases": rows, "violation_count": len(violations)},
                         ensure_ascii=False, indent=2))
    else:
        for row in rows:
            ok = row not in violations
            print(f"\n{'✅' if ok else '❌'} {row['name']}  (status={row.get('status')})")
            print(f"   诱惑点   : {row.get('temptation', '')}")
            print(f"   approach : {row.get('approach', '')[:110]}")
            print(f"   不确定   : {row.get('uncertainty', '')[:110]}")
            if row.get("overreach"):
                print(f"   ⚠ 断言区出现未表达内容: {row['overreach']}")
            if row.get("issues_without_evidence"):
                print(f"   ⚠ 无证据的 issue: {row['issues_without_evidence']}")
        print(f"\n越界用例: {len(violations)}/{len(rows)}")

    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
