from copy import deepcopy

from study.repository import StudyRepository
from .test_personal_study import setup_study, account


def bookmark_fixture(setup_study):
    client, _, repo, _ = setup_study
    owner, headers = account(client)
    material = {"id": "bookmark-material", "owner_id": owner, "request_key": "bookmark-fixture", "fingerprint": "fixture",
                "title": "书签验收", "purpose": "systematic", "status": "completed", "task_id": "fixture-task",
                "updated_at": "2026-11-07T00:00:00Z", "request": {"source_sections": []}, "plans": [], "notes": {},
                "revisions": [{"id": "revision-a", "status": "completed", "sections": [{"id": "s1", "title": "第一讲",
                               "complete": True, "fragment": "", "blocks": [{"block_id": "b1", "content_type": "definition", "content": "原文"},
                               {"block_id": "answer", "content_type": "answer", "answer_to": "b1", "content": "解答"}]}]}]}
    repo.reserve(owner, "bookmark-fixture", "fixture", material)
    payload = {"revision_id": "revision-a", "expected_version": 0, "request_id": "bookmark-request-0001",
               "position": {"sectionId": "s1", "blockId": "b1", "offset": 83.5, "atTop": False, "expandedAnswers": ["answer"]}}
    return client, repo, owner, headers, material, payload, "/api/study/materials/bookmark-material/reading-position"


def test_bookmark_survives_restart_without_editing_content_or_mastery(setup_study):
    client, repo, owner, headers, original, payload, path = bookmark_fixture(setup_study)
    events = deepcopy(repo.storage.load_data("learning_events.json"))
    result = client.put(path, headers=headers, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["version"] == 1
    saved = StudyRepository(repo.storage).get(owner, original["id"])
    assert saved.pop("reading_positions")["revision-a"]["position"] == payload["position"]
    assert saved == original
    assert repo.storage.load_data("learning_events.json") == events
    public = client.get(path.removesuffix("/reading-position"), headers=headers)
    assert public.status_code == 200, public.text
    assert public.json()["reading_positions"]["revision-a"]["version"] == 1


def test_bookmark_retries_idempotently_and_rejects_stale_window(setup_study):
    client, repo, owner, headers, original, payload, path = bookmark_fixture(setup_study)
    first = client.put(path, headers=headers, json=payload).json()
    assert client.put(path, headers=headers, json=payload).json() == first
    newer = {**payload, "request_id": "bookmark-request-0002", "expected_version": 1,
             "position": {**payload["position"], "offset": 125}}
    assert client.put(path, headers=headers, json=newer).status_code == 200
    stale = {**payload, "request_id": "bookmark-request-0003"}
    assert client.put(path, headers=headers, json=stale).status_code == 409
    assert repo.get(owner, original["id"])["reading_positions"]["revision-a"]["position"]["offset"] == 125


def test_bookmark_enforces_owner_revision_anchor_and_source_access(setup_study, monkeypatch):
    client, repo, owner, headers, original, payload, path = bookmark_fixture(setup_study)
    _, other = account(client, "student_b")
    assert client.put(path, headers=other, json=payload).status_code == 404
    assert client.put(path, json=payload).status_code == 401
    assert client.put(path, headers=headers, json={**payload, "revision_id": "missing"}).status_code == 409
    for changes in [{"sectionId": "missing"}, {"blockId": "other-block"}, {"expandedAnswers": ["b1"]}]:
        assert client.put(path, headers=headers, json={**payload, "position": {**payload["position"], **changes}}).status_code == 409
    assert "reading_positions" not in repo.get(owner, original["id"])
    def revoked(*args):
        raise KeyError("revoked")
    monkeypatch.setattr(repo, "get", revoked)
    assert client.put(path, headers=headers, json=payload).status_code == 404


def test_bookmark_keeps_positions_separate_across_revisions(setup_study):
    client, repo, owner, headers, original, payload, path = bookmark_fixture(setup_study)
    assert client.put(path, headers=headers, json=payload).status_code == 200
    revisions = deepcopy(original["revisions"])
    revisions.append({**deepcopy(revisions[0]), "id": "revision-b"})
    repo.update(owner, original["id"], {"revisions": revisions})
    result = client.put(path, headers=headers, json={**payload, "revision_id": "revision-b", "position": {**payload["position"], "offset": 0, "atTop": True}})
    assert result.status_code == 200
    positions = repo.get(owner, original["id"])["reading_positions"]
    assert positions["revision-a"]["position"]["offset"] == 83.5
    assert positions["revision-b"]["position"]["offset"] == 0
