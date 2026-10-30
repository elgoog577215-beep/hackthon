"""Stable scan identities shared by routing and recovery."""
from typing import Any
from course_document import stable_hash

def unit_fingerprint(unit: Any) -> str:
    return stable_hash({**unit.model_dump(mode="json"), "full_text_fields": unit.full_text_fields},
                       prefix="scan-unit-")


def routing_fingerprint(routing: dict) -> str:
    return stable_hash({k:routing.get(k) for k in ('contract','mode','topics','lecture_ids','selected_unit_ids','aliases')}, prefix='routing-')
