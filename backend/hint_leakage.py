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


__all__ = [
    "MAX_REPRODUCED_STEP_RATIO",
    "STEP_REPRODUCED_AT",
    "coverage_ratio",
    "measure_deepest_hint_overlap",
]
