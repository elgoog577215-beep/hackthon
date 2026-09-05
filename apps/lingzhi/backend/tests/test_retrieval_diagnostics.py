from __future__ import annotations

import pytest

from retrieval_diagnostics import (
    RetrievalDiagnosticError,
    assert_retrieval_feature,
    run_retrieval_matrix,
)


class FakeGateway:
    def __init__(self, *, failing_purpose: str = "") -> None:
        self.failing_purpose = failing_purpose
        self.requests = []

    async def retrieve(self, request):
        self.requests.append(request)
        completed = request.purpose != self.failing_purpose
        return {
            "provider": "searxng",
            "purpose": request.purpose,
            "category": request.category,
            "status": "completed" if completed else "failed_fallback_local",
            "queries": request.queries,
            "sources": ([{"url": "https://example.edu/source"}] if completed else []),
            "receipt": {
                "status": "completed" if completed else "failed_fallback_local",
                "source_count": 1 if completed else 0,
                "error_codes": [] if completed else ["no_sources"],
            },
        }


def test_retrieval_feature_requires_live_on_searxng() -> None:
    assert_retrieval_feature({
        "mode": "on",
        "enabled": True,
        "enabled_for_user": True,
        "provider": "searxng",
        "provider_configured": True,
    })

    with pytest.raises(RetrievalDiagnosticError):
        assert_retrieval_feature({
            "mode": "off",
            "enabled": False,
            "provider": "searxng",
            "provider_configured": True,
        })


@pytest.mark.asyncio
async def test_retrieval_matrix_covers_every_product_purpose() -> None:
    gateway = FakeGateway()

    result = await run_retrieval_matrix(
        gateway,
        query="请联网搜索一下什么是面向对象编程，找点例子",
    )

    assert set(result) == {"course", "assessment", "ai_teacher", "ppt_image"}
    assert {request.purpose for request in gateway.requests} == set(result)
    ppt_request = next(
        request for request in gateway.requests if request.purpose == "ppt_image"
    )
    assert ppt_request.category == "images"
    assert ppt_request.queries == ["human heart anatomy"]


@pytest.mark.asyncio
async def test_retrieval_matrix_fails_when_any_product_path_falls_back() -> None:
    gateway = FakeGateway(failing_purpose="assessment")

    with pytest.raises(RetrievalDiagnosticError, match="assessment"):
        await run_retrieval_matrix(
            gateway,
            query="请联网搜索一下什么是面向对象编程，找点例子",
        )
