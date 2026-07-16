from __future__ import annotations

from copy import deepcopy

import pytest

from change_proposals import (
    ChangeProposalConflict,
    ChangeProposalNotFound,
    ChangeProposalRepository,
    apply_item,
    create_proposal,
    reject_item,
    regenerate_item,
)
from course_commands import CourseCommandService
from course_repository import CourseDocumentRepository
import learning_events
import storage as storage_module


class MemoryDataStorage:
    """Minimal stand-in for `storage.storage`, mirroring the pattern used in
    test_learning_events_v2.py, so `record_learning_event` writes are
    observable without touching the real DATA_DIR."""

    def __init__(self) -> None:
        self.data: dict[str, list] = {}

    def load_data(self, filename):
        return deepcopy(self.data.get(filename, []))

    def save_data(self, filename, value):
        self.data[filename] = deepcopy(value)


class MemoryStorage:
    def __init__(self, course: dict) -> None:
        self.course = deepcopy(course)
        self.save_count = 0

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)
        self.save_count += 1


def legacy_course() -> dict:
    return {
        "course_id": "course-1",
        "course_name": "线性代数",
        "nodes": [
            {
                "node_id": "objective-1",
                "parent_node_id": "root",
                "node_name": "向量",
                "node_level": 2,
                "learning_objective": "理解向量的方向与大小",
                "objective_id": "lo-1",
                "content_blocks": [
                    {
                        "block_id": "block-1",
                        "type": "concept",
                        "title": "向量定义",
                        "content": "向量同时具有大小和方向。",
                        "order": 0,
                    },
                    {
                        "block_id": "block-2",
                        "type": "example",
                        "title": "坐标例子",
                        "content": "二维向量可以写成 (x, y)。",
                        "order": 1,
                    },
                ],
            }
        ],
    }


async def canonical_setup(tmp_path):
    storage = MemoryStorage(legacy_course())
    course_repository = CourseDocumentRepository(storage)
    preview = course_repository.document_envelope("course-1")
    await course_repository.migrate_legacy_course(
        "course-1",
        expected_source_checksum=preview["migration"]["source_checksum"],
    )
    proposal_repository = ChangeProposalRepository(tmp_path / "change_proposals")
    command_service = CourseCommandService(course_repository)
    document, _ = course_repository.load_document("course-1")
    return storage, course_repository, proposal_repository, command_service, document


def block(document, block_id):
    return next(b for b in document.blocks if b.block_id == block_id)


@pytest.mark.asyncio
async def test_create_proposal_serialization_and_scope(tmp_path):
    _storage, _repo, proposals, _cmd, document = await canonical_setup(tmp_path)
    target1 = block(document, "block-1")
    target2 = block(document, "block-2")

    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="req-1",
        scope="section",
        target_block_ids=["block-1", "block-2"],
        items=[
            {
                "block_id": "block-1",
                "before": target1.payload,
                "after": {"payload": {**target1.payload, "content": "更详细的向量定义。"}},
                "reason": "补充解释",
            },
            {
                "block_id": "block-2",
                "before": target2.payload,
                "after": {"payload": {**target2.payload, "content": "补充坐标示例。"}},
                "reason": "补充示例",
            },
        ],
    )

    assert proposal["scope"] == "section"
    assert proposal["status"] == "pending"
    assert proposal["target_block_ids"] == ["block-1", "block-2"]
    assert len(proposal["items"]) == 2
    assert all(item["status"] == "pending" for item in proposal["items"])
    assert proposal["source"] == "manual"

    reloaded = proposals.load(proposal["proposal_id"])
    assert reloaded == proposal

    # idempotent create for the same request_id
    repeated = create_proposal(
        proposals,
        "course-1",
        request_id="req-1",
        scope="section",
        target_block_ids=["block-1", "block-2"],
        items=[{"block_id": "block-1", "before": {}, "after": {"payload": {}}, "reason": "ignored"}],
    )
    assert repeated["proposal_id"] == proposal["proposal_id"]
    assert len(repeated["items"]) == 2


@pytest.mark.asyncio
async def test_items_require_membership_in_target_block_ids(tmp_path):
    _storage, _repo, proposals, _cmd, document = await canonical_setup(tmp_path)
    with pytest.raises(ValueError):
        create_proposal(
            proposals,
            "course-1",
            request_id="req-bad",
            scope="block",
            target_block_ids=["block-1"],
            items=[{"block_id": "block-2", "before": {}, "after": {"payload": {}}, "reason": "x"}],
        )


@pytest.mark.asyncio
async def test_apply_item_writes_via_course_command_service_and_is_isolated(tmp_path):
    storage, repository, proposals, command_service, document = await canonical_setup(tmp_path)
    target1 = block(document, "block-1")
    target2 = block(document, "block-2")

    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="req-apply",
        scope="sections",
        target_block_ids=["block-1", "block-2"],
        items=[
            {
                "block_id": "block-1",
                "before": target1.payload,
                "after": {"payload": {**target1.payload, "markdown": "向量由大小与方向共同确定。"}},
                "reason": "补充解释",
            },
            {
                "block_id": "block-2",
                "before": target2.payload,
                "after": {"payload": {**target2.payload, "markdown": "坐标示例补充说明。"}},
                "reason": "补充示例",
            },
        ],
    )
    item1_id = proposal["items"][0]["item_id"]
    item2_id = proposal["items"][1]["item_id"]

    saves_before = storage.save_count
    applied = await apply_item(
        proposals,
        command_service,
        proposal["proposal_id"],
        item1_id,
        expected_document_revision=document.document_revision,
        expected_block_revision=target1.internal_revision,
        actor="user-1",
    )

    assert storage.save_count == saves_before + 1
    applied_item = next(i for i in applied["items"] if i["item_id"] == item1_id)
    assert applied_item["status"] == "applied"
    assert applied_item["receipt"] is not None
    # unrelated item unaffected
    other_item = next(i for i in applied["items"] if i["item_id"] == item2_id)
    assert other_item["status"] == "pending"
    assert applied["status"] == "pending"  # not all items resolved yet

    updated_document, _ = repository.load_document("course-1")
    updated_block1 = block(updated_document, "block-1")
    assert updated_block1.payload["markdown"] == "向量由大小与方向共同确定。"

    # re-applying the same item must not silently overwrite
    with pytest.raises(ChangeProposalConflict):
        await apply_item(
            proposals,
            command_service,
            proposal["proposal_id"],
            item1_id,
            expected_document_revision=updated_document.document_revision,
            expected_block_revision=updated_block1.internal_revision,
            actor="user-1",
        )

    # resolve the remaining item -> proposal becomes fully resolved
    resolved = await apply_item(
        proposals,
        command_service,
        proposal["proposal_id"],
        item2_id,
        expected_document_revision=updated_document.document_revision,
        expected_block_revision=target2.internal_revision,
        actor="user-1",
    )
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] is not None


@pytest.mark.asyncio
async def test_reject_item_records_reason_and_is_idempotent_protected(tmp_path, monkeypatch):
    memory_events = MemoryDataStorage()
    monkeypatch.setattr(learning_events, "storage", memory_events)
    _storage, _repo, proposals, _cmd, document = await canonical_setup(tmp_path)
    target1 = block(document, "block-1")
    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="req-reject",
        scope="block",
        target_block_ids=["block-1"],
        items=[
            {
                "block_id": "block-1",
                "before": target1.payload,
                "after": {"payload": target1.payload},
                "reason": "补充解释",
            }
        ],
    )
    item_id = proposal["items"][0]["item_id"]

    rejected = reject_item(proposals, proposal["proposal_id"], item_id, reason="内容不准确")
    item = rejected["items"][0]
    assert item["status"] == "rejected"
    assert item["resolution_reason"] == "内容不准确"
    assert rejected["status"] == "resolved"

    # Evidence back-flow: the rejection reason MUST be written back as a new
    # LearningEvent (spec §4), not just parked on the change-proposal item.
    recorded_events = memory_events.data.get(learning_events.LEARNING_EVENTS_FILE, [])
    reason_events = [
        e for e in recorded_events
        if e.get("event_type") == "learner_self_reported"
        and e.get("source") == "change_proposal_rejection"
    ]
    assert len(reason_events) == 1
    reason_event = reason_events[0]
    assert reason_event["evidence"]["statement"] == "内容不准确"
    assert reason_event["course_id"] == "course-1"
    assert reason_event["node_id"] == "block-1"
    assert reason_event["evidence"]["change_proposal_item_id"] == item_id

    with pytest.raises(ChangeProposalConflict):
        reject_item(proposals, proposal["proposal_id"], item_id, reason="again")


@pytest.mark.asyncio
async def test_regenerate_item_creates_new_pending_item_without_reusing_content(tmp_path):
    _storage, _repo, proposals, _cmd, document = await canonical_setup(tmp_path)
    target1 = block(document, "block-1")
    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="req-regen",
        scope="block",
        target_block_ids=["block-1"],
        items=[
            {
                "block_id": "block-1",
                "before": target1.payload,
                "after": {"payload": {**target1.payload, "markdown": "第一版候选内容"}},
                "reason": "补充解释",
            }
        ],
    )
    item_id = proposal["items"][0]["item_id"]

    updated = regenerate_item(
        proposals,
        proposal["proposal_id"],
        item_id,
        extra_instruction="请再具体一些",
    )

    old_item = next(i for i in updated["items"] if i["item_id"] == item_id)
    assert old_item["status"] == "rejected"
    assert old_item["resolution_reason"] == "请再具体一些"

    new_items = [i for i in updated["items"] if i["item_id"] != item_id]
    assert len(new_items) == 1
    new_item = new_items[0]
    assert new_item["status"] == "pending"
    assert new_item["after"] is None
    assert new_item["regenerated_from"] == item_id
    assert new_item["block_id"] == "block-1"

    # proposal not resolved since new pending item exists
    assert updated["status"] == "pending"

    with pytest.raises(ChangeProposalConflict):
        regenerate_item(proposals, proposal["proposal_id"], item_id, extra_instruction="again")


@pytest.mark.asyncio
async def test_regenerate_item_reruns_template_generator_for_evidence_source(tmp_path, monkeypatch):
    """`source == "evidence"` items targeting a real course block should get a
    freshly-regenerated `after.payload` (via the same MVP template generator
    `evaluate_and_propose_change` uses), rather than being left permanently
    `after=None`, whenever the triggering course/block/evidence can still be
    resolved.

    Forces the template-fallback path deterministically (rather than
    depending on whether the host environment happens to have a real
    AI_API_KEY configured) by making `_llm_supplement_text` behave like the
    provider is unavailable - `learner_model_service._generate_supplement_payload`
    tries the real LLM first and only falls back to the template otherwise."""
    import learner_model_service

    async def _no_llm(*_args, **_kwargs):
        return None

    monkeypatch.setattr(learner_model_service, "_llm_supplement_text", _no_llm)

    memory_events = MemoryDataStorage()
    monkeypatch.setattr(learning_events, "storage", memory_events)
    storage, _repo, proposals, _cmd, document = await canonical_setup(tmp_path)
    # The lazily-imported `storage.storage` singleton inside change_proposals
    # must resolve to the same course storage this test set up.
    monkeypatch.setattr(storage_module, "storage", storage)

    learning_events.record_learning_event(
        event_type="learner_self_reported",
        actor="learner",
        source="test",
        user_id="learner-1",
        course_id="course-1",
        node_id="block-1",
        evidence={"statement": "这里讲得太快，没听懂方向的定义。"},
    )

    target1 = block(document, "block-1")
    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="req-regen-evidence",
        scope="block",
        target_block_ids=["block-1"],
        items=[
            {
                "block_id": "block-1",
                "before": target1.payload,
                "after": {"payload": {**target1.payload, "markdown": "第一版候选内容"}},
                "reason": "学习证据触发变更",
            }
        ],
        source="evidence",
        generation_meta={"user_id": "learner-1"},
    )
    item_id = proposal["items"][0]["item_id"]

    updated = regenerate_item(proposals, proposal["proposal_id"], item_id)
    new_item = next(i for i in updated["items"] if i["item_id"] != item_id)

    assert new_item["status"] == "pending"
    assert new_item["after"] is not None
    assert new_item["after"]["payload"]["title"] == target1.payload["title"]
    assert "这里讲得太快，没听懂方向的定义。" in new_item["after"]["payload"]["markdown"]
    assert "AI 补充说明" in new_item["after"]["payload"]["markdown"]


@pytest.mark.asyncio
async def test_apply_item_reports_awaiting_generation_for_null_after(tmp_path):
    """`apply_item` on an item whose `after is None` (the "awaiting
    regeneration" contract) must fail with a message that tells the caller
    what to do next, not the generic "'after' payload is invalid" text used
    for genuinely malformed payloads."""
    _storage, _repo, proposals, command_service, document = await canonical_setup(tmp_path)
    target1 = block(document, "block-1")
    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="req-awaiting",
        scope="block",
        target_block_ids=["block-1"],
        items=[
            {
                "block_id": "block-1",
                "before": target1.payload,
                "after": {"payload": {**target1.payload, "markdown": "第一版候选内容"}},
                "reason": "补充解释",
            }
        ],
    )
    item_id = proposal["items"][0]["item_id"]
    updated = regenerate_item(proposals, proposal["proposal_id"], item_id)
    new_item = next(i for i in updated["items"] if i["item_id"] != item_id)
    assert new_item["after"] is None

    with pytest.raises(ChangeProposalConflict) as excinfo:
        await apply_item(
            proposals,
            command_service,
            proposal["proposal_id"],
            new_item["item_id"],
            expected_document_revision=document.document_revision,
            expected_block_revision=target1.internal_revision,
            actor="user-1",
        )
    message = str(excinfo.value)
    assert "重新生成" in message
    assert message != "Item 'after' payload is invalid"


def test_router_applies_kg_node_item_as_review_acknowledgement(tmp_path, monkeypatch):
    """Route-level: an item whose target_kind is "kg_node" must never reach
    the course-block lookup (which would previously 404 with a misleading
    "Course block not found"). When the course's subject resolves to a real
    curated knowledge library, applying it now succeeds by recording an
    operator review-acknowledgement on the catalog node (see
    `change_proposals.apply_kg_node_item`), instead of the old unconditional
    409."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import shutil

    import routers.change_proposals as change_proposals_router
    import storage as storage_module
    import subject_knowledge

    # Isolate the curated catalog directory so this test's write doesn't
    # mutate the real production catalog file on disk.
    catalog_copy = tmp_path / "catalogs"
    catalog_copy.mkdir()
    shutil.copy(
        subject_knowledge.CATALOG_DIR / "debate-logic-v1.json",
        catalog_copy / "debate-logic-v1.json",
    )
    monkeypatch.setattr(subject_knowledge, "CATALOG_DIR", catalog_copy)
    subject_knowledge.load_subject_library.cache_clear()
    subject_knowledge.available_subject_libraries.cache_clear()

    class _Storage:
        def load_course(self, _course_id: str) -> dict:
            return {"course_id": "course-1", "course_name": "辩论：逻辑构建与实战技巧"}

    monkeypatch.setattr(storage_module, "storage", _Storage())

    proposals = ChangeProposalRepository(tmp_path / "change_proposals")
    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="req-kg-node",
        scope="block",
        target_block_ids=["debate.logic.argument.claim"],
        items=[
            {
                "block_id": "debate.logic.argument.claim",
                "target_kind": "kg_node",
                "before": {"name": "论点（Claim）"},
                "after": {
                    "note": "课程正文已变更，建议核对该知识节点定义是否需要同步更新。",
                    "source_block_id": "block-1",
                },
                "reason": "内容变更同步到知识库节点",
            }
        ],
    )
    item_id = proposal["items"][0]["item_id"]

    monkeypatch.setattr(change_proposals_router, "change_proposal_repository", proposals)
    monkeypatch.setattr(
        change_proposals_router,
        "get_change_proposal_repository",
        lambda: proposals,
    )

    app = FastAPI()
    app.include_router(change_proposals_router.router, prefix="")
    client = TestClient(app)

    response = client.post(
        f"/courses/course-1/change_proposals/{proposal['proposal_id']}/items/{item_id}/apply",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code != 404
    assert response.status_code == 200

    reloaded = proposals.load(proposal["proposal_id"])
    item = next(i for i in reloaded["items"] if i["item_id"] == item_id)
    assert item["status"] == "applied"
    assert item["receipt"]["kind"] == "kg_node_review_acknowledged"
    assert item["receipt"]["reviewed_by"] == "user-1"

    # The review note is preserved on the raw curated catalog file (an audit
    # trail for the human maintainer), not surfaced through the normalized
    # runtime view `load_subject_library` returns.
    import json

    raw = json.loads((catalog_copy / "debate-logic-v1.json").read_text(encoding="utf-8"))

    def find_node(node: dict, knowledge_id: str) -> dict | None:
        if node.get("knowledge_id") == knowledge_id:
            return node
        for child in node.get("children") or []:
            found = find_node(child, knowledge_id)
            if found:
                return found
        return None

    raw_node = find_node(raw["tree"], "debate.logic.argument.claim")
    assert raw_node["review_notes"][0]["source_block_id"] == "block-1"

    # Clear caches while still pointed at the tmp catalog dir, so the next
    # real lookup (once monkeypatch reverts CATALOG_DIR) re-reads the real,
    # untouched production catalog instead of this test's cached copy.
    subject_knowledge.load_subject_library.cache_clear()
    subject_knowledge.available_subject_libraries.cache_clear()


def test_router_rejects_kg_node_item_apply_with_409_when_library_unresolvable(tmp_path, monkeypatch):
    """When the course's subject doesn't resolve to any curated knowledge
    library, applying a kg_node item must fail with an honest 409 rather
    than silently succeeding or 404ing on a course-block lookup that never
    applies to kg_node items. Reject must still work normally."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import routers.change_proposals as change_proposals_router
    import storage as storage_module

    class _Storage:
        def load_course(self, _course_id: str) -> dict:
            return {"course_id": "course-1", "course_name": "一门无法匹配任何知识库的课程"}

    monkeypatch.setattr(storage_module, "storage", _Storage())
    # The reject path records rejection evidence via `learning_events`, which
    # binds its own `storage` reference at import time (`from storage import
    # storage`) - patching `storage_module.storage` above does not affect it,
    # so it must be isolated separately to avoid writing to the real
    # DATA_DIR/learning_events.json on every test run.
    monkeypatch.setattr(learning_events, "storage", MemoryDataStorage())

    proposals = ChangeProposalRepository(tmp_path / "change_proposals")
    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="req-kg-node-unresolved",
        scope="block",
        target_block_ids=["unknown.node"],
        items=[
            {
                "block_id": "unknown.node",
                "target_kind": "kg_node",
                "before": {"name": "未知节点"},
                "after": {"note": "课程正文已变更"},
                "reason": "内容变更同步到知识库节点",
            }
        ],
    )
    item_id = proposal["items"][0]["item_id"]

    monkeypatch.setattr(change_proposals_router, "change_proposal_repository", proposals)
    monkeypatch.setattr(
        change_proposals_router,
        "get_change_proposal_repository",
        lambda: proposals,
    )

    app = FastAPI()
    app.include_router(change_proposals_router.router, prefix="")
    client = TestClient(app)

    response = client.post(
        f"/courses/course-1/change_proposals/{proposal['proposal_id']}/items/{item_id}/apply",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code != 404
    assert response.status_code == 409

    reloaded = proposals.load(proposal["proposal_id"])
    item = next(i for i in reloaded["items"] if i["item_id"] == item_id)
    assert item["status"] == "pending"

    # reject path must still work normally for a kg_node item.
    reject_response = client.post(
        f"/courses/course-1/change_proposals/{proposal['proposal_id']}/items/{item_id}/reject",
        json={"reason": "人工核对后拒绝"},
    )
    assert reject_response.status_code == 200
    rejected = proposals.load(proposal["proposal_id"])
    rejected_item = next(i for i in rejected["items"] if i["item_id"] == item_id)
    assert rejected_item["status"] == "rejected"


@pytest.mark.asyncio
async def test_apply_unknown_item_raises_not_found(tmp_path):
    _storage, _repo, proposals, command_service, document = await canonical_setup(tmp_path)
    target1 = block(document, "block-1")
    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="req-missing",
        scope="block",
        target_block_ids=["block-1"],
        items=[
            {
                "block_id": "block-1",
                "before": target1.payload,
                "after": {"payload": target1.payload},
                "reason": "x",
            }
        ],
    )

    with pytest.raises(ChangeProposalNotFound):
        await apply_item(
            proposals,
            command_service,
            proposal["proposal_id"],
            "missing-item",
            expected_document_revision=document.document_revision,
            expected_block_revision=target1.internal_revision,
            actor="user-1",
        )
