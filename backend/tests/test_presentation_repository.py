from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from course_document import document_from_legacy_course
from presentation_models import (
    ArtifactReceipt,
    DeckProposal,
    DeckRevision,
    GenerationWorkingSnapshot,
    PresentationDeck,
    PresentationEvent,
    PresentationScope,
    QualityReport,
    Slide,
)
from presentation_repository import (
    ArtifactAccessError,
    IdempotencyKeyReuseConflict,
    PresentationRepository,
    PresentationRepositoryConflict,
    StaleRevisionConflict,
)
from presentation_source import project_presentation_source, source_packet, validate_source_snapshot


def _course() -> dict:
    legacy = {
        "course_id": "course-1",
        "course_name": "C语言",
        "current_course_version_id": "cv3",
        "learning_asset_bundle_revision_id": "lab3",
        "course_blueprint": {
            "positioning": "从内存模型理解指针",
            "nodes": [
                {"node_id": "chapter-1", "title": "第一章"},
                {"node_id": "section-1", "title": "指针"},
                {"node_id": "section-2", "title": "数组"},
            ],
        },
        "nodes": [
            {
                "node_id": "chapter-1",
                "parent_node_id": "root",
                "node_name": "第一章",
                "node_level": 1,
                "node_content": "",
            },
            {
                "node_id": "section-1",
                "parent_node_id": "chapter-1",
                "node_name": "指针",
                "node_level": 2,
                "learning_objective": "解释地址和值的关系",
                "objective_id": "obj-pointer",
                "node_content": "## 核心概念\n\n指针保存地址。",
                "content_blocks": [{
                    "block_id": "block-pointer",
                    "type": "concept",
                    "title": "核心概念",
                    "content": "指针保存地址。",
                    "metadata": {"asset_refs": ["asset-pointer"]},
                }],
            },
            {
                "node_id": "section-2",
                "parent_node_id": "root",
                "node_name": "数组",
                "node_level": 2,
                "learning_objective": "理解数组",
                "objective_id": "obj-array",
                "node_content": "数组正文",
            },
        ],
        "learning_assets": {
            "questions": [
                {"question_id": "q-pointer", "node_id": "section-1", "prompt": "&x 是什么？"},
                {"question_id": "q-array", "node_id": "section-2", "prompt": "数组长度？"},
            ],
            "misconceptions": [
                {"misconception_id": "m-pointer", "node_id": "section-1", "text": "空指针等于0地址"},
            ],
            "media": [
                {"asset_id": "asset-pointer", "node_id": "section-2", "url": "asset://pointer"},
                {"asset_id": "asset-array", "node_id": "section-2", "url": "asset://array"},
            ],
        },
    }
    document = document_from_legacy_course(legacy)
    canonical = deepcopy(legacy)
    canonical.pop("nodes")
    canonical.update({
        "course_schema_version": "course_document_v1",
        "course_document_authoritative": True,
        "course_document_revision": document.document_revision,
        "course_document": document.model_dump(mode="json"),
    })
    return canonical


def _deck_and_snapshot():
    snapshot, source_ref = project_presentation_source(
        _course(), PresentationScope(type="chapter", section_ids=["chapter-1"])
    )
    deck = PresentationDeck(
        deck_id="deck-1",
        course_id="course-1",
        title="指针课件",
        source_ref=source_ref,
        scope=PresentationScope(type="chapter", section_ids=["chapter-1"]),
        template_id="lingzhi-engineering",
    )
    return deck, snapshot


def _slide(slide_id: str = "slide-1", position: int = 0) -> Slide:
    return Slide(
        slide_id=slide_id,
        position=position,
        layout_id="L04",
        status="ready",
        title="地址与变量",
        source_refs={
            "section_ids": ["section-1"],
            "block_ids": ["block-pointer"],
            "objective_ids": ["obj-pointer"],
        },
    )


def _revision(deck: PresentationDeck, revision_id: str, parent: str | None = None) -> DeckRevision:
    return DeckRevision(
        revision_id=revision_id,
        parent_revision_id=parent,
        deck_id=deck.deck_id,
        reason="initial_generation" if parent is None else "chat_patch",
        source_snapshot_id=deck.source_ref.source_snapshot_id,
        slide_order=["slide-1"],
        slides=[_slide()],
    )


def _sha(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def test_source_projection_filters_chapter_and_keeps_input_immutable():
    course = _course()
    before = deepcopy(course)

    snapshot, source_ref = project_presentation_source(
        course, {"type": "chapter", "section_ids": ["chapter-1"]}
    )

    assert course == before
    assert source_ref.source_format == "canonical"
    assert snapshot["publication_allowed"] is True
    assert snapshot["publication"]["blocking_issues"] == []
    assert {item["section_id"] for item in snapshot["sections"]} == {"chapter-1", "section-1"}
    assert [item["question_id"] for item in snapshot["questions"]] == ["q-pointer"]
    assert [item["misconception_id"] for item in snapshot["misconceptions"]] == ["m-pointer"]
    # A block reference retains its asset even if the asset's legacy node metadata is wrong.
    assert [item["asset_id"] for item in snapshot["assets"]] == ["asset-pointer"]
    assert {item["objective_id"] for item in snapshot["objectives"]} == {"obj-pointer"}
    validate_source_snapshot(snapshot)
    assert source_packet(snapshot)["source_ref"]["source_snapshot_sha256"] == source_ref.source_snapshot_sha256


def test_legacy_source_projection_is_deterministic_and_rejects_unknown_section():
    canonical = _course()
    legacy = {
        "course_id": canonical["course_id"],
        "course_name": canonical["course_name"],
        "nodes": [
            {"node_id": "n1", "parent_node_id": "root", "node_name": "节点", "node_content": "正文"}
        ],
    }
    one, ref_one = project_presentation_source(legacy, {"type": "course", "section_ids": []})
    two, ref_two = project_presentation_source(legacy, {"type": "course", "section_ids": []})

    assert ref_one.source_format == "legacy_snapshot"
    assert one == two
    assert ref_one == ref_two
    with pytest.raises(ValueError, match="unknown section"):
        project_presentation_source(legacy, {"type": "chapter", "section_ids": ["missing"]})


def test_create_list_reload_and_request_idempotency(tmp_path):
    repository = PresentationRepository(tmp_path)
    deck, snapshot = _deck_and_snapshot()

    created = repository.create_deck(deck, snapshot, request_id="create/request:1")
    repeated = repository.create_deck(deck, snapshot, request_id="create/request:1")

    assert repeated == created
    assert repository.list_decks("course-1")[0]["deck_id"] == "deck-1"
    assert repository.load_source_snapshot("deck-1") == snapshot
    assert repository.get_deck("deck-1")["active_revision"] is None
    for unsafe_id in (".", "..", "../escape", "deck.with-dot"):
        with pytest.raises(ValueError, match="Invalid"):
            repository.load_manifest(unsafe_id)


def test_create_request_id_is_bound_to_operation_and_intent(tmp_path):
    repository = PresentationRepository(tmp_path)
    deck, snapshot = _deck_and_snapshot()
    intent = {
        "course_id": deck.course_id,
        "title": deck.title,
        "scope": deck.scope.model_dump(mode="json"),
        "purpose": deck.purpose,
        "template_id": deck.template_id,
        "page_budget": 8,
        "extra_requirements": "",
        "source_snapshot_sha256": deck.source_ref.source_snapshot_sha256,
    }
    created = repository.create_deck(
        deck,
        snapshot,
        request_id="create-intent-request",
        operation="create_presentation",
        fingerprint_payload=intent,
    )
    retry_deck = deck.model_copy(update={"deck_id": "deck-retry"})

    repeated = repository.create_deck(
        retry_deck,
        snapshot,
        request_id="create-intent-request",
        operation="create_presentation",
        fingerprint_payload=intent,
    )
    assert repeated == created
    assert not (tmp_path / "course-1" / "deck-retry").exists()

    with pytest.raises(IdempotencyKeyReuseConflict, match="idempotency_key_reused"):
        repository.create_deck(
            retry_deck,
            snapshot,
            request_id="create-intent-request",
            operation="create_presentation",
            fingerprint_payload={**intent, "title": "另一套课件"},
        )
    with pytest.raises(IdempotencyKeyReuseConflict, match="idempotency_key_reused"):
        repository.create_deck(
            retry_deck,
            snapshot,
            request_id="create-intent-request",
            operation="clone_presentation",
            fingerprint_payload=intent,
        )


def test_working_snapshot_and_event_replay_are_monotonic(tmp_path):
    repository = PresentationRepository(tmp_path)
    deck, snapshot = _deck_and_snapshot()
    repository.create_deck(deck, snapshot)
    working = GenerationWorkingSnapshot(
        generation_id="gen-1", deck_id="deck-1", slide_order=["slide-1"], slides=[_slide()]
    )

    repository.save_working("deck-1", working)
    first = PresentationEvent(
        event_type="deck_outline", deck_id="deck-1", generation_id="gen-1",
        event_seq=1, outline_revision=1,
    )
    second = PresentationEvent(
        event_type="slide_upsert", deck_id="deck-1", generation_id="gen-1",
        event_seq=2, outline_revision=1,
    )
    repository.append_event("deck-1", first)
    repository.append_event("deck-1", second)

    assert repository.load_manifest("deck-1")["status"] == "generating"
    assert [item["event_seq"] for item in repository.replay_events("deck-1", "gen-1", 1)] == [2]
    assert repository.append_event("deck-1", second)["event_seq"] == 2
    with pytest.raises(PresentationRepositoryConflict, match="gap"):
        repository.append_event("deck-1", {**second.model_dump(), "event_seq": 4})
    with pytest.raises(PresentationRepositoryConflict, match="already_active"):
        repository.save_working(
            "deck-1", {**working.model_dump(), "generation_id": "gen-2"}
        )
    completed = PresentationEvent(
        event_type="generation_complete", deck_id="deck-1", generation_id="gen-1",
        event_seq=3, outline_revision=1,
    )
    repository.append_event("deck-1", completed)
    assert repository.load_manifest("deck-1")["active_generation_id"] is None


def test_revisions_are_immutable_stale_safe_restorable_and_idempotent(tmp_path):
    repository = PresentationRepository(tmp_path)
    deck, snapshot = _deck_and_snapshot()
    repository.create_deck(deck, snapshot)
    first = _revision(deck, "rev-1")
    repository.append_revision("deck-1", first, command_id="command-initial")
    second = _revision(deck, "rev-2", "rev-1")

    receipt = repository.append_revision(
        "deck-1", second, expected_revision_id="rev-1", command_id="command-patch"
    )
    retry_payload = second.model_dump()
    retry_payload["revision_id"] = "rev-retry-is-ignored"
    retry_payload["created_at"] = "2099-01-01T00:00:00+00:00"
    repeated = repository.append_revision(
        "deck-1", retry_payload,
        expected_revision_id="rev-1", command_id="command-patch",
    )

    assert repeated == receipt
    with pytest.raises(IdempotencyKeyReuseConflict, match="idempotency_key_reused"):
        repository.append_revision(
            "deck-1", {**second.model_dump(), "created_by": "different"},
            expected_revision_id="rev-1", command_id="command-patch",
        )
    with pytest.raises(StaleRevisionConflict):
        repository.append_revision(
            "deck-1", _revision(deck, "rev-3", "rev-2"),
            expected_revision_id="rev-1", command_id="command-stale",
        )
    with pytest.raises(PresentationRepositoryConflict, match="immutable"):
        repository.append_revision(
            "deck-1", {**second.model_dump(), "created_by": "different"}, activate=False
        )

    restored = repository.restore_revision(
        "deck-1", "rev-1", expected_revision_id="rev-2", command_id="command-restore"
    )
    restored_again = repository.restore_revision(
        "deck-1", "rev-1", expected_revision_id="rev-2", command_id="command-restore"
    )
    assert restored_again == restored
    assert restored["revision_id"] not in {"rev-1", "rev-2"}
    assert restored["operation"] == "restore_revision"
    assert restored["restored_from_revision_id"] == "rev-1"
    assert restored["expected_revision_id"] == "rev-2"
    assert restored["command_fingerprint"].startswith("sha256:")
    assert repository.get_revision("deck-1")["parent_revision_id"] == "rev-2"


def test_request_and_command_ids_are_bound_to_operation_and_intent(tmp_path):
    repository = PresentationRepository(tmp_path)
    deck, snapshot = _deck_and_snapshot()
    repository.create_deck(deck, snapshot)
    request_intent = {"deck_id": "deck-1", "page_budget": 7, "expected_revision_id": None}
    saved = repository.save_request_receipt(
        "deck-1",
        "shared-request-id",
        {"kind": "generation", "generation_id": "gen-1"},
        operation="generate_presentation",
        fingerprint_payload=request_intent,
    )
    assert repository.get_request_receipt(
        "deck-1",
        "shared-request-id",
        operation="generate_presentation",
        fingerprint_payload=request_intent,
    ) == saved
    with pytest.raises(IdempotencyKeyReuseConflict):
        repository.get_request_receipt(
            "deck-1",
            "shared-request-id",
            operation="create_proposal",
            fingerprint_payload={"deck_id": "deck-1", "prompt": "补例子"},
        )
    with pytest.raises(IdempotencyKeyReuseConflict):
        repository.save_request_receipt(
            "deck-1",
            "shared-request-id",
            {"operation": "generate_presentation", "generation_id": "gen-2"},
            operation="generate_presentation",
            fingerprint_payload={**request_intent, "page_budget": 9},
        )

    repository.append_revision("deck-1", _revision(deck, "rev-1"))
    applied = repository.append_revision(
        "deck-1",
        _revision(deck, "rev-2", "rev-1"),
        expected_revision_id="rev-1",
        command_id="shared-command-id",
        command_operation="apply_proposal",
        command_metadata={"proposal_id": "proposal-1", "expected_revision_id": "rev-1"},
    )
    assert applied["operation"] == "apply_proposal"
    assert applied["proposal_id"] == "proposal-1"
    assert applied["command_fingerprint"].startswith("sha256:")
    with pytest.raises(IdempotencyKeyReuseConflict):
        repository.restore_revision(
            "deck-1",
            "rev-1",
            expected_revision_id="rev-2",
            command_id="shared-command-id",
        )


def test_failed_manifest_switch_leaves_old_pointer_and_new_entity(tmp_path, monkeypatch):
    repository = PresentationRepository(tmp_path)
    deck, snapshot = _deck_and_snapshot()
    repository.create_deck(deck, snapshot)
    repository.append_revision("deck-1", _revision(deck, "rev-1"))
    original_atomic_write = repository._atomic_write

    def fail_manifest(path, data):
        if path.name == "manifest.json" and data.get("active_revision_id") == "rev-2":
            raise OSError("simulated pointer failure")
        return original_atomic_write(path, data)

    monkeypatch.setattr(repository, "_atomic_write", fail_manifest)
    with pytest.raises(OSError, match="pointer failure"):
        repository.append_revision(
            "deck-1", _revision(deck, "rev-2", "rev-1"), expected_revision_id="rev-1"
        )

    assert repository.load_manifest("deck-1")["active_revision_id"] == "rev-1"
    assert repository.get_revision("deck-1", "rev-2")["revision_id"] == "rev-2"


def test_proposal_quality_artifact_and_safe_resolution(tmp_path):
    repository = PresentationRepository(tmp_path)
    deck, snapshot = _deck_and_snapshot()
    repository.create_deck(deck, snapshot)
    repository.append_revision("deck-1", _revision(deck, "rev-1"))
    proposal = DeckProposal(
        proposal_id="proposal-1", request_id="proposal-request-1", deck_id="deck-1",
        base_revision_id="rev-1", scope="slide", slide_ids=["slide-1"],
        prompt="补一个例子", patches=[],
    )
    assert repository.save_proposal("deck-1", proposal) == repository.save_proposal("deck-1", proposal)
    applied = proposal.model_copy(update={"status": "applied"})
    repository.save_proposal("deck-1", applied)
    assert repository.get_proposal("deck-1", "proposal-1")["status"] == "applied"
    report = QualityReport(
        report_id="quality-1", deck_id="deck-1", revision_id="rev-1",
        source_snapshot_id=deck.source_ref.source_snapshot_id, status="passed",
    )
    repository.save_quality("deck-1", report, expected_revision_id="rev-1")

    artifact_dir = repository.artifact_directory("deck-1", "artifact-1")
    html = b"<html>deck</html>"
    pptx = b"fake-pptx-for-repository-layer"
    (artifact_dir / "deck.html").write_bytes(html)
    (artifact_dir / "deck.pptx").write_bytes(pptx)
    receipt = ArtifactReceipt(
        artifact_id="artifact-1", deck_id="deck-1", revision_id="rev-1",
        source_snapshot_id=deck.source_ref.source_snapshot_id,
        template_id=deck.template_id, template_version="1.0.0", layout_registry_version="1.0.0",
        html_path=str(artifact_dir / "deck.html"), html_sha256=_sha(html),
        pptx_path=str(artifact_dir / "deck.pptx"), pptx_sha256=_sha(pptx),
        page_count=1, title_digest=_sha(b"title"), speaker_notes_digest=_sha(b"notes"),
        quality_report_id="quality-1",
    )
    repository.save_artifact(
        "deck-1", receipt, expected_revision_id="rev-1", command_id="finalize-command"
    )

    assert repository.resolve_artifact_file("artifact-1", "html") == artifact_dir / "deck.html"
    repository.append_revision(
        "deck-1", _revision(deck, "rev-2", "rev-1"), expected_revision_id="rev-1"
    )
    assert repository.get_artifact("artifact-1")["stale"] is True
    with pytest.raises(ArtifactAccessError, match="stale"):
        repository.resolve_artifact_file("artifact-1", "pptx")


def test_artifact_rejects_outside_paths_and_unpassed_quality(tmp_path):
    repository = PresentationRepository(tmp_path)
    deck, snapshot = _deck_and_snapshot()
    repository.create_deck(deck, snapshot)
    repository.append_revision("deck-1", _revision(deck, "rev-1"))
    report = QualityReport(
        report_id="quality-blocked", deck_id="deck-1", revision_id="rev-1",
        source_snapshot_id=deck.source_ref.source_snapshot_id, status="blocked",
    )
    repository.save_quality("deck-1", report, expected_revision_id="rev-1")
    artifact_dir = repository.artifact_directory("deck-1", "artifact-blocked")
    (artifact_dir / "deck.html").write_bytes(b"html")
    (artifact_dir / "deck.pptx").write_bytes(b"pptx")
    receipt = ArtifactReceipt(
        artifact_id="artifact-blocked", deck_id="deck-1", revision_id="rev-1",
        source_snapshot_id=deck.source_ref.source_snapshot_id,
        template_id=deck.template_id, template_version="1", layout_registry_version="1",
        html_path=str(tmp_path / "outside.html"), html_sha256=_sha(b"html"),
        pptx_path=str(artifact_dir / "deck.pptx"), pptx_sha256=_sha(b"pptx"),
        page_count=1, title_digest=_sha(b"title"), speaker_notes_digest=_sha(b"notes"),
        quality_report_id="quality-blocked",
    )
    with pytest.raises(PresentationRepositoryConflict, match="not_passed"):
        repository.save_artifact("deck-1", receipt, expected_revision_id="rev-1")
