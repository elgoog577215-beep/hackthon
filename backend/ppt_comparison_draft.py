"""Compact model response lowered into the sole formal page manuscript.

The model owns text, source choices, identities and reveal order. The compiler
only assigns IDs and expands repeated references; it never fills missing cells.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from ppt_teaching_content import Contract, PageTeachingV2
from ppt_draft_common import QuoteChoice, DraftRelation, bind_choices, draft_element_text




class DraftElement(Contract):
    key: str = ""
    text: str = ""
    use_source_text: bool = False
    kind: Literal["text", "formula", "code", "quote", "data", "image"] = "text"
    sources: list[QuoteChoice] = Field(min_length=1)
    show_from: int = Field(default=1, ge=1, le=12)
    role: Literal["label", "condition", "evidence", "question", "answer", "claim"] = "evidence"
    asset_id: str = ""
    asset_digest: str = ""
    answers_question_id: str = ""




class DraftIdentity(DraftElement):
    key: str = Field(min_length=1)


class DraftCell(Contract):
    subject_key: str
    dimension_key: str
    content: list[DraftElement] = Field(min_length=1, max_length=4)


class ComparisonPageDraft(Contract):
    expression_kind: Literal["comparison"] = "comparison"
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
    conditions: list[DraftElement] = Field(min_length=1, max_length=2)
    subjects: list[DraftIdentity] = Field(min_length=2, max_length=4)
    dimensions: list[DraftIdentity] = Field(min_length=1, max_length=4)
    cells: list[DraftCell] = Field(min_length=2, max_length=16)
    screen_question: DraftElement | None = None
    conclusion: DraftElement | None = None
    reveal_notes: list[str] = Field(min_length=1, max_length=12)
    relations: list[DraftRelation] = Field(default_factory=list, max_length=24)


def lower_comparison_draft(value, sources):
    draft = ComparisonPageDraft.model_validate(value)
    elements, stages = [], {}
    subject_ids, dimension_ids, keys = {}, {}, {}

    def element(key, item, role="evidence", subject_id="", dimension_id=""):
        if item.key:
            if item.key in keys:
                raise ValueError(f"comparison_element_key_duplicate:{item.key}")
            keys[item.key] = key
        text = draft_element_text(item, sources)
        ranges = bind_choices(item.sources, sources, owner=key,
                              exact_text=text if item.kind in {"formula", "code", "quote", "data"} else None)
        elements.append({"element_id": key, "text": text, "kind": item.kind, "role": role,
                         "sources": ranges, "subject_id": subject_id, "dimension_id": dimension_id,
                         "answers_question_id": item.answers_question_id,
                         "asset_id": item.asset_id, "asset_digest": item.asset_digest})
        stages[key] = item.show_from
        return key

    conditions = [element(f"condition-{i}", item, "condition") for i, item in enumerate(draft.conditions)]
    subjects, dimensions, cells = [], [], []
    for index, item in enumerate(draft.subjects):
        if item.key in subject_ids:
            raise ValueError("comparison_subject_duplicate")
        key = subject_ids[item.key] = f"subject-{index}"
        subjects.append({"subject_id": key, "label_element_id": element(key, item, "label", subject_id=key)})
    for index, item in enumerate(draft.dimensions):
        if item.key in dimension_ids:
            raise ValueError("comparison_dimension_duplicate")
        key = dimension_ids[item.key] = f"dimension-{index}"
        dimensions.append({"dimension_id": key, "label_element_id": element(key, item, "label", dimension_id=key)})
    # Shared conditions and headers are fixed comparison context. Their
    # visibility is part of this draft compiler's layout policy; only cells,
    # questions and conclusions have model-planned reveal timing.
    for key in stages:
        stages[key] = 1
    for index, cell in enumerate(draft.cells):
        if cell.subject_key not in subject_ids or cell.dimension_key not in dimension_ids:
            raise ValueError("comparison_cell_identity_unknown")
        subject_id, dimension_id = subject_ids[cell.subject_key], dimension_ids[cell.dimension_key]
        ids = [element(f"cell-{index}-{i}", item, item.role, subject_id=subject_id, dimension_id=dimension_id) for i, item in enumerate(cell.content)]
        cells.append({"subject_id": subject_id, "dimension_id": dimension_id, "element_ids": ids})
    prompt = [element("question", draft.screen_question, "question")] if draft.screen_question else []
    conclusion = [element("conclusion", draft.conclusion, "answer" if draft.conclusion.role == "answer" else "claim")] if draft.conclusion else []
    for item in elements:
        if item["answers_question_id"]:
            if item["answers_question_id"] not in keys:
                raise ValueError(f"answer_question_key_unknown:{item['answers_question_id']}")
            item["answers_question_id"] = keys[item["answers_question_id"]]
    relations = []
    for i, relation in enumerate(draft.relations):
        if not {relation.source_key, relation.target_key, *relation.condition_keys} <= set(keys):
            raise ValueError("comparison_relation_key_unknown")
        relations.append({"relation_id": f"relation-{i}", "source_id": keys[relation.source_key],
                          "target_id": keys[relation.target_key], "kind": relation.kind, "label": relation.label,
                          "condition_element_ids": [keys[k] for k in relation.condition_keys],
                          "sources": bind_choices(relation.sources, sources, owner=f"relation-{i}")})
    if max(stages.values()) != len(draft.reveal_notes):
        raise ValueError(f"reveal_notes_count_must_match_last_show_from: max show_from={max(stages.values())}, notes={len(draft.reveal_notes)}; each page part needs its own notes, exactly one per step; remove unused trailing steps or assign the intended element to that step")
    dispositions = []
    for block_id in sources:
        ids = [e["element_id"] for e in elements if any(s["block_id"] == block_id for s in e["sources"])]
        dispositions.append({"block_id": block_id, "purpose": "screen" if ids else "notes", "element_ids": ids,
                             "reason": "本页引用的条件与比较信息列在屏幕元素中，完整原文保留在备注。"})
    content = PageTeachingV2.model_validate({"elements": elements,
        "expression": {"kind": "comparison", "subjects": subjects, "dimensions": dimensions, "cells": cells,
                       "condition_element_ids": conditions, "prompt_element_ids": prompt, "conclusion_element_ids": conclusion,
                       "relations": relations},
        "must_show": list(stages),
        "source_dispositions": dispositions,
        "states": [{"state_id": f"step-{i}", "visible_element_ids": [key for key, stage in stages.items() if stage <= i],
                    "emphasized_element_ids": [], "teaching_note": note}
                   for i, note in enumerate(draft.reveal_notes, 1)]})
    metadata = draft.model_dump(mode="json", exclude={"expression_kind", "conditions", "subjects", "dimensions", "cells", "screen_question", "conclusion", "reveal_notes", "relations"})
    return {**metadata, "teaching": content.model_dump(mode="json")}
