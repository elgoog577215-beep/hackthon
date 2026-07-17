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
from course_knowledge_base import compile_course_knowledge_base
from course_repository import CourseDocumentRepository
import learning_events


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
async def test_evidence_must_use_course_evolution_instead_of_second_proposal_circuit(tmp_path):
    storage, repository, proposals, _command_service, document = await canonical_setup(tmp_path)
    target = block(document, "block-1")
    saves_before = storage.save_count

    with pytest.raises(ValueError, match="course evolution plan"):
        create_proposal(
            proposals,
            "course-1",
            request_id="evidence-must-use-course-evolution",
            scope="block",
            target_block_ids=[target.block_id],
            items=[{
                "block_id": target.block_id,
                "before": target.payload,
                "after": {"payload": {**target.payload, "markdown": "课程补充"}},
                "reason": "学习证据触发课程演进",
            }],
            source="evidence",
        )

    unchanged, _ = repository.load_document("course-1")
    assert unchanged == document
    assert storage.save_count == saves_before


@pytest.mark.asyncio
async def test_base_course_rejection_does_not_become_learner_evidence(tmp_path, monkeypatch):
    memory_events = MemoryDataStorage()
    monkeypatch.setattr(learning_events, "storage", memory_events)
    _storage, _repo, proposals, _cmd, document = await canonical_setup(tmp_path)
    target = block(document, "block-1")
    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="teacher-rejects-authoring-change",
        scope="block",
        target_block_ids=[target.block_id],
        items=[{
            "block_id": target.block_id,
            "before": target.payload,
            "after": {"payload": target.payload},
            "reason": "课程维护建议",
        }],
        source="representation_semantic",
    )

    rejected = reject_item(
        proposals,
        proposal["proposal_id"],
        proposal["items"][0]["item_id"],
        reason="维护者认为语义不准确",
    )
    item = rejected["items"][0]
    assert item["status"] == "rejected"
    assert item["resolution_reason"] == "维护者认为语义不准确"
    assert rejected["status"] == "resolved"
    assert memory_events.data.get(learning_events.LEARNING_EVENTS_FILE, []) == []
    with pytest.raises(ChangeProposalConflict):
        reject_item(
            proposals,
            proposal["proposal_id"],
            proposal["items"][0]["item_id"],
            reason="重复拒绝",
        )

    assert memory_events.data.get(learning_events.LEARNING_EVENTS_FILE, []) == []


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


@pytest.mark.asyncio
async def test_regenerate_route_generates_candidate_before_replacing_item(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import routers.change_proposals as change_proposals_router

    _storage, course_repository, proposals, _cmd, document = await canonical_setup(tmp_path)
    target = block(document, "block-1")
    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="req-route-regen",
        scope="block",
        target_block_ids=["block-1"],
        items=[{
            "block_id": "block-1",
            "before": target.payload,
            "after": {"payload": {**target.payload, "markdown": "first candidate"}},
            "reason": "improve explanation",
        }],
    )
    item_id = proposal["items"][0]["item_id"]

    class ReadyRegenerationService:
        def __init__(self):
            self.calls = []

        async def create_candidate(self, course_id, block_id, **kwargs):
            self.calls.append({"course_id": course_id, "block_id": block_id, **kwargs})
            return {
                "candidate_id": "candidate-ready-1",
                "status": "ready",
                "proposed_block": {
                    "payload": {**target.payload, "markdown": "AI regenerated content"},
                },
                "quality_report": {"passed": True, "issues": []},
            }

    regeneration_service = ReadyRegenerationService()
    monkeypatch.setattr(change_proposals_router, "get_change_proposal_repository", lambda: proposals)
    monkeypatch.setattr(change_proposals_router, "get_course_document_repository", lambda: course_repository)
    monkeypatch.setattr(
        change_proposals_router,
        "get_change_proposal_regeneration_service",
        lambda: regeneration_service,
        raising=False,
    )

    app = FastAPI()
    app.include_router(change_proposals_router.authoring_router, prefix="")
    client = TestClient(app)
    response = client.post(
        f"/courses/course-1/authoring-changes/{proposal['proposal_id']}/items/{item_id}/regenerate",
        json={"extra_instruction": "make it more concrete"},
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    assert len(regeneration_service.calls) == 1
    updated = response.json()
    old_item = next(item for item in updated["items"] if item["item_id"] == item_id)
    new_item = next(item for item in updated["items"] if item.get("regenerated_from") == item_id)
    assert old_item["status"] == "rejected"
    assert new_item["status"] == "pending"
    assert new_item["after"]["payload"]["markdown"] == "AI regenerated content"
    assert new_item["generation_meta"]["candidate_id"] == "candidate-ready-1"


@pytest.mark.asyncio
async def test_router_base_course_apply_returns_representation_sync_receipt(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import routers.change_proposals as change_proposals_router

    _storage, course_repository, proposals, _command_service, document = await canonical_setup(tmp_path)
    target = block(document, "block-1")
    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="base-course-sync-receipt",
        scope="block",
        target_block_ids=[target.block_id],
        items=[{
            "block_id": target.block_id,
            "before": target.payload,
            "after": {
                "payload": {
                    **target.payload,
                    "content": "向量不仅有坐标，还表达大小与方向。",
                },
            },
            "reason": "修正课程语义",
        }],
        source="representation_semantic",
    )
    sync_receipt = {
        "status": "synchronized",
        "quality": {"passed": True, "issues": []},
        "stale_before": [{
            "representation_type": "slide_deck",
            "stale_unit_ids": ["slide:section-a"],
        }],
        "rebuilt": [{
            "representation_type": "slide_deck",
            "rebuilt_unit_ids": ["slide:section-a"],
        }],
    }
    monkeypatch.setattr(change_proposals_router, "change_proposal_repository", proposals)
    monkeypatch.setattr(change_proposals_router, "get_change_proposal_repository", lambda: proposals)
    monkeypatch.setattr(change_proposals_router, "get_course_document_repository", lambda: course_repository)
    monkeypatch.setattr(
        change_proposals_router,
        "synchronize_teaching_representations",
        lambda _course_id: sync_receipt,
    )

    app = FastAPI()
    app.include_router(change_proposals_router.router)
    client = TestClient(app)
    response = client.post(
        f"/courses/course-1/change_proposals/{proposal['proposal_id']}/items/{proposal['items'][0]['item_id']}/apply",
        headers={"X-User-Id": "teacher-1"},
    )

    assert response.status_code == 200
    assert response.json()["representation_sync"] == sync_receipt
    updated, canonical = course_repository.load_document("course-1")
    assert canonical is True
    assert block(updated, target.block_id).payload["content"] == "向量不仅有坐标，还表达大小与方向。"


def test_router_applies_kg_node_item_as_review_acknowledgement(tmp_path, monkeypatch):
    """Accepting a knowledge-node proposal records a course-local review."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import routers.change_proposals as change_proposals_router

    course = legacy_course()
    course["nodes"][0]["knowledge_structure"] = [
        {
            "concept_group": "向量语义",
            "description": "向量的几何与代数含义。",
            "knowledge_points": [
                {
                    "name": "向量的大小与方向",
                    "statement": "向量同时具有大小和方向。",
                    "knowledge_type": "definition",
                    "conditions": ["向量已定义"],
                    "boundaries": ["标量没有方向"],
                    "entry_reason": "这是理解向量表示与运算的基础。",
                    "capability_points": [
                        {
                            "name": "识别向量的大小与方向",
                            "observable_behavior": "能从表示中指出大小与方向。",
                        }
                    ],
                    "mastery_criteria": [
                        {
                            "name": "解释向量语义",
                            "observable_performance": "能用自己的语言说明大小与方向。",
                            "verification_method": "独立解释并完成概念检查。",
                        }
                    ],
                }
            ],
        }
    ]
    course["course_knowledge_base"] = compile_course_knowledge_base(deepcopy(course))
    knowledge_id = course["course_knowledge_base"]["knowledge_points"][0]["knowledge_id"]

    class _CourseRepository:
        def load_course_view(self, _course_id: str) -> dict:
            return deepcopy(course)

    proposals = ChangeProposalRepository(tmp_path / "change_proposals")
    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="req-kg-node",
        scope="block",
        target_block_ids=[knowledge_id],
        items=[
            {
                "block_id": knowledge_id,
                "target_kind": "kg_node",
                "before": {"name": "formal knowledge node"},
                "after": {
                    "note": "Course content changed; review the formal definition.",
                    "source_block_id": "block-1",
                },
                "reason": "Synchronize a reviewed content change",
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
    monkeypatch.setattr(
        change_proposals_router,
        "get_course_document_repository",
        lambda: _CourseRepository(),
    )
    app = FastAPI()
    app.include_router(change_proposals_router.router, prefix="")
    client = TestClient(app)

    response = client.post(
        f"/courses/course-1/change_proposals/{proposal['proposal_id']}/items/{item_id}/apply",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200

    reloaded = proposals.load(proposal["proposal_id"])
    item = next(i for i in reloaded["items"] if i["item_id"] == item_id)
    assert item["status"] == "applied"
    assert item["receipt"]["kind"] == "course_knowledge_review_acknowledged"
    assert item["receipt"]["knowledge_scope"] == "current_course_only"
    assert item["receipt"]["knowledge_id"] == knowledge_id
    assert item["receipt"]["reviewed_by"] == "user-1"
    assert item["receipt"]["source_block_id"] == "block-1"


def test_router_rejects_kg_node_item_apply_with_409_when_id_is_not_course_local(
    tmp_path,
    monkeypatch,
):
    """A knowledge review cannot target an ID outside the current course."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import routers.change_proposals as change_proposals_router

    class _CourseRepository:
        def load_course_view(self, _course_id: str) -> dict:
            return {
                "course_id": "course-1",
                "course_name": "当前课程",
                "nodes": [],
            }

    # Isolate the compatibility reject side effect from the real data store.
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
    monkeypatch.setattr(
        change_proposals_router,
        "get_course_document_repository",
        lambda: _CourseRepository(),
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
        headers={"X-User-Id": "user-1"},
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
