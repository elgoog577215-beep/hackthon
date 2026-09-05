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
            raise ValueError("selected_artifact_requires_one_source_quote")
        return resolve_quote_choice(item.sources[0], sources)[1]
    if not item.text.strip():
        raise ValueError("screen_element_text_missing")
    return item.text

