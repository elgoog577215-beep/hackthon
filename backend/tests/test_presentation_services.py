from __future__ import annotations

import asyncio
import hashlib
import json
import re
from copy import deepcopy

import pytest

from course_document import document_from_legacy_course
from presentation_generation import (
    GenerationSession,
    PresentationQualityBlocked,
    PresentationService,
    PresentationServiceConflict,
)
from presentation_models import (
    ChatPresentationRequest,
    CreatePresentationRequest,
    FinalizePresentationRequest,
    GeneratePresentationRequest,
    GenerationWorkingSnapshot,
    PresentationDeck,
    PresentationEvent,
    PresentationScope,
    RevisionCommand,
    Slide,
    SlideSourceRefs,
)
from presentation_quality import evaluate_presentation_quality, revision_checksum
from presentation_repository import IdempotencyKeyReuseConflict, PresentationRepository
from presentation_source import (
    project_presentation_source,
    source_packet,
    source_snapshot_sha256,
)


class _HealthyPresentationAI:
    async def _call_llm(self, prompt: str, **_kwargs) -> str:
        if prompt.lstrip().startswith("{"):
            request = json.loads(prompt)
            slide = request["slide"]
            return json.dumps({
                "changes": {
                    "speaker_notes": f"{slide.get('speaker_notes', '')}\nAI 修改已应用。",
                },
            }, ensure_ascii=False)
        layout_match = re.search(r"页面版式：(L\d{2})", prompt)
        layout = layout_match.group(1) if layout_match else "L04"
        title_match = re.search(r"标题：([^\n]+)", prompt)
        key_match = re.search(r"核心信息：([^\n]+)", prompt)
        block_type = {
            "L02": "bullets", "L04": "callout", "L05": "comparison", "L06": "bullets",
            "L07": "code", "L08": "comparison", "L09": "exercise", "L10": "bullets",
        }.get(layout)
        blocks = [] if block_type is None else [{
            "block_id": f"stub-{layout}", "type": block_type, "title": "课程要点",
            "content": "来自当前页面绑定的冻结课程来源。",
            "items": ["解释概念", "联系例子"] if block_type in {"bullets", "exercise"} else [],
            "metadata": {"left": "常见误区", "right": "正确理解"} if block_type == "comparison" else {},
        }]
        return json.dumps({
            "title": title_match.group(1) if title_match else "课件页面",
            "subtitle": "", "key_message": key_match.group(1) if key_match else "课程核心信息",
            "blocks": blocks, "speaker_notes": "依据当前页冻结来源讲授。",
        }, ensure_ascii=False)

    @staticmethod
    def _extract_json(response: str) -> dict:
        return json.loads(response)


class _NullPresentationAI:
    async def _call_llm(self, _prompt: str, **_kwargs):
        return None


class _FailingPresentationAI:
    async def _call_llm(self, _prompt: str, **_kwargs):
        raise RuntimeError("400 invalid model deepseek-ai/DeepSeek-V4-Flash")


class _IrregularBlockPresentationAI:
    async def _call_llm(self, _prompt: str, **_kwargs):
        return json.dumps({
            "title": "规范化边界",
            "subtitle": None,
            "key_message": "只规范化已知字段",
            "blocks": [
                  {
                      "block_id": 101,
                      "type": "text",
                      "title": 202,
                      "content": "int main() {\n    int x = 1;\n    return x;\n}",
                    "items": [],
                    "metadata": {},
                },
                {
                    "type": "bullets",
                    "title": "误区辨析",
                    "content": None,
                    "items": [
                        {"error": "空指针可以直接使用", "correction": "使用前必须判空"},
                        {"unknown": {"nested": "不可序列化为任意文本"}},
                    ],
                    "metadata": None,
                },
                {
                    "block_id": None,
                    "type": "callout",
                    "title": None,
                    "content": None,
                    "items": [],
                    "metadata": None,
                },
            ],
            "speaker_notes": "保持现有质量门。",
        }, ensure_ascii=False)

    @staticmethod
    def _extract_json(response: str) -> dict:
        return json.loads(response)


class RecordingPresentationRepository(PresentationRepository):
    def __init__(self, root_dir):
        super().__init__(root_dir)
        self.persistence_order: list[tuple[str, int]] = []

    def save_working(self, deck_id, snapshot, **kwargs):
        result = super().save_working(deck_id, snapshot, **kwargs)
        self.persistence_order.append(("working", int(result["event_seq"])))
        return result

    def append_event(self, deck_id, event, **kwargs):
        result = super().append_event(deck_id, event, **kwargs)
        self.persistence_order.append(("event", int(result["event_seq"])))
        return result


class FailOnceAppendPresentationRepository(PresentationRepository):
    def __init__(self, root_dir):
        super().__init__(root_dir)
        self.fail_next_append = False

    def append_event(self, deck_id, event, **kwargs):
        if self.fail_next_append:
            self.fail_next_append = False
            raise OSError("injected event append failure")
        return super().append_event(deck_id, event, **kwargs)


def _course(*, publication_allowed: bool = True) -> dict:
    legacy = {
        "course_id": "course-service-1",
        "course_name": "C语言：指针与内存",
        "current_course_version_id": "cv3",
        "publication_allowed": publication_allowed,
        "is_published": publication_allowed,
        "course_blueprint": {"positioning": "从内存模型理解指针"},
        "nodes": [
            {
                "node_id": "chapter-1",
                "parent_node_id": "root",
                "node_name": "第一章 指针",
                "node_level": 1,
                "node_content": "",
            },
            {
                "node_id": "section-1",
                "parent_node_id": "chapter-1",
                "node_name": "指针与地址",
                "node_level": 2,
                "learning_objective": "解释地址、指针和值的关系",
                "objective_id": "obj-pointer",
                "node_content": "## 指针\n\n指针变量保存另一个变量的内存地址。",
                "content_blocks": [{
                    "block_id": "block-pointer",
                    "type": "concept",
                    "title": "指针定义",
                    "content": "int x = 10; int *p = &x; 指针 p 保存 x 的地址。",
                    "metadata": {},
                }],
            },
        ],
        "learning_assets": {
            "questions": [{"question_id": "q1", "node_id": "section-1", "prompt": "&x 表示什么？"}],
            "misconceptions": [{"misconception_id": "m1", "node_id": "section-1", "text": "空指针可以直接解引用"}],
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


async def _generated_service(
    tmp_path,
    *,
    publication_allowed: bool = True,
    repository_type=PresentationRepository,
    offline: bool = False,
    ai_factory=_HealthyPresentationAI,
):
    course = _course(publication_allowed=publication_allowed)
    repository = repository_type(tmp_path / "presentations")
    service = PresentationService(
        repository,
        course_loader=lambda _course_id: course,
        source_projector=project_presentation_source,
        source_packet_builder=source_packet,
        ai_factory=None if offline else ai_factory,
    )
    manifest = await service.create_presentation(
        course["course_id"],
        CreatePresentationRequest(
            request_id="create-request-1",
            title="指针课件",
            scope=PresentationScope(type="chapter", section_ids=["chapter-1"]),
            template_id="lingzhi-engineering",
        ),
    )
    deck_id = manifest["deck_id"]
    session = await service.prepare_generation(
        deck_id,
        GeneratePresentationRequest(request_id="generate-request-1", page_budget=7),
    )
    events = [event async for event in service.stream_generation(deck_id, session.generation_id)]
    return service, repository, deck_id, events


def _serialized_digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


@pytest.mark.asyncio
async def test_create_request_reuses_only_the_exact_course_and_request_intent(tmp_path):
    course = _course()
    repository = PresentationRepository(tmp_path / "create-idempotency")
    service = PresentationService(
        repository,
        course_loader=lambda _course_id: course,
        source_projector=project_presentation_source,
        source_packet_builder=source_packet,
        ai_factory=_HealthyPresentationAI,
    )
    base = {
        "request_id": "create-intent-request",
        "title": "指针课件",
        "scope": PresentationScope(type="chapter", section_ids=["chapter-1"]),
        "purpose": "teaching",
        "template_id": "lingzhi-engineering",
        "page_budget": 7,
        "extra_requirements": "突出地址和值的关系",
    }
    created = await service.create_presentation(course["course_id"], CreatePresentationRequest(**base))
    repeated = await service.create_presentation(course["course_id"], CreatePresentationRequest(**base))
    assert repeated["deck_id"] == created["deck_id"]
    assert len(repository.list_decks(course["course_id"])) == 1

    variants = [
        {"title": "另一套课件"},
        {"scope": PresentationScope(type="course", section_ids=[])},
        {"purpose": "self_study"},
        {"template_id": "lingzhi-academic"},
        {"page_budget": 9},
        {"extra_requirements": "改为学生自学语气"},
    ]
    for override in variants:
        with pytest.raises(IdempotencyKeyReuseConflict, match="idempotency_key_reused"):
            await service.create_presentation(
                course["course_id"],
                CreatePresentationRequest(**{**base, **override}),
            )

    course["current_course_version_id"] = "cv4"
    with pytest.raises(IdempotencyKeyReuseConflict, match="idempotency_key_reused"):
        await service.create_presentation(course["course_id"], CreatePresentationRequest(**base))


@pytest.mark.asyncio
async def test_get_and_list_mark_old_course_source_without_mutating_snapshot(tmp_path):
    course = _course()
    repository = PresentationRepository(tmp_path / "source-freshness")
    service = PresentationService(
        repository,
        course_loader=lambda _course_id: course,
        source_projector=project_presentation_source,
        source_packet_builder=source_packet,
        ai_factory=_HealthyPresentationAI,
    )
    manifest = await service.create_presentation(
        course["course_id"],
        CreatePresentationRequest(
            request_id="source-version-create",
            title="指针课件",
            scope=PresentationScope(type="chapter", section_ids=["chapter-1"]),
        ),
    )
    deck_id = manifest["deck_id"]
    frozen_ref = deepcopy(manifest["source_ref"])
    frozen_source = repository.load_source_snapshot(deck_id)

    current = await service.get_presentation(deck_id)
    assert current["source_outdated"] is False
    assert current["current_course_version_id"] == "cv3"
    assert current["manifest"]["source_outdated"] is False

    course["current_course_version_id"] = "cv4"
    stale = await service.get_presentation(deck_id)
    listed = await service.list_presentations(course["course_id"])
    assert stale["source_outdated"] is True
    assert stale["current_course_version_id"] == "cv4"
    assert stale["manifest"]["source_outdated"] is True
    assert listed[0]["source_outdated"] is True
    assert listed[0]["current_course_version_id"] == "cv4"
    assert repository.load_manifest(deck_id)["source_ref"] == frozen_ref
    assert repository.load_source_snapshot(deck_id) == frozen_source
    assert source_snapshot_sha256(repository.load_source_snapshot(deck_id)) == frozen_ref["source_snapshot_sha256"]


@pytest.mark.asyncio
async def test_append_event_failure_rolls_back_sequence_without_losing_working_content(tmp_path):
    course = _course()
    snapshot, source_ref = project_presentation_source(
        course,
        PresentationScope(type="chapter", section_ids=["chapter-1"]),
    )
    repository = FailOnceAppendPresentationRepository(tmp_path / "event-rollback")
    deck = PresentationDeck(
        deck_id="deck-event-rollback",
        course_id=course["course_id"],
        title="事件回滚课件",
        source_ref=source_ref,
        scope=PresentationScope(type="chapter", section_ids=["chapter-1"]),
    )
    repository.create_deck(deck, snapshot)
    slide = Slide(
        slide_id="slide-event-1",
        position=0,
        layout_id="L04",
        status="ready",
        title="计划中的标题",
        source_refs=SlideSourceRefs(section_ids=["section-1"]),
    )
    working = GenerationWorkingSnapshot(
        generation_id="gen-event-rollback",
        deck_id=deck.deck_id,
        event_seq=1,
        slide_order=[slide.slide_id],
        slides=[slide],
    )
    repository.save_working(deck.deck_id, working)
    repository.append_event(
        deck.deck_id,
        PresentationEvent(
            event_type="deck_outline",
            deck_id=deck.deck_id,
            generation_id=working.generation_id,
            event_seq=1,
            outline_revision=1,
        ),
    )
    working.slides[0] = working.slides[0].model_copy(update={"title": "已经生成并必须保留的内容"})
    session = GenerationSession(
        deck_id=deck.deck_id,
        course_id=course["course_id"],
        generation_id=working.generation_id,
        request=GeneratePresentationRequest(request_id="event-rollback-request", page_budget=3),
        source_snapshot=snapshot,
        working=working,
        outline=[],
    )
    service = PresentationService(repository, ai_factory=None)

    repository.fail_next_append = True
    with pytest.raises(OSError, match="injected event append failure"):
        await service._persist_event(
            session,
            "slide_upsert",
            {"slide": working.slides[0].model_dump(mode="json")},
        )

    rolled_back = repository.load_working(deck.deck_id, working.generation_id)
    assert rolled_back["event_seq"] == 1
    assert rolled_back["slides"][0]["title"] == "已经生成并必须保留的内容"
    assert [event["event_seq"] for event in repository.replay_events(deck.deck_id, working.generation_id)] == [1]

    event = await service._persist_event(
        session,
        "slide_upsert",
        {"slide": session.working.slides[0].model_dump(mode="json")},
    )
    assert event.event_seq == 2
    assert [item["event_seq"] for item in repository.replay_events(deck.deck_id, working.generation_id)] == [1, 2]
    assert repository.load_working(deck.deck_id, working.generation_id)["slides"][0]["title"] == "已经生成并必须保留的内容"


@pytest.mark.asyncio
async def test_generation_persists_ordered_events_and_model_draft(tmp_path):
    service, repository, deck_id, events = await _generated_service(
        tmp_path,
        repository_type=RecordingPresentationRepository,
    )

    assert events[0]["event_type"] == "deck_outline"
    assert events[0]["payload"]["slide_order"] == [
        slide["slide_id"] for slide in events[0]["payload"]["slides"]
    ]
    assert all("blocks" in slide and "source_refs" in slide for slide in events[0]["payload"]["slides"])
    assert events[-1]["event_type"] == "generation_complete"
    assert "export_ready" not in [event["event_type"] for event in events]
    assert [event["event_seq"] for event in events] == list(range(1, len(events) + 1))
    assert any(event["event_type"] == "slide_upsert" for event in events)
    assert all(
        event["payload"].get("generation_mode") == "llm"
        for event in events if event["event_type"] == "slide_upsert" and event["payload"]["slide"]["status"] == "ready"
    )
    assert repository.replay_events(deck_id, events[0]["generation_id"], after_seq=2)[0]["event_seq"] == 3
    assert repository.persistence_order == [
        item
        for sequence in range(1, len(events) + 1)
        for item in (("working", sequence), ("event", sequence))
    ]

    state = await service.get_presentation(deck_id)
    assert state["manifest"]["active_generation_id"] is None
    assert state["active_revision"]["revision_id"] == events[-1]["payload"]["revision"]["revision_id"]
    assert state["active_revision"]["slides"]


@pytest.mark.asyncio
async def test_offline_fallback_is_visible_draft_but_cannot_export(tmp_path):
    service, repository, deck_id, events = await _generated_service(tmp_path, offline=True)
    revision = repository.get_revision(deck_id)
    assert all(
        event["payload"].get("generation_mode") == "deterministic_fallback"
        for event in events if event["event_type"] == "slide_upsert"
    )
    with pytest.raises(PresentationQualityBlocked) as blocked:
        await service.finalize_presentation(
            deck_id,
            FinalizePresentationRequest(
                command_id="offline-finalize-command",
                expected_revision_id=revision["revision_id"],
                render_measurement={
                    "revision_checksum": revision_checksum(revision),
                    "slide_count": len(revision["slides"]),
                    "overflow": False,
                    "collision": False,
                },
            ),
        )
    assert any(
        issue["code"] == "deterministic_fallback_export_blocked"
        for issue in blocked.value.report["issues"]
    )


def test_page_packet_and_prompt_only_include_the_slides_bound_sources(tmp_path):
    service = PresentationService(PresentationRepository(tmp_path / "page-packet"), ai_factory=None)
    packet = {
        "sections": [{"section_id": "s1", "title": "第一节"}, {"section_id": "s2", "title": "第二节"}],
        "blocks": [
            {"block_id": "b1", "section_id": "s1", "payload": {"markdown": "第一节私有内容"}},
            {"block_id": "b2", "section_id": "s2", "payload": {"markdown": "第二节绑定内容"}},
        ],
        "objectives": [
            {"objective_id": "o1", "section_id": "s1", "text": "第一节目标"},
            {"objective_id": "o2", "section_id": "s2", "text": "第二节目标"},
        ],
        "assets": [], "misconceptions": [], "practices": [], "questions": [],
    }
    slide = Slide(
        slide_id="slide-bound", position=0, layout_id="L04", title="第二节概念",
        source_refs=SlideSourceRefs(section_ids=["s2"], block_ids=["b2"], objective_ids=["o2"]),
    )
    page_packet = service._page_packet(slide, packet)
    prompt = service._page_prompt(slide, page_packet)
    assert [item["block_id"] for item in page_packet["blocks"]] == ["b2"]
    assert [item["objective_id"] for item in page_packet["objectives"]] == ["o2"]
    assert "第二节绑定内容" in prompt
    assert "第一节私有内容" not in prompt


@pytest.mark.asyncio
async def test_provider_empty_response_marks_pages_failed_instead_of_forging_ready(tmp_path):
    _service, repository, deck_id, events = await _generated_service(
        tmp_path,
        ai_factory=_NullPresentationAI,
    )
    page_events = [event for event in events if event["event_type"] == "slide_upsert"]
    assert page_events
    assert all(event["payload"]["slide"]["status"] == "failed" for event in page_events)
    assert all(
        any(issue["code"] == "model_unavailable" for issue in event["payload"]["slide"]["quality"]["issues"])
        for event in page_events
    )
    quality = repository.get_deck(deck_id)["quality"]
    assert quality["status"] == "blocked"
    assert any(issue["code"] == "model_unavailable" for issue in quality["issues"])
    assert not any(issue["code"] == "layout_required_slot_missing" for issue in quality["issues"])


@pytest.mark.asyncio
async def test_provider_error_is_preserved_in_the_deck_quality_report(tmp_path):
    _service, repository, deck_id, _events = await _generated_service(
        tmp_path,
        ai_factory=_FailingPresentationAI,
    )

    quality = repository.get_deck(deck_id)["quality"]
    provider_issues = [issue for issue in quality["issues"] if issue["code"] == "model_unavailable"]

    assert provider_issues
    assert all("400 invalid model" in issue["message"] for issue in provider_issues)
    assert not any(issue["code"] == "layout_required_slot_missing" for issue in quality["issues"])


@pytest.mark.asyncio
async def test_model_blocks_are_safely_normalized_before_schema_validation(tmp_path):
    service = PresentationService(PresentationRepository(tmp_path / "normalize-blocks"))
    slide = Slide(
        slide_id="slide-normalize",
        position=0,
        layout_id="L04",
        title="规范化测试",
        source_refs=SlideSourceRefs(section_ids=["section-1"]),
    )

    normalized, used_fallback = await service._fill_slide(
        slide,
        {"blocks": [], "objectives": []},
        _IrregularBlockPresentationAI(),
        asyncio.Semaphore(1),
    )

    assert used_fallback is False
    assert normalized.status == "ready"
    assert normalized.blocks[0].block_id == "101"
    assert normalized.blocks[0].title == "202"
    assert normalized.blocks[0].content == "int main() {\n    int x = 1;\n    return x;\n}"
    assert normalized.blocks[1].block_id == "slide-normalize-model-block-2"
    assert normalized.blocks[1].content == ""
    assert normalized.blocks[1].items == ["错误：空指针可以直接使用；纠正：使用前必须判空"]
    assert normalized.blocks[1].metadata == {}
    assert normalized.blocks[2].block_id == "slide-normalize-model-block-3"
    assert normalized.blocks[2].content == ""
    assert normalized.blocks[2].metadata == {}


@pytest.mark.asyncio
async def test_finalize_rejects_incomplete_browser_measurement(tmp_path):
    service, repository, deck_id, _events = await _generated_service(tmp_path)
    revision = repository.get_revision(deck_id)
    with pytest.raises(PresentationQualityBlocked) as blocked:
        await service.finalize_presentation(
            deck_id,
            FinalizePresentationRequest(
                command_id="incomplete-measurement-command",
                expected_revision_id=revision["revision_id"],
                render_measurement={
                    "revision_checksum": revision_checksum(revision),
                    "slide_count": len(revision["slides"]),
                },
            ),
        )
    assert any(issue["code"] == "render_measurement_incomplete" for issue in blocked.value.report["issues"])


@pytest.mark.asyncio
async def test_proposal_is_current_page_only_append_only_and_idempotent(tmp_path):
    service, repository, deck_id, _events = await _generated_service(tmp_path)
    before = (await service.get_presentation(deck_id))["active_revision"]
    target = next(slide for slide in before["slides"] if slide["layout_id"] == "L04")
    proposal = await service.create_proposal(
        deck_id,
        ChatPresentationRequest(
            request_id="proposal-request-1",
            expected_revision_id=before["revision_id"],
            scope="slide",
            slide_ids=[target["slide_id"]],
            prompt="补一个贴近课堂的例子",
        ),
    )
    command = RevisionCommand(command_id="apply-command-1", expected_revision_id=before["revision_id"])
    first = await service.apply_proposal(deck_id, proposal["proposal_id"], command)
    repeated = await service.apply_proposal(deck_id, proposal["proposal_id"], command)

    assert repeated == first
    after = repository.get_revision(deck_id, first["revision_id"])
    changed = [slide["slide_id"] for slide, old in zip(after["slides"], before["slides"]) if slide != old]
    assert changed == [target["slide_id"]]
    assert next(slide for slide in after["slides"] if slide["slide_id"] == target["slide_id"])["source_refs"] == target["source_refs"]
    with pytest.raises(PresentationServiceConflict, match="版本已变化"):
        await service.create_proposal(
            deck_id,
            ChatPresentationRequest(
                request_id="proposal-request-2",
                expected_revision_id=before["revision_id"],
                scope="slide",
                slide_ids=[target["slide_id"]],
                prompt="精简本页",
            ),
        )


@pytest.mark.asyncio
async def test_mutating_commands_reject_an_active_generation(tmp_path):
    service, repository, deck_id, _events = await _generated_service(tmp_path)
    before = repository.get_revision(deck_id)
    target = next(slide for slide in before["slides"] if slide["layout_id"] == "L04")
    proposal = await service.create_proposal(
        deck_id,
        ChatPresentationRequest(
            request_id="proposal-before-generation",
            expected_revision_id=before["revision_id"],
            scope="slide",
            slide_ids=[target["slide_id"]],
            prompt="补一个例子",
        ),
    )

    gate = asyncio.Event()

    class SlowAI:
        async def _call_llm(self, *_args, **_kwargs):
            await gate.wait()
            return None

    service.ai_factory = lambda: SlowAI()
    session = await service.prepare_generation(
        deck_id,
        GeneratePresentationRequest(
            request_id="second-generation-request",
            expected_revision_id=before["revision_id"],
            page_budget=7,
        ),
    )

    with pytest.raises(PresentationServiceConflict) as apply_conflict:
        await service.apply_proposal(
            deck_id,
            proposal["proposal_id"],
            RevisionCommand(
                command_id="apply-during-generation",
                expected_revision_id=before["revision_id"],
            ),
        )
    assert apply_conflict.value.code == "generation_in_progress"

    with pytest.raises(PresentationServiceConflict) as finalize_conflict:
        await service.finalize_presentation(
            deck_id,
            FinalizePresentationRequest(
                command_id="finalize-during-generation",
                expected_revision_id=before["revision_id"],
                render_measurement={
                    "revision_checksum": revision_checksum(before),
                    "slide_count": len(before["slides"]),
                    "overflow": False,
                    "collision": False,
                },
            ),
        )
    assert finalize_conflict.value.code == "generation_in_progress"

    gate.set()
    completed = [event async for event in service.stream_generation(deck_id, session.generation_id)]
    assert completed[-1]["event_type"] == "generation_complete"


@pytest.mark.asyncio
async def test_finalize_requires_publication_and_creates_receipt_bound_artifacts(tmp_path):
    service, repository, deck_id, _events = await _generated_service(tmp_path)
    revision = repository.get_revision(deck_id)
    measurement = {
        "revision_checksum": revision_checksum(revision),
        "slide_count": len(revision["slides"]),
        "overflow": False,
        "collision": False,
    }
    result = await service.finalize_presentation(
        deck_id,
        FinalizePresentationRequest(
            command_id="finalize-command-1",
            expected_revision_id=revision["revision_id"],
            render_measurement=measurement,
        ),
    )

    assert result["artifact"]["revision_id"] == revision["revision_id"]
    assert result["event"]["event_type"] == "export_ready"
    assert (await service.resolve_artifact(result["artifact"]["artifact_id"], "html")).is_file()
    assert (await service.resolve_artifact(result["artifact"]["artifact_id"], "pptx")).is_file()
    repeated = await service.finalize_presentation(
        deck_id,
        FinalizePresentationRequest(
            command_id="finalize-command-1",
            expected_revision_id=revision["revision_id"],
            render_measurement=measurement,
        ),
    )
    assert repeated["artifact"]["artifact_id"] == result["artifact"]["artifact_id"]


@pytest.mark.asyncio
async def test_full_lifecycle_keeps_course_and_frozen_source_digests_immutable(tmp_path):
    course = _course()
    course_digest_before = _serialized_digest(course)
    repository = PresentationRepository(tmp_path / "lifecycle-immutability")
    service = PresentationService(
        repository,
        course_loader=lambda _course_id: course,
        source_projector=project_presentation_source,
        source_packet_builder=source_packet,
        ai_factory=_HealthyPresentationAI,
    )
    manifest = await service.create_presentation(
        course["course_id"],
        CreatePresentationRequest(
            request_id="lifecycle-create-request",
            title="指针课件",
            scope=PresentationScope(type="chapter", section_ids=["chapter-1"]),
            purpose="teaching",
            template_id="lingzhi-engineering",
            page_budget=7,
            extra_requirements="适合课堂讲授",
        ),
    )
    deck_id = manifest["deck_id"]
    source_before = repository.load_source_snapshot(deck_id)
    source_digest_before = source_before["source_snapshot_sha256"]

    session = await service.prepare_generation(
        deck_id,
        GeneratePresentationRequest(
            request_id="lifecycle-generate-request",
            page_budget=7,
            extra_requirements="适合课堂讲授",
        ),
    )
    events = [event async for event in service.stream_generation(deck_id, session.generation_id)]
    assert events[-1]["event_type"] == "generation_complete"

    generated = repository.get_revision(deck_id)
    target = next(slide for slide in generated["slides"] if slide["layout_id"] == "L04")
    proposal = await service.create_proposal(
        deck_id,
        ChatPresentationRequest(
            request_id="lifecycle-proposal-request",
            expected_revision_id=generated["revision_id"],
            scope="slide",
            slide_ids=[target["slide_id"]],
            prompt="补一个贴近课堂的例子",
        ),
    )
    await service.apply_proposal(
        deck_id,
        proposal["proposal_id"],
        RevisionCommand(
            command_id="lifecycle-apply-command",
            expected_revision_id=generated["revision_id"],
        ),
    )
    patched = repository.get_revision(deck_id)
    finalized = await service.finalize_presentation(
        deck_id,
        FinalizePresentationRequest(
            command_id="lifecycle-finalize-command",
            expected_revision_id=patched["revision_id"],
            render_measurement={
                "revision_checksum": revision_checksum(patched),
                "slide_count": len(patched["slides"]),
                "overflow": False,
                "collision": False,
            },
        ),
    )
    assert finalized["artifact"]["revision_id"] == patched["revision_id"]

    source_after = repository.load_source_snapshot(deck_id)
    assert _serialized_digest(course) == course_digest_before
    assert source_after == source_before
    assert source_after["source_snapshot_sha256"] == source_digest_before
    assert source_snapshot_sha256(source_after) == source_digest_before
    assert repository.load_manifest(deck_id)["source_ref"]["source_snapshot_sha256"] == source_digest_before


@pytest.mark.asyncio
async def test_finalize_returns_structured_course_publication_block(tmp_path):
    service, repository, deck_id, _events = await _generated_service(tmp_path, publication_allowed=False)
    revision = repository.get_revision(deck_id)
    with pytest.raises(PresentationQualityBlocked) as blocked:
        await service.finalize_presentation(
            deck_id,
            FinalizePresentationRequest(
                command_id="blocked-finalize-1",
                expected_revision_id=revision["revision_id"],
                render_measurement={
                    "revision_checksum": revision_checksum(revision),
                    "slide_count": len(revision["slides"]),
                    "overflow": False,
                    "collision": False,
                },
            ),
        )
    assert any(issue["code"] == "source_publication_blocked" for issue in blocked.value.report["issues"])
    assert repository.get_deck(deck_id)["artifact"] is None


@pytest.mark.asyncio
async def test_finalize_blocks_renderer_receipt_parity_mismatch(tmp_path):
    service, repository, deck_id, _events = await _generated_service(tmp_path)
    revision = repository.get_revision(deck_id)
    real_renderer = service.renderer

    def mismatched_renderer(current_revision, template_id, artifact_dir):
        result = dict(real_renderer(current_revision, template_id, artifact_dir))
        result["page_count"] = int(result["page_count"]) + 1
        return result

    service.renderer = mismatched_renderer
    with pytest.raises(PresentationQualityBlocked) as blocked:
        await service.finalize_presentation(
            deck_id,
            FinalizePresentationRequest(
                command_id="finalize-parity-mismatch",
                expected_revision_id=revision["revision_id"],
                render_measurement={
                    "revision_checksum": revision_checksum(revision),
                    "slide_count": len(revision["slides"]),
                    "overflow": False,
                    "collision": False,
                },
            ),
        )

    assert any(issue["code"] == "artifact_render_failed" for issue in blocked.value.report["issues"])
    assert repository.get_deck(deck_id)["artifact"] is None


def test_quality_reports_missing_misconception_and_practice_pages(tmp_path):
    course = _course()
    snapshot, source_ref = project_presentation_source(
        course,
        PresentationScope(type="chapter", section_ids=["chapter-1"]),
    )
    repository = PresentationRepository(tmp_path / "quality")
    from presentation_models import DeckRevision, PresentationDeck, Slide, SlideSourceRefs

    deck = PresentationDeck(
        deck_id="deck-quality",
        course_id=course["course_id"],
        title="质量测试",
        source_ref=source_ref,
        scope=PresentationScope(type="chapter", section_ids=["chapter-1"]),
    )
    repository.create_deck(deck, snapshot)
    section = snapshot["sections"][0]
    block = snapshot["blocks"][0]
    objective = snapshot["objectives"][0]
    slide = Slide(
        slide_id="slide-quality",
        position=0,
        layout_id="L04",
        status="ready",
        title="核心概念",
        source_refs=SlideSourceRefs(
            section_ids=[section["section_id"]],
            block_ids=[block["block_id"]],
            block_revision_ids=[block["internal_revision"]],
            objective_ids=[objective["objective_id"]],
        ),
    )
    revision = DeckRevision(
        revision_id="rev-quality",
        deck_id=deck.deck_id,
        reason="initial_generation",
        source_snapshot_id=source_ref.source_snapshot_id,
        slide_order=[slide.slide_id],
        slides=[slide],
    )
    report = evaluate_presentation_quality(deck, revision, snapshot)
    codes = {issue.code for issue in report.issues}
    assert "layout_required_slot_missing" in codes
    assert "misconception_slide_required" in codes
    assert "practice_slide_required" in codes
