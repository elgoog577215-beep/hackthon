from __future__ import annotations

from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from slide_image_provider import SlideImageProvider


def test_modelscope_provider_submits_polls_and_downloads_image(
    monkeypatch,
    tmp_path: Path,
) -> None:
    image_buffer = BytesIO()
    image = Image.new("RGB", (64, 64), "#2F6FE4")
    drawing = ImageDraw.Draw(image)
    for offset in range(0, 64, 8):
        drawing.line((0, offset, 63, 63 - offset), fill="#F29D38", width=3)
        drawing.ellipse((offset, 8, min(63, offset + 10), 22), fill="#E2F7F0")
    image.save(image_buffer, format="PNG")
    image_payload = image_buffer.getvalue()
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.method == "POST":
            assert request.headers["X-ModelScope-Async-Mode"] == "true"
            body = __import__("json").loads(request.content)
            assert "text" in body["negative_prompt"]
            return httpx.Response(200, json={"task_id": "task-1"})
        if request.url.path.endswith("/tasks/task-1"):
            assert request.headers["X-ModelScope-Task-Type"] == "image_generation"
            return httpx.Response(200, json={
                "task_status": "SUCCEED",
                "output_images": ["https://assets.example/result.png"],
            })
        return httpx.Response(200, content=image_payload)

    transport = httpx.MockTransport(handler)
    client_class = httpx.Client
    monkeypatch.setattr(
        "slide_image_provider.httpx.Client",
        lambda **_kwargs: client_class(transport=transport),
    )
    provider = SlideImageProvider(
        api_base="https://api-inference.modelscope.cn/v1",
        api_key="test-key",
        model="Qwen/Qwen-Image",
    )

    output = provider.generate(
        prompt="educational vector-space illustration",
        output_path=tmp_path / "result.png",
        size="1024x1024",
        seed=42,
    )

    assert output.exists()
    assert requests == [
        ("POST", "/v1/images/generations"),
        ("GET", "/v1/tasks/task-1"),
        ("GET", "/result.png"),
    ]


def test_modelscope_is_reused_only_with_an_explicit_image_model_or_known_host(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SLIDE_IMAGE_API_BASE", raising=False)
    monkeypatch.delenv("SLIDE_IMAGE_API_KEY", raising=False)
    monkeypatch.delenv("SLIDE_IMAGE_MODEL", raising=False)
    monkeypatch.setenv(
        "AI_API_BASE",
        "https://api-inference.modelscope.cn/v1/",
    )
    monkeypatch.setenv("AI_API_KEY", "test-key")

    provider = SlideImageProvider()

    assert provider.configured is True
    assert provider.model == "Qwen/Qwen-Image"
