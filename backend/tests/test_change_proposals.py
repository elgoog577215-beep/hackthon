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
async def test_reject_item_records_reason_and_is_idempotent_protected(tmp_path):
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
