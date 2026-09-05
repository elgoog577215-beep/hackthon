"""Shared draft syntax and exact source selection; no page lowering."""
from typing import Literal
from pydantic import Field
from ppt_teaching_content import Contract
from ppt_source_quotes import resolve_quote_choice

class QuoteChoice(Contract):
    quote_id: str = ""
    block_id: str = ""
    quote: str = ""


class DraftRelation(Contract):
    source_key: str
    target_key: str
    kind: Literal["sequence", "causal", "parent_child", "association"]
    label: str = ""
    condition_keys: list[str] = Field(default_factory=list)
    sources: list[QuoteChoice] = Field(min_length=1)


class DraftMetadata(Contract):
    layout_id: str = ""
    title: str = Field(min_length=1, max_length=60)
    page_goal: str = Field(min_length=1)
    primary_claim: str = ""
    audience_question: str = ""
    audience_action: str = ""
    expected_response: str = ""
    observable_evidence: str = ""
    transition: str = ""
    composition_notes: str = ""


def lower_reveal_states(stages, notes):
    """Before confirmation, merge identical canvases and keep all narration."""
    if max(stages.values()) > len(notes):
        raise ValueError(f"reveal_note_missing: show_from_by_element={stages}, notes={len(notes)}; "
                         "provide the teaching note for every declared reveal step")
    states = []
    for index, note in enumerate(notes, 1):
        visible = [key for key, stage in stages.items() if stage <= index]
        if not visible:
            raise ValueError("initial_reveal_empty: at least one screen element must show from step 1")
        if states and states[-1]["visible_element_ids"] == visible:
            states[-1]["teaching_note"] += "\n\n" + note
        else:
            states.append({"state_id": f"step-{index}", "visible_element_ids": visible,
                           "emphasized_element_ids": [], "teaching_note": note})
    return states


def bind_choices(choices, sources, *, owner, exact_text=None):
    ranges = []
    for choice in choices:
        source, quote, start = resolve_quote_choice(choice, sources)
        if exact_text is not None and len(choices) == 1 and exact_text in quote:
            start += quote.index(exact_text)
            quote = exact_text
        ranges.append({"block_id": source["block_id"], "block_revision": source["block_revision"],
                       "start": start, "end": start + len(quote), "quote": quote})
    return ranges


def draft_element_text(item, sources):
    if item.use_source_text or (not item.text and item.kind in {"formula", "code", "quote", "data"}):
        if len(item.sources) != 1:
            raise ValueError(f"selected_artifact_requires_one_source_quote:{item.key}: kind={item.kind}, "
                             f"quote_ids={[s.quote_id for s in item.sources]}; select exactly one quote for this artifact. "
                             "Separate independent formulas into separate elements; ordinary explanations use kind=text with explicit text and supporting sources.")
        return resolve_quote_choice(item.sources[0], sources)[1]
    if not item.text.strip():
        raise ValueError(f"screen_element_text_missing:{item.key}: provide concise text; "
                         "for an exact source artifact set use_source_text=true with one quote_id")
    return item.text
