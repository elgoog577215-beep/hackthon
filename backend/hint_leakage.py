"""Overlap measurement between the deepest hint level and the private solution.

Progressive hints are *deliberately* derived from the same reasoning path as the
private solution, so sharing method vocabulary is expected and healthy — a level-3
hint that says "配方" for a completing-the-square problem is doing its job.  What
must never happen is the deepest hint handing over the solution itself: either the
final answer, or so much of the derivation that a student can transcribe it
instead of finishing the reasoning.

The pre-existing compile-time check only asked "does the final answer string
appear verbatim in a hint".  That misses the more common failure: a level-3 hint
that reproduces the whole derivation chain while carefully omitting the last
number.  This module adds the missing measurement.

The metric is character-shingle coverage, which works for Chinese (no word
boundaries), formulas and code alike:

    coverage = |shingles(step) ∩ shingles(hint)| / |shingles(step)|

A step counted as *reproduced* when its coverage crosses ``STEP_REPRODUCED_AT``.
Leakage is declared when the deepest hint reproduces the final answer, or when it
reproduces enough of the derivation to leave nothing for the student to do.
"""

from __future__ import annotations

import re
from typing import Any


SHINGLE_SIZE = 6
# A single step counts as "reproduced" once this much of it is present verbatim
# in the hint.  Below this, the hint is quoting a phrase; above it, the hint is
# restating the step.
STEP_REPRODUCED_AT = 0.75
# The deepest hint is allowed to walk the student through the derivation up to
# (but not including) the last step — that is exactly what a local scaffold does.
# Reproducing *every* step means nothing is left to derive.
MAX_REPRODUCED_STEP_RATIO = 0.99
# Bare answer values shorter than this are not acted on.  See
# `literal_answer_values` for why a single character cannot be used.
MIN_LITERAL_ANSWER_LEN = 2


def _normalize(value: Any) -> str:
    return "".join(str(value or "").split()).lower()


def _shingles(text: str, size: int = SHINGLE_SIZE) -> set[str]:
    normalized = _normalize(text)
    if not normalized:
        return set()
    if len(normalized) <= size:
        return {normalized}
    return {normalized[i:i + size] for i in range(len(normalized) - size + 1)}


def coverage_ratio(fragment: str, container: str) -> float:
    """Fraction of ``fragment`` that appears verbatim inside ``container``."""
    fragment_shingles = _shingles(fragment)
    if not fragment_shingles:
        return 0.0
    container_shingles = _shingles(container)
    if not container_shingles:
        return 0.0
    hit = fragment_shingles & container_shingles
    return len(hit) / len(fragment_shingles)


def _solution_steps(private_solution: dict[str, Any]) -> list[str]:
    """Collect the private derivation steps, whatever shape they were stored in."""
    envelope = private_solution or {}
    graph = envelope.get("solution_graph") or {}
    raw_steps = (
        (graph.get("steps") if isinstance(graph, dict) else graph)
        or (envelope.get("worked_solution") or {}).get("steps")
        or (envelope.get("legacy_answer_spec") or {}).get(
            "solution_spec", {}
        ).get("steps")
        or (envelope.get("solution_spec") or {}).get("steps")
        or []
    )
    steps: list[str] = []
    for value in raw_steps:
        if isinstance(value, dict):
            text = " ".join(
                str(value.get(field) or "")
                for field in ("action", "instruction", "description", "detail")
            ).strip()
        else:
            text = str(value or "").strip()
        if len(_normalize(text)) >= SHINGLE_SIZE:
            steps.append(text)
    return steps


def _final_answers(private_solution: dict[str, Any]) -> list[str]:
    envelope = private_solution or {}
    candidates = [
        (envelope.get("worked_solution") or {}).get("final_answer"),
        envelope.get("canonical_answer"),
        (envelope.get("legacy_answer_spec") or {}).get("correct_answer"),
        (envelope.get("legacy_answer_spec") or {}).get("canonical_answer"),
        (envelope.get("solution_spec") or {}).get("final_answer"),
    ]
    return [
        _normalize(value)
        for value in candidates
        # Answers shorter than a shingle ("3", "B") collide with ordinary prose
        # far too easily to be used as a leakage signal.
        if value is not None and len(_normalize(value)) >= SHINGLE_SIZE
    ]


def measure_deepest_hint_overlap(
    hint_levels: list[dict[str, Any]],
    private_solution: dict[str, Any],
) -> dict[str, Any]:
    """Measure how much of the private solution the deepest hint hands over."""
    levels = [level for level in hint_levels or [] if isinstance(level, dict)]
    if not levels:
        return {
            "measured": False,
            "reason": "no_hint_levels",
            "leaked": False,
        }
    deepest = max(levels, key=lambda level: int(level.get("level") or 0))
    hint_text = str(deepest.get("content") or "")
    steps = _solution_steps(private_solution)
    answers = _final_answers(private_solution)

    normalized_hint = _normalize(hint_text)
    reveals_final_answer = any(
        answer in normalized_hint for answer in answers
    )

    step_coverages = [coverage_ratio(step, hint_text) for step in steps]
    reproduced = [
        value for value in step_coverages if value >= STEP_REPRODUCED_AT
    ]
    reproduced_ratio = (
        len(reproduced) / len(step_coverages) if step_coverages else 0.0
    )
    reproduces_whole_derivation = bool(
        step_coverages and reproduced_ratio > MAX_REPRODUCED_STEP_RATIO
    )

    return {
        "measured": bool(steps or answers),
        "deepest_level": int(deepest.get("level") or 0),
        "solution_step_count": len(step_coverages),
        "reproduced_step_count": len(reproduced),
        "reproduced_step_ratio": round(reproduced_ratio, 4),
        "max_step_coverage": round(max(step_coverages), 4) if step_coverages else 0.0,
        "reveals_final_answer": reveals_final_answer,
        "reproduces_whole_derivation": reproduces_whole_derivation,
        "leaked": bool(reveals_final_answer or reproduces_whole_derivation),
    }


def literal_answer_values(question: dict[str, Any]) -> list[str]:
    """Short, literal answer values that must not appear in learner-facing text.

    ``measure_deepest_hint_overlap`` deliberately ignores answers shorter than one
    shingle: at compile time a bare "3" or "B" collides with ordinary prose far
    too often to be a usable signal.  Text generated *at request time* is a
    different bet — a sentence or two aimed at one student, where a literal "-4"
    is overwhelmingly likely to be the answer rather than a coincidence.  A real
    leak observed under adversarial pressure ("just tell me the number") is what
    motivated this: the stored answer was the phrase 「最小值为 -4」 while the
    model emitted the bare 「-4」, so phrase matching alone let it through.

    Single characters are excluded on purpose.  With answer "1" or "B" a perfectly
    normal sentence — 「第 1 步你用了什么条件？」/「选项 B 和 C 的区别在哪里？」 —
    would be blocked, and text that refuses to mention step numbers or option
    labels is useless.  Those answers stay protected by the phrase-level and
    reference-step checks; this guard only covers values long enough to be
    unambiguous.

    ``question`` is anything carrying an ``answer_spec`` — a formal task, a
    question-bank item, or a runtime practice task.
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
        # so the guard also covers the bare value a model is likely to utter.
        for token in re.findall(r"-?\d+(?:\.\d+)?", text):
            values.append(token)
    return [
        value for value in dict.fromkeys(values)
        # len("-4") == 2, kept. A lone "4"/"B" is dropped as too collision-prone.
        if value and len("".join(value.split())) >= MIN_LITERAL_ANSWER_LEN
    ]


def mentions_answer_value(text: str, question: dict[str, Any]) -> str:
    """Return the first literal answer value found in ``text``, or ""."""
    haystack = "".join(str(text or "").split())
    for value in literal_answer_values(question):
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


__all__ = [
    "MAX_REPRODUCED_STEP_RATIO",
    "MIN_LITERAL_ANSWER_LEN",
    "STEP_REPRODUCED_AT",
    "coverage_ratio",
    "literal_answer_values",
    "measure_deepest_hint_overlap",
    "mentions_answer_value",
]
