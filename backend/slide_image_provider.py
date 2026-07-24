"""Optional OpenAI Images-compatible provider for original slide illustrations."""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageFilter

IMAGE_PROMPT_POLICY_VERSION = "slide_scene_prompt_v5_llm_visual_director"


class SlideImageProvider:
    def __init__(
        self,
        *,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        configured_base = str(
            api_base
            or os.getenv("SLIDE_IMAGE_API_BASE")
            or os.getenv("AI_API_BASE")
            or ""
        ).rstrip("/")
        self.api_base = configured_base
        self.api_key = str(
            api_key
            or os.getenv("SLIDE_IMAGE_API_KEY")
            or os.getenv("AI_API_KEY")
            or ""
        )
        default_model = (
            "Qwen/Qwen-Image"
            if "api-inference.modelscope.cn" in configured_base
            else ""
        )
        self.model = str(
            model
            or os.getenv("SLIDE_IMAGE_MODEL")
            or default_model
        )
        self.prompt_api_base = str(
            os.getenv("AI_API_BASE") or self.api_base
        ).rstrip("/")
        self.prompt_api_key = str(os.getenv("AI_API_KEY") or self.api_key)
        self.prompt_model = str(
            os.getenv("SLIDE_IMAGE_PROMPT_MODEL")
            or os.getenv("AI_MODEL_FAST")
            or os.getenv("AI_MODEL")
            or ""
        )
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_base and self.api_key and self.model)

    def plan_prompt(self, *, source_text: str, style: str) -> str:
        """Use the website LLM to turn source prose into a concrete visual scene."""
        fallback = (
            f"{style}. A concrete visual metaphor for this source concept: "
            f"{source_text[:500]}"
        )
        if not (
            self.prompt_api_base
            and self.prompt_api_key
            and self.prompt_model
        ):
            return fallback
        try:
            response = httpx.post(
                f"{self.prompt_api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.prompt_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.prompt_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Convert source-bound course prose into one concrete "
                                "English image-generation scene. Output only 40-80 "
                                "English words. Depict the mechanism with physical or "
                                "geometric objects and spatial relationships. Never "
                                "request text, labels, formulas, signs, posters, slides, "
                                "screens, classrooms, or empty rooms. Do not invent facts."
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"Style: {style}\nSource: {source_text[:1200]}",
                        },
                    ],
                    "temperature": 0,
                    "max_tokens": 180,
                    "enable_thinking": False,
                },
                timeout=45.0,
            )
            response.raise_for_status()
            content = str(
                (((response.json().get("choices") or [{}])[0].get("message") or {})
                 .get("content") or "")
            ).strip()
            content = content.strip("` \n\t\"'")
            if len(content) >= 30:
                return content[:900]
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            pass
        return fallback

    def generate(
        self,
        *,
        prompt: str,
        output_path: str | Path,
        size: str = "1664x928",
        seed: int | None = None,
    ) -> Path:
        if not self.configured:
            raise RuntimeError("Slide image provider is not configured")
        display_prompt = re.sub(r"^\[[^\]]+\]\s*", "", prompt.strip())
        safe_prompt = (
            "A single subject-focused conceptual editorial scene with a clear visual "
            f"mechanism and generous composition. {display_prompt}. "
            "Use objects, spatial relationships, color, light, and texture. "
            "Original work, cinematic 16:9 composition."
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
            for attempt in range(2):
                attempt_prompt = safe_prompt
                if attempt:
                    attempt_prompt += (
                        " Pure abstract scene with blank surfaces and simple physical "
                        "objects."
                    )
                if "api-inference.modelscope.cn" in self.api_base:
                    payload = self._generate_modelscope(
                        client,
                        attempt_prompt,
                        headers,
                        size=size,
                        seed=(None if seed is None else seed + (attempt * 104729)),
                    )
                else:
                    payload = self._generate_openai(
                        client,
                        attempt_prompt,
                        headers,
                        size=size,
                    )
                target.write_bytes(payload)
                try:
                    with Image.open(target) as image:
                        image.verify()
                except Exception as exc:
                    target.unlink(missing_ok=True)
                    if attempt:
                        raise ValueError(
                            "Image provider returned a bad image"
                        ) from exc
                    continue
                if (
                    not _contains_embedded_text(target)
                    and not _is_low_information(target)
                ):
                    return target
                target.unlink(missing_ok=True)
        raise ValueError(
            "Image provider returned embedded text or a low-information scene"
        )

    def _generate_openai(
        self,
        client: httpx.Client,
        prompt: str,
        headers: dict[str, str],
        *,
        size: str,
    ) -> bytes:
        response = client.post(
            f"{self.api_base}/images/generations",
            headers=headers,
            json={
                "model": self.model,
                "prompt": prompt,
                "size": size,
                "response_format": "b64_json",
                "n": 1,
            },
        )
        response.raise_for_status()
        data = response.json()
        item = (data.get("data") or [{}])[0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"], validate=True)
        if item.get("url"):
            image_response = client.get(str(item["url"]))
            image_response.raise_for_status()
            return image_response.content
        raise ValueError("Image provider returned no image payload")

    def _generate_modelscope(
        self,
        client: httpx.Client,
        prompt: str,
        headers: dict[str, str],
        *,
        size: str,
        seed: int | None,
    ) -> bytes:
        request_headers = {
            **headers,
            "X-ModelScope-Async-Mode": "true",
        }
        request_body: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
            "negative_prompt": (
                "text, typography, words, letters, numbers, formula, caption, label, "
                "logo, watermark, signature, poster, presentation slide, article, "
                "document, blackboard writing, signage, UI, infographic, low quality"
            ),
        }
        if seed is not None:
            request_body["seed"] = int(seed) % (2**31)
        response = client.post(
            f"{self.api_base}/images/generations",
            headers=request_headers,
            json=request_body,
        )
        response.raise_for_status()
        task_id = str(response.json().get("task_id") or "")
        if not task_id:
            raise ValueError("ModelScope image provider returned no task id")
        deadline = time.monotonic() + self.timeout_seconds
        poll_headers = {
            **headers,
            "X-ModelScope-Task-Type": "image_generation",
        }
        while time.monotonic() < deadline:
            result = client.get(
                f"{self.api_base}/tasks/{task_id}",
                headers=poll_headers,
            )
            result.raise_for_status()
            data = result.json()
            status = str(data.get("task_status") or "").upper()
            if status == "SUCCEED":
                urls = data.get("output_images") or []
                if not urls:
                    raise ValueError(
                        "ModelScope image provider returned no output image"
                    )
                image_response = client.get(str(urls[0]))
                image_response.raise_for_status()
                return image_response.content
            if status == "FAILED":
                raise RuntimeError(
                    str(data.get("message") or "ModelScope image generation failed")
                )
            time.sleep(1.0)
        raise TimeoutError("ModelScope image generation timed out")


def _contains_embedded_text(path: Path) -> bool:
    """Reject poster-like generations; use the runtime OCR already shipped by the site."""
    try:
        from rapidocr_onnxruntime import RapidOCR

        result, _ = RapidOCR()(str(path))
        for item in result or []:
            if len(item) < 3:
                continue
            text = str(item[1] or "")
            confidence = float(item[2] or 0)
            glyphs = re.sub(r"[\W_]+", "", text, flags=re.UNICODE)
            if confidence >= 0.55 and len(glyphs) >= 2:
                return True
        return False
    except (ImportError, OSError, RuntimeError, ValueError):
        pass

    executable = shutil.which("tesseract")
    if not executable and os.name == "nt":
        candidate = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        if candidate.exists():
            executable = str(candidate)
    if not executable:
        return False
    try:
        completed = subprocess.run(
            [executable, str(path), "stdout", "-l", "eng", "--psm", "11"],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    glyphs = re.sub(r"[^A-Za-z0-9]+", "", completed.stdout or "")
    return len(glyphs) >= 4


def _is_low_information(path: Path) -> bool:
    """Reject empty rooms, plain gradients, and other non-explanatory filler."""
    try:
        with Image.open(path) as image:
            grayscale = image.convert("L").resize((256, 144))
            edges = grayscale.filter(ImageFilter.FIND_EDGES)
            histogram = edges.histogram()
    except (OSError, ValueError):
        return True
    edge_pixels = sum(
        count for intensity, count in enumerate(histogram)
        if intensity >= 28
    )
    edge_density = edge_pixels / float(256 * 144)
    return edge_density < 0.055


__all__ = ["IMAGE_PROMPT_POLICY_VERSION", "SlideImageProvider"]
