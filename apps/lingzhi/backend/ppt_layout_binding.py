"""Bind model-facing semantic layout keys to one frozen template contract."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from ppt_fixed_draft import form_type
from ppt_fixed_templates import fixed_slug


def template_layout_key(layout: Any) -> str:
    return str(getattr(layout, "layout_slug", "") or fixed_slug(layout.template_layout_id))


def template_layout_bindings(template: Any, *, include_figure: bool = True) -> dict[str, str]:
    """Return unambiguous semantic key -> frozen layout ID bindings."""
    grouped: dict[str, list[str]] = {}
    for layout in template.layouts:
        key = template_layout_key(layout)
        if not include_figure and key == "figure":
            continue
        grouped.setdefault(key, []).append(str(layout.template_layout_id))
    ambiguous = sorted(key for key, values in grouped.items() if len(values) != 1)
    if ambiguous:
        raise ValueError("template_layout_key_ambiguous:" + ",".join(ambiguous))
    return {key: values[0] for key, values in grouped.items()}


def _matching_field_layout_keys(fields: Any, bindings: dict[str, str]) -> list[str]:
    if not isinstance(fields, dict):
        return []
    matches = []
    for key in bindings:
        try:
            form_type(key, authored=True).model_validate(fields)
        except (KeyError, TypeError, ValueError, ValidationError):
            continue
        matches.append(key)
    return matches


def bind_page_layout(page: dict[str, Any], template: Any) -> dict[str, Any]:
    """Resolve stable, exact, or safely inferable page layout identities."""
    candidate = deepcopy(page)
    bindings = template_layout_bindings(template)
    known_ids = set(bindings.values())
    supplied_key = str(candidate.get("layout_key") or "").strip()
    supplied_id = str(candidate.get("layout_id") or "").strip()

    if supplied_key and supplied_id:
        id_key = ""
        if supplied_id in known_ids:
            id_key = next(key for key, value in bindings.items() if value == supplied_id)
        else:
            possible_key = fixed_slug(supplied_id)
            if possible_key in bindings:
                id_key = possible_key
        if supplied_key not in bindings or id_key != supplied_key:
            safe_key = supplied_key.replace("\n", " ")[:120]
            safe_id = supplied_id.replace("\n", " ")[:120]
            raise ValueError(
                "script_ppt_layout_identity_conflict:"
                f"layout_key={safe_key};layout_id={safe_id}"
            )

    resolved = ""
    if supplied_key in bindings:
        resolved = bindings[supplied_key]
    elif supplied_id in known_ids:
        resolved = supplied_id
    elif supplied_id:
        semantic_key = fixed_slug(supplied_id)
        if semantic_key in bindings:
            resolved = bindings[semantic_key]
    if not resolved:
        matches = _matching_field_layout_keys(candidate.get("fields"), bindings)
        if len(matches) == 1:
            resolved = bindings[matches[0]]

    if resolved:
        candidate["layout_id"] = resolved
    elif supplied_key and not supplied_id:
        # Preserve the rejected value under the legacy field so the shared
        # validator reports one layout error rather than a generic shape error.
        candidate["layout_id"] = supplied_key
    candidate.pop("layout_key", None)
    return candidate


def unresolved_layout_error(block_id: str, page_index: int, page: dict[str, Any], template: Any) -> str:
    supplied = str(page.get("layout_id") or page.get("layout_key") or "").replace("\n", " ")[:120]
    allowed = ",".join(sorted(template_layout_bindings(template)))
    return (
        f"script_ppt_layout_unresolved:{block_id}:{page_index}:"
        f"supplied={supplied};allowed={allowed}"
    )
