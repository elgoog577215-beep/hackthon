"""Choose classroom stops before confirmation; narration is not pagination."""
from __future__ import annotations

from ppt_teaching_content import PagePresentationV1, PageTeachingV2


def default_presentation(content):
    return PagePresentationV1(mode="question_answer" if any(e.role == "answer" for e in content.elements) else "complete")


def presentation_states(content: PageTeachingV2):
    """Legacy states stay unchanged. New policies preserve all original notes."""
    policy = content.presentation
    if policy is None:
        return content.states
    elements = {e.element_id for e in content.elements}
    answers = {e.element_id for e in content.elements if e.role == "answer"}
    if policy.mode in {"complete", "question_answer"}:
        last = content.states[-1]
        if set(last.visible_element_ids) != elements:
            raise ValueError("presentation_complete_state_missing: non-cumulative views require explicit key_steps")
        if policy.mode == "complete":
            if answers:
                raise ValueError("presentation_answer_requires_separation")
            selected = [last]
        else:
            if not answers:
                raise ValueError("presentation_question_answer_missing")
            question = last.model_copy(update={"state_id": "question", "visible_element_ids": [e for e in last.visible_element_ids if e not in answers],
                "emphasized_element_ids": [], "teaching_note": "先独立作答，再核对答案。"})
            selected = [question, last.model_copy(update={"state_id": "answer"})]
    else:
        ids = [s.state_id for s in content.states]
        selected_ids = [c.state_id for c in policy.checkpoints]
        if (not selected_ids or len(set(selected_ids)) != len(selected_ids)
                or any(s not in ids for s in selected_ids)
                or selected_ids != sorted(selected_ids, key=ids.index)):
            raise ValueError("presentation_checkpoint_order_invalid")
        selected = [content.states[ids.index(key)] for key in selected_ids]
    # One source of truth for visible coverage, conditions and answer order.
    payload = content.model_dump(mode="json")
    payload["states"] = [s.model_dump(mode="json") for s in selected]
    PageTeachingV2.model_validate(payload)
    result = []
    for state in selected:
        signature = (frozenset(state.visible_element_ids), frozenset(state.emphasized_element_ids))
        if result and signature == (frozenset(result[-1].visible_element_ids), frozenset(result[-1].emphasized_element_ids)):
            continue
        result.append(state)
    return result


def validate_page_sources(graph, source_ids, anchor):
    """Source units own evidence, not page boundaries; keep a stable anchor."""
    if not source_ids or len(source_ids) != len(set(source_ids)):
        raise ValueError("teaching_page_sources_invalid")
    order = list(dict.fromkeys(b for u in graph.units for b in u.primary_block_ids))
    owner = {b: u.teaching_unit_id for u in graph.units for b in u.primary_block_ids}
    if any(b not in owner for b in source_ids) or owner[source_ids[0]] != anchor:
        raise ValueError("teaching_unit_source_mismatch")
    indices = [order.index(b) for b in source_ids]
    if indices != list(range(indices[0], indices[0] + len(indices))):
        raise ValueError("teaching_page_sources_not_contiguous")


PACING_ISSUE_CODES = {"ppt_pacing_budget_exceeded", "ppt_pacing_duplicate_canvas"}

