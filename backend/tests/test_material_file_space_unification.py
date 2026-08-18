"""F-3 统一上传入口：生成侧资料自动进文件空间。

改造前两条上传路径各存各的：课程生成的「添加资料」写 `material_storage`
（`data/materials/mat-*`），文件空间写 `data/teacher_course_spaces/tcs-*`，
零交集。老师在生成里传了资料，去文件空间找不到——这正是要修的。

改法是**存储不动、文件空间建引用**：解析产物与生成链路都依赖 `mat-*`，搬存储会
切断那条链路。所以上传仍进 material_storage，同时在教师的文件空间登记一条引用。

这组测试钉住四条边界：
1. 上传即登记，且幂等；
2. **跨教师去重不串包**（最危险的一条，见下）；
3. 删引用不碰底层资产；
4. 登记失败不阻断上传。
"""

from __future__ import annotations

import pytest

from material_storage import MaterialRepository
from teacher_course_space import (
    MATERIAL_REFERENCE_KIND,
    TeacherCourseSpaceRepository,
)


class _Upload:
    """最小 UploadFile 替身：save_upload 只用到 filename/content_type/read。"""

    def __init__(self, filename: str, data: bytes) -> None:
        self.filename = filename
        self.content_type = "text/markdown"
        self._data = data
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._data):
            return b""
        chunk = self._data[self._offset:] if size < 0 else self._data[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk


@pytest.fixture()
def stores(tmp_path):
    return (
        MaterialRepository(tmp_path / "materials"),
        TeacherCourseSpaceRepository(tmp_path / "spaces"),
    )


def _references(space: TeacherCourseSpaceRepository, owner: str) -> list[dict]:
    found: list[dict] = []
    for summary in space.list_owned(owner):
        package = space.load_owned(summary["package_id"], owner)
        found.extend(
            item for item in package.get("assets", [])
            if item.get("source_kind") == MATERIAL_REFERENCE_KIND
        )
    return found


@pytest.mark.asyncio
async def test_uploaded_material_shows_up_in_the_file_space(stores):
    """用户抱怨的核心：传了资料，文件空间要看得到。"""
    materials, space = stores
    asset = await materials.save_upload(_Upload("讲义.md", b"# hello"))

    result = space.register_material_reference("teacher-a", asset)

    assert result["outcome"] == "registered"
    assert result["material_asset_id"] == asset.asset_id
    references = _references(space, "teacher-a")
    assert [item["material_asset_id"] for item in references] == [asset.asset_id]
    # 引用条目不复制字节：包内没有 stored_name 副本
    assert references[0]["stored_name"] == ""


@pytest.mark.asyncio
async def test_registering_the_same_material_twice_is_idempotent(stores):
    materials, space = stores
    asset = await materials.save_upload(_Upload("讲义.md", b"# hello"))

    space.register_material_reference("teacher-a", asset)
    again = space.register_material_reference("teacher-a", asset)

    assert again["outcome"] == "duplicate"
    assert len(_references(space, "teacher-a")) == 1


@pytest.mark.asyncio
async def test_global_dedupe_does_not_leak_one_teachers_file_into_anothers_space(stores):
    """最危险的一条：material_storage 按 sha256 **全局**去重。

    teacher B 上传与 teacher A 相同的文件时，`save_upload` 会直接返回 A 的
    `mat-*` 资产。今天无害（资料无归属、无列表），但登记进按 owner 分包的文件
    空间后，如果引用跟着资产走，B 的文件就会出现在 A 的空间里——反之亦然。

    所以引用必须记在各自 owner 的包下：同一底层资产可被多人各自引用，互不可见。
    """
    materials, space = stores
    same_bytes = b"# shared handout"
    asset_a = await materials.save_upload(_Upload("讲义.md", same_bytes))
    asset_b = await materials.save_upload(_Upload("讲义.md", same_bytes))
    assert asset_a.asset_id == asset_b.asset_id, "前提：全局去重确实返回同一资产"

    ref_a = space.register_material_reference("teacher-a", asset_a)
    ref_b = space.register_material_reference("teacher-b", asset_b)

    # 两条引用落在不同的包里
    assert ref_a["package_id"] != ref_b["package_id"]
    # 各自只看得到自己那条
    assert len(_references(space, "teacher-a")) == 1
    assert len(_references(space, "teacher-b")) == 1
    a_packages = {item["package_id"] for item in space.list_owned("teacher-a")}
    b_packages = {item["package_id"] for item in space.list_owned("teacher-b")}
    assert a_packages.isdisjoint(b_packages)


@pytest.mark.asyncio
async def test_reference_download_reads_through_to_the_underlying_material(stores, monkeypatch):
    """引用条目不存字节，下载要能转发到底层 material_storage。"""
    materials, space = stores
    monkeypatch.setattr("material_storage.material_repository", materials)
    asset = await materials.save_upload(_Upload("讲义.md", b"# payload"))
    reference = space.register_material_reference("teacher-a", asset)
    package = space.load_owned(reference["package_id"], "teacher-a")

    found, path = space.source_file(package, reference["asset_id"])

    assert found["asset_id"] == reference["asset_id"]
    assert path.read_bytes() == b"# payload"


@pytest.mark.asyncio
async def test_deleting_the_reference_keeps_the_underlying_material(stores):
    """删引用只是"我的文件空间里不要了"，不能顺手毁掉生成链路在用的资产。"""
    materials, space = stores
    asset = await materials.save_upload(_Upload("讲义.md", b"# keep me"))
    reference = space.register_material_reference("teacher-a", asset)
    package = space.load_owned(reference["package_id"], "teacher-a")

    space.delete_asset(package, reference["asset_id"])

    assert _references(space, "teacher-a") == []
    assert materials.get_asset(asset.asset_id) is not None, "底层资产必须还在"
    assert materials.source_path(materials.get_asset(asset.asset_id)).is_file()


@pytest.mark.asyncio
async def test_deleting_a_folder_of_references_keeps_underlying_materials(stores):
    """删文件夹会级联删资产，引用条目同样只删引用。"""
    materials, space = stores
    asset = await materials.save_upload(_Upload("讲义.md", b"# keep me too"))
    reference = space.register_material_reference("teacher-a", asset)
    package = space.load_owned(reference["package_id"], "teacher-a")
    folder = reference["relative_path"].rsplit("/", 1)[0]

    space.delete_folder(package, folder)

    assert _references(space, "teacher-a") == []
    assert materials.get_asset(asset.asset_id) is not None


@pytest.mark.asyncio
async def test_registration_failure_does_not_break_the_upload(stores, monkeypatch):
    """文件空间是可见性，上传+解析才是生成链路的命脉。

    登记失败时上传必须照常成功——否则文件空间的任何问题都会连带打断课程生成。
    """
    from routers import materials as materials_router

    materials, space = stores
    monkeypatch.setattr(materials_router, "material_repository", materials)

    def _boom(*args, **kwargs):
        raise RuntimeError("文件空间不可用")

    monkeypatch.setattr(
        materials_router.teacher_course_space_repository,
        "register_material_reference",
        _boom,
    )

    payload = await materials_router.upload_material(
        file=_Upload("讲义.md", b"# still fine"),
        upload_batch_id="batch-1",
        x_user_id="teacher-a",
    )

    assert payload["asset_id"].startswith("mat-")
    assert payload["course_space"] == {"registered": False}


@pytest.mark.asyncio
async def test_upload_without_identity_still_works(stores, monkeypatch):
    """`/api/materials` 历史上不要求身份，改造不能把它变成强制。"""
    from routers import materials as materials_router

    materials, _space = stores
    monkeypatch.setattr(materials_router, "material_repository", materials)

    payload = await materials_router.upload_material(
        file=_Upload("讲义.md", b"# anonymous"),
        upload_batch_id="",
        x_user_id=None,
    )

    assert payload["asset_id"].startswith("mat-")
    assert payload["course_space"] == {"registered": False}
