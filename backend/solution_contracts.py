"""Projection helpers for learner-facing worked solutions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable


SOLUTION_SPEC_SCHEMA = "solution_spec_v1"


def project_solution_spec(
    solution_envelope: dict[str, Any] | None,
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project one private envelope into a stable learner-facing solution."""
    envelope = solution_envelope or {}
    fallback_answer = fallback or {}
    legacy_spec = deepcopy(
        fallback_answer.get("solution_spec")
        or (envelope.get("legacy_answer_spec") or {}).get("solution_spec")
        or {}
    )
    worked = deepcopy(envelope.get("worked_solution") or {})
    graph = envelope.get("solution_graph") or {}
    graph_steps = (
        graph.get("steps") if isinstance(graph, dict) else graph
    ) or []

    raw_steps = (
        worked.get("steps")
        or legacy_spec.get("steps")
        or graph_steps
    )
    step_details = [
        detail
        for detail in (
            _step_detail(value, position)
            for position, value in enumerate(raw_steps or [], start=1)
        )
        if detail
    ]
    steps = [
        text
        for text in (_step_text(value) for value in raw_steps or [])
        if text
    ]
    final_answer = _first_present(
        worked.get("final_answer"),
        legacy_spec.get("final_answer"),
        envelope.get("canonical_answer"),
        fallback_answer.get("canonical_answer"),
        fallback_answer.get("correct_answer"),
    )
    checks = _unique_texts(
        worked.get("checks")
        or legacy_spec.get("checks")
        or [
            step.get("check")
            for step in graph_steps
            if isinstance(step, dict)
        ]
        or envelope.get("rubric")
        or fallback_answer.get("criteria")
        or []
    )
    summary = str(
        worked.get("summary")
        or legacy_spec.get("summary")
        or ""
    ).strip()
    choice_diagnostics = (
        (envelope.get("choice_answer_spec") or {}).get(
            "choice_diagnostics"
        )
        or fallback_answer.get("choice_diagnostics")
        or {}
    )
    option_analysis = _normalize_option_analysis(
        worked.get("option_analysis")
        or legacy_spec.get("option_analysis")
        or _option_analysis_from_diagnostics(choice_diagnostics)
        or []
    )
    common_errors = _unique_texts(
        worked.get("common_errors")
        or legacy_spec.get("common_errors")
        or []
    )
    representation = deepcopy(
        worked.get("representation")
        or legacy_spec.get("representation")
    )

    return {
        "schema_version": SOLUTION_SPEC_SCHEMA,
        "summary": summary,
        "steps": steps,
        "step_details": step_details,
        "final_answer": deepcopy(final_answer),
        "checks": checks,
        "option_analysis": option_analysis,
        "common_errors": common_errors,
        "representation": representation,
    }


def worked_solution_is_complete(
    solution_envelope: dict[str, Any] | None,
    *,
    option_ids: Iterable[str] = (),
) -> bool:
    """Return whether a generated solution has a complete teaching explanation."""
    envelope = solution_envelope or {}
    worked = envelope.get("worked_solution")
    if not isinstance(worked, dict):
        return False
    projected = project_solution_spec(envelope)
    if (
        len(str(projected.get("summary") or "").strip()) < 8
        or not projected.get("steps")
        or projected.get("final_answer") in (None, "", [], {})
        or not projected.get("checks")
    ):
        return False
    canonical = envelope.get("canonical_answer")
    if (
        canonical not in (None, "", [], {})
        and projected.get("final_answer") != canonical
    ):
        return False
    generic_markers = (
        "分析题意",
        "按步骤计算",
        "检查答案",
        "定位任务目标、材料和限制条件",
        "形成规定产物",
        "执行结果、边界和依据检查",
        "a concise verifiable solution step",
    )
    if not any(
        len(str(step).strip()) >= 12
        and not any(
            marker in str(step).lower()
            for marker in generic_markers
        )
        for step in projected.get("steps") or []
    ):
        return False
    expected_options = {
        str(value).strip()
        for value in option_ids
        if str(value).strip()
    }
    if expected_options:
        analyzed = {
            str(item.get("option_id") or "").strip()
            for item in projected.get("option_analysis") or []
            if isinstance(item, dict)
            and str(item.get("explanation") or "").strip()
        }
        if not expected_options.issubset(analyzed):
            return False
    return True


def _step_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return str(value or "").strip()
    parts = _unique_texts([
        value.get("title"),
        value.get("action"),
        value.get("explanation"),
        value.get("calculation"),
        value.get("result"),
        value.get("check"),
        value.get("result_check"),
    ])
    return "；".join(parts)


def _step_detail(value: Any, position: int) -> dict[str, Any] | None:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return {
            "step_id": f"step_{position}",
            "title": f"步骤 {position}",
            "explanation": text,
        }
    if not isinstance(value, dict):
        return None
    explanation = str(
        value.get("explanation")
        or value.get("action")
        or value.get("instruction")
        or value.get("operation")
        or ""
    ).strip()
    if not explanation:
        return None
    detail = {
        "step_id": str(
            value.get("step_id") or f"step_{position}"
        ),
        "title": str(value.get("title") or f"步骤 {position}"),
        "explanation": explanation,
    }
    for field in ("calculation", "result", "check", "result_check"):
        if value.get(field) not in (None, "", [], {}):
            detail[field] = deepcopy(value[field])
    return detail


def _normalize_option_analysis(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        entries = [
            {
                "option_id": option_id,
                "explanation": explanation,
            }
            for option_id, explanation in value.items()
        ]
    elif isinstance(value, list):
        entries = value
    else:
        entries = []
    result: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        option_id = str(
            entry.get("option_id")
            or entry.get("id")
            or ""
        ).strip()
        explanation = str(
            entry.get("explanation")
            or entry.get("reason")
            or ""
        ).strip()
        if option_id and explanation:
            result.append({
                "option_id": option_id,
                "is_correct": bool(entry.get("is_correct")),
                "explanation": explanation,
            })
    return result


def _option_analysis_from_diagnostics(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    return [
        {
            "option_id": option_id,
            "is_correct": (
                isinstance(detail, dict)
                and detail.get("kind") == "correct"
            ),
            "explanation": (
                detail.get("feedback")
                if isinstance(detail, dict)
                else detail
            ),
        }
        for option_id, detail in value.items()
    ]


def _unique_texts(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


__all__ = [
    "SOLUTION_SPEC_SCHEMA",
    "project_solution_spec",
    "worked_solution_is_complete",
]
