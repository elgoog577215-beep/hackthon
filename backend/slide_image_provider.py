"""Optional OpenAI Images-compatible provider for original slide illustrations."""

from __future__ import annotations

import base64
import os
from pathlib import Path

import httpx
from PIL import Image


class SlideImageProvider:
    def __init__(
        self,
        *,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 45.0,
    ) -> None:
        self.api_base = str(api_base or os.getenv("SLIDE_IMAGE_API_BASE") or "").rstrip("/")
        self.api_key = str(api_key or os.getenv("SLIDE_IMAGE_API_KEY") or "")
        self.model = str(model or os.getenv("SLIDE_IMAGE_MODEL") or "")
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_base and self.api_key and self.model)

    def generate(
        self,
        *,
        prompt: str,
        output_path: str | Path,
        size: str = "1536x1024",
    ) -> Path:
        if not self.configured:
            raise RuntimeError("Slide image provider is not configured")
        safe_prompt = (
            f"{prompt.strip()}. Original educational editorial illustration. "
            "No words, letters, numbers, captions, logos, watermarks, UI, or trademarks. "
            "Do not imitate any living artist."
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = client.post(
                f"{self.api_base}/images/generations",
                headers=headers,
                json={
                    "model": self.model,
                    "prompt": safe_prompt,
                    "size": size,
                    "response_format": "b64_json",
                    "n": 1,
                },
            )
            response.raise_for_status()
            data = response.json()
            item = (data.get("data") or [{}])[0]
            if item.get("b64_json"):
                payload = base64.b64decode(item["b64_json"], validate=True)
            elif item.get("url"):
                image_response = client.get(str(item["url"]))
                image_response.raise_for_status()
                payload = image_response.content
            else:
                raise ValueError("Image provider returned no image payload")
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        try:
            with Image.open(target) as image:
                image.verify()
        except Exception as exc:
            target.unlink(missing_ok=True)
            raise ValueError("Image provider returned a bad image") from exc
        return target


__all__ = ["SlideImageProvider"]
