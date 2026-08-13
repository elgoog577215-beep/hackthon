"""Stepwise answers: normalization and per-step judgement (J3).

Students previously submitted exactly one `answer_payload`.  Process evaluation
needs more than that — it needs to see *where* in a derivation the student went
wrong, not just that the final text fell short of the rubric.

The data shape is an additive extension of the existing payload rather than a new
top-level field or a schema bump:

    {"steps": [{"step_index": 1, "step_id": "s1", "text": "..."}, ...],
     "text": "..."}

Three properties this buys, all load-bearing:

1. **Old attempts need no migration.**  A payload without ``steps`` simply is not
   stepwise, and the repository already stores arbitrary nested values.
2. **The degradation path is free.**  Missing/empty ``steps`` falls straight back
   to whole-answer grading — a student who does not want to work step by step is
   never forced to, which is a hard requirement.
3. **No parallel source of truth.**  There is still exactly one answer payload.

Evidence strength is *deliberately not* affected by stepwise submission: working
step by step is a form of expression, not a form of assistance.  A student gains
no help by showing their work, so penalising them for it would be perverse.  The
existing `_support_level` / `evidence_strength` accounting (hints, AI support,
solution reveal) remains the only thing that discounts evidence.
"""

from __future__ import annotations

from typing import Any


MAX_STEPS = 20
MAX_STEP_TEXT = 5000
# A derivation needs at least this many reference steps before splitting it into
# separate boxes helps rather than just adding clicks.
MIN_STEPS_TO_OFFER = 2


def derive_stepwise_capability(
    *,
    input_mode: str,
    reference_step_count: int,
    existing: Any = None,
) -> bool:
    """Decide whether one question should *offer* stepwise answering.

    Deterministic and shared by both contract paths (`assessment_compiler` for
    compiled v2 items, `practice_contracts` for legacy/asset-backed ones) so a
    question cannot offer stepwise on one path and not the other.

    An explicit `existing` True is honoured — authors may turn it on deliberately
    — but it is never inferred for choice items, which have no derivation to
    split. This is an offer, never a requirement: answering as a whole always
    remains available.
    """
    if existing is True:
        return True
    if input_mode in {"choice", ""}:
        return False
    return reference_step_count >= MIN_STEPS_TO_OFFER


def stepwise_enabled(question: dict[str, Any]) -> bool:
    """Whether the question offers stepwise submission.

    Off by default: enabling stepwise answering per question is a pedagogical
    decision, not something to impose on every item in the bank.
    """
    contract = question.get("input_contract") or {}
    return bool(contract.get("stepwise"))


def extract_steps(answer_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize the student's submitted steps; empty means 'not stepwise'.

    Indices are renumbered contiguously from 1 rather than trusted as given.  A
    client-supplied ``step_index`` can repeat or skip (a stale draft, a hand-built
    payload, a step deleted mid-edit), and per-step verdicts are matched back by
    index — so a duplicate would silently attach the model's judgement of "step 1"
    to the wrong step.  Attributing a verdict to a step the student did not write
    is precisely what the honesty rule forbids, so position wins over the claim.
    """
    raw = (answer_payload or {}).get("steps")
    if not isinstance(raw, list):
        return []
    steps: list[dict[str, Any]] = []
    for value in raw[:MAX_STEPS]:
        if isinstance(value, dict):
            text = str(value.get("text") or value.get("content") or "").strip()
            step_id = str(value.get("step_id") or "").strip()
        else:
            text = str(value or "").strip()
            step_id = ""
        if not text:
            # A blank step is the student not having written that step yet.  It is
            # not evidence of anything, so it must not become a judged step.
            continue
        steps.append({
            # Renumbered below once blanks are dropped, so indices stay contiguous.
            "step_index": 0,
            "step_id": step_id,
            "text": text[:MAX_STEP_TEXT],
        })
    for position, step in enumerate(steps, start=1):
        step["step_index"] = position
    return steps


def reference_steps(question: dict[str, Any]) -> list[dict[str, Any]]:
    """The private reference derivation, used only as hidden grading reference."""
    spec = question.get("answer_spec") or {}
    solution = spec.get("solution_spec") or {}
    raw = (
        solution.get("steps")
        or spec.get("solution_trace")
        or question.get("result_checks")
        or []
    )
    steps: list[dict[str, Any]] = []
    for position, value in enumerate(raw[:MAX_STEPS], start=1):
        if isinstance(value, dict):
            text = str(
                value.get("action")
                or value.get("text")
                or value.get("description")
                or ""
            ).strip()
            step_id = str(value.get("step_id") or "").strip()
        else:
            text = str(value or "").strip()
            step_id = ""
        if text:
            steps.append({
                "step_index": position,
                "step_id": step_id,
                "text": text,
            })
    return steps


def merged_answer_text(answer_payload: dict[str, Any]) -> str:
    """Flatten a stepwise answer into one text so whole-answer grading still works.

    Stepwise judging never replaces the overall rubric verdict; it adds a second,
    finer-grained view.  The overall grade must therefore still see everything the
    student wrote, including any steps.
    """
    payload = answer_payload or {}
    parts: list[str] = []
    for step in extract_steps(payload):
        parts.append(f"步骤{step['step_index']}：{step['text']}")
    tail = str(payload.get("text") or "").strip()
    if tail:
        parts.append(tail)
    return "\n".join(parts)


def normalize_step_judgements(
    value: Any,
    submitted_steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sanitize model-produced per-step verdicts and bind them to real steps.

    Verdicts for steps the student never submitted are dropped: judging a step
    that was not written would be inventing reasoning the student never expressed,
    which is exactly what the diagnosis honesty rule forbids.
    """
    if not isinstance(value, list):
        return []
    by_index = {step["step_index"]: step for step in submitted_steps}
    results: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in value[:MAX_STEPS]:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("step_index"))
        except (TypeError, ValueError):
            continue
        if index not in by_index or index in seen:
            continue
        seen.add(index)
        verdict = str(item.get("verdict") or "").strip().lower()
        if verdict not in {"correct", "flawed", "unclear"}:
            # An unrecognized verdict must degrade to "unclear", never to a pass.
            verdict = "unclear"
        results.append({
            "step_index": index,
            "step_id": by_index[index]["step_id"],
            "verdict": verdict,
            "comment": str(item.get("comment") or "")[:1000],
            "evidence": str(item.get("evidence") or "")[:1000],
        })
    return sorted(results, key=lambda item: item["step_index"])


def first_flawed_step(judgements: list[dict[str, Any]]) -> int | None:
    """Index of the earliest flawed step — where the derivation first breaks."""
    for item in judgements:
        if item.get("verdict") == "flawed":
            return int(item["step_index"])
    return None


def stepwise_summary(
    submitted_steps: list[dict[str, Any]],
    judgements: list[dict[str, Any]],
) -> dict[str, Any]:
    counts = {"correct": 0, "flawed": 0, "unclear": 0}
    for item in judgements:
        counts[item["verdict"]] = counts.get(item["verdict"], 0) + 1
    return {
        "schema_version": "stepwise_judgement_v1",
        "submitted_step_count": len(submitted_steps),
        "judged_step_count": len(judgements),
        "correct_step_count": counts["correct"],
        "flawed_step_count": counts["flawed"],
        "unclear_step_count": counts["unclear"],
        "first_flawed_step_index": first_flawed_step(judgements),
        "steps": judgements,
    }


__all__ = [
    "MAX_STEPS",
    "MIN_STEPS_TO_OFFER",
    "derive_stepwise_capability",
    "extract_steps",
    "first_flawed_step",
    "merged_answer_text",
    "normalize_step_judgements",
    "reference_steps",
    "stepwise_enabled",
    "stepwise_summary",
]
