"""F-2：生成产物落进教师课程空间。

老师的验收是「新建课程→上传资料→生成→产物出现在文件系统里，全程不跳出工作台」。
生成侧本来就产出了大纲/教案/正文，缺的是最后一跳——`course_service` 与
`teacher_course_space` 此前互不引用，文件空间是个孤岛。

这里钉住三条硬要求：

1. **幂等**：重跑生成不得产生重复条目，也不得覆盖老师手动上传的文件；
2. **入库失败不回滚课程**：产物已经生成好了，入库是下游动作，失败如实报出即可；
3. **层级正确**：落在学校模板既有的文件夹（教学大纲/教案/PPT）下的「AI 生成」子目录。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from course_space_publication import (
    GENERATED_DIR,
    MISSING_COURSE_ID,
    MISSING_TEACHER_IDENTITY,
    NO_COURSE_SPACE_PACKAGE,
    SKIP_MESSAGES,
    build_course_artifact_documents,
    publish_course_artifacts,
)
from teacher_course_space import TeacherCourseSpaceRepository


def _course() -> dict:
    return {
        "course_id": "course-f2",
        "course_name": "微积分",
        "teacher_course_brief": {
            "academic_term": "2026 秋季学期",
            "total_class_hours": 8,
        },
        "course_outline": {
            "positioning": "在 8 课时内掌握核心推理链条",
            "learning_objectives": ["能计算导数与定积分"],
            "chapters": [{
                "title": "第1章 极限",
                "sections": [
                    {"section_number": "1.1", "title": "函数极限",
                     "learning_objective": "理解极限"},
                ],
            }],
        },
        "course_teaching_plan": {
            "sections": [{
                "node_id": "L2-1-1", "node_name": "1.1 函数极限",
                "teaching_modules": [{
                    "module_id": "core_explanation", "label": "核心讲解",
                    "teaching_guidance": "先比较两段变化再归纳",
                    "planned_minutes": 15,
                }],
            }],
        },
        "generation_stage_artifacts": {
            "outline": {
                "course_coverage_verdict": {
                    "scale_label": "微型课",
                    "coverage_promise": "只覆盖核心切面",
                    "class_hours": 8,
                    "may_claim_complete_subject": False,
                    "covered_topics": ["函数、极限与连续"],
                    "uncovered_topics": ["中值定理", "洛必达法则与未定式"],
                },
            },
        },
        "nodes": [
            {"node_id": "L1-1", "node_level": 1, "node_name": "第1章 极限"},
            {"node_id": "L2-1-1", "node_level": 2, "node_name": "1.1 函数极限",
             "parent_node_id": "L1-1", "node_content": "极限的直观认识……"},
            {"node_id": "L2-1-2", "node_level": 2, "node_name": "1.2 连续性",
             "parent_node_id": "L1-1", "node_content": "连续性的判定……"},
        ],
    }


@pytest.fixture()
def repo(tmp_path: Path) -> TeacherCourseSpaceRepository:
    return TeacherCourseSpaceRepository(tmp_path / "spaces")


# --- 要求三：层级正确 -------------------------------------------------------


def test_artifacts_land_in_the_school_template_folders():
    """产物必须落进老师既有的归档文件夹，而不是另起一套目录。"""
    documents = build_course_artifact_documents(_course())
    paths = [item["relative_path"] for item in documents]

    assert any(p.startswith(f"0、教学大纲/{GENERATED_DIR}/") for p in paths)
    assert any(p.startswith(f"1、教案/{GENERATED_DIR}/") for p in paths)
    # 正文按章节分层，便于老师按章找。
    assert any(
        p.startswith(f"1、教案/{GENERATED_DIR}/第1章 极限/") for p in paths
    )


def test_every_section_with_content_becomes_one_file():
    documents = build_course_artifact_documents(_course())
    sections = [d for d in documents if d["artifact_type"] == "section_content"]

    assert {d["node_id"] for d in sections} == {"L2-1-1", "L2-1-2"}


def test_sections_without_content_are_not_published():
    """没有正文的小节不该产生空文件。"""
    course = _course()
    for node in course["nodes"]:
        node.pop("node_content", None)
    documents = build_course_artifact_documents(course)

    assert not [d for d in documents if d["artifact_type"] == "section_content"]


def test_outline_document_carries_the_coverage_verdict():
    """归档的大纲必须带上覆盖度结论——否则等于把 D-1 的诚实性丢在导出这一步。"""
    documents = build_course_artifact_documents(_course())
    outline = next(d for d in documents if d["artifact_type"] == "course_outline")

    assert "微型课" in outline["content"]
    assert "本次不覆盖" in outline["content"]
    assert "中值定理" in outline["content"]


# --- 要求一：幂等 -----------------------------------------------------------


def test_republishing_writes_nothing_and_adds_no_duplicate(repo):
    course = _course()
    first = publish_course_artifacts(course, owner_id="t1", repository=repo)
    second = publish_course_artifacts(course, owner_id="t1", repository=repo)
    third = publish_course_artifacts(course, owner_id="t1", repository=repo)

    assert first["status"] == "completed"
    assert len(first["written"]) > 0
    # 第二、三次：全部命中未变更，零写入。
    assert second["written"] == [] and third["written"] == []
    assert len(second["unchanged"]) == len(first["written"])
    # 不重复建包，资产条目不增长。
    assert first["package_id"] == second["package_id"] == third["package_id"]
    package = repo.load_owned(first["package_id"], "t1")
    assert len(package["assets"]) == len(first["written"])
    assert len(repo.list_owned("t1")) == 1


def test_manual_upload_is_never_overwritten(repo):
    """同路径下老师手动上传的文件优先，绝不被重新生成的产物覆盖。"""
    course = _course()
    first = publish_course_artifacts(course, owner_id="t1", repository=repo)
    package = repo.load_owned(first["package_id"], "t1")

    target = next(
        item for item in package["assets"]
        if item["relative_path"].endswith("课程大纲.md")
    )
    # 模拟老师手动传的同名文件：没有 origin 标记、内容不同。
    target.pop("origin", None)
    target["sha256"] = "teacher-edited"
    manual = Path(repo.root) / first["package_id"] / "content" / target["relative_path"]
    manual.write_text("老师手写的大纲", encoding="utf-8")
    repo.save(package)

    second = publish_course_artifacts(course, owner_id="t1", repository=repo)

    assert [c["reason"] for c in second["conflicts"]] == ["manual_upload_present"]
    assert manual.read_text(encoding="utf-8") == "老师手写的大纲"
    # 其余产物不受影响。
    assert second["written"] == []


def test_changed_content_updates_in_place_without_duplicating(repo):
    """课程内容真的变了时要更新，但仍是同一条资产、不新增条目。"""
    course = _course()
    first = publish_course_artifacts(course, owner_id="t1", repository=repo)
    before = len(repo.load_owned(first["package_id"], "t1")["assets"])

    course["nodes"][1]["node_content"] = "改写后的正文内容"
    second = publish_course_artifacts(course, owner_id="t1", repository=repo)

    assert len(second["written"]) == 1
    after = repo.load_owned(first["package_id"], "t1")
    assert len(after["assets"]) == before
    changed = next(
        a for a in after["assets"] if a.get("node_id") == "L2-1-1"
    )
    assert changed["origin"] == "course_generation"


# --- 要求二：入库失败不得让生成失败 -----------------------------------------


def test_publish_never_raises_when_the_repository_is_broken():
    """仓库整个坏掉也只能如实报，不能抛给生成主链路。"""
    class BrokenRepository:
        root = "/nonexistent"

        def list_owned(self, owner_id):
            raise OSError("disk offline")

    report = publish_course_artifacts(
        _course(), owner_id="t1", repository=BrokenRepository(),
    )

    assert report["status"] == "failed"
    assert report["failures"]
    assert "disk offline" in report["failures"][0]["error"]


def test_single_file_failure_does_not_abort_the_rest(repo, monkeypatch):
    """单个文件写失败时，其余产物仍要写进去。"""
    import course_space_publication as module

    real_write = module._write_asset
    calls = {"n": 0}

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("no space left on device")
        return real_write(**kwargs)

    monkeypatch.setattr(module, "_write_asset", flaky)
    report = publish_course_artifacts(_course(), owner_id="t1", repository=repo)

    assert report["status"] == "failed"
    assert len(report["failures"]) == 1
    # 其余的照常写入，不因一个失败全盘放弃。
    assert len(report["written"]) >= 2


def test_missing_owner_is_reported_not_raised(repo):
    report = publish_course_artifacts(_course(), owner_id="", repository=repo)

    assert report["status"] == "skipped"
    # 原因必须指向"缺教师身份"，而不是笼统的"没有课程包"——后者会把人
    # 引去检查空间配置，而真正要做的是带上 X-User-Id。
    assert report["reason"] == MISSING_TEACHER_IDENTITY


def test_course_without_artifacts_is_skipped_cleanly(repo):
    report = publish_course_artifacts(
        {"course_id": "c1", "course_name": "空课程"},
        owner_id="t1", repository=repo,
    )

    assert report["status"] == "skipped"
    assert report["reason"] == "no_publishable_artifact"
    # 没有产物时不该凭空建包。
    assert repo.list_owned("t1") == []


# --- 绑定与真实落盘 ---------------------------------------------------------


def test_package_is_bound_to_the_course_and_reused(repo):
    """包上记 course_id，重跑时按它找回同一个包。"""
    first = publish_course_artifacts(_course(), owner_id="t1", repository=repo)
    package = repo.load_owned(first["package_id"], "t1")

    assert package["course_id"] == "course-f2"
    assert package["created_by"] == "course_generation"
    assert package["template"] == "school_course_materials"


def test_files_are_actually_written_to_disk(repo):
    report = publish_course_artifacts(_course(), owner_id="t1", repository=repo)
    content_root = Path(repo.root) / report["package_id"] / "content"

    written = sorted(
        str(p.relative_to(content_root)) for p in content_root.rglob("*.md")
    )
    assert written == sorted(report["written"])
    # 内容非空且可读。
    for path in content_root.rglob("*.md"):
        assert path.read_text(encoding="utf-8").strip()


def test_generated_assets_are_marked_and_folders_registered(repo):
    report = publish_course_artifacts(_course(), owner_id="t1", repository=repo)
    package = repo.load_owned(report["package_id"], "t1")

    assert all(
        item.get("origin") == "course_generation"
        for item in package["assets"]
    )
    folders = {
        item.get("path") for item in package.get("entries") or []
        if item.get("kind") == "folder"
    }
    assert f"1、教案/{GENERATED_DIR}/第1章 极限" in folders


# --- 缺教师身份：不建包、不入库、如实说明原因 -------------------------------
#
# 「入库失败」这种笼统说法会把一个老师自己就能修的问题（没带 X-User-Id）
# 变成一张工单。所以每种跳过都必须说清是哪一种原因。


def test_missing_teacher_identity_creates_nothing_and_says_why(repo, tmp_path):
    """缺教师身份：不建包、不写文件，且原因明确指向身份而不是笼统失败。"""
    report = publish_course_artifacts(_course(), owner_id="", repository=repo)

    assert report["status"] == "skipped"
    assert report["reason"] == MISSING_TEACHER_IDENTITY
    # 不是"没有课程包"这种会把人引向错误方向的说法。
    assert report["reason"] != NO_COURSE_SPACE_PACKAGE
    assert "教师身份" in report["message"]
    assert "X-User-Id" in report["message"]
    # 什么都没建、什么都没写。
    assert repo.list_owned("") == []
    assert report["written"] == []
    assert not list((tmp_path / "spaces").glob("tcs-*"))


def test_blank_teacher_identity_is_treated_as_missing(repo):
    """只有空白字符的身份等同于没有身份，不得被当成合法 owner。"""
    report = publish_course_artifacts(_course(), owner_id="   ", repository=repo)

    assert report["reason"] == MISSING_TEACHER_IDENTITY
    assert report["written"] == []


def test_missing_course_id_is_reported_separately_from_identity(repo):
    """缺 course_id 与缺身份是两回事，修法不同，不能混成一个原因。"""
    course = _course()
    course.pop("course_id")

    report = publish_course_artifacts(course, owner_id="t1", repository=repo)

    assert report["reason"] == MISSING_COURSE_ID
    assert "course_id" in report["message"]
    assert repo.list_owned("t1") == []


def test_every_skip_reason_carries_an_actionable_message():
    """每个跳过原因都必须有对应文案，不能有"沉默的跳过"。"""
    for reason, message in SKIP_MESSAGES.items():
        assert message.strip(), f"{reason} 缺少说明文案"
        # 都要说清"没写任何文件"，避免老师以为写了一半。
        assert "未" in message


def test_publish_endpoint_rejects_missing_identity_without_creating_a_package(
    tmp_path, monkeypatch,
):
    """走真实 HTTP 端点：不带 X-User-Id 时不建包、不入库，并说清原因。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_course_or_404
    from routers import courses as courses_router

    async def fake_course(course_id: str):
        return _course()

    monkeypatch.setattr(courses_router, "get_course_or_404", fake_course)
    called = {"n": 0}

    def unexpected(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("缺身份时不得进入入库流程")

    monkeypatch.setattr(courses_router, "publish_course_artifacts", unexpected)

    app = FastAPI()
    app.include_router(courses_router.router, prefix="/api")
    app.dependency_overrides[get_course_or_404] = fake_course
    client = TestClient(app)

    response = client.post("/api/courses/course-f2/course-space/publish")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "skipped"
    assert body["reason"] == MISSING_TEACHER_IDENTITY
    assert "教师身份" in body["message"]
    assert body["written"] == [] and body["package_id"] == ""
    # 根本没有走到入库这一步。
    assert called["n"] == 0


def test_publish_endpoint_rejects_the_shared_default_identity(
    tmp_path, monkeypatch,
):
    """共享的 default_user 不算教师身份——否则产物会落进所有人共用的空间。

    教师课程空间自身的写入口（require_user_id）就是这么判的，这里必须一致。
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from learner_context import DEFAULT_USER_ID
    from routers import courses as courses_router

    async def fake_course(course_id: str):
        return _course()

    monkeypatch.setattr(courses_router, "get_course_or_404", fake_course)
    monkeypatch.setattr(
        courses_router, "publish_course_artifacts",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("不得入库")),
    )

    app = FastAPI()
    app.include_router(courses_router.router, prefix="/api")
    client = TestClient(app)

    response = client.post(
        "/api/courses/course-f2/course-space/publish",
        headers={"X-User-Id": DEFAULT_USER_ID},
    )

    assert response.json()["reason"] == MISSING_TEACHER_IDENTITY
