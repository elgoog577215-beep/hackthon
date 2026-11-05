from copy import deepcopy
import json

import pytest

from study import assistant
from .test_personal_assistant import ready
from .test_personal_study import setup_study


async def ready_note(setup_study):
    client, manager, repo, writer, owner, headers, material, question = await ready(setup_study)
    note_payload = {
        "request_id": "note-assistant-create-001", "revision_id": question["revision_id"],
        "section_id": question["section_id"], "block_id": question["block_id"],
        "quote": "向量用有序分量表示。", "content": "我自己的解释：分量对应同一维度。",
        "question_state": "open", "important": True,
    }
    base = f"/api/study/materials/{material['id']}"
    response = client.post(base + "/notes", headers=headers, json=note_payload)
    assert response.status_code == 200, response.text
    note = response.json()
    question.update(note_id=note["id"], note_version=note["version"], note_draft="尚未保存的手工补充。")
    return client, manager, repo, writer, owner, headers, material, question, note, base


def latest(client, base, headers):
    return client.get(base + "/assistant", headers=headers).json()["messages"][-1]


@pytest.mark.asyncio
@pytest.mark.parametrize("fenced", [False, True])
async def test_note_discussion_proposes_a_draft_without_saving_and_uses_server_anchor(setup_study, monkeypatch, fenced):
    client, manager, repo, writer, owner, headers, material, question, note, base = await ready_note(setup_study)
    before = deepcopy(repo.get(owner, material["id"]))
    events = deepcopy(repo.storage.load_data("learning_events.json"))
    # The browser may have scrolled or supplied arbitrary coordinates. The
    # saved note is the only authority for a note discussion's original scope.
    question.update(revision_id="spoofed-revision", section_id="spoofed-section", block_id="spoofed-block", quote="伪造引文")
    request = client.post(base + "/assistant", headers=headers, json=question)
    assert request.status_code == 200, request.text
    task_id = request.json()["messages"][-1]["task_ref"]["task_id"]

    async def model(prompt, system, **kwargs):
        context = json.loads(prompt)
        assert context["selected_display_text"] == note["quote"]
        assert context["block"]["title"] == note["block_title"]
        assert context["note"] == {"content": "尚未保存的手工补充。", "question_state": "open", "important": True}
        assert kwargs["max_attempts"] == kwargs["retry_count"] == 1
        assert kwargs["json_schema"]["required"] == ["reply", "note_draft"]
        await kwargs["on_content_delta"]('{"reply":"流式内容不能把 JSON 展示给学生')
        interim = latest(client, base, headers)
        assert interim["content"] == "" and "note_draft" not in interim
        assert repo.get(owner, material["id"]) == before
        raw = json.dumps({"reply": "按相同维度逐一相加。", "note_draft": "尚未保存的手工补充。增加一个二维例子。"})
        return "```json\n" + raw + "\n```" if fenced else raw

    monkeypatch.setattr(writer, "_call_llm", model)
    await manager._run_job(task_id)
    response = latest(client, base, headers)
    assert response["status"] == "complete"
    assert response["content"] == "按相同维度逐一相加。"
    assert response["note_draft"] == "尚未保存的手工补充。增加一个二维例子。"
    assert response["note_version"] == 1 and response["based_on_note_draft"] == question["note_draft"]
    assert response["context_ref"]["revision_id"] == note["revision_id"]
    assert response["context_ref"]["block_id"] == note["block_id"]
    assert repo.get(owner, material["id"]) == before
    assert repo.storage.load_data("learning_events.json") == events


@pytest.mark.asyncio
async def test_saved_edit_during_generation_rejects_the_late_draft_and_old_retry(setup_study, monkeypatch):
    client, manager, repo, writer, owner, headers, material, question, note, base = await ready_note(setup_study)
    turn = client.post(base + "/assistant", headers=headers, json=question).json()
    task_id = turn["messages"][-1]["task_ref"]["task_id"]

    async def model(_prompt, _system, **kwargs):
        await kwargs["on_content_delta"]('{"reply":"延迟响应')
        saved = client.patch(base + "/notes/" + note["id"], headers=headers,
                             json={"expected_version": 1, "content": "生成期间我自己修改并保存的内容"})
        assert saved.status_code == 200
        return json.dumps({"reply": "旧回复", "note_draft": "过期整理稿不能覆盖"})

    monkeypatch.setattr(writer, "_call_llm", model)
    await manager._run_job(task_id)
    response = latest(client, base, headers)
    assert response["status"] == "failed" and response["content"] == ""
    assert "note_draft" not in response
    saved_note = client.get(base + "/notes", headers=headers).json()["entries"][0]
    assert saved_note["version"] == 2 and saved_note["content"] == "生成期间我自己修改并保存的内容"
    assert client.post(base + "/assistant/" + task_id + "/continue", headers=headers).status_code == 409
    assert client.post(base + "/assistant", headers=headers, json={**question, "request_id": "stale-note-question-002"}).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [
    '{"reply":"incomplete',
    '{"reply":"complete but missing draft"}',
    '{"reply":"complete", "note_draft":""}',
    '{"reply":"complete", "note_draft":null}',
    '{"reply":false, "note_draft":"draft"}',
    "provider interrupted",
])
async def test_note_failures_never_expose_json_or_replace_a_note(setup_study, monkeypatch, raw):
    client, manager, repo, writer, owner, headers, material, question, note, base = await ready_note(setup_study)
    before = deepcopy(repo.get(owner, material["id"]))
    task_id = client.post(base + "/assistant", headers=headers, json=question).json()["messages"][-1]["task_ref"]["task_id"]
    calls = []

    async def model(_prompt, _system, **kwargs):
        calls.append(1)
        await kwargs["on_content_delta"]('{"reply":"不完整 JSON", "note_draft":"')
        if raw == "provider interrupted":
            raise RuntimeError(raw)
        return raw

    monkeypatch.setattr(writer, "_call_llm", model)
    await manager._run_job(task_id)
    response = latest(client, base, headers)
    assert response["status"] == "failed" and response["content"] == ""
    assert "note_draft" not in response and "based_on_note_draft" not in response
    assert repo.get(owner, material["id"]) == before and len(calls) == 1
    if raw != "provider interrupted":
        assert manager.tasks[task_id]["error"] == "笔记讨论尚未完整生成，原笔记与手工草稿已保留"


@pytest.mark.asyncio
async def test_each_note_uses_only_its_own_prior_discussion_and_current_draft(setup_study, monkeypatch):
    client, manager, repo, writer, owner, headers, material, question, first_note, base = await ready_note(setup_study)
    other_section = material["revisions"][0]["sections"][1]
    second = client.post(base + "/notes", headers=headers, json={
        "request_id": "note-assistant-create-002", "revision_id": question["revision_id"],
        "section_id": other_section["id"], "block_id": other_section["blocks"][0]["block_id"],
        "content": "第二条笔记", "quote": "有序分量",
    }).json()

    def history(conversation):
        for number, (note_id, text) in enumerate([(first_note["id"], "第一条笔记的讨论"), (second["id"], "第二条笔记的讨论"), ("", "普通讲义讨论")]):
            conversation["messages"].append({"message_id": f"past-{number}", "role": "assistant", "status": "complete", "content": text,
                "context_ref": {"note_id": note_id, "section_title": "历史章节", "block_title": "历史正文"}})

    assistant.ai_teacher_repository.material_conversation(owner, material["id"], question["revision_id"], history)
    payload = {**question, "note_id": second["id"], "note_version": 1, "note_draft": "第二条的未保存稿"}
    task_id = client.post(base + "/assistant", headers=headers, json=payload).json()["messages"][-1]["task_ref"]["task_id"]

    async def model(prompt, _system, **_kwargs):
        context = json.loads(prompt)
        assert context["section"] == other_section["title"]
        assert context["selected_display_text"] == second["quote"]
        assert context["note"]["content"] == "第二条的未保存稿"
        assert [message["content"] for message in context["recent_dialogue"]] == ["第二条笔记的讨论"]
        return json.dumps({"reply": "第二条回复", "note_draft": "第二条整理稿"})

    monkeypatch.setattr(writer, "_call_llm", model)
    await manager._run_job(task_id)
    assert latest(client, base, headers)["status"] == "complete"
    entries = client.get(base + "/notes", headers=headers).json()["entries"]
    assert {note["content"] for note in entries} == {first_note["content"], "第二条笔记"}


@pytest.mark.asyncio
@pytest.mark.parametrize("draft", ["omitted", None, ""])
async def test_absent_note_draft_falls_back_to_saved_text_and_missing_version_is_rejected(setup_study, monkeypatch, draft):
    client, manager, repo, writer, owner, headers, material, question, note, base = await ready_note(setup_study)
    no_version = {key: value for key, value in question.items() if key != "note_version"}
    assert client.post(base + "/assistant", headers=headers, json=no_version).status_code == 409
    payload = {key: value for key, value in question.items() if key != "note_draft"}
    if draft != "omitted":
        payload["note_draft"] = draft
    expected = "" if draft == "" else note["content"]
    result = client.post(base + "/assistant", headers=headers, json=payload)
    assert result.status_code == 200, result.text
    conversation = result.json()
    task_id = conversation["messages"][-1]["task_ref"]["task_id"]

    async def model(prompt, _system, **_kwargs):
        context = json.loads(prompt)
        assert context["note"]["content"] == expected
        return json.dumps({"reply": "保留原稿", "note_draft": note["content"]})

    monkeypatch.setattr(writer, "_call_llm", model)
    await manager._run_job(task_id)
    response = latest(client, base, headers)
    assert response["status"] == "complete" and response["based_on_note_draft"] == expected
