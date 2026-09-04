from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from course_document import CourseDocument, legacy_source_checksum, refresh_document_revision
from course_repository import CourseDocumentConflict, CourseDocumentRepository
from routers import courses
from storage import Storage
from teacher_course_upgrade import (
    TeacherCourseUpgradeError,
    TeacherCourseUpgradeService,
    preview_legacy_course_upgrade,
)


def _legacy_course() -> dict:
    return {
        "course_id": "legacy-course",
        "course_name": "高等数学",
        "owner_id": "teacher-old",
        "academic_year": "2025-2026",
        "term": "秋季",
        "course_profile": {"credits": 4, "planned_lecture_count": 2},
        "teaching_plan": {"revision_id": "legacy-plan-history"},
        "teacher_lesson_authoring": {"lessons": {"old": {"history": [1, 2]}}},
        "generation_job_id": "legacy-job",
        "nodes": [
            {
                "node_id": "chapter-a",
                "parent_node_id": "root",
                "node_name": "第一章 极限",
                "node_level": 1,
                "node_content": "",
            },
            {
                "node_id": "section-a1",
                "parent_node_id": "chapter-a",
                "node_name": "数列极限",
                "node_level": 2,
                "node_content": "## 定义\n\n数列极限描述趋近过程。",
                "learning_objective": "理解数列极限",
            },
            {
                "node_id": "section-a2",
                "parent_node_id": "chapter-a",
                "node_name": "函数极限",
                "node_level": 2,
                "content_blocks": [{
                    "block_id": "old-block",
                    "type": "concept",
                    "title": "函数极限",
                    "content": "函数极限与自变量趋近方式有关。",
                }],
            },
            {
                "node_id": "chapter-b",
                "parent_node_id": "root",
                "node_name": "第二章 导数",
                "node_level": 1,
                "node_content": "导数刻画瞬时变化率。",
            },
        ],
    }


def _request(actor_id: str = "teacher-new") -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"x-user-id", actor_id.encode("utf-8"))],
    })


@pytest.mark.asyncio
async def test_preview_is_read_only_and_mapping_is_stable(tmp_path):
    storage = Storage(data_dir=str(tmp_path))
    source = _legacy_course()
    await storage.save_course(source["course_id"], source)
    before_course = deepcopy(storage.load_course(source["course_id"]))
    before_list = deepcopy(storage.list_courses())

    service = TeacherCourseUpgradeService(storage)
    first = service.preview(source["course_id"], owner_id="teacher-new")
    second = service.preview(source["course_id"], owner_id="teacher-new")

    assert first == second
    assert first["eligible"] is True
    assert first["source_checksum"].startswith("tcus_")
    assert [item["lesson_unit_id"] for item in first["lesson_mappings"]] == [
        "L1-1",
        "L1-2",
    ]
    assert first["lesson_mappings"][0]["source_node_ids"] == [
        "section-a1",
        "section-a2",
    ]
    assert first["lesson_mappings"][1]["source_node_ids"] == ["chapter-b"]
    assert storage.load_course(source["course_id"]) == before_course
    assert storage.list_courses() == before_list


@pytest.mark.asyncio
async def test_old_filename_identity_is_used_without_backfilling_source(tmp_path):
    storage = Storage(data_dir=str(tmp_path))
    source = _legacy_course()
    source.pop("course_id")
    await storage.save_course("legacy-filename-id", source)
    before = deepcopy(storage.load_course("legacy-filename-id"))

    report = TeacherCourseUpgradeService(storage).preview(
        "legacy-filename-id",
        owner_id="teacher-new",
    )

    assert report["eligible"] is True
    assert report["source_course_id"] == "legacy-filename-id"
    assert storage.load_course("legacy-filename-id") == before
    assert "course_id" not in storage.load_course("legacy-filename-id")


@pytest.mark.asyncio
async def test_publish_creates_new_valid_lecture_course_without_legacy_history(tmp_path):
    storage = Storage(data_dir=str(tmp_path))
    source = _legacy_course()
    await storage.save_course(source["course_id"], source)
    source_before = deepcopy(storage.load_course(source["course_id"]))
    legacy_checksum_before = legacy_source_checksum(source_before)
    service = TeacherCourseUpgradeService(storage)
    preview = service.preview(source["course_id"], owner_id="teacher-new")

    result = await service.publish(
        source["course_id"],
        expected_source_checksum=preview["source_checksum"],
        owner_id="teacher-new",
    )

    assert result["course_id"] != source["course_id"]
    upgraded = storage.load_course(result["course_id"])
    document = CourseDocument.model_validate(upgraded["course_document"])
    view = service.repository.load_course_view(result["course_id"])
    lesson_nodes = [node for node in view["nodes"] if node["node_level"] == 1]
    section_nodes = [node for node in view["nodes"] if node["node_level"] == 2]

    assert upgraded["authoring_structure_version"] == "lecture_v1"
    assert upgraded["owner_id"] == "teacher-new"
    assert document.course_id == result["course_id"]
    assert [node["node_id"] for node in lesson_nodes] == ["L1-1", "L1-2"]
    assert all(node["parent_node_id"] == "root" for node in lesson_nodes)
    assert {node["parent_node_id"] for node in section_nodes} == {"L1-1", "L1-2"}
    assert upgraded["course_upgrade"] == preview
    assert upgraded["course_document_publication"]["source_checksum"] == preview["source_checksum"]
    for forbidden in (
        "teaching_plan",
        "teacher_lesson_authoring",
        "generation_job_id",
        "generation_error",
    ):
        assert forbidden not in upgraded or upgraded.get(forbidden) in {None, ""}
    assert storage.load_course(source["course_id"]) == source_before
    assert legacy_source_checksum(storage.load_course(source["course_id"])) == legacy_checksum_before


@pytest.mark.asyncio
async def test_publish_retry_is_idempotent_and_creates_one_course(tmp_path):
    storage = Storage(data_dir=str(tmp_path))
    source = _legacy_course()
    await storage.save_course(source["course_id"], source)
    service = TeacherCourseUpgradeService(storage)
    preview = service.preview(
        source["course_id"],
        owner_id="teacher-new",
        upgrade_key="teacher-confirmation-1",
    )

    first = await service.publish(
        source["course_id"],
        expected_source_checksum=preview["source_checksum"],
        owner_id="teacher-new",
        upgrade_key="teacher-confirmation-1",
    )
    second = await service.publish(
        source["course_id"],
        expected_source_checksum=preview["source_checksum"],
        owner_id="teacher-new",
        upgrade_key="teacher-confirmation-1",
    )

    assert first["course_id"] == second["course_id"]
    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert {item["course_id"] for item in storage.list_courses()} == {
        source["course_id"],
        first["course_id"],
    }


@pytest.mark.asyncio
async def test_concurrent_publish_requests_share_one_idempotent_result(tmp_path):
    storage = Storage(data_dir=str(tmp_path))
    source = _legacy_course()
    await storage.save_course(source["course_id"], source)
    first_service = TeacherCourseUpgradeService(storage)
    second_service = TeacherCourseUpgradeService(storage)
    preview = first_service.preview(
        source["course_id"],
        owner_id="teacher-new",
        upgrade_key="same-request",
    )

    first, second = await asyncio.gather(
        first_service.publish(
            source["course_id"],
            expected_source_checksum=preview["source_checksum"],
            owner_id="teacher-new",
            upgrade_key="same-request",
        ),
        second_service.publish(
            source["course_id"],
            expected_source_checksum=preview["source_checksum"],
            owner_id="teacher-new",
            upgrade_key="same-request",
        ),
    )

    assert first["course_id"] == second["course_id"]
    assert {first["idempotent"], second["idempotent"]} == {False, True}
    assert len(storage.list_courses()) == 2


@pytest.mark.asyncio
async def test_concurrent_storage_instances_use_atomic_create_if_absent(tmp_path):
    first_storage = Storage(data_dir=str(tmp_path))
    source = _legacy_course()
    await first_storage.save_course(source["course_id"], source)
    second_storage = Storage(data_dir=str(tmp_path))
    first_service = TeacherCourseUpgradeService(first_storage)
    second_service = TeacherCourseUpgradeService(second_storage)
    preview = first_service.preview(
        source["course_id"],
        owner_id="teacher-new",
        upgrade_key="cross-storage-request",
    )

    first, second = await asyncio.gather(
        first_service.publish(
            source["course_id"],
            expected_source_checksum=preview["source_checksum"],
            owner_id="teacher-new",
            upgrade_key="cross-storage-request",
        ),
        second_service.publish(
            source["course_id"],
            expected_source_checksum=preview["source_checksum"],
            owner_id="teacher-new",
            upgrade_key="cross-storage-request",
        ),
    )

    assert first["course_id"] == second["course_id"]
    assert {first["idempotent"], second["idempotent"]} == {False, True}
    assert CourseDocument.model_validate(
        first_storage.load_course(first["course_id"])["course_document"]
    )


@pytest.mark.asyncio
async def test_source_change_rejects_confirmed_preview_and_keeps_old_course(tmp_path):
    storage = Storage(data_dir=str(tmp_path))
    source = _legacy_course()
    await storage.save_course(source["course_id"], source)
    service = TeacherCourseUpgradeService(storage)
    preview = service.preview(source["course_id"], owner_id="teacher-new")
    changed = deepcopy(source)
    changed["nodes"][1]["node_content"] = "正文已变化"
    await storage.save_course(source["course_id"], changed)

    with pytest.raises(TeacherCourseUpgradeError) as caught:
        await service.publish(
            source["course_id"],
            expected_source_checksum=preview["source_checksum"],
            owner_id="teacher-new",
        )

    assert caught.value.code == "source_checksum_changed"
    assert storage.load_course(source["course_id"]) == changed
    assert len(storage.list_courses()) == 1


@pytest.mark.asyncio
async def test_metadata_change_rejects_confirmed_preview(tmp_path):
    storage = Storage(data_dir=str(tmp_path))
    source = _legacy_course()
    await storage.save_course(source["course_id"], source)
    service = TeacherCourseUpgradeService(storage)
    preview = service.preview(source["course_id"], owner_id="teacher-new")
    changed = deepcopy(source)
    changed["course_profile"]["credits"] = 5
    await storage.save_course(source["course_id"], changed)

    with pytest.raises(TeacherCourseUpgradeError) as caught:
        await service.publish(
            source["course_id"],
            expected_source_checksum=preview["source_checksum"],
            owner_id="teacher-new",
        )

    assert caught.value.code == "source_checksum_changed"
    assert len(storage.list_courses()) == 1


@pytest.mark.asyncio
async def test_canonical_chapter_course_can_upgrade_through_read_only_view(tmp_path):
    storage = Storage(data_dir=str(tmp_path))
    source = _legacy_course()
    repository = CourseDocumentRepository(storage)
    await repository.create_imported_course(
        source["course_id"],
        imported_course=source,
    )
    canonical_before = deepcopy(storage.load_course(source["course_id"]))
    assert "nodes" not in canonical_before
    service = TeacherCourseUpgradeService(storage)

    preview = service.preview(source["course_id"], owner_id="teacher-new")
    result = await service.publish(
        source["course_id"],
        expected_source_checksum=preview["source_checksum"],
        owner_id="teacher-new",
    )

    assert preview["eligible"] is True
    assert result["course_id"] != source["course_id"]
    assert storage.load_course(source["course_id"]) == canonical_before


def test_preview_blocks_any_empty_lesson_even_when_other_lessons_have_content():
    source = _legacy_course()
    source["nodes"][1]["node_content"] = ""
    source["nodes"][2]["content_blocks"] = []

    report = preview_legacy_course_upgrade(source, owner_id="teacher-new")

    assert report["eligible"] is False
    assert "source_lesson_content_empty" in {
        item["code"] for item in report["blockers"]
    }


def test_preview_does_not_treat_title_only_blocks_as_lesson_content():
    source = _legacy_course()
    source["nodes"][1]["node_content"] = ""
    source["nodes"][2]["content_blocks"] = [{
        "block_id": "title-only",
        "type": "concept",
        "title": "只有标题",
        "content": "",
    }]

    report = preview_legacy_course_upgrade(source, owner_id="teacher-new")

    assert report["eligible"] is False
    assert "source_lesson_content_empty" in {
        item["code"] for item in report["blockers"]
    }


@pytest.mark.asyncio
async def test_canonical_upgrade_never_revives_retired_blocks(tmp_path):
    storage = Storage(data_dir=str(tmp_path))
    source = _legacy_course()
    repository = CourseDocumentRepository(storage)
    await repository.create_imported_course(
        source["course_id"],
        imported_course=source,
    )
    raw = deepcopy(storage.load_course(source["course_id"]))
    document = CourseDocument.model_validate(raw["course_document"])
    for block in document.blocks:
        block.status = "retired"
    document = refresh_document_revision(document)
    raw["course_document"] = document.model_dump(mode="json")
    raw["course_document_revision"] = document.document_revision
    await storage.save_course(source["course_id"], raw)

    report = TeacherCourseUpgradeService(storage).preview(
        source["course_id"],
        owner_id="teacher-new",
    )

    assert report["eligible"] is False
    assert "source_content_empty" in {item["code"] for item in report["blockers"]}


@pytest.mark.asyncio
async def test_invalid_mapping_never_publishes_and_old_course_remains_readable(tmp_path):
    storage = Storage(data_dir=str(tmp_path))
    source = _legacy_course()
    source["nodes"][2]["node_id"] = "section-a1"
    await storage.save_course(source["course_id"], source)
    service = TeacherCourseUpgradeService(storage)
    report = service.preview(source["course_id"], owner_id="teacher-new")

    assert report["eligible"] is False
    assert "source_node_id_duplicate" in {item["code"] for item in report["blockers"]}
    with pytest.raises(TeacherCourseUpgradeError) as caught:
        await service.publish(
            source["course_id"],
            expected_source_checksum=report["source_checksum"],
            owner_id="teacher-new",
        )

    assert caught.value.code == "upgrade_preflight_blocked"
    assert storage.load_course(source["course_id"])["course_name"] == "高等数学"
    assert len(storage.list_courses()) == 1


class _FailedPublishStorage:
    def __init__(self, source: dict) -> None:
        self.courses = {source["course_id"]: deepcopy(source)}
        self.deleted: list[str] = []

    def load_course(self, course_id: str) -> dict:
        return deepcopy(self.courses.get(course_id) or {})

    def list_courses(self) -> list[dict]:
        return [{"course_id": key} for key in self.courses]

    async def create_course_if_absent(self, course_id: str, data: dict) -> bool:
        partial = {
            "course_id": course_id,
            "course_upgrade": deepcopy(data["course_upgrade"]),
            "course_document": {"invalid": True},
        }
        self.courses[course_id] = partial
        raise OSError("simulated publish failure")

    def delete_course(self, course_id: str) -> None:
        self.deleted.append(course_id)
        self.courses.pop(course_id, None)


@pytest.mark.asyncio
async def test_failed_publish_cleans_its_own_partial_candidate_only():
    source = _legacy_course()
    storage = _FailedPublishStorage(source)
    service = TeacherCourseUpgradeService(storage)
    report = service.preview(source["course_id"], owner_id="teacher-new")

    with pytest.raises(TeacherCourseUpgradeError) as caught:
        await service.publish(
            source["course_id"],
            expected_source_checksum=report["source_checksum"],
            owner_id="teacher-new",
        )

    assert caught.value.code == "upgrade_publish_failed"
    assert caught.value.report == report
    assert storage.deleted == [report["proposed_course_id"]]
    assert storage.load_course(report["proposed_course_id"]) == {}
    assert storage.load_course(source["course_id"]) == source
    assert storage.list_courses() == [{"course_id": source["course_id"]}]


@pytest.mark.asyncio
async def test_existing_unrelated_course_id_is_never_overwritten_or_deleted(tmp_path):
    storage = Storage(data_dir=str(tmp_path))
    source = _legacy_course()
    await storage.save_course(source["course_id"], source)
    service = TeacherCourseUpgradeService(storage)
    report = service.preview(source["course_id"], owner_id="teacher-new")
    unrelated = {"course_id": report["proposed_course_id"], "course_name": "保留我", "nodes": []}
    await storage.save_course(report["proposed_course_id"], unrelated)

    with pytest.raises(CourseDocumentConflict, match="already occupied"):
        await service.publish(
            source["course_id"],
            expected_source_checksum=report["source_checksum"],
            owner_id="teacher-new",
        )

    assert storage.load_course(report["proposed_course_id"]) == unrelated


def test_preview_reports_orphans_and_cycles_without_mutating_input():
    source = _legacy_course()
    source["nodes"] = [
        {
            "node_id": "cycle-a",
            "parent_node_id": "cycle-b",
            "node_name": "A",
            "node_level": 2,
            "node_content": "A",
        },
        {
            "node_id": "cycle-b",
            "parent_node_id": "cycle-a",
            "node_name": "B",
            "node_level": 2,
            "node_content": "B",
        },
        {
            "node_id": "orphan",
            "parent_node_id": "missing",
            "node_name": "孤立节点",
            "node_level": 2,
            "node_content": "正文",
        },
    ]
    before = deepcopy(source)

    report = preview_legacy_course_upgrade(source)

    assert report["eligible"] is False
    codes = {item["code"] for item in report["blockers"]}
    assert {"source_parent_missing", "source_cycle", "source_lessons_empty"} <= codes
    assert source == before


@pytest.mark.asyncio
async def test_upgrade_api_preserves_explicit_read_then_confirm_boundary(tmp_path, monkeypatch):
    storage = Storage(data_dir=str(tmp_path))
    source = _legacy_course()
    await storage.save_course(source["course_id"], source)
    repository = CourseDocumentRepository(storage)
    monkeypatch.setattr(courses, "get_course_document_repository", lambda: repository)
    before = deepcopy(storage.list_courses())

    preview = await courses.preview_teacher_course_upgrade(
        source["course_id"],
        _request("teacher-old"),
        upgrade_key="api-confirmation",
    )
    assert storage.list_courses() == before

    with pytest.raises(HTTPException) as unconfirmed:
        await courses.publish_teacher_course_upgrade(
            source["course_id"],
            courses.TeacherCourseUpgradeRequest(
                source_checksum=preview["source_checksum"],
                upgrade_key="api-confirmation",
                confirm=False,
            ),
            _request(),
        )
    assert unconfirmed.value.status_code == 400
    assert storage.list_courses() == before

    published = await courses.publish_teacher_course_upgrade(
        source["course_id"],
        courses.TeacherCourseUpgradeRequest(
            source_checksum=preview["source_checksum"],
            upgrade_key="api-confirmation",
            confirm=True,
        ),
        _request("teacher-old"),
    )
    assert published["course_id"] == preview["proposed_course_id"]
    assert storage.load_course(published["course_id"])["owner_id"] == "teacher-old"


@pytest.mark.asyncio
async def test_upgrade_api_rejects_non_owner_of_published_teacher_course(tmp_path, monkeypatch):
    storage = Storage(data_dir=str(tmp_path))
    source = _legacy_course()
    source.update({
        "authoring_surface": "teacher",
        "owner_id": "teacher-owner",
        "is_published": True,
    })
    await storage.save_course(source["course_id"], source)
    repository = CourseDocumentRepository(storage)
    monkeypatch.setattr(courses, "get_course_document_repository", lambda: repository)

    with pytest.raises(HTTPException) as preview_denied:
        await courses.preview_teacher_course_upgrade(
            source["course_id"],
            _request("teacher-other"),
        )
    assert preview_denied.value.status_code == 404

    with pytest.raises(HTTPException) as publish_denied:
        await courses.publish_teacher_course_upgrade(
            source["course_id"],
            courses.TeacherCourseUpgradeRequest(
                source_checksum="untrusted",
                confirm=True,
            ),
            _request("teacher-other"),
        )
    assert publish_denied.value.status_code == 404


@pytest.mark.asyncio
async def test_upgrade_api_rejects_non_owner_when_legacy_surface_is_missing(tmp_path, monkeypatch):
    storage = Storage(data_dir=str(tmp_path))
    source = _legacy_course()
    assert "authoring_surface" not in source
    await storage.save_course(source["course_id"], source)
    repository = CourseDocumentRepository(storage)
    monkeypatch.setattr(courses, "get_course_document_repository", lambda: repository)

    with pytest.raises(HTTPException) as denied:
        await courses.preview_teacher_course_upgrade(
            source["course_id"],
            _request("teacher-other"),
        )

    assert denied.value.status_code == 404
