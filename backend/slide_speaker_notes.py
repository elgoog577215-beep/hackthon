"""Exact speaker-note serialization for both V6 exporters."""
from __future__ import annotations
import json
from slide_deck_v6_models import SlidePageV6

def _speaker_notes(page: SlidePageV6) -> str:
    sections = [
        f"source_document_revision: {page.speaker_notes.source_document_revision}",
        f"teaching_unit_id: {page.speaker_notes.teaching_unit_id}",
        "source_section_ids: " + json.dumps(
            page.speaker_notes.source_section_ids,
            ensure_ascii=False,
        ),
    ]
    if page.speaker_notes.teaching_notes is not None:
        sections.append("讲述提示\n" + "\n\n".join(page.speaker_notes.teaching_notes))
    sections.extend(
        "\n".join([
            f"[{block.block_id} @ {block.block_revision}]",
            f"source_kind: {block.source_kind}",
            f"asset_refs: {json.dumps(block.asset_refs, ensure_ascii=False)}",
            block.full_text,
            f"source_payload: {json.dumps(block.source_payload, ensure_ascii=False, sort_keys=True)}",
        ])
        for block in page.speaker_notes.source_blocks
    )
    return "\n\n".join(sections)
