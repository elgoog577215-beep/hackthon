from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "configure_modelscope_fallback.py"


def test_configure_modelscope_fallback_updates_env_without_echoing_secret(
    tmp_path,
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AI_API_KEY=primary-key\n"
        "MODELSCOPE_API_KEY=old-key\n"
        "UNRELATED=value\n",
        encoding="utf-8",
    )
    secret = "fallback-secret-value"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--env-file",
            str(env_file),
        ],
        input=json.dumps({
            "api_key": secret,
            "base_url": "https://api-inference.modelscope.cn/v1/",
            "model": "deepseek-ai/DeepSeek-V4-Pro",
            "smart_models": [
                "deepseek-ai/DeepSeek-V4-Pro",
                "Qwen/Qwen3.5-35B-A3B",
                "ZhipuAI/GLM-4.7-Flash",
            ],
            "fast_models": [
                "deepseek-ai/DeepSeek-V4-Flash-0731",
                "Qwen/Qwen3.5-35B-A3B",
                "Qwen/Qwen3-8B",
                "ZhipuAI/GLM-4.7-Flash",
            ],
        }),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    content = env_file.read_text(encoding="utf-8")
    assert "AI_API_KEY=primary-key" in content
    assert "UNRELATED=value" in content
    assert content.count("MODELSCOPE_API_KEY=") == 1
    assert f"MODELSCOPE_API_KEY={secret}" in content
    assert (
        "MODELSCOPE_BASE_URL=https://api-inference.modelscope.cn/v1/"
        in content
    )
    assert "MODELSCOPE_MODEL=deepseek-ai/DeepSeek-V4-Pro" in content
    assert (
        "MODELSCOPE_MODEL_CANDIDATES="
        "deepseek-ai/DeepSeek-V4-Pro,Qwen/Qwen3.5-35B-A3B,"
        "ZhipuAI/GLM-4.7-Flash"
    ) in content
    assert (
        "MODELSCOPE_MODEL_FAST_CANDIDATES="
        "deepseek-ai/DeepSeek-V4-Flash-0731,Qwen/Qwen3.5-35B-A3B,"
        "Qwen/Qwen3-8B,ZhipuAI/GLM-4.7-Flash"
    ) in content
    assert secret not in result.stdout
    assert secret not in result.stderr


def test_configure_modelscope_fallback_rejects_untrusted_endpoint(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("AI_API_KEY=primary-key\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--env-file",
            str(env_file),
        ],
        input=json.dumps({
            "api_key": "fallback-secret-value",
            "base_url": "https://attacker.example/v1/",
            "model": "deepseek-ai/DeepSeek-V4-Pro",
        }),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert env_file.read_text(encoding="utf-8") == "AI_API_KEY=primary-key\n"


def test_configure_modelscope_fallback_rejects_invalid_candidate_atomically(
    tmp_path,
):
    env_file = tmp_path / ".env"
    original = "AI_API_KEY=primary-key\n"
    env_file.write_text(original, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--env-file",
            str(env_file),
        ],
        input=json.dumps({
            "api_key": "fallback-secret-value",
            "base_url": "https://api-inference.modelscope.cn/v1/",
            "model": "deepseek-ai/DeepSeek-V4-Pro",
            "smart_models": ["deepseek-ai/DeepSeek-V4-Pro"],
            "fast_models": ["bad model; rm -rf /"],
        }),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert env_file.read_text(encoding="utf-8") == original
