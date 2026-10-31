"""Record learning facts for record-producing flows."""
from typing import Any
from learning_events import record_learning_event

def _record_event(event_type: str, record: dict[str, Any], *, user_id: str) -> None:
    record_learning_event(
        event_type=event_type,
        actor="migration" if event_type == "legacy_learning_record_imported" else "user",
        source=f"learning_records.{record.get('origin') or 'user'}",
        user_id=user_id,
        course_id=record.get("course_id"),
        course_version_id=record.get("course_version_id"),
        node_id=record.get("node_id"),
        node_name=record.get("node_name", ""),
        objective_id=record.get("objective_id"),
        objective_revision_id=record.get("objective_revision_id"),
        record_id=record.get("record_id"),
        record_type=record.get("record_type"),
        operation_id=f"record:{record.get('record_id')}:{record.get('revision')}",
        idempotency_key=f"{event_type}:{record.get('record_id')}:{record.get('revision')}",
        entity_type="learning_record",
        entity_id=record.get("record_id"),
        entity_revision=record.get("revision"),
        evidence={
            "quote": record.get("quote", ""),
            "anchor": record.get("anchor") or {},
            "origin": record.get("origin"),
        },
        result={
            "status": record.get("status"),
            "revision": record.get("revision"),
        },
        metadata=record.get("metadata") or {},
    )
