"""K2: multi-round Socratic guidance on top of the existing ai-support endpoint.

The three-level hints already in place are compiled once and frozen with the item
revision.  They cannot react to what a student actually says.  This module adds
the missing piece: a dialogue that asks the next question based on the student's
own last reply ("你这一步用了什么条件？这个条件成立吗？").

Two hard constraints shape everything here:

1. **No answer disclosure, ever.**  Guidance is generated at request time, so it
   cannot rely on the compile-time leakage gate that protects frozen hints.  Every
   generated turn is therefore screened before it is returned, reusing the same
   overlap measurement as K1 (`hint_leakage`).  A turn that fails is replaced by a
   safe fallback question rather than being shown, retried into compliance, or
   silently trimmed — see `screen_guidance_turn`.
2. **Guidance is support, and support weakens evidence.**  Rounds feed the
   existing `ai_support_level` accounting (K3) rather than a second metric: more
   guidance means weaker evidence of independent mastery.  The escalation is
   deliberately slow — one probing question should not cost as much as revealing
   a scaffold — so level rises with round count via `support_level_for_round`.

Quality of the questioning itself is NOT self-assessed here.  Whether a follow-up
question is pedagogically good is a teaching-research judgement; this module only
enforces that it is safe and grounded.  See NOTES_TO_OWNER.md.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ai_base import AIBase
from hint_leakage import coverage_ratio, measure_deepest_hint_overlap


logger = logging.getLogger(__name__)

GUIDANCE_SCHEMA = "socratic_guidance_v1"
MAX_ROUNDS = 6
MAX_HISTORY_TURNS = 12
# A guidance turn may quote the student's own words freely, but must not restate
# the reference derivation.  This is the same signal K1 uses on frozen hints.
MAX_REFERENCE_COVERAGE = 0.6
# Bare answer values shorter than this are not acted on: a lone "1"/"B" collides
# with step indices and option labels, and blocking those makes guidance unusable.
MIN_LITERAL_ANSWER_LEN = 2


_GUIDANCE_SYSTEM_PROMPT = """
你是课程正式练习的苏格拉底式引导者。你的唯一任务是**提问**，帮助学习者自己发现
下一步，绝不替他完成推理。

严格禁止：
- 给出最终答案、关键中间结果或可直接抄写的成品；
- 复述参考解答的推导步骤（reference 是隐藏依据，只用来判断学生偏在哪里）；
- 补写学生没有表达的推理，或声称他用了某个他没写出来的方法；
- 一次问多个问题。

每一轮只提**一个**问题，针对学习者最近一条回答里**真实出现**的内容发问，
优先问"你这一步用了什么条件""这个条件在这里成立吗""你怎么检查这一步"。
若学习者的回答无法判断，就请他把某一步说得更具体，不要猜测。

只返回严格 JSON：{"question":"一个追问","focus":"这一轮在检查什么",
"student_signal":"学习者回答中你据以发问的原话片段",
"is_stuck":false,"closing":"若学习者已自行走通，写一句确认；否则留空"}
""".strip()


def support_level_for_round(round_number: int) -> int:
    """Map guidance rounds onto the existing 1–3 support scale (K3).

    Escalation is intentionally gentle: a couple of probing questions is lighter
    support than being handed a scaffold, and treating them as equivalent would
    push students away from asking at exactly the moment asking helps most.
    """
    if round_number <= 2:
        return 1
    if round_number <= 4:
        return 2
    return 3


def _reference_material(question: dict[str, Any]) -> dict[str, Any]:
    spec = question.get("answer_spec") or {}
    solution = spec.get("solution_spec") or {}
    return {
        "canonical_answer": spec.get("canonical_answer")
        or spec.get("correct_answer"),
        "solution_spec": solution,
        "legacy_answer_spec": {"correct_answer": spec.get("correct_answer")},
        "solution_graph": {"steps": solution.get("steps") or []},
    }


def _reference_texts(question: dict[str, Any]) -> list[str]:
    spec = question.get("answer_spec") or {}
    solution = spec.get("solution_spec") or {}
    texts: list[str] = []
    for step in solution.get("steps") or []:
        if isinstance(step, dict):
            value = str(
                step.get("action") or step.get("text") or step.get("description") or ""
            ).strip()
        else:
            value = str(step or "").strip()
        if value:
            texts.append(value)
    return texts


def _answer_values(question: dict[str, Any]) -> list[str]:
    """Short, literal answer values that must not appear in guidance.

    `hint_leakage` deliberately ignores answers shorter than one shingle: at
    compile time a bare "3" or "B" collides with ordinary prose far too often to
    be a usable signal.  Runtime guidance is a different bet — it is one or two
    sentences of freshly generated text aimed at a specific student, so a literal
    "-4" appearing there is overwhelmingly likely to be the answer rather than a
    coincidence.  A real leak observed under adversarial pressure ("just tell me
    the number") is what motivated this: the stored answer was the phrase
    「最小值为 -4」 while the model emitted the bare 「-4」, so phrase matching
    alone let it through.

    Single characters are excluded on purpose.  With answer "1" or "B" a perfectly
    normal turn — 「第 1 步你用了什么条件？」/「选项 B 和 C 的区别在哪里？」 —
    would be blocked, and guidance that refuses to mention step numbers or option
    labels is useless.  Those answers stay protected by the phrase-level check and
    by the reference-step check; the bare-value guard only covers values long
    enough to be unambiguous.
    """
    spec = question.get("answer_spec") or {}
    solution = spec.get("solution_spec") or {}
    values: list[str] = []
    for raw in (
        solution.get("final_answer"),
        spec.get("canonical_answer"),
        spec.get("correct_answer"),
    ):
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        values.append(text)
        # Pull the numeric core out of phrasings like 「最小值为 -4」/"answer: 50 km/h"
        # so the guard also covers the bare value the model is likely to utter.
        for token in re.findall(r"-?\d+(?:\.\d+)?", text):
            values.append(token)
    return [
        value for value in dict.fromkeys(values)
        # "".join drops the "-" of "-4"? No: len("-4") == 2, kept. A lone "4"/"B"
        # is dropped as too collision-prone to act on.
        if value and len("".join(value.split())) >= MIN_LITERAL_ANSWER_LEN
    ]


def _mentions_answer_value(text: str, question: dict[str, Any]) -> str:
    """Return the first literal answer value found in ``text``, or ""."""
    haystack = "".join(str(text or "").split())
    for value in _answer_values(question):
        needle = "".join(value.split())
        if not needle:
            continue
        # Numeric values need a digit-boundary check so "-4" does not fire on
        # "-42" or on a step index like "第 4 步".
        if re.fullmatch(r"-?\d+(?:\.\d+)?", needle):
            if re.search(rf"(?<!\d){re.escape(needle)}(?!\d)", haystack):
                return value
            continue
        if needle in haystack:
            return value
    return ""


def screen_guidance_turn(
    turn: dict[str, Any],
    question: dict[str, Any],
) -> dict[str, Any]:
    """Decide whether one generated turn is safe to show the student.

    Runtime guidance gets no compile-time gate, so this is the only thing standing
    between a chatty model and a leaked answer.  It errs toward rejection: a
    slightly unhelpful question costs far less than a disclosed solution.
    """
    text = " ".join(
        str(turn.get(field) or "")
        for field in ("question", "focus", "closing")
    ).strip()
    if not text:
        return {"safe": False, "reason": "empty_guidance"}

    overlap = measure_deepest_hint_overlap(
        [{"level": 3, "content": text}],
        _reference_material(question),
    )
    if overlap.get("reveals_final_answer"):
        return {
            "safe": False,
            "reason": "reveals_final_answer",
            "overlap": overlap,
        }
    # Catches the bare value the phrase-level check above cannot see.
    literal = _mentions_answer_value(text, question)
    if literal:
        return {
            "safe": False,
            "reason": "reveals_final_answer",
            "matched_value": literal,
            "overlap": overlap,
        }
    if overlap.get("reproduces_whole_derivation"):
        return {
            "safe": False,
            "reason": "reproduces_derivation",
            "overlap": overlap,
        }
    for reference in _reference_texts(question):
        if coverage_ratio(reference, text) > MAX_REFERENCE_COVERAGE:
            return {
                "safe": False,
                "reason": "restates_reference_step",
                "overlap": overlap,
            }
    return {"safe": True, "reason": "", "overlap": overlap}


def _fallback_turn(round_number: int) -> dict[str, Any]:
    """What the student sees when generation fails or is rejected.

    Still a question, never an answer, and honestly marked as a fallback so the
    rejection is visible in telemetry instead of looking like a normal turn.
    """
    return {
        "question": "请把你最近这一步用到的条件写出来，并说明它在这里为什么成立。",
        "focus": "让学习者自己复述所依赖的条件",
        "student_signal": "",
        "is_stuck": False,
        "closing": "",
        "round": round_number,
        "generated": False,
    }


class SocraticGuide(AIBase):
    """Generate one guidance turn per request, screened before it is returned."""

    async def next_turn(
        self,
        question: dict[str, Any],
        attempt: dict[str, Any],
        history: list[dict[str, Any]],
        student_message: str,
    ) -> dict[str, Any]:
        round_number = min(len(history) + 1, MAX_ROUNDS)
        if not self.client:
            return {
                **_fallback_turn(round_number),
                "status": "unavailable",
                "reason": "guidance_model_not_configured",
            }

        payload = {
            "question": {
                "prompt": question.get("prompt"),
                "question_type": question.get("question_type"),
                "rubric": (question.get("answer_spec") or {}).get("criteria") or [],
            },
            # The reference derivation is a hidden judging aid only; the system
            # prompt forbids restating it and screen_guidance_turn enforces that.
            "reference": {"solution_steps": _reference_texts(question)},
            "student_current_answer": attempt.get("answer_payload") or {},
            "conversation": [
                {
                    "role": str(item.get("role") or ""),
                    "text": str(item.get("text") or "")[:2000],
                }
                for item in history[-MAX_HISTORY_TURNS:]
            ],
            "student_message": student_message[:2000],
            "round": round_number,
        }
        try:
            response = await self._call_llm(
                json.dumps(payload, ensure_ascii=False),
                system_prompt=_GUIDANCE_SYSTEM_PROMPT,
                use_fast_model=False,
                retry_count=2,
                enable_thinking=False,
            )
        except Exception:
            logger.warning("socratic guidance call failed", exc_info=True)
            response = None
        parsed = self._extract_json(response or "") if response else None
        if not isinstance(parsed, dict) or not str(parsed.get("question") or "").strip():
            return {
                **_fallback_turn(round_number),
                "status": "degraded",
                "reason": "guidance_output_unusable",
            }

        turn = {
            "question": str(parsed.get("question") or "").strip()[:1000],
            "focus": str(parsed.get("focus") or "").strip()[:500],
            "student_signal": str(parsed.get("student_signal") or "").strip()[:500],
            "is_stuck": bool(parsed.get("is_stuck")),
            "closing": str(parsed.get("closing") or "").strip()[:500],
            "round": round_number,
            "generated": True,
        }
        screening = screen_guidance_turn(turn, question)
        if not screening["safe"]:
            logger.warning(
                "socratic guidance rejected by leakage screen: %s",
                screening["reason"],
            )
            return {
                **_fallback_turn(round_number),
                "status": "screened",
                "reason": screening["reason"],
            }
        return {**turn, "status": "ok", "reason": ""}


socratic_guide = SocraticGuide()


__all__ = [
    "GUIDANCE_SCHEMA",
    "MAX_ROUNDS",
    "SocraticGuide",
    "screen_guidance_turn",
    "socratic_guide",
    "support_level_for_round",
]
