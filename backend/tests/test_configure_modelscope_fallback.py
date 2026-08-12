from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "configure_modelscope_fallback.py"
DEPLOY_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "deploy-lingzhi.yml"


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
            "model": "Qwen/Qwen3.5-35B-A3B",
            "ppt_story_models": (
                "deepseek-ai/DeepSeek-V4-Flash-0731,"
                "Qwen/Qwen3.5-122B-A10B"
            ),
            "ppt_visual_models": (
                "deepseek-ai/DeepSeek-V4-Flash-0731,"
                "Qwen/Qwen3.5-122B-A10B"
            ),
            "slide_deck_v6_enabled": True,
            "slide_deck_v6_default_enabled": True,
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
    assert "MODELSCOPE_MODEL=Qwen/Qwen3.5-35B-A3B" in content
    assert (
        "AI_PPT_STORY_MODELS=deepseek-ai/DeepSeek-V4-Flash-0731,"
        "Qwen/Qwen3.5-122B-A10B"
    ) in content
    assert (
        "AI_PPT_VISUAL_MODELS=deepseek-ai/DeepSeek-V4-Flash-0731,"
        "Qwen/Qwen3.5-122B-A10B"
    ) in content
    assert "SLIDE_DECK_V6_ENABLED=true" in content
    assert "SLIDE_DECK_V6_DEFAULT_ENABLED=true" in content
    assert "MODELSCOPE_MODEL_CANDIDATES=" not in content
    assert "MODELSCOPE_MODEL_FAST_CANDIDATES=" not in content
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


def test_configure_modelscope_fallback_rejects_invalid_model_atomically(
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
            "model": "bad model; rm -rf /",
        }),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert env_file.read_text(encoding="utf-8") == original


def test_deploy_workflow_provisions_verified_ppt_role_routes():
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "MODELSCOPE_MODEL: Qwen/Qwen3.5-35B-A3B" in workflow
    assert (
        "AI_PPT_STORY_MODELS: deepseek-ai/DeepSeek-V4-Flash-0731,"
        "Qwen/Qwen3.5-122B-A10B"
    ) in workflow
    assert (
        "AI_PPT_VISUAL_MODELS: deepseek-ai/DeepSeek-V4-Flash-0731,"
        "Qwen/Qwen3.5-122B-A10B"
    ) in workflow
    assert '"ppt_story_models": os.environ["AI_PPT_STORY_MODELS"]' in workflow
    assert '"ppt_visual_models": os.environ["AI_PPT_VISUAL_MODELS"]' in workflow
    assert "SLIDE_DECK_V6_ENABLED: true" in workflow
    assert "SLIDE_DECK_V6_DEFAULT_ENABLED: true" in workflow
    assert '"slide_deck_v6_enabled": os.environ["SLIDE_DECK_V6_ENABLED"]' in workflow
    assert (
        '"slide_deck_v6_default_enabled": '
        'os.environ["SLIDE_DECK_V6_DEFAULT_ENABLED"]'
    ) in workflow
    assert "MODELSCOPE_MODEL_CANDIDATES" not in workflow
    assert "MODELSCOPE_MODEL_FAST_CANDIDATES" not in workflow
