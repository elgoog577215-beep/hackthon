from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest
from fastapi import HTTPException, Request

from block_regeneration import (
    BlockRegenerationCandidateRepository,
    BlockRegenerationConflict,
    BlockRegenerationService,
)
from course_commands import CourseCommandService
from course_document import COURSE_DOCUMENT_SCHEMA
from course_repository import CourseDocumentRepository
from models import AskQuestionRequest, RegenerateContentBlockRequest
from routers import course_versions, nodes


class MemoryStorage:
    def __init__(self, course: dict) -> None:
        self.course = deepcopy(course)
        self.save_count = 0

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)
        self.save_count += 1


class SequenceGenerator:
    def __init__(self, *outputs: str) -> None:
        self.outputs = list(outputs)
        self.calls: list[dict] = []

    async def generate_course_block_candidate(self, **kwargs) -> str:
        self.calls.append(deepcopy(kwargs))
        index = min(len(self.calls) - 1, len(self.outputs) - 1)
        return self.outputs[index]


class BlockingGenerator:
    def __init__(self, output: str) -> None:
        self.output = output
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def generate_course_block_candidate(self, **_kwargs) -> str:
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return self.output


class FailOnceGenerator:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_course_block_candidate(self, **_kwargs) -> str:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("provider unavailable")
        return "向量由大小与方向共同确定，并能用坐标完整表示。"


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


async def canonical_service(tmp_path, generator: SequenceGenerator):
    storage = MemoryStorage(legacy_course())
    course_repository = CourseDocumentRepository(storage)
    preview = course_repository.document_envelope("course-1")
    await course_repository.migrate_legacy_course(
        "course-1",
        expected_source_checksum=preview["migration"]["source_checksum"],
    )
    candidate_repository = BlockRegenerationCandidateRepository(tmp_path / "candidates")
    service = BlockRegenerationService(
        course_repository,
        candidate_repository,
        generator=generator,
    )
    document, _ = course_repository.load_document("course-1")
    target = next(block for block in document.blocks if block.block_id == "block-1")
    return storage, course_repository, candidate_repository, service, document, target


@pytest.mark.asyncio
async def test_candidate_is_isolated_preserves_block_contract_and_is_request_idempotent(tmp_path):
    generator = SequenceGenerator("向量不仅有大小，还以方向区分其几何作用。")
    storage, _repository, _candidates, service, document, target = await canonical_service(tmp_path, generator)
    saves_before = storage.save_count

    candidate = await service.create_candidate(
        "course-1",
        "block-1",
        request_id="request-1",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        instruction="把定义讲得更清楚",
        user_id="user-1",
    )
    repeated = await service.create_candidate(
        "course-1",
        "block-1",
        request_id="request-1",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        instruction="把定义讲得更清楚",
        user_id="user-1",
    )

    assert candidate["status"] == "ready"
    assert repeated == candidate
    assert len(generator.calls) == 1
    assert storage.save_count == saves_before
    proposed = candidate["proposed_block"]
    assert proposed["block_id"] == target.block_id
    assert proposed["kind"] == target.kind
    assert proposed["role"] == target.role
    assert proposed["position"] == target.position
    assert proposed["objective_refs"] == target.objective_refs
    current, _ = service.course_repository.load_document("course-1")
    assert current.document_revision == document.document_revision
    assert current.blocks[0].payload == target.payload


@pytest.mark.asyncio
async def test_candidate_request_id_reuse_with_different_payload_returns_409(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routers import block_regeneration as regeneration_router

    generator = SequenceGenerator(
        "A vector has magnitude and direction and can be represented with coordinates."
    )
    _storage, _repository, _candidates, service, document, target = await canonical_service(
        tmp_path,
        generator,
    )
    await service.create_candidate(
        "course-1",
        "block-1",
        request_id="reused-request-id",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        instruction="explain the definition",
        action_type="rewrite",
        user_id="user-1",
    )
    monkeypatch.setattr(regeneration_router, "get_block_regeneration_service", lambda: service)
    app = FastAPI()
    app.include_router(regeneration_router.router)

    response = TestClient(app).post(
        "/courses/course-1/blocks/block-1/regeneration-candidates",
        headers={"X-User-Id": "user-1"},
        json={
            "request_id": "reused-request-id",
            "expected_document_revision": document.document_revision,
            "expected_block_revision": target.internal_revision,
            "instruction": "use simpler examples based on new feedback",
            "action_type": "simplify",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "request_id reused with different payload"
    assert len(generator.calls) == 1


@pytest.mark.asyncio
async def test_quality_gate_retries_once_and_blocks_unchanged_candidate(tmp_path):
    original = "向量同时具有大小和方向。"
    generator = SequenceGenerator(original, original)
    storage, _repository, _candidates, service, document, target = await canonical_service(tmp_path, generator)
    saves_before = storage.save_count

    candidate = await service.create_candidate(
        "course-1",
        "block-1",
        request_id="request-quality-fail",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        instruction="改写定义",
        user_id="user-1",
    )

    assert candidate["status"] == "quality_failed"
    assert len(candidate["attempts"]) == 2
    assert len(generator.calls) == 2
    assert generator.calls[1]["quality_feedback"] == ["候选与原文没有实质变化"]
    with pytest.raises(BlockRegenerationConflict):
        await service.apply_candidate("course-1", "block-1", candidate["candidate_id"], actor="user-1")
    assert storage.save_count == saves_before


@pytest.mark.asyncio
async def test_quality_retry_can_repair_candidate(tmp_path):
    original = "向量同时具有大小和方向。"
    generator = SequenceGenerator(original, "向量由大小与方向共同确定，缺一不可。")
    _storage, _repository, _candidates, service, document, target = await canonical_service(tmp_path, generator)

    candidate = await service.create_candidate(
        "course-1",
        "block-1",
        request_id="request-quality-repair",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        instruction="改写定义",
        user_id="user-1",
    )

    assert candidate["status"] == "ready"
    assert len(candidate["attempts"]) == 2
    assert candidate["quality_report"]["passed"] is True


@pytest.mark.asyncio
async def test_candidate_is_persisted_before_model_finishes_and_concurrent_request_is_deduplicated(tmp_path):
    generator = BlockingGenerator("向量由大小和方向共同确定，并能用于描述位移。")
    _storage, _repository, candidates, service, document, target = await canonical_service(
        tmp_path, generator
    )
    request = {
        "request_id": "request-inflight",
        "expected_document_revision": document.document_revision,
        "expected_block_revision": target.internal_revision,
        "instruction": "补充定义",
        "user_id": "user-1",
    }

    running = asyncio.create_task(service.create_candidate("course-1", "block-1", **request))
    await generator.started.wait()
    candidate_id = candidates.candidate_id_for("course-1", "block-1", "request-inflight")
    persisted = candidates.load(candidate_id)
    repeated = await service.create_candidate("course-1", "block-1", **request)

    assert persisted["status"] == "generating"
    assert repeated["status"] == "generating"
    assert repeated["candidate_id"] == candidate_id
    assert generator.calls == 1

    generator.release.set()
    completed = await running
    assert completed["status"] == "ready"


@pytest.mark.asyncio
async def test_runtime_failure_is_persisted_and_retry_reuses_same_candidate(tmp_path):
    generator = FailOnceGenerator()
    _storage, _repository, candidates, service, document, target = await canonical_service(
        tmp_path, generator
    )
    failed = await service.create_candidate(
        "course-1",
        "block-1",
        request_id="request-runtime-failure",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        instruction="补充定义",
        user_id="user-1",
    )

    assert failed["status"] == "generation_failed"
    assert failed["retryable"] is True
    assert failed["failure_code"] == "provider_error"
    assert candidates.load(failed["candidate_id"])["status"] == "generation_failed"

    recovered = await service.retry_candidate(
        "course-1",
        "block-1",
        failed["candidate_id"],
        user_id="user-1",
    )

    assert recovered["candidate_id"] == failed["candidate_id"]
    assert recovered["status"] == "ready"
    assert recovered["retry_count"] == 1
    assert generator.calls == 2


@pytest.mark.asyncio
async def test_old_process_generation_is_exposed_as_retryable_interruption(tmp_path):
    generator = SequenceGenerator("不会被调用")
    _storage, _repository, candidates, service, document, target = await canonical_service(
        tmp_path, generator
    )
    candidate_id = candidates.candidate_id_for("course-1", "block-1", "request-old-process")
    candidates.create({
        "candidate_id": candidate_id,
        "request_id": "request-old-process",
        "course_id": "course-1",
        "block_id": "block-1",
        "status": "generating",
        "expected_document_revision": document.document_revision,
        "expected_block_revision": target.internal_revision,
        "generation_owner": "stopped-process",
        "generation_run_id": "stopped-run",
        "created_at": "2026-07-14T00:00:00+00:00",
        "updated_at": "2026-07-14T00:00:00+00:00",
    })

    recovered = service.get_latest_candidate(
        "course-1",
        "block-1",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
    )

    assert recovered["candidate_id"] == candidate_id
    assert recovered["status"] == "generation_failed"
    assert recovered["retryable"] is True
    assert recovered["failure_code"] == "process_interrupted"
    assert generator.calls == []


@pytest.mark.asyncio
async def test_generating_candidate_cannot_be_rejected(tmp_path):
    generator = BlockingGenerator("向量由大小和方向共同确定，并能用于描述位移。")
    _storage, _repository, candidates, service, document, target = await canonical_service(
        tmp_path, generator
    )
    running = asyncio.create_task(service.create_candidate(
        "course-1",
        "block-1",
        request_id="request-reject-inflight",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        instruction="补充定义",
        user_id="user-1",
    ))
    await generator.started.wait()
    candidate_id = candidates.candidate_id_for("course-1", "block-1", "request-reject-inflight")

    with pytest.raises(BlockRegenerationConflict) as exc:
        service.reject_candidate("course-1", "block-1", candidate_id)

    assert exc.value.candidate["status"] == "generating"
    generator.release.set()
    assert (await running)["status"] == "ready"


@pytest.mark.asyncio
async def test_apply_uses_course_command_preserves_identity_and_is_idempotent(tmp_path):
    generator = SequenceGenerator("向量由大小和方向共同确定，并可用坐标表示。")
    storage, repository, _candidates, service, document, target = await canonical_service(tmp_path, generator)
    candidate = await service.create_candidate(
        "course-1",
        "block-1",
        request_id="request-apply",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        instruction="补足定义",
        user_id="user-1",
    )
    saves_before = storage.save_count

    result = await service.apply_candidate("course-1", "block-1", candidate["candidate_id"], actor="user-1")
    repeated = await service.apply_candidate("course-1", "block-1", candidate["candidate_id"], actor="user-1")

    assert repeated["receipt"] == result["receipt"]
    assert storage.save_count == saves_before + 1
    updated, _ = repository.load_document("course-1")
    updated_target = next(block for block in updated.blocks if block.block_id == "block-1")
    assert updated_target.block_id == target.block_id
    assert updated_target.kind == target.kind
    assert updated_target.role == target.role
    assert updated_target.section_id == target.section_id
    assert updated_target.position == target.position
    assert updated_target.objective_refs == target.objective_refs
    assert updated_target.payload["markdown"] == "向量由大小和方向共同确定，并可用坐标表示。"
    assert updated_target.internal_revision != target.internal_revision
    assert updated.document_revision != document.document_revision
    assert storage.course["current_course_version_id"] == updated.document_revision
    assert result["document"]["current_course_version_id"] == updated.document_revision
    assert len(storage.course["course_operation_log"]) == 1
    assert "nodes" not in storage.course


@pytest.mark.asyncio
async def test_apply_route_reconciles_representations_after_canonical_write(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from representation_compiler import compile_core_representations
    from routers import block_regeneration as regeneration_router
    from teaching_representations import TeachingRepresentationRepository

    generator = SequenceGenerator(
        "A vector is determined by magnitude and direction, with coordinates as one representation."
    )
    _storage, course_repository, _candidates, service, document, target = await canonical_service(
        tmp_path,
        generator,
    )
    representation_repository = TeachingRepresentationRepository(tmp_path / "representations")
    compile_core_representations(
        document,
        course_repository.load_course_view("course-1"),
        representation_repository,
    )
    candidate = await service.create_candidate(
        "course-1",
        "block-1",
        request_id="request-route-reconcile",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        instruction="improve the definition",
        user_id="user-1",
    )
    monkeypatch.setattr(regeneration_router, "get_block_regeneration_service", lambda: service)
    monkeypatch.setattr(
        regeneration_router,
        "get_course_document_repository",
        lambda: course_repository,
    )
    monkeypatch.setattr(
        regeneration_router,
        "teaching_representation_repository",
        representation_repository,
        raising=False,
    )
    monkeypatch.setattr(
        regeneration_router,
        "propose_kb_linkage_from_block_change",
        lambda *_args, **_kwargs: None,
    )
    app = FastAPI()
    app.include_router(regeneration_router.router)

    response = TestClient(app).post(
        f"/courses/course-1/blocks/block-1/regeneration-candidates/{candidate['candidate_id']}/apply",
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    reconcile = response.json()["representation_reconcile"]
    assert reconcile["status"] == "reconciled"
    assert reconcile["stale_representation_ids"]
    registry = representation_repository.load("course-1")
    assert any(item.status == "stale" for item in registry.representations)


@pytest.mark.asyncio
async def test_apply_marks_candidate_stale_when_course_changed(tmp_path):
    generator = SequenceGenerator("候选内容具有足够差异，并准备稍后应用。")
    _storage, repository, candidates, service, document, target = await canonical_service(tmp_path, generator)
    candidate = await service.create_candidate(
        "course-1",
        "block-1",
        request_id="request-stale",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        instruction="改进定义",
        user_id="user-1",
    )
    await CourseCommandService(repository).replace_block(
        "course-1",
        command_id="external-edit",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        block_id="block-1",
        payload={**target.payload, "markdown": "用户在另一处保存的新内容。"},
        actor="user-2",
    )

    with pytest.raises(BlockRegenerationConflict) as exc:
        await service.apply_candidate("course-1", "block-1", candidate["candidate_id"], actor="user-1")

    assert exc.value.candidate["status"] == "stale"
    assert candidates.load(candidate["candidate_id"])["status"] == "stale"
    current, _ = repository.load_document("course-1")
    assert current.blocks[0].payload["markdown"] == "用户在另一处保存的新内容。"


@pytest.mark.asyncio
async def test_legacy_block_route_rejects_canonical_course_before_ai(monkeypatch):
    class CanonicalRepository:
        def load_raw(self, _course_id: str) -> dict:
            return {"course_schema_version": COURSE_DOCUMENT_SCHEMA, "course_document": {}}

        def is_canonical(self, _raw: dict) -> bool:
            return True

    monkeypatch.setattr(nodes, "get_course_document_repository", lambda: CanonicalRepository())
    request = Request({"type": "http", "headers": []})

    with pytest.raises(HTTPException) as exc:
        await nodes.regenerate_node_content_block(
            "course-1",
            "objective-1",
            "block-1",
            RegenerateContentBlockRequest(requirement="改写"),
            request,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "canonical_block_regeneration_required"


@pytest.mark.asyncio
async def test_old_whole_course_regeneration_rejects_canonical_course_before_task_creation(monkeypatch):
    class CanonicalRepository:
        def load_raw(self, _course_id: str) -> dict:
            return {"course_schema_version": COURSE_DOCUMENT_SCHEMA, "course_document": {}}

        def is_canonical(self, _raw: dict) -> bool:
            return True

    class TaskManagerProbe:
        called = False

        async def create_regeneration_job(self, *_args, **_kwargs):
            self.called = True

    async def course_exists(_course_id: str) -> dict:
        return {"course_id": "course-1"}

    task_manager = TaskManagerProbe()
    monkeypatch.setattr(course_versions, "get_course_document_repository", lambda: CanonicalRepository())
    monkeypatch.setattr(course_versions, "get_course_or_404", course_exists)

    with pytest.raises(HTTPException) as exc:
        await course_versions.regenerate_course(
            "course-1",
            course_versions.RegenerateCourseRequest(reason="旧整课重生成"),
            task_manager,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "canonical_block_regeneration_required"
    assert task_manager.called is False


def test_ai_teacher_accepts_stable_block_entrypoint():
    request = AskQuestionRequest(
        course_id="course-1",
        entrypoint="block",
        node_id="objective-1",
        question="解释当前块",
        context_ref={
            "content_anchor": {
                "block_id": "block-1",
                "block_revision_id": "cbr-1",
            }
        },
    )

    assert request.entrypoint == "block"
