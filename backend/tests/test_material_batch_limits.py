"""针对同一上传批次（upload_batch_id）的材料总数量 / 总字节数上限做校验。"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from material_storage import (
    DEFAULT_MAX_BATCH_BYTES,
    DEFAULT_MAX_BATCH_FILES,
    MaterialRepository,
    MaterialStorageError,
)


class FakeUpload:
    def __init__(self, filename: str, content: bytes, content_type: str = "text/markdown"):
        self.filename = filename
        self.content_type = content_type
        self._content = content
        self._offset = 0

    async def read(self, size: int) -> bytes:
        if self._offset >= len(self._content):
            return b""
        chunk = self._content[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk


@pytest.mark.asyncio
async def test_batch_file_count_limit_gives_clear_error(tmp_path):
    repository = MaterialRepository(tmp_path / "materials")
    batch_id = "course-batch-1"
    limit = 3
    for i in range(limit):
        await repository.save_upload(
            FakeUpload(f"note-{i}.md", f"# note {i}\n\ncontent {i}".encode()),
            upload_batch_id=batch_id,
            max_batch_files=limit,
        )

    with pytest.raises(MaterialStorageError) as excinfo:
        await repository.save_upload(
            FakeUpload("note-overflow.md", b"# overflow\n\nmore content"),
            upload_batch_id=batch_id,
            max_batch_files=limit,
        )

    message = str(excinfo.value)
    assert "数量" in message
    assert str(limit) in message
    assert str(limit + 1) in message or str(limit) in message


@pytest.mark.asyncio
async def test_batch_total_bytes_limit_gives_clear_error(tmp_path):
    repository = MaterialRepository(tmp_path / "materials")
    batch_id = "course-batch-bytes"
    per_file = 100
    byte_limit = 250

    await repository.save_upload(
        FakeUpload("a.md", b"a" * per_file),
        upload_batch_id=batch_id,
        max_batch_bytes=byte_limit,
    )
    await repository.save_upload(
        FakeUpload("b.md", b"b" * per_file),
        upload_batch_id=batch_id,
        max_batch_bytes=byte_limit,
    )

    with pytest.raises(MaterialStorageError) as excinfo:
        await repository.save_upload(
            FakeUpload("c.md", b"c" * per_file),
            upload_batch_id=batch_id,
            max_batch_bytes=byte_limit,
        )

    message = str(excinfo.value)
    assert "大小" in message
    assert str(byte_limit) in message
    assert "200" in message  # 已使用字节数应体现在错误信息中


@pytest.mark.asyncio
async def test_different_batches_do_not_share_limits(tmp_path):
    repository = MaterialRepository(tmp_path / "materials")
    limit = 1
    await repository.save_upload(
        FakeUpload("first.md", b"# a\n\ncontent"),
        upload_batch_id="batch-a",
        max_batch_files=limit,
    )
    # 不同批次不应受彼此计数影响
    asset = await repository.save_upload(
        FakeUpload("second.md", b"# b\n\ncontent"),
        upload_batch_id="batch-b",
        max_batch_files=limit,
    )
    assert asset is not None


def test_material_upload_api_returns_422_on_batch_overflow(monkeypatch, tmp_path):
    from routers import materials

    repository = MaterialRepository(tmp_path / "materials")
    monkeypatch.setattr(materials, "material_repository", repository)
    app = FastAPI()
    app.include_router(materials.router, prefix="/api")
    client = TestClient(app)

    monkeypatch.setenv("MATERIAL_MAX_BATCH_FILES", "1")
    batch_id = "api-batch-1"

    first = client.post(
        "/api/materials",
        data={"upload_batch_id": batch_id},
        files={"file": ("one.md", b"# one\n\ncontent", "text/markdown")},
    )
    assert first.status_code == 201

    second = client.post(
        "/api/materials",
        data={"upload_batch_id": batch_id},
        files={"file": ("two.md", b"# two\n\nmore content", "text/markdown")},
    )
    assert second.status_code == 422
    detail = second.json()["detail"]
    assert "数量" in detail
    assert "1" in detail


def test_default_batch_limits_are_reasonable_and_exported():
    # 数量上限应与 models.py 中 CourseGenerationRequest.material_bindings 的 max_length=30 语义对齐，
    # 避免用户传完文件后才在生成请求校验阶段发现绑定不了。
    assert DEFAULT_MAX_BATCH_FILES == 30
    assert DEFAULT_MAX_BATCH_BYTES > 0
