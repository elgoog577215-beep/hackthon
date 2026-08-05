"""知识命令 HTTP 边界测试（教师端入口）。

这里刻意不 mock 领域服务：候选门、稳定身份检查和原子提交都走真实的
CourseKnowledgeCommandService 与 CourseDocumentRepository，只把存储换成内存。
把服务 mock 掉就只能测到"路由转发正确"，测不到"过期修订会被拒绝"这类
真正会在生产出问题的行为。
"""

from __future__ import annotations

from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from content_blocks import set_node_content_blocks
from course_document import (
    CourseBlock,
    CourseDocument,
    CourseSection,
    refresh_document_revision,
)
from course_knowledge_base import compile_course_knowledge_base
from course_knowledge_map import compile_course_knowledge_map
from course_repository import CourseDocumentRepository
from routers import knowledge_libraries


def _knowledge_points() -> list[dict]:
    return [
        {
            "name": "容量耗尽判定",
            "statement": "当元素数量等于当前容量时，下一次插入必须先获得更大的连续存储空间。",
            "knowledge_type": "rule",
            "conditions": ["使用连续存储且不存在可用槽位"],
            "boundaries": ["尚有空闲槽位时不触发扩容"],
            "capability_points": [{
                "name": "判断扩容触发时机",
                "observable_behavior": "给定长度与容量，准确判断下一次插入是否触发扩容",
            }],
            "mastery_criteria": [{
                "name": "扩容触发判断达标",
                "observable_performance": "在不同长度与容量组合中独立判断扩容时机并说明依据",
                "verification_method": "使用至少三个边界案例进行判断并核对结果",
            }],
            "entry_reason": "这是理解动态数组扩容机制的课程入口。",
            "aliases": ["满容量判定"],
            "relations": [{
                "target_name": "动态数组扩容",
                "relation_type": "prerequisite",
                "reason": "必须先识别容量耗尽，才能确定何时执行扩容",
            }],
        },
        {
            "name": "动态数组扩容",
            "statement": "倍增扩容把少数 O(n) 复制成本分摊到一系列插入，使平均单次插入保持常数阶。",
            "knowledge_type": "principle",
            "conditions": ["扩容因子大于 1 且按几何级数增长"],
            "boundaries": ["结论描述摊还成本，不等于每次插入的最坏成本"],
            "capability_points": [{
                "name": "动态数组扩容实现",
                "observable_behavior": "独立实现倍增扩容并用复制次数解释摊还复杂度",
            }],
            "misconceptions": [{
                "name": "把单次复制成本当作每次插入成本",
                "observable_error_pattern": "看到一次扩容需要复制 n 个元素，就断言每次插入都是 O(n)",
                "discrimination": "区分单次操作最坏成本与一系列操作的摊还成本",
                "repair_strategy": "列出连续插入过程中的扩容位置与累计复制次数后重新计算平均成本",
            }],
            "mastery_criteria": [{
                "name": "扩容实现与分析达标",
                "observable_performance": "独立实现倍增扩容，并正确说明最坏成本与摊还成本的区别",
                "verification_method": "运行连续插入测试并提交复杂度推导",
            }],
            "aliases": ["可变长数组"],
        },
    ]


def _blueprint_course() -> dict:
    course = {
        "course_id": "course-1",
        "course_name": "数据结构",
        "course_purpose": "systematic",
        "nodes": [{
            "node_id": "section-1",
            "node_level": 2,
            "node_name": "线性表与动态数组",
            "learning_objective": "能够实现动态数组扩容并分析摊还复杂度",
            "knowledge_structure": [{
                "concept_group": "动态容量管理",
                "description": "识别扩容触发条件，并解释倍增扩容的摊还成本",
                "knowledge_points": _knowledge_points(),
            }],
            "key_points": ["容量耗尽判定", "动态数组扩容"],
            "content_blocks": [],
            "generation_status": "completed",
            "node_content": (
                "## 容量耗尽判定\n\n根据长度与容量识别扩容触发时机。\n\n"
                "## 动态数组扩容\n\n实现倍增扩容，并区分最坏成本与摊还成本。"
            ),
        }],
    }
    set_node_content_blocks(course["nodes"][0], course["nodes"][0]["node_content"])
    return course


def _canonical_course() -> dict:
    document = refresh_document_revision(CourseDocument(
        course_id="course-1",
        title="数据结构",
        sections=[CourseSection(
            section_id="section-1",
            parent_section_id="chapter-1",
            title="线性表与动态数组",
            position=0,
            level=2,
            learning_objective="能够实现动态数组扩容并分析摊还复杂度",
        )],
        blocks=[
            CourseBlock(
                block_id="section-1-1-custom",
                section_id="section-1",
                position=0,
                role="concept",
                payload={"markdown": "扩容触发条件。"},
            ),
            CourseBlock(
                block_id="section-1-2-custom",
                section_id="section-1",
                position=1,
                role="concept",
                payload={"markdown": "倍增扩容与摊还成本。"},
            ),
        ],
    ))
    blueprint = _blueprint_course()
    return {
        "course_id": "course-1",
        "course_name": "数据结构",
        "course_schema_version": "course_document_v1",
        "course_document_authoritative": True,
        "course_document": document.model_dump(mode="json"),
        "course_document_revision": document.document_revision,
        "current_course_version_id": document.document_revision,
        "course_operation_log": [],
        "course_knowledge_base": compile_course_knowledge_base(
            blueprint, course_map=compile_course_knowledge_map(blueprint),
        ),
    }


class MemoryStorage:
    def __init__(self, course: dict) -> None:
        self.course = deepcopy(course)
        self.save_count = 0

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)
        self.save_count += 1


def _client(course: dict | None = None) -> tuple[TestClient, MemoryStorage]:
    storage = MemoryStorage(course if course is not None else _canonical_course())
    repository = CourseDocumentRepository(storage)
    app = FastAPI()
    app.include_router(knowledge_libraries.router, prefix="/api")
    app.dependency_overrides[
        knowledge_libraries.get_course_document_repository
    ] = lambda: repository
    return TestClient(app), storage


def _revised_knowledge_base(course: dict) -> dict:
    revised = deepcopy(course["course_knowledge_base"])
    for point in revised["knowledge_points"]:
        if point["name"] == "容量耗尽判定":
            point["statement"] = "长度等于容量时，插入前必须先获得更大的连续存储空间。"
            point["revision_id"] = "ckpr_revised"
    revised["revision_id"] = "ckbr_revised"
    return revised


def _candidate_body(course: dict, **overrides) -> dict:
    body = {
        "operation": "revise_knowledge_point",
        "reason": "补充扩容触发条件的精确表述",
        "proposed_knowledge_base": _revised_knowledge_base(course),
        "identity_map": {},
    }
    body.update(overrides)
    return body


# --- 候选预览：确认前不改活动知识库 -----------------------------------------


def test_candidate_preview_returns_impact_without_writing() -> None:
    """预览返回质量报告与影响面，但不写知识库。"""
    course = _canonical_course()
    client, storage = _client(course)

    response = client.post(
        "/api/courses/course-1/knowledge-library/candidates",
        json=_candidate_body(course),
    )

    assert response.status_code == 200
    candidate = response.json()["candidate"]
    assert candidate["confirmable"] is True
    assert candidate["operation"] == "revise_knowledge_point"
    assert candidate["impact_report"]["changed_knowledge_ids"]
    assert candidate["quality_report"]["passed"] is True
    # 关键：预览没有落盘。
    assert storage.save_count == 0
    assert storage.course["course_knowledge_base"]["revision_id"] == (
        course["course_knowledge_base"]["revision_id"]
    )


def test_non_whitelisted_operation_is_rejected_with_400() -> None:
    """白名单之外的操作是客户端错误，返回 400 与可读代码。"""
    course = _canonical_course()
    client, storage = _client(course)

    response = client.post(
        "/api/courses/course-1/knowledge-library/candidates",
        json=_candidate_body(course, operation="delete_everything"),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "knowledge_command_not_whitelisted"
    assert storage.save_count == 0


def test_identity_moving_operation_requires_mapping() -> None:
    """拆分会移动稳定 ID，缺少映射时在 HTTP 层就被拒绝。"""
    course = _canonical_course()
    client, _ = _client(course)

    response = client.post(
        "/api/courses/course-1/knowledge-library/candidates",
        json=_candidate_body(course, operation="split_knowledge_point"),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "knowledge_identity_map_required"


def test_candidate_failing_quality_gate_is_returned_but_not_confirmable() -> None:
    """未过质量门的候选仍返回（审阅者要看原因），但标为不可确认。"""
    course = _canonical_course()
    client, _ = _client(course)
    broken = deepcopy(course["course_knowledge_base"])
    broken["knowledge_points"] = []
    broken["revision_id"] = "ckbr_broken"

    response = client.post(
        "/api/courses/course-1/knowledge-library/candidates",
        json=_candidate_body(course, proposed_knowledge_base=broken),
    )

    assert response.status_code == 200
    candidate = response.json()["candidate"]
    assert candidate["confirmable"] is False
    assert candidate["blocking_issues"]


# --- 确认：原子提交与幂等 ---------------------------------------------------


def test_confirm_applies_knowledge_and_records_receipt() -> None:
    """确认后知识库生效，回执带新旧修订，课程正文不被知识命令改动。"""
    course = _canonical_course()
    client, storage = _client(course)
    candidate = client.post(
        "/api/courses/course-1/knowledge-library/candidates",
        json=_candidate_body(course),
    ).json()["candidate"]

    response = client.post(
        "/api/courses/course-1/knowledge-library/candidates/confirm",
        json={
            "command_id": "cmd-1",
            "candidate": candidate,
            "proposed_knowledge_base": _revised_knowledge_base(course),
        },
        headers={"X-User-Id": "teacher-1"},
    )

    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert receipt["knowledge_revision_id"] == "ckbr_revised"
    assert receipt["operation"] == "knowledge:revise_knowledge_point"
    assert storage.course["course_knowledge_base"]["revision_id"] == "ckbr_revised"
    assert storage.course["course_document"] == course["course_document"]


def test_replaying_the_same_command_id_returns_the_original_receipt() -> None:
    """重试同一 command_id 不重复应用 —— 响应丢失后的重发必须安全。"""
    course = _canonical_course()
    client, storage = _client(course)
    candidate = client.post(
        "/api/courses/course-1/knowledge-library/candidates",
        json=_candidate_body(course),
    ).json()["candidate"]
    payload = {
        "command_id": "cmd-1",
        "candidate": candidate,
        "proposed_knowledge_base": _revised_knowledge_base(course),
    }

    first = client.post(
        "/api/courses/course-1/knowledge-library/candidates/confirm", json=payload,
    )
    saves_after_first = storage.save_count
    second = client.post(
        "/api/courses/course-1/knowledge-library/candidates/confirm", json=payload,
    )

    assert first.status_code == second.status_code == 200
    assert second.json()["receipt"]["command_id"] == first.json()["receipt"]["command_id"]
    assert storage.save_count == saves_after_first


def test_stale_base_revision_returns_409_not_400() -> None:
    """并发导致的过期是冲突不是参数错误：客户端应刷新重算，而非改负载。"""
    course = _canonical_course()
    client, storage = _client(course)
    candidate = client.post(
        "/api/courses/course-1/knowledge-library/candidates",
        json=_candidate_body(course),
    ).json()["candidate"]
    candidate["base_knowledge_revision_id"] = "ckbr_someone_elses"

    response = client.post(
        "/api/courses/course-1/knowledge-library/candidates/confirm",
        json={
            "command_id": "cmd-1",
            "candidate": candidate,
            "proposed_knowledge_base": _revised_knowledge_base(course),
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "knowledge_base_revision_changed"
    assert storage.save_count == 0


def test_unconfirmable_candidate_cannot_be_confirmed_through_http() -> None:
    """绕过预览直接提交不可确认的候选，HTTP 层同样必须拒绝。"""
    course = _canonical_course()
    client, storage = _client(course)
    broken = deepcopy(course["course_knowledge_base"])
    broken["knowledge_points"] = []
    broken["revision_id"] = "ckbr_broken"
    candidate = client.post(
        "/api/courses/course-1/knowledge-library/candidates",
        json=_candidate_body(course, proposed_knowledge_base=broken),
    ).json()["candidate"]

    response = client.post(
        "/api/courses/course-1/knowledge-library/candidates/confirm",
        json={
            "command_id": "cmd-1",
            "candidate": candidate,
            "proposed_knowledge_base": broken,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "knowledge_candidate_not_confirmable"
    assert storage.save_count == 0
    assert storage.course["course_knowledge_base"]["knowledge_points"]


# --- 修订列表与反向覆盖检查 -------------------------------------------------


def test_revision_log_is_readable_after_confirmation() -> None:
    """教师可以查到这门课的知识演进历史与白名单操作集合。"""
    course = _canonical_course()
    client, _ = _client(course)
    empty = client.get("/api/courses/course-1/knowledge-library/revisions")
    assert empty.status_code == 200
    assert empty.json()["revisions"] == []
    assert "revise_knowledge_point" in empty.json()["whitelisted_operations"]

    candidate = client.post(
        "/api/courses/course-1/knowledge-library/candidates",
        json=_candidate_body(course),
    ).json()["candidate"]
    client.post(
        "/api/courses/course-1/knowledge-library/candidates/confirm",
        json={
            "command_id": "cmd-1",
            "candidate": candidate,
            "proposed_knowledge_base": _revised_knowledge_base(course),
        },
        headers={"X-User-Id": "teacher-1"},
    )

    listed = client.get("/api/courses/course-1/knowledge-library/revisions").json()
    assert len(listed["revisions"]) == 1
    entry = listed["revisions"][0]
    assert entry["operation"] == "revise_knowledge_point"
    assert entry["actor"] == "teacher-1"
    assert entry["revision_id"] == "ckbr_revised"


def test_coverage_check_reports_uncovered_block() -> None:
    """正文块没有知识绑定时报出缺口，供教师发起知识维护。"""
    client, storage = _client()

    response = client.post(
        "/api/courses/course-1/knowledge-library/coverage-check",
        json={"changed_block_ids": ["block-without-binding"]},
    )

    assert response.status_code == 200
    coverage = response.json()["coverage"]
    assert coverage["requires_knowledge_review"] is True
    assert coverage["gaps"]
    # 覆盖检查是只读的，不得写知识库。
    assert storage.save_count == 0


def test_coverage_check_reports_no_gap_for_bound_block() -> None:
    """已被绑定覆盖的正文块不报缺口，否则每次改字都要求知识复核。"""
    course = _canonical_course()
    client, _ = _client(course)
    bound = next(
        item["target_id"] for item in course["course_knowledge_base"]["bindings"]
        if item.get("target_type") == "course_block"
    )

    response = client.post(
        "/api/courses/course-1/knowledge-library/coverage-check",
        json={"changed_block_ids": [bound]},
    )

    coverage = response.json()["coverage"]
    assert coverage["gaps"] == []
    assert coverage["requires_knowledge_review"] is False


# --- 定向单点编辑（教师端界面使用的轻量路径） -------------------------------


def _point_id(course: dict, name: str) -> str:
    for point in course["course_knowledge_base"]["knowledge_points"]:
        if point["name"] == name:
            return point["knowledge_id"]
    raise AssertionError(f"知识点 {name} 不存在")


def test_point_edit_preview_does_not_write() -> None:
    """定向编辑预览同样是只读的。"""
    course = _canonical_course()
    client, storage = _client(course)

    response = client.post(
        "/api/courses/course-1/knowledge-library/points/preview-edit",
        json={
            "knowledge_id": _point_id(course, "容量耗尽判定"),
            "operation": "revise_knowledge_point",
            "value": "长度等于容量时，插入前必须先扩容。",
            "reason": "表述更精确",
        },
    )

    assert response.status_code == 200
    candidate = response.json()["candidate"]
    assert candidate["confirmable"] is True
    assert candidate["impact_report"]["changed_knowledge_ids"]
    assert storage.save_count == 0


def test_point_edit_only_moves_the_target_point_revision() -> None:
    """只有被编辑的知识点修订变化，其余保持不变——这是局部影响面的前提。

    同时断言影响面本身是局部的：只比对修订键还不够，一个改动如果让别的
    知识点也进了 needs_regeneration，"精确影响面"就名存实亡了。
    """
    course = _canonical_course()
    client, _ = _client(course)
    target = _point_id(course, "容量耗尽判定")
    other = _point_id(course, "动态数组扩容")

    response = client.post(
        "/api/courses/course-1/knowledge-library/points/preview-edit",
        json={
            "knowledge_id": target,
            "operation": "revise_knowledge_point",
            "value": "长度等于容量时，插入前必须先扩容。",
            "reason": "表述更精确",
        },
    )

    candidate = response.json()["candidate"]
    changed = candidate["revision_event"]["changed_source_keys"]
    assert f"point:{target}" in changed
    assert f"point:{other}" not in changed

    report = candidate["impact_report"]
    assert report["changed_knowledge_ids"] == [target]
    # 直接重建组只能由被改的知识点驱动；其他知识点若受影响，只能经关系
    # 进入 stale（待复核），语义不同，不得混入直接重建。
    assert {item.get("knowledge_id") for item in report["needs_regeneration"]} == {target}


def test_point_edit_confirm_applies_atomically() -> None:
    """确认后知识库换版，课程正文不受影响。"""
    course = _canonical_course()
    client, storage = _client(course)
    before = course["course_knowledge_base"]["revision_id"]

    response = client.post(
        "/api/courses/course-1/knowledge-library/points/confirm-edit",
        json={
            "command_id": "cmd-point-1",
            "knowledge_id": _point_id(course, "容量耗尽判定"),
            "operation": "revise_knowledge_point",
            "value": "长度等于容量时，插入前必须先扩容。",
            "reason": "表述更精确",
        },
        headers={"X-User-Id": "teacher-1"},
    )

    assert response.status_code == 200
    assert storage.course["course_knowledge_base"]["revision_id"] != before
    assert storage.course["course_document"] == course["course_document"]
    log = client.get("/api/courses/course-1/knowledge-library/revisions").json()["revisions"]
    assert log[-1]["actor"] == "teacher-1"


def test_point_edit_replay_is_idempotent() -> None:
    """同一 command_id 重发不重复应用。"""
    course = _canonical_course()
    client, storage = _client(course)
    payload = {
        "command_id": "cmd-point-1",
        "knowledge_id": _point_id(course, "容量耗尽判定"),
        "operation": "revise_knowledge_point",
        "value": "长度等于容量时，插入前必须先扩容。",
        "reason": "表述更精确",
    }

    client.post("/api/courses/course-1/knowledge-library/points/confirm-edit", json=payload)
    saves = storage.save_count
    second = client.post(
        "/api/courses/course-1/knowledge-library/points/confirm-edit", json=payload,
    )

    assert second.status_code == 200
    assert storage.save_count == saves


def test_point_edit_rejects_unknown_point() -> None:
    """知识点不存在时明确拒绝，不静默无操作。"""
    client, storage = _client()

    response = client.post(
        "/api/courses/course-1/knowledge-library/points/preview-edit",
        json={
            "knowledge_id": "ckp_ghost",
            "operation": "revise_knowledge_point",
            "value": "任意内容",
            "reason": "测试",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "knowledge_point_not_found"
    assert storage.save_count == 0


def test_point_edit_rejects_unsupported_operation() -> None:
    """定向编辑只开放不移动稳定 ID 的操作；拆分必须走完整命令路径。"""
    course = _canonical_course()
    client, _ = _client(course)

    response = client.post(
        "/api/courses/course-1/knowledge-library/points/preview-edit",
        json={
            "knowledge_id": _point_id(course, "容量耗尽判定"),
            "operation": "split_knowledge_point",
            "value": "任意内容",
            "reason": "测试",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "knowledge_point_edit_unsupported"


def test_point_edit_rejects_no_op_edit() -> None:
    """内容没变时不产生空修订，避免下游被无谓地标记待重建。"""
    course = _canonical_course()
    client, _ = _client(course)
    target = next(
        item for item in course["course_knowledge_base"]["knowledge_points"]
        if item["name"] == "容量耗尽判定"
    )

    response = client.post(
        "/api/courses/course-1/knowledge-library/points/preview-edit",
        json={
            "knowledge_id": target["knowledge_id"],
            "operation": "revise_knowledge_point",
            "value": target["statement"],
            "reason": "测试",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "knowledge_point_edit_no_change"
