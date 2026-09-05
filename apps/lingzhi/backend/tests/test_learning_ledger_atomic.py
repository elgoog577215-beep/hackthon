"""Atomicity coverage for the remaining high-risk generic ledgers."""

from __future__ import annotations

import multiprocessing
from pathlib import Path
from unittest.mock import patch

import pytest

import learning_events
import learning_governance
import storage as storage_module
from storage import Storage


def _append_fact(data_dir: str, record_id: str) -> None:
    worker_storage = Storage(data_dir=data_dir)
    learning_events.storage = worker_storage
    learning_events.record_learning_event(
        event_type="learning_record_created",
        user_id="learner-1",
        course_id="course-1",
        source="atomic-test",
        record_id=record_id,
        idempotency_key=record_id,
    )


def _append_receipt(data_dir: str, receipt_id: str) -> None:
    worker_storage = Storage(data_dir=data_dir)
    learning_governance.storage = worker_storage
    learning_governance._append_receipt({
        "receipt_id": receipt_id,
        "schema_version": learning_governance.SCHEMA_VERSION,
        "scope": "learner",
        "user_id": "learner-1",
        "deleted_event_count": 0,
        "deleted_events": [],
        "invalidated_projections": [],
        "aggregated_not_reverted": [],
    })


def _delete_fact(data_dir: str, event_id: str) -> None:
    worker_storage = Storage(data_dir=data_dir)
    learning_governance.storage = worker_storage
    learning_governance.delete_learning_facts(
        user_id="learner-1",
        scope="event",
        event_id=event_id,
    )


def _run_workers(target, data_dir: Path, identities: list[str]) -> None:
    context = multiprocessing.get_context("spawn")
    workers = [
        context.Process(target=target, args=(str(data_dir), identity))
        for identity in identities
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=20)
        assert worker.exitcode == 0


def test_learning_fact_appends_are_cross_process_atomic(tmp_path: Path) -> None:
    Storage(data_dir=str(tmp_path)).save_data(
        learning_events.LEARNING_EVENTS_FILE,
        [{"event_id": "legacy", "event_type": "legacy_fact"}],
    )

    _run_workers(_append_fact, tmp_path, ["record-a", "record-b"])

    stored = Storage(data_dir=str(tmp_path)).load_data(
        learning_events.LEARNING_EVENTS_FILE
    )
    assert {item["event_id"] for item in stored if "event_id" in item} >= {"legacy"}
    assert {item.get("record_id") for item in stored} >= {"record-a", "record-b"}


def test_deletion_receipt_appends_are_cross_process_atomic(tmp_path: Path) -> None:
    Storage(data_dir=str(tmp_path)).save_data(
        learning_governance.DELETION_RECEIPTS_FILE,
        [{"receipt_id": "legacy", "scope": "learner"}],
    )

    _run_workers(_append_receipt, tmp_path, ["receipt-a", "receipt-b"])

    stored = Storage(data_dir=str(tmp_path)).load_data(
        learning_governance.DELETION_RECEIPTS_FILE
    )
    assert {item["receipt_id"] for item in stored} == {
        "legacy",
        "receipt-a",
        "receipt-b",
    }


def test_fact_delete_does_not_overwrite_concurrent_append(tmp_path: Path) -> None:
    Storage(data_dir=str(tmp_path)).save_data(
        learning_events.LEARNING_EVENTS_FILE,
        [{
            "event_id": "remove-me",
            "event_type": "legacy_fact",
            "user_id": "learner-1",
        }],
    )
    context = multiprocessing.get_context("spawn")
    workers = [
        context.Process(target=_delete_fact, args=(str(tmp_path), "remove-me")),
        context.Process(target=_append_fact, args=(str(tmp_path), "keep-me")),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=20)
        assert worker.exitcode == 0

    stored = Storage(data_dir=str(tmp_path)).load_data(
        learning_events.LEARNING_EVENTS_FILE
    )
    assert {item.get("event_id") for item in stored} != {"remove-me"}
    assert {item.get("record_id") for item in stored} == {"keep-me"}


def test_learning_fact_replace_failure_preserves_ledger_and_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger_storage = Storage(data_dir=str(tmp_path))
    original = [{"event_id": "stable", "event_type": "legacy_fact"}]
    ledger_storage.save_data(learning_events.LEARNING_EVENTS_FILE, original)
    monkeypatch.setattr(learning_events, "storage", ledger_storage)

    with patch.object(storage_module.os, "replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            learning_events.record_learning_event(event_type="new_fact")

    assert ledger_storage.load_data(learning_events.LEARNING_EVENTS_FILE) == original


def test_learning_fact_delete_failure_preserves_ledger_and_skips_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger_storage = Storage(data_dir=str(tmp_path))
    original = [{
        "event_id": "stable",
        "event_type": "legacy_fact",
        "user_id": "learner-1",
    }]
    ledger_storage.save_data(learning_events.LEARNING_EVENTS_FILE, original)
    monkeypatch.setattr(learning_governance, "storage", ledger_storage)

    with patch.object(storage_module.os, "replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            learning_governance.delete_learning_facts(
                user_id="learner-1",
                scope="event",
                event_id="stable",
            )

    assert ledger_storage.load_data(learning_events.LEARNING_EVENTS_FILE) == original
    assert ledger_storage.load_data(
        learning_governance.DELETION_RECEIPTS_FILE
    ) is None


def test_deletion_receipt_failure_preserves_ledger_and_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger_storage = Storage(data_dir=str(tmp_path))
    original = [{"receipt_id": "stable", "scope": "learner"}]
    ledger_storage.save_data(
        learning_governance.DELETION_RECEIPTS_FILE,
        original,
    )
    monkeypatch.setattr(learning_governance, "storage", ledger_storage)

    with patch.object(storage_module.os, "replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            _append_receipt(str(tmp_path), "new-receipt")

    assert ledger_storage.load_data(
        learning_governance.DELETION_RECEIPTS_FILE
    ) == original
