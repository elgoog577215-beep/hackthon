"""前端静态文件的缓存契约。

Vite 构建后的 ``assets`` 文件名包含内容哈希，可以长期缓存；
``index.html`` 会引用当前版本的哈希文件，必须每次重新验证。
"""

from os import PathLike

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

FilePath = str | PathLike[str]

ENTRYPOINT_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}

REVALIDATE_HEADERS = {
    "Cache-Control": "no-cache, must-revalidate",
}

IMMUTABLE_ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"


def frontend_file_response(file_path: FilePath, *, entrypoint: bool = False) -> FileResponse:
    """返回带明确缓存策略的前端文件。"""

    headers = ENTRYPOINT_HEADERS if entrypoint else REVALIDATE_HEADERS
    return FileResponse(file_path, headers=headers)


class ImmutableStaticFiles(StaticFiles):
    """为 Vite 带哈希的构建资源添加长期不变缓存。"""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = IMMUTABLE_ASSET_CACHE_CONTROL
        return response
