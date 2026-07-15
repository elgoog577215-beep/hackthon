from __future__ import annotations

import json
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from presentation_generation import PresentationService
from presentation_quality import revision_checksum
from presentation_repository import PresentationRepository
from presentation_source import project_presentation_source, source_packet
from routers.presentations import configure_presentation_service, router


class _HealthyPresentationAI:
    async def _call_llm(self, prompt: str, **_kwargs) -> str:
        if prompt.lstrip().startswith("{"):
            request = json.loads(prompt)
            slide = request["slide"]
            return json.dumps({
                "changes": {"speaker_notes": f"{slide.get('speaker_notes', '')}\nAI 修改已应用。"},
            }, ensure_ascii=False)
        layout_match = re.search(r"页面版式：(L\d{2})", prompt)
        layout = layout_match.group(1) if layout_match else "L04"
        title_match = re.search(r"标题：([^\n]+)", prompt)
        block_type = {
            "L02": "bullets", "L04": "callout", "L05": "comparison", "L06": "bullets",
            "L07": "code", "L08": "comparison", "L09": "exercise", "L10": "bullets",
        }.get(layout)
        blocks = [] if block_type is None else [{
            "block_id": f"api-{layout}", "type": block_type, "title": "课程要点",
            "content": "绑定来源内容", "items": ["课程要点"] if block_type in {"bullets", "exercise"} else [],
            "metadata": {"left": "误区", "right": "正确"} if block_type == "comparison" else {},
        }]
        return json.dumps({
            "title": title_match.group(1) if title_match else "课件页面", "subtitle": "",
            "key_message": "课程核心信息", "blocks": blocks, "speaker_notes": "课程讲稿",
        }, ensure_ascii=False)

    @staticmethod
    def _extract_json(response: str) -> dict:
        return json.loads(response)


def _course() -> dict:
    return {
        "course_id": "course-api-1",
        "course_name": "C语言 API 课件",
        "current_course_version_id": "cv1",
        "publication_allowed": True,
        "is_published": True,
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
                "node_name": "地址和值",
                "node_level": 2,
                "learning_objective": "解释地址和值的关系",
                "objective_id": "obj-1",
                "node_content": "## 指针\n\n指针变量保存地址。",
                "content_blocks": [{
                    "block_id": "block-1",
                    "type": "concept",
                    "title": "指针定义",
                    "content": "int x = 10; int *p = &x;",
                    "metadata": {},
                }],
            },
        ],
        "learning_assets": {
            "questions": [{"question_id": "q1", "node_id": "section-1", "prompt": "&x 是什么？"}],
            "misconceptions": [{"misconception_id": "m1", "node_id": "section-1", "text": "空指针可以直接解引用"}],
        },
    }


@pytest.fixture
def presentation_api(tmp_path):
    course = _course()
    repository = PresentationRepository(tmp_path / "presentations")
    service = PresentationService(
        repository,
        course_loader=lambda _course_id: course,
        source_projector=project_presentation_source,
        source_packet_builder=source_packet,
        ai_factory=_HealthyPresentationAI,
    )
    configure_presentation_service(service)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    with TestClient(app) as client:
        yield client, repository
    configure_presentation_service(None)


def _create_and_generate(client: TestClient) -> tuple[str, list[dict]]:
    created = client.post("/api/courses/course-api-1/presentations", json={
        "request_id": "api-create-request-1",
        "title": "指针课件",
        "scope": {"type": "chapter", "section_ids": ["chapter-1"]},
        "purpose": "teaching",
        "template_id": "lingzhi-classroom",
        "page_budget": 7,
    })
    assert created.status_code == 201, created.text
    deck_id = created.json()["deck"]["deck_id"]

    with client.stream("POST", f"/api/presentations/{deck_id}/generate", json={
        "request_id": "api-generate-request-1",
        "page_budget": 7,
    }) as response:
        assert response.status_code == 200, response.read().decode()
        events = [
            json.loads(line[6:])
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]
    return deck_id, events


def test_api_create_generate_replay_and_get_envelope(presentation_api):
    client, _repository = presentation_api
    deck_id, events = _create_and_generate(client)

    assert events[0]["event_type"] == "deck_outline"
    assert events[-1]["event_type"] == "generation_complete"
    assert events[-1]["payload"]["revision"]["slides"]
    assert "export_ready" not in {event["event_type"] for event in events}

    state = client.get(f"/api/presentations/{deck_id}")
    assert state.status_code == 200
    assert set(state.json()) >= {"deck", "revision", "working", "quality", "artifact"}
    assert state.json()["revision"]["revision_id"] == events[-1]["payload"]["revision"]["revision_id"]
    assert state.json()["revision_checksum"] == revision_checksum(state.json()["revision"])
    assert events[-1]["payload"]["revision_checksum"] == state.json()["revision_checksum"]
    assert state.json()["deck"]["source_outdated"] is False
    assert state.json()["deck"]["current_course_version_id"] == "cv1"

    listed = client.get("/api/courses/course-api-1/presentations")
    assert listed.status_code == 200
    assert listed.json()["decks"][0]["deck_id"] == deck_id
    assert listed.json()["decks"][0]["source_outdated"] is False
    assert listed.json()["decks"][0]["current_course_version_id"] == "cv1"

    generation_id = events[0]["generation_id"]
    with client.stream(
        "GET",
        f"/api/presentations/{deck_id}/events?generation_id={generation_id}&after_seq=2",
    ) as replay:
        replayed = [json.loads(line[6:]) for line in replay.iter_lines() if line.startswith("data: ")]
    assert replayed[0]["event_seq"] == 3

    with client.stream(
        "GET",
        f"/api/presentations/{deck_id}/events?generation_id={generation_id}&after_seq=0",
        headers={"Last-Event-ID": "different-generation:999"},
    ) as replay:
        wrong_generation_replay = [
            json.loads(line[6:]) for line in replay.iter_lines() if line.startswith("data: ")
        ]
    assert wrong_generation_replay[0]["event_seq"] == 1


def test_api_patch_stale_conflict_finalize_and_receipt_download(presentation_api):
    client, _repository = presentation_api
    deck_id, _events = _create_and_generate(client)
    before = client.get(f"/api/presentations/{deck_id}").json()["revision"]
    target = next(slide for slide in before["slides"] if slide["layout_id"] == "L04")

    proposal_response = client.post(f"/api/presentations/{deck_id}/chat", json={
        "request_id": "api-proposal-request-1",
        "expected_revision_id": before["revision_id"],
        "scope": "slide",
        "slide_ids": [target["slide_id"]],
        "prompt": "补一个例子",
    })
    assert proposal_response.status_code == 201, proposal_response.text
    proposal_id = proposal_response.json()["proposal"]["proposal_id"]

    applied = client.post(f"/api/presentations/{deck_id}/patches/{proposal_id}/apply", json={
        "command_id": "api-apply-command-1",
        "expected_revision_id": before["revision_id"],
    })
    assert applied.status_code == 200, applied.text
    revision = applied.json()["revision"]
    assert revision["revision_id"] != before["revision_id"]

    stale = client.post(f"/api/presentations/{deck_id}/chat", json={
        "request_id": "api-proposal-request-2",
        "expected_revision_id": before["revision_id"],
        "scope": "slide",
        "slide_ids": [target["slide_id"]],
        "prompt": "精简本页",
    })
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_revision"

    reused_command = client.post(f"/api/presentations/{deck_id}/finalize", json={
        "command_id": "api-apply-command-1",
        "expected_revision_id": revision["revision_id"],
        "render_measurement": {
            "revision_checksum": revision_checksum(revision),
            "slide_count": len(revision["slides"]),
            "overflow": False,
            "collision": False,
        },
    })
    assert reused_command.status_code == 409
    assert reused_command.json()["detail"]["code"] == "command_id_reused"

    finalized = client.post(f"/api/presentations/{deck_id}/finalize", json={
        "command_id": "api-finalize-command-1",
        "expected_revision_id": revision["revision_id"],
        "render_measurement": {
            "revision_checksum": revision_checksum(revision),
            "slide_count": len(revision["slides"]),
            "overflow": False,
            "collision": False,
        },
    })
    assert finalized.status_code == 200, finalized.text
    artifact = finalized.json()["artifact"]
    assert artifact["html_url"].endswith("/html")
    assert artifact["pptx_url"].endswith("/pptx")
    assert artifact["stale"] is False
    assert client.get(artifact["html_url"]).status_code == 200
    pptx = client.get(artifact["pptx_url"])
    assert pptx.status_code == 200
    assert pptx.content.startswith(b"PK")

    next_proposal = client.post(f"/api/presentations/{deck_id}/chat", json={
        "request_id": "api-proposal-request-3",
        "expected_revision_id": revision["revision_id"],
        "scope": "slide",
        "slide_ids": [target["slide_id"]],
        "prompt": "精简本页",
    })
    assert next_proposal.status_code == 201, next_proposal.text
    advanced = client.post(
        f"/api/presentations/{deck_id}/patches/{next_proposal.json()['proposal']['proposal_id']}/apply",
        json={
            "command_id": "api-apply-command-2",
            "expected_revision_id": revision["revision_id"],
        },
    )
    assert advanced.status_code == 200, advanced.text
    stale_download = client.get(artifact["html_url"])
    assert stale_download.status_code == 400
    assert stale_download.json()["detail"]["code"] == "artifact_access_rejected"

    rejected = client.get("/api/presentation-artifacts/bad..artifact/html")
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "presentation_validation_failed"
