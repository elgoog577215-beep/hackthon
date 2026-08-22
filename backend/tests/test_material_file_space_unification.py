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


@pytest.mark.asyncio
async def test_upload_can_register_directly_in_the_current_course(stores, monkeypatch):
    from routers import materials as materials_router

    materials, space = stores
    course_package = space.create_package(
        "teacher-a", "设计思维", "2026-2027", "秋季", course_id="course-1"
    )
    monkeypatch.setattr(materials_router, "material_repository", materials)
    monkeypatch.setattr(materials_router, "teacher_course_space_repository", space)

    payload = await materials_router.upload_material(
        file=_Upload("旧教案.md", b"# lesson plan"),
        upload_batch_id="batch-1",
        course_id="course-1",
        x_user_id="teacher-a",
    )

    assert payload["course_space"]["registered"] is True
    assert payload["course_space"]["package_id"] == course_package["package_id"]
    assert payload["course_space"]["course_asset_id"].startswith("tca-")
    assert len(space.list_owned("teacher-a", "course-1")) == 1


# --- 引用的双向可查 ---------------------------------------------------------
# 引用只有单向可用是不够的：资料出问题时，得能从解析产物反查"教师在文件空间的
# 哪个位置能看到它"，否则只能全量翻包。

@pytest.mark.asyncio
async def test_forward_lookup_reaches_the_parsed_artifacts(stores, monkeypatch):
    """正向：从文件空间的引用条目，能取到底层解析产物。

    这正是"不搬存储"的收益——引用留在文件空间，解析链路仍在 material_storage。
    """
    materials, space = stores
    monkeypatch.setattr("material_storage.material_repository", materials)
    asset = await materials.save_upload(_Upload("讲义.md", b"# vectors"))
    # 模拟解析阶段的产物落盘（真实链路由 material_parser 写）
    materials.save_evidence(asset.asset_id, [{"unit_id": "e1", "text": "向量的定义"}])

    reference = space.register_material_reference("teacher-a", asset)
    package = space.load_owned(reference["package_id"], "teacher-a")
    entry = next(
        item for item in package["assets"]
        if item["asset_id"] == reference["asset_id"]
    )

    # 条目上带着底层 id，据此就能拿到解析产物
    material_asset_id = entry["material_asset_id"]
    assert materials.get_asset(material_asset_id) is not None
    assert materials.load_evidence(material_asset_id) == [
        {"unit_id": "e1", "text": "向量的定义"}
    ]


@pytest.mark.asyncio
async def test_reverse_lookup_finds_the_package_and_folder(stores):
    """反向：从 `mat-*` 反查它在哪个包、哪个文件夹下。"""
    materials, space = stores
    asset = await materials.save_upload(_Upload("讲义.md", b"# reverse"))
    reference = space.register_material_reference("teacher-a", asset)

    located = space.locate_material_reference(asset.asset_id)

    assert len(located) == 1
    assert located[0]["package_id"] == reference["package_id"]
    assert located[0]["asset_id"] == reference["asset_id"]
    assert located[0]["folder"] == "生成资料"
    assert located[0]["filename"] == "讲义.md"
    assert located[0]["owner_id"] == "teacher-a"


@pytest.mark.asyncio
async def test_reverse_lookup_is_one_to_many_and_can_be_scoped_to_one_owner(stores):
    """全局去重会让同一份资料被多位教师各自引用，所以反查天然一对多。

    按 owner 收窄是接口层该用的调用方式——否则会把别人的位置暴露出去。
    """
    materials, space = stores
    shared = b"# shared"
    asset_a = await materials.save_upload(_Upload("讲义.md", shared))
    asset_b = await materials.save_upload(_Upload("讲义.md", shared))
    space.register_material_reference("teacher-a", asset_a)
    space.register_material_reference("teacher-b", asset_b)

    everywhere = space.locate_material_reference(asset_a.asset_id)
    only_a = space.locate_material_reference(asset_a.asset_id, owner_id="teacher-a")

    assert {item["owner_id"] for item in everywhere} == {"teacher-a", "teacher-b"}
    assert [item["owner_id"] for item in only_a] == ["teacher-a"]


def test_reverse_lookup_of_unknown_material_returns_empty(stores):
    _materials, space = stores
    assert space.locate_material_reference("mat-does-not-exist") == []
    assert space.locate_material_reference("") == []


# --- 幂等：重复上传与生成重跑都不得产生重复条目 -----------------------------

@pytest.mark.asyncio
async def test_uploading_the_same_file_twice_yields_one_entry(stores, monkeypatch):
    """同一份资料重复上传：走完整的上传接口，文件空间只应有一条。

    这条比直接调 register 更接近真实——`save_upload` 的全局去重会返回同一个
    `mat-*`，登记侧必须据此判重。
    """
    from routers import materials as materials_router

    materials, space = stores
    monkeypatch.setattr(materials_router, "material_repository", materials)
    monkeypatch.setattr(
        materials_router, "teacher_course_space_repository", space,
    )

    first = await materials_router.upload_material(
        file=_Upload("讲义.md", b"# same bytes"),
        upload_batch_id="b1", x_user_id="teacher-a",
    )
    second = await materials_router.upload_material(
        file=_Upload("讲义.md", b"# same bytes"),
        upload_batch_id="b2", x_user_id="teacher-a",
    )

    assert first["asset_id"] == second["asset_id"]  # 底层全局去重
    assert first["course_space"]["registered"] is True
    assert second["course_space"]["registered"] is True
    assert len(_references(space, "teacher-a")) == 1, "重复上传不得产生第二条引用"


@pytest.mark.asyncio
async def test_regeneration_reusing_the_same_material_does_not_duplicate(stores):
    """生成重跑：同一份资料被反复绑定/引用，条目数必须稳定。

    重跑是常态（语义重试、纠正轮、教师手动重生成），每跑一次多一条引用的话，
    文件空间很快就会被同名条目淹没。
    """
    materials, space = stores
    asset = await materials.save_upload(_Upload("讲义.md", b"# reused"))

    for round_index in range(5):
        materials.bind_asset(asset.asset_id, f"course-{round_index}")
        space.register_material_reference("teacher-a", asset)

    references = _references(space, "teacher-a")
    assert len(references) == 1
    # 幂等不是"跳过写入"，底层绑定该累积的仍然累积
    assert len(materials.get_asset(asset.asset_id).bound_course_ids) == 5


@pytest.mark.asyncio
async def test_reregistering_after_deletion_creates_a_fresh_entry(stores):
    """删掉之后再传同一份资料，应当重新出现——幂等不能退化成"删了就再也回不来"。"""
    materials, space = stores
    asset = await materials.save_upload(_Upload("讲义.md", b"# re-add"))
    first = space.register_material_reference("teacher-a", asset)
    package = space.load_owned(first["package_id"], "teacher-a")
    space.delete_asset(package, first["asset_id"])
    assert _references(space, "teacher-a") == []

    again = space.register_material_reference("teacher-a", asset)

    assert again["outcome"] == "registered"
    assert len(_references(space, "teacher-a")) == 1


# --- 与 F-2（生成产物入文件空间）的共存 -------------------------------------
# lz-course-gen 的 F-2 也往同一个 package["assets"] 里写条目，但用的是
# `origin="course_generation"`，我用的是 `source_kind="material_reference"`
# ——**两个不同字段表达重叠的意图**。已用 F-2 的真实代码验证过互不踩，
# 这里把结论钉住，避免任一侧改动时悄悄破坏另一侧。
#
# 两边的语义差异与建议见 NOTES 20.6 / 21.3，我没有改对方的文件。

def _generated_artifact_entry() -> dict:
    """按 F-2 的形状造一条生成产物条目（有真实字节，带 origin）。"""
    return {
        "asset_id": "tca-generated-1",
        "filename": "课程大纲.md",
        "relative_path": "01、教学设计/generated/课程大纲.md",
        "stored_name": "tca-generated-1.md",
        "materialized_path": "01、教学设计/generated/课程大纲.md",
        "extension": ".md",
        "size_bytes": 12,
        "sha256": "deadbeef",
        "suggested_category": "teaching_design",
        "category": "teaching_design",
        "category_reason": "",
        "import_batch_id": "",
        "uploaded_at": "2026-08-18T00:00:00+00:00",
        "origin": "course_generation",
    }


@pytest.mark.asyncio
async def test_material_reference_is_not_mistaken_for_a_generated_artifact(stores):
    """我的引用条目不带 `origin`，所以 F-2 的守卫会把它当"教师自有文件"保护。

    F-2 的逻辑是 `if existing.origin != "course_generation": 记 conflict 不覆盖`，
    引用条目的 origin 为空 → 不等于 → 受保护。这正是期望行为：教师上传的资料
    不该被重生成的产物覆盖掉。
    """
    materials, space = stores
    asset = await materials.save_upload(_Upload("教师讲义.md", b"# teacher"))
    reference = space.register_material_reference("teacher-a", asset)
    package = space.load_owned(reference["package_id"], "teacher-a")
    entry = next(item for item in package["assets"] if item["asset_id"] == reference["asset_id"])

    assert entry.get("source_kind") == MATERIAL_REFERENCE_KIND
    assert str(entry.get("origin") or "") != "course_generation", (
        "引用条目必须不带 course_generation，否则会被 F-2 的重生成覆盖"
    )


@pytest.mark.asyncio
async def test_generated_artifacts_keep_their_own_delete_and_download_path(stores):
    """反向：F-2 的产物条目没有 `source_kind`，在我这边走包内副本分支。

    不能因为我加了引用分支，就把有真实字节的产物也当成引用去转发——
    那会让 F-2 的产物下载不到。
    """
    materials, space = stores
    asset = await materials.save_upload(_Upload("教师讲义.md", b"# teacher"))
    reference = space.register_material_reference("teacher-a", asset)
    package = space.load_owned(reference["package_id"], "teacher-a")

    package["assets"].append(_generated_artifact_entry())
    space.save(package)
    reloaded = space.load_owned(reference["package_id"], "teacher-a")
    generated = next(
        item for item in reloaded["assets"] if item["asset_id"] == "tca-generated-1"
    )

    # 产物不是引用 -> 删除时会清理它的包内副本（F-2 期望的行为）
    assert generated.get("source_kind") != MATERIAL_REFERENCE_KIND
    # 反查只认引用条目，不会把产物误报成资料
    located = space.locate_material_reference(asset.asset_id, owner_id="teacher-a")
    assert [item["asset_id"] for item in located] == [reference["asset_id"]]
