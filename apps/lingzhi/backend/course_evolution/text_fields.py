"""Editable prose shared by exact search, candidate generation and review.

This is a disposable projection of the owning asset, never a second body.
Identifiers, enum values and source contracts are not editable prose.
"""

from copy import deepcopy
from typing import Any

PROSE_FIELDS = frozenset(
    {
        "title",
        "name",
        "content",
        "text",
        "markdown",
        "summary",
        "content_summary",
        "teacher_activity",
        "student_activity",
        "expected_output",
        "purpose",
        "learning_objective",
        "learning_objectives",
        "learning_focus",
        "key_message",
        "subtitle",
        "question",
        "prompt",
        "stem",
        "answer",
        "explanation",
        "speaker_notes",
        "description",
        "requirements",
        "objectives",
        "goals",
        "key_points",
        "difficult_points",
        "teaching_focus",
        "teaching_difficulty",
        "activity",
        "activities",
        "instructions",
        "instruction",
        "deliverable",
        "assessment",
        "assessment_method",
        "assessment_criteria",
        "feedback",
        "transition",
        "opening",
        "closing",
        "notes",
        "label",
        "key_difficulties",
        "in_class_checks",
        "homework",
        "teaching_notes",
        "statement",
        "teaching_purpose",
        "teaching_guidance",
        "knowledge_names",
        "deliverables",
        "example",
        "examples",
        "boundary",
        "boundaries",
        "misconceptions",
        "learning_outcomes",
        "assessment_evidence",
    }
)
PROTECTED_FIELDS = frozenset(
    {
        "id",
        "schema_version",
        "source_refs",
        "sources",
        "material_asset_ids",
        "url",
        "urls",
        "href",
        "quality_report",
        "artifact_contract",
        "source_bindings",
        "source_snapshot",
        "source_plan_context",
        "metadata",
    }
)


def _protected(key: str) -> bool:
    return (
        key in PROTECTED_FIELDS or key.endswith(("_id", "_ids")) or "revision" in key or key.endswith(("_refs", "_url"))
    )


def editable_text_fields(value: Any, *, key: str = "", path: str = "") -> dict[str, str]:
    if _protected(key):
        return {}
    if isinstance(value, str):
        return {path: value} if key in PROSE_FIELDS and value else {}
    if isinstance(value, list):
        return {
            p: text
            for i, item in enumerate(value)
            for p, text in editable_text_fields(item, key=key, path=f"{path}/{i}").items()
        }
    if isinstance(value, dict):
        return {
            p: text
            for child, item in value.items()
            for p, text in editable_text_fields(item, key=str(child), path=f"{path}/{child}").items()
        }
    return {}


def replace_editable_text(value: Any, before: str, after: str, *, key: str = "") -> tuple[Any, int]:
    if _protected(key):
        return deepcopy(value), 0
    if isinstance(value, str):
        if key not in PROSE_FIELDS or not before:
            return value, 0
        return value.replace(before, after), value.count(before)
    if isinstance(value, list):
        pairs = [replace_editable_text(item, before, after, key=key) for item in value]
        return [item for item, _ in pairs], sum(count for _, count in pairs)
    if isinstance(value, dict):
        pairs = {child: replace_editable_text(item, before, after, key=str(child)) for child, item in value.items()}
        return {child: item for child, (item, _) in pairs.items()}, sum(count for _, count in pairs.values())
    return value, 0


def readable_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return "\n\n".join(editable_text_fields(value).values())
