from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.routing import Mount

from static_serving import (
    ENTRYPOINT_HEADERS,
    IMMUTABLE_ASSET_CACHE_CONTROL,
    ImmutableStaticFiles,
    frontend_file_response,
)


def test_entrypoint_is_never_reused_without_validation(tmp_path: Path):
    index_html = tmp_path / "index.html"
    index_html.write_text("<div id=\"app\"></div>", encoding="utf-8")

    response = frontend_file_response(index_html, entrypoint=True)

    for header, expected in ENTRYPOINT_HEADERS.items():
        assert response.headers[header] == expected


@pytest.mark.asyncio
async def test_hashed_assets_are_cached_as_immutable(tmp_path: Path):
    asset = tmp_path / "index-buildhash.js"
    asset.write_text("console.log('ok')", encoding="utf-8")
    app = Starlette(routes=[Mount("/", app=ImmutableStaticFiles(directory=tmp_path))])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/index-buildhash.js")

    assert response.status_code == 200
    assert response.headers["cache-control"] == IMMUTABLE_ASSET_CACHE_CONTROL
