"""Compact source choices compiled to the existing formal teaching manuscript.

Only the model supplies teaching content and relationships. Stable references,
source offsets and cumulative reveal sets are mechanical compiler work.
"""
from typing import Literal

from pydantic import Field

from ppt_draft_common import DraftMetadata, DraftRelation, QuoteChoice, bind_choices, draft_element_text
from ppt_teaching_content import Contract, PageTeachingV2




class PageDraftElement(Contract):
    key: str = Field(min_length=1, max_length=100)
    text: str = ""
    use_source_text: bool = False
    kind: Literal["text", "formula", "code", "quote", "data", "image"] = "text"
    role: Literal["label", "condition", "evidence", "question", "answer", "claim"] = "evidence"
    sources: list[QuoteChoice] = Field(min_length=1)
    show_from: int = Field(default=1, ge=1, le=12)
    answers_question_id: str = ""
    asset_id: str = ""
    asset_digest: str = ""


class TeachingPageDraft(DraftMetadata):
    expression_kind: Literal["process", "causal", "hierarchy", "concept", "problem", "derivation", "exercise", "recap", "cover", "agenda", "evidence"]
    elements: list[PageDraftElement] = Field(min_length=1, max_length=80)
    relations: list[DraftRelation] = Field(default_factory=list, max_length=24)
    reveal_notes: list[str] = Field(min_length=1, max_length=12)






def lower_teaching_draft(value, sources):
    draft = TeachingPageDraft.model_validate(value)
    elements = []
    stages = {}
    for item in draft.elements:
        if item.key in stages:
            raise ValueError(f"element_id_duplicate:{item.key}")
        stages[item.key] = item.show_from
        text = draft_element_text(item, sources)
        elements.append({"element_id": item.key, "text": text, "kind": item.kind, "role": item.role,
                         "answers_question_id": item.answers_question_id,
                         "asset_id": item.asset_id, "asset_digest": item.asset_digest,
                         "sources": bind_choices(item.sources, sources, owner=item.key,
                             exact_text=text if item.kind in {"formula", "code", "quote", "data"} else None)})
    if max(stages.values()) != len(draft.reveal_notes):
        raise ValueError("reveal_notes_count_must_match_last_show_from")
    if draft.expression_kind in {"concept", "process", "causal", "hierarchy"}:
        endpoints = {key for r in draft.relations for key in (r.source_key, r.target_key)}
        # A claim may itself be a graph node. Teaching role does not override
        # the model's explicit relation endpoints or decide their placement.
        expression = {"kind": draft.expression_kind,
            "node_element_ids": [e.key for e in draft.elements if e.key in endpoints or e.role not in {"condition", "claim"}],
            "condition_element_ids": [e.key for e in draft.elements if e.role == "condition" and e.key not in endpoints],
            "conclusion_element_ids": [e.key for e in draft.elements if e.role == "claim" and e.key not in endpoints],
            "relations": [{"relation_id": f"relation-{i}", "source_id": r.source_key, "target_id": r.target_key,
                           "kind": r.kind, "label": r.label, "condition_element_ids": r.condition_keys,
                           "sources": bind_choices(r.sources, sources, owner=f"relation-{i}")}
                          for i, r in enumerate(draft.relations)]}
    else:
        if draft.relations:
            raise ValueError(f"linear_expression_cannot_discard_relations:{draft.expression_kind}: "
                             "set relations=[] for linear pages. Instruction order uses element order/show_from, "
                             "not graph edges such as display/ask. Use a graph expression/layout for actual conceptual relationships.")
        expression = {"kind": draft.expression_kind, "ordered_element_ids": list(stages)}
    dispositions = []
    for block_id in sources:
        ids = [e["element_id"] for e in elements if any(s["block_id"] == block_id for s in e["sources"])]
        dispositions.append({"block_id": block_id, "purpose": "screen" if ids else "notes", "element_ids": ids,
                             "reason": "屏幕保留本页教学表达所引用的内容，完整原文保存在备注。"})
    content = PageTeachingV2.model_validate({"elements": elements, "expression": expression,
        "must_show": list(stages), "source_dispositions": dispositions,
        "states": [{"state_id": f"step-{i}", "visible_element_ids": [key for key, stage in stages.items() if stage <= i],
                    "teaching_note": note} for i, note in enumerate(draft.reveal_notes, 1)]})
    metadata = draft.model_dump(mode="json", exclude={"expression_kind", "elements", "relations", "reveal_notes"})
    return {**metadata, "teaching": content.model_dump(mode="json")}
