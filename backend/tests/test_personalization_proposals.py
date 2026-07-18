from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import threading

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

import block_regeneration
from block_regeneration import BlockRegenerationCandidateRepository
from change_proposals import (
    ChangeProposalConflict,
    ChangeProposalRepository,
    apply_selected_items,
    create_proposal,
    reject_item,
)
from course_document import (
    COURSE_DOCUMENT_SCHEMA,
    CourseBlock,
    CourseDocument,
    CourseSection,
    refresh_document_revision,
)
from course_repository import CourseDocumentRepository
from routers import block_regeneration as block_regeneration_router
from routers import change_proposals as change_proposals_router


class MemoryStorage:
    def __init__(self, course: dict) -> None:
        self.course = deepcopy(course)
        self.save_count = 0

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)
        self.save_count += 1


class CountingCourseRepository(CourseDocumentRepository):
    def __init__(self, storage_obj) -> None:
        super().__init__(storage_obj)
        self.load_document_count = 0
        self.commit_document_count = 0

    def load_document(self, course_id: str):
        self.load_document_count += 1
        return super().load_document(course_id)

    async def commit_document(self, *args, **kwargs):
        self.commit_document_count += 1
        return await super().commit_document(*args, **kwargs)


class FakePersonalizationGenerator:
    def __init__(self, *, failing_block_ids: set[str] | None = None) -> None:
        self.failing_block_ids = failing_block_ids or set()
        self.calls: list[dict] = []

    async def generate_course_block_candidate(self, **kwargs) -> str:
        self.calls.append(deepcopy(kwargs))
        block_id = kwargs["target_block"]["block_id"]
        if block_id in self.failing_block_ids:
            raise RuntimeError("fake related generation failure")
        return f"针对反馈完成明显优化：{kwargs['instruction']}（块 {block_id}）。"


def canonical_document() -> CourseDocument:
    return refresh_document_revision(CourseDocument(
        course_id="course-1",
        title="线性代数",
        sections=[
            CourseSection(
                section_id="section-a",
                title="向量",
                position=0,
                learning_objective="理解向量",
                objective_id="lo-a",
            ),
            CourseSection(
                section_id="section-b",
                title="矩阵",
                position=1,
                learning_objective="理解矩阵",
                objective_id="lo-b",
            ),
        ],
        blocks=[
            CourseBlock(
                block_id="target",
                section_id="section-a",
                position=0,
                role="concept",
                objective_refs=["lo-a"],
                payload={"title": "定义", "markdown": "向量有大小和方向。"},
            ),
            CourseBlock(
                block_id="related-summary",
                section_id="section-a",
                position=1,
                role="summary",
                objective_refs=["lo-a"],
                payload={"title": "小结", "markdown": "回顾向量定义。"},
            ),
            CourseBlock(
                block_id="related-example",
                section_id="section-a",
                position=2,
                role="example",
                objective_refs=["lo-a"],
                payload={"title": "例子", "markdown": "位移可以表示为向量。"},
            ),
            CourseBlock(
                block_id="related-reasoning",
                section_id="section-a",
                position=3,
                role="reasoning",
                objective_refs=["lo-a"],
                payload={"title": "推理", "markdown": "方向决定向量的几何意义。"},
            ),
            CourseBlock(
                block_id="other-objective",
                section_id="section-a",
                position=4,
                role="example",
                objective_refs=["lo-other"],
                payload={"title": "其他目标", "markdown": "不属于当前学习目标。"},
            ),
            CourseBlock(
                block_id="other-section",
                section_id="section-b",
                position=0,
                role="reasoning",
                objective_refs=["lo-a"],
                payload={"title": "其他章节", "markdown": "即使目标相同也不能跨章节。"},
            ),
        ],
    ))


def canonical_repositories(tmp_path):
    document = canonical_document()
    storage = MemoryStorage({
        "course_id": document.course_id,
        "course_name": document.title,
        "course_schema_version": COURSE_DOCUMENT_SCHEMA,
        "course_document": document.model_dump(mode="json"),
        "course_document_revision": document.document_revision,
        "current_course_version_id": document.document_revision,
        "course_operation_log": [],
    })
    courses = CountingCourseRepository(storage)
    candidates = BlockRegenerationCandidateRepository(tmp_path / "candidates")
    proposals = ChangeProposalRepository(tmp_path / "proposals")
    return storage, courses, candidates, proposals, document


def proposal_items(document: CourseDocument) -> list[dict]:
    items = []
    for block_id in ("target", "related-example", "related-summary"):
        target = next(item for item in document.blocks if item.block_id == block_id)
        after = target.model_copy(deep=True)
        after.payload["markdown"] = f"{target.payload['markdown']} 已按反馈改进。"
        items.append({
            "block_id": block_id,
            "before": target.model_dump(mode="json"),
            "after": after.model_dump(mode="json"),
            "reason": "响应学习反馈",
            "selected": True,
            "expected_block_revision": target.internal_revision,
        })
    return items


def test_personalization_proposal_selects_only_same_section_and_objective_and_records_feedback(
    tmp_path,
    monkeypatch,
):
    service_type = getattr(block_regeneration, "PersonalizationProposalService", None)
    assert service_type is not None, "PersonalizationProposalService must be implemented"
    _storage, courses, candidates, proposals, document = canonical_repositories(tmp_path)
    generator = FakePersonalizationGenerator()
    events: list[dict] = []

    def record_event(**kwargs):
        events.append(deepcopy(kwargs))
        return kwargs

    service = service_type(
        courses,
        candidates,
        proposals,
        generator=generator,
        event_recorder=record_event,
    )
    monkeypatch.setattr(
        block_regeneration_router,
        "get_personalization_proposal_service",
        lambda: service,
        raising=False,
    )
    app = FastAPI()
    app.include_router(block_regeneration_router.router)
    client = TestClient(app)

    target = next(item for item in document.blocks if item.block_id == "target")
    response = client.post(
        "/courses/course-1/blocks/target/personalization-proposals",
        headers={"X-User-Id": "student-1"},
        json={
            "request_id": "personalize-1",
            "expected_document_revision": document.document_revision,
            "expected_block_revision": target.internal_revision,
            "direction": "expand",
            "feedback": "我不理解方向为什么重要，请增加直观解释",
        },
    )

    assert response.status_code == 200
    proposal = response.json()
    assert proposal["source"] == "personalization"
    assert proposal["target_block_ids"] == ["target", "related-reasoning", "related-example"]
    assert 1 <= len(proposal["items"]) <= 3
    assert all(item["selected"] is True for item in proposal["items"])
    assert all("before" in item and "after" in item and item["reason"] for item in proposal["items"])
    submitted_feedback = json.loads(response.request.content)["feedback"]
    assert submitted_feedback not in json.dumps(proposal, ensure_ascii=False)
    assert "other-objective" not in proposal["target_block_ids"]
    assert "other-section" not in proposal["target_block_ids"]
    assert "我不理解方向为什么重要" in generator.calls[0]["instruction"]
    assert len(events) == 1
    assert events[0]["event_type"] == "personalization_feedback_submitted"
    assert events[0]["user_id"] == "student-1"
    assert events[0]["evidence"]["direction"] == "expand"
    assert "我不理解方向为什么重要" in events[0]["evidence"]["feedback_summary"]
    assert "feedback" not in events[0]["evidence"]
    assert events[0]["result"]["changed_block_ids"] == proposal["target_block_ids"]


@pytest.mark.asyncio
async def test_concurrent_identical_personalization_requests_share_one_proposal(tmp_path):
    class BlockingTargetGenerator(FakePersonalizationGenerator):
        def __init__(self) -> None:
            super().__init__()
            self.target_started = asyncio.Event()
            self.release_target = asyncio.Event()
            self.target_call_count = 0

        async def generate_course_block_candidate(self, **kwargs) -> str:
            if kwargs["target_block"]["block_id"] == "target":
                self.target_call_count += 1
                self.target_started.set()
                await self.release_target.wait()
            return await super().generate_course_block_candidate(**kwargs)

    service_type = getattr(block_regeneration, "PersonalizationProposalService", None)
    assert service_type is not None
    _storage, courses, candidates, proposals, document = canonical_repositories(tmp_path)
    generator = BlockingTargetGenerator()
    events: list[dict] = []
    services = [
        service_type(
            courses,
            candidates,
            proposals,
            generator=generator,
            event_recorder=lambda **kwargs: events.append(deepcopy(kwargs)) or kwargs,
        )
        for _ in range(2)
    ]
    target = next(item for item in document.blocks if item.block_id == "target")
    request = {
        "request_id": "concurrent-identical-request",
        "expected_document_revision": document.document_revision,
        "expected_block_revision": target.internal_revision,
        "direction": "expand",
        "feedback": "请补充方向的直观解释",
        "user_id": "student-a",
    }

    first = asyncio.create_task(services[0].create_proposal("course-1", "target", **request))
    await generator.target_started.wait()
    with pytest.raises(
        block_regeneration.BlockRegenerationConflict,
        match="different inputs",
    ):
        await services[1].create_proposal(
            "course-1",
            "target",
            **{**request, "direction": "simplify"},
        )
    second = asyncio.create_task(services[1].create_proposal("course-1", "target", **request))
    await asyncio.sleep(0)
    generator.release_target.set()

    results = await asyncio.wait_for(
        asyncio.gather(first, second, return_exceptions=True),
        timeout=1,
    )

    assert not [result for result in results if isinstance(result, BaseException)]
    first_proposal, second_proposal = results
    assert second_proposal == first_proposal
    assert generator.target_call_count == 1
    assert len(generator.calls) == 3
    assert len(events) == 1


@pytest.mark.asyncio
async def test_concurrent_identical_personalization_timeout_is_retryable_and_reuses_proposal(
    tmp_path,
    monkeypatch,
):
    class HangingTargetGenerator(FakePersonalizationGenerator):
        def __init__(self) -> None:
            super().__init__()
            self.target_started = asyncio.Event()
            self.release_target = asyncio.Event()

        async def generate_course_block_candidate(self, **kwargs) -> str:
            if kwargs["target_block"]["block_id"] == "target":
                self.target_started.set()
                await self.release_target.wait()
            return await super().generate_course_block_candidate(**kwargs)

    monkeypatch.setattr(
        block_regeneration,
        "PERSONALIZATION_IDEMPOTENCY_WAIT_SECONDS",
        0.01,
    )
    service_type = getattr(block_regeneration, "PersonalizationProposalService", None)
    _storage, courses, candidates, proposals, document = canonical_repositories(tmp_path)
    generator = HangingTargetGenerator()
    services = [
        service_type(
            courses,
            candidates,
            proposals,
            generator=generator,
            event_recorder=lambda **kwargs: kwargs,
        )
        for _ in range(2)
    ]
    target = next(item for item in document.blocks if item.block_id == "target")
    request = {
        "request_id": "bounded-identical-request",
        "expected_document_revision": document.document_revision,
        "expected_block_revision": target.internal_revision,
        "direction": "expand",
        "feedback": "请补充方向的直观解释",
        "user_id": "student-a",
    }
    body = block_regeneration_router.CreatePersonalizationProposalRequest(
        **{key: value for key, value in request.items() if key != "user_id"}
    )
    http_request = Request({
        "type": "http",
        "headers": [(b"x-user-id", b"student-a")],
    })
    monkeypatch.setattr(
        block_regeneration_router,
        "get_personalization_proposal_service",
        lambda: services[1],
    )

    first = asyncio.create_task(services[0].create_proposal("course-1", "target", **request))
    await generator.target_started.wait()
    try:
        with pytest.raises(HTTPException) as caught:
            await block_regeneration_router.create_personalization_proposal(
                "course-1",
                "target",
                body,
                http_request,
            )
        assert caught.value.status_code == 503
        assert caught.value.detail["code"] == "personalization_generation_in_progress"
        assert caught.value.headers == {"Retry-After": "2"}
    finally:
        generator.release_target.set()
        first_proposal = await asyncio.wait_for(first, timeout=1)

    retried = await block_regeneration_router.create_personalization_proposal(
        "course-1",
        "target",
        body,
        http_request,
    )
    assert retried == first_proposal
    target_calls = [
        call
        for call in generator.calls
        if call["target_block"]["block_id"] == "target"
    ]
    assert len(target_calls) == 1


@pytest.mark.asyncio
async def test_personalization_request_id_reuse_requires_matching_user_and_request_fingerprint(
    tmp_path,
    monkeypatch,
):
    service_type = getattr(block_regeneration, "PersonalizationProposalService", None)
    assert service_type is not None
    _storage, courses, candidates, proposals, document = canonical_repositories(tmp_path)
    generator = FakePersonalizationGenerator()
    service = service_type(
        courses,
        candidates,
        proposals,
        generator=generator,
        event_recorder=lambda **kwargs: kwargs,
    )
    target = next(item for item in document.blocks if item.block_id == "target")
    request = {
        "request_id": "shared-request-id",
        "expected_document_revision": document.document_revision,
        "expected_block_revision": target.internal_revision,
        "direction": "expand",
        "feedback": "请补充方向的直观解释",
    }

    proposal = await service.create_proposal(
        "course-1",
        "target",
        user_id="student-a",
        **request,
    )
    call_count = len(generator.calls)

    monkeypatch.setattr(
        block_regeneration_router,
        "get_personalization_proposal_service",
        lambda: service,
    )
    app = FastAPI()
    app.include_router(block_regeneration_router.router)
    response = TestClient(app).post(
        "/courses/course-1/blocks/target/personalization-proposals",
        headers={"X-User-Id": "student-b"},
        json=request,
    )

    assert response.status_code == 409
    assert len(generator.calls) == call_count
    metadata = proposal["generation_meta"]
    assert metadata["request_fingerprint"]
    assert metadata["feedback_hash"]
    assert metadata["base_document_revision"] == document.document_revision
    assert "feedback" not in metadata


@pytest.mark.asyncio
async def test_personalization_creation_rechecks_the_winning_request_fingerprint(tmp_path):
    service_type = getattr(block_regeneration, "PersonalizationProposalService", None)
    assert service_type is not None
    _storage, courses, candidates, proposals, document = canonical_repositories(tmp_path)
    create_proposal(
        proposals,
        "course-1",
        request_id="raced-request-id",
        scope="block",
        target_block_ids=["target"],
        items=proposal_items(document)[:1],
        source="personalization",
        generation_meta={"request_fingerprint": "student-a-fingerprint"},
    )

    class HideExistingOnPrecheck(ChangeProposalRepository):
        def __init__(self, root_dir) -> None:
            super().__init__(root_dir)
            self.hide_once = True

        def load_optional(self, proposal_id: str):
            if self.hide_once:
                self.hide_once = False
                return None
            return super().load_optional(proposal_id)

    raced_proposals = HideExistingOnPrecheck(tmp_path / "proposals")
    service = service_type(
        courses,
        candidates,
        raced_proposals,
        generator=FakePersonalizationGenerator(),
        event_recorder=lambda **kwargs: kwargs,
    )
    target = next(item for item in document.blocks if item.block_id == "target")

    with pytest.raises(block_regeneration.BlockRegenerationConflict):
        await service.create_proposal(
            "course-1",
            "target",
            request_id="raced-request-id",
            expected_document_revision=document.document_revision,
            expected_block_revision=target.internal_revision,
            direction="expand",
            feedback="补充方向的直观解释",
            user_id="student-b",
        )


@pytest.mark.asyncio
async def test_related_generation_failure_keeps_target_proposal(tmp_path, monkeypatch):
    service_type = getattr(block_regeneration, "PersonalizationProposalService", None)
    assert service_type is not None, "PersonalizationProposalService must be implemented"
    _storage, courses, candidates, proposals, document = canonical_repositories(tmp_path)
    generator = FakePersonalizationGenerator()
    service = service_type(
        courses,
        candidates,
        proposals,
        generator=generator,
        event_recorder=lambda **kwargs: kwargs,
    )
    create_candidate = service.regeneration_service.create_candidate

    async def fail_related_context(course_id, block_id, **kwargs):
        if block_id == "related-reasoning":
            raise block_regeneration.BlockRegenerationConflict("fake related revision conflict")
        return await create_candidate(course_id, block_id, **kwargs)

    monkeypatch.setattr(service.regeneration_service, "create_candidate", fail_related_context)
    target = next(item for item in document.blocks if item.block_id == "target")

    proposal = await service.create_proposal(
        "course-1",
        "target",
        request_id="personalize-related-failure",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        direction="expand",
        feedback="增加推导",
        user_id="student-1",
    )

    assert proposal["target_block_ids"] == ["target", "related-example"]
    assert proposal["items"][0]["block_id"] == "target"
    assert proposal["items"][0]["after"]["payload"]["markdown"] != target.payload["markdown"]


@pytest.mark.asyncio
async def test_related_blocks_start_concurrently_after_target_succeeds(tmp_path):
    class CoordinatedGenerator(FakePersonalizationGenerator):
        def __init__(self) -> None:
            super().__init__()
            self.related_started: set[str] = set()
            self.both_related_started = asyncio.Event()

        async def generate_course_block_candidate(self, **kwargs) -> str:
            block_id = kwargs["target_block"]["block_id"]
            if block_id == "target":
                return await super().generate_course_block_candidate(**kwargs)
            self.related_started.add(block_id)
            if len(self.related_started) == 2:
                self.both_related_started.set()
            await self.both_related_started.wait()
            return await super().generate_course_block_candidate(**kwargs)

    service_type = getattr(block_regeneration, "PersonalizationProposalService", None)
    _storage, courses, candidates, proposals, document = canonical_repositories(tmp_path)
    generator = CoordinatedGenerator()
    service = service_type(
        courses,
        candidates,
        proposals,
        generator=generator,
        event_recorder=lambda **kwargs: kwargs,
    )
    target = next(item for item in document.blocks if item.block_id == "target")

    proposal = await asyncio.wait_for(service.create_proposal(
        "course-1",
        "target",
        request_id="concurrent-related",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        direction="expand",
        feedback="补充推理和例子",
        user_id="student-1",
    ), timeout=0.3)

    assert set(proposal["target_block_ids"]) == {"target", "related-reasoning", "related-example"}


@pytest.mark.asyncio
async def test_related_timeout_is_best_effort_and_does_not_delay_target_proposal(tmp_path, monkeypatch):
    class HangingRelatedGenerator(FakePersonalizationGenerator):
        async def generate_course_block_candidate(self, **kwargs) -> str:
            if kwargs["target_block"]["block_id"] == "related-reasoning":
                await asyncio.Event().wait()
            return await super().generate_course_block_candidate(**kwargs)

    monkeypatch.setattr(
        block_regeneration,
        "PERSONALIZATION_RELATED_TIMEOUT_SECONDS",
        0.02,
        raising=False,
    )
    service_type = getattr(block_regeneration, "PersonalizationProposalService", None)
    _storage, courses, candidates, proposals, document = canonical_repositories(tmp_path)
    service = service_type(
        courses,
        candidates,
        proposals,
        generator=HangingRelatedGenerator(),
        event_recorder=lambda **kwargs: kwargs,
    )
    target = next(item for item in document.blocks if item.block_id == "target")

    proposal = await asyncio.wait_for(service.create_proposal(
        "course-1",
        "target",
        request_id="related-deadline",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        direction="expand",
        feedback="补充推理",
        user_id="student-1",
    ), timeout=0.3)

    assert proposal["target_block_ids"] == ["target", "related-example"]


def test_apply_selected_updates_partial_items_with_one_document_commit(tmp_path, monkeypatch):
    apply_selected = getattr(__import__("change_proposals"), "apply_selected_items", None)
    assert apply_selected is not None, "apply_selected_items must be implemented"
    storage, courses, _candidates, proposals, document = canonical_repositories(tmp_path)
    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="partial-apply",
        scope="section",
        target_block_ids=["target", "related-example", "related-summary"],
        items=proposal_items(document),
        source="personalization",
        generation_meta={"base_document_revision": document.document_revision},
    )
    selected_ids = [proposal["items"][0]["item_id"], proposal["items"][1]["item_id"]]
    monkeypatch.setattr(change_proposals_router, "get_change_proposal_repository", lambda: proposals)
    monkeypatch.setattr(change_proposals_router, "get_course_document_repository", lambda: courses)
    monkeypatch.setattr(
        change_proposals_router,
        "synchronize_teaching_representations",
        lambda _course_id: {"status": "synchronized"},
    )
    app = FastAPI()
    app.include_router(change_proposals_router.authoring_router)
    client = TestClient(app)
    saves_before = storage.save_count

    response = client.post(
        f"/courses/course-1/authoring-changes/{proposal['proposal_id']}/apply-selected",
        headers={"X-User-Id": "student-1"},
        json={
            "item_ids": selected_ids,
            "expected_document_revision": document.document_revision,
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert courses.load_document_count == 1
    assert courses.commit_document_count == 1
    assert storage.save_count == saves_before + 1
    assert result["receipt"]["affected_block_ids"] == ["related-example", "target"]
    changed_keys = result["receipt"]["revision_change"]["changed_source_keys"]
    assert "block:target" in changed_keys
    assert "block:related-example" in changed_keys
    assert "block:related-summary" not in changed_keys
    statuses = {item["block_id"]: item["status"] for item in result["proposal"]["items"]}
    assert statuses == {
        "target": "applied",
        "related-example": "applied",
        "related-summary": "pending",
    }
    updated, _ = courses.load_document("course-1")
    by_id = {item.block_id: item for item in updated.blocks}
    assert by_id["target"].payload["markdown"].endswith("已按反馈改进。")
    assert by_id["related-example"].payload["markdown"].endswith("已按反馈改进。")
    assert not by_id["related-summary"].payload["markdown"].endswith("已按反馈改进。")
    assert len(storage.course["course_operation_log"]) == 1


def test_apply_selected_revision_conflict_writes_nothing(tmp_path, monkeypatch):
    apply_selected = getattr(__import__("change_proposals"), "apply_selected_items", None)
    assert apply_selected is not None, "apply_selected_items must be implemented"
    storage, courses, _candidates, proposals, document = canonical_repositories(tmp_path)
    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="conflicting-apply",
        scope="section",
        target_block_ids=["target", "related-example", "related-summary"],
        items=proposal_items(document),
        source="personalization",
        generation_meta={"base_document_revision": document.document_revision},
    )
    selected_ids = [item["item_id"] for item in proposal["items"][:2]]
    monkeypatch.setattr(change_proposals_router, "get_change_proposal_repository", lambda: proposals)
    monkeypatch.setattr(change_proposals_router, "get_course_document_repository", lambda: courses)
    app = FastAPI()
    app.include_router(change_proposals_router.authoring_router)
    client = TestClient(app)
    course_before = deepcopy(storage.course)
    saves_before = storage.save_count

    response = client.post(
        f"/courses/course-1/authoring-changes/{proposal['proposal_id']}/apply-selected",
        headers={"X-User-Id": "student-1"},
        json={
            "item_ids": selected_ids,
            "expected_document_revision": "stale-document-revision",
        },
    )

    assert response.status_code == 409
    assert courses.commit_document_count == 0
    assert storage.save_count == saves_before
    assert storage.course == course_before
    assert all(item["status"] == "pending" for item in proposals.load(proposal["proposal_id"])["items"])


@pytest.mark.asyncio
async def test_apply_selected_rejects_latest_revision_when_proposal_is_bound_to_older_base(tmp_path):
    storage, courses, _candidates, proposals, document = canonical_repositories(tmp_path)
    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="base-bound-apply",
        scope="block",
        target_block_ids=["target"],
        items=proposal_items(document)[:1],
        source="personalization",
        generation_meta={"base_document_revision": document.document_revision},
    )
    external, _ = courses.load_document("course-1")
    unrelated = next(item for item in external.blocks if item.block_id == "other-objective")
    unrelated.payload["markdown"] = "并发更新了其他内容。"
    await courses.commit_document(
        "course-1",
        external,
        expected_revision=document.document_revision,
        operation={
            "command_id": "external-edit",
            "operation": "replace_block",
            "affected_block_ids": [unrelated.block_id],
        },
    )
    latest, _ = courses.load_document("course-1")
    commits_before = courses.commit_document_count

    with pytest.raises(ChangeProposalConflict):
        await apply_selected_items(
            proposals,
            courses,
            proposal["proposal_id"],
            [proposal["items"][0]["item_id"]],
            expected_document_revision=latest.document_revision,
            actor="student-1",
        )

    assert courses.commit_document_count == commits_before
    assert storage.course["course_document_revision"] == latest.document_revision
    assert proposals.load(proposal["proposal_id"])["items"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_apply_selected_recovers_after_final_proposal_save_failure_without_second_course_commit(tmp_path):
    class FailFinalProposalSaveOnce(ChangeProposalRepository):
        def __init__(self, root_dir) -> None:
            super().__init__(root_dir)
            self.failed = False

        def update(self, proposal_id, updater):
            preview = updater(self.load(proposal_id))
            if not self.failed and any(item.get("status") == "applied" for item in preview.get("items") or []):
                self.failed = True
                raise OSError("simulated final proposal save failure")
            return super().update(proposal_id, updater)

    storage, courses, _candidates, _proposals, document = canonical_repositories(tmp_path)
    proposals = FailFinalProposalSaveOnce(tmp_path / "flaky-proposals")
    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="recover-final-save",
        scope="block",
        target_block_ids=["target"],
        items=proposal_items(document)[:1],
        source="personalization",
        generation_meta={"base_document_revision": document.document_revision},
    )
    item_id = proposal["items"][0]["item_id"]

    with pytest.raises(OSError, match="simulated final proposal save failure"):
        await apply_selected_items(
            proposals,
            courses,
            proposal["proposal_id"],
            [item_id],
            expected_document_revision=document.document_revision,
            actor="student-1",
        )

    interrupted = proposals.load(proposal["proposal_id"])
    assert interrupted["pending_operation"]["command_id"]
    assert courses.commit_document_count == 1
    with pytest.raises(ChangeProposalConflict):
        reject_item(proposals, proposal["proposal_id"], item_id, reason="must not overtake recovery")

    recovered = await apply_selected_items(
        proposals,
        courses,
        proposal["proposal_id"],
        [item_id],
        expected_document_revision=document.document_revision,
        actor="student-1",
    )

    assert recovered["proposal"]["items"][0]["status"] == "applied"
    assert recovered["proposal"].get("pending_operation") is None
    assert courses.commit_document_count == 1
    assert storage.save_count == 1


@pytest.mark.asyncio
async def test_apply_selected_and_reject_are_serialized_across_course_commit(tmp_path):
    class PausingCommitRepository(CountingCourseRepository):
        def __init__(self, storage_obj) -> None:
            super().__init__(storage_obj)
            self.course_committed = asyncio.Event()
            self.release_commit = asyncio.Event()

        async def commit_document(self, *args, **kwargs):
            receipt = await super().commit_document(*args, **kwargs)
            self.course_committed.set()
            await self.release_commit.wait()
            return receipt

    storage, _base_courses, _candidates, proposals, document = canonical_repositories(tmp_path)
    courses = PausingCommitRepository(storage)
    proposal = create_proposal(
        proposals,
        "course-1",
        request_id="apply-reject-race",
        scope="block",
        target_block_ids=["target"],
        items=proposal_items(document)[:1],
        source="personalization",
        generation_meta={"base_document_revision": document.document_revision},
    )
    item_id = proposal["items"][0]["item_id"]
    reject_started = threading.Event()
    reject_finished = threading.Event()

    def reject_concurrently():
        reject_started.set()
        try:
            return reject_item(proposals, proposal["proposal_id"], item_id, reason="concurrent reject")
        finally:
            reject_finished.set()

    apply_task = asyncio.create_task(apply_selected_items(
        proposals,
        courses,
        proposal["proposal_id"],
        [item_id],
        expected_document_revision=document.document_revision,
        actor="student-1",
    ))
    await asyncio.wait_for(courses.course_committed.wait(), timeout=1)
    reject_task = asyncio.create_task(asyncio.to_thread(reject_concurrently))
    assert await asyncio.to_thread(reject_started.wait, 1)
    reject_finished_before_commit_release = await asyncio.to_thread(reject_finished.wait, 0.2)
    courses.release_commit.set()
    apply_result, reject_result = await asyncio.gather(
        apply_task,
        reject_task,
        return_exceptions=True,
    )

    assert reject_finished_before_commit_release is False
    assert not isinstance(apply_result, Exception)
    assert isinstance(reject_result, ChangeProposalConflict)
    assert courses.commit_document_count == 1
    assert storage.save_count == 1
    current = proposals.load(proposal["proposal_id"])
    assert current["items"][0]["status"] == "applied"
    assert len(storage.course["course_operation_log"]) == 1
