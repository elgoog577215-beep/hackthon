from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "configure_modelscope_fallback.py"
DEPLOY_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "deploy-lingzhi.yml"
DIAGNOSTICS_WORKFLOW = (
    REPOSITORY_ROOT / ".github" / "workflows" / "production-diagnostics.yml"
)


def test_configure_modelscope_fallback_updates_env_without_echoing_secret(
    tmp_path,
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AI_API_KEY=primary-key\n"
        "AI_PPT_API_KEY=old-ppt-key\n"
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
            "ppt_api_key": "ppt-deepseek-secret",
            "ppt_api_base": "https://api.deepseek.com",
            "ppt_story_models": (
                "deepseek-v4-pro,deepseek-v4-flash"
            ),
            "ppt_visual_models": (
                "deepseek-v4-flash,deepseek-v4-pro"
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
    assert content.count("AI_PPT_API_KEY=") == 1
    assert "AI_PPT_API_KEY=ppt-deepseek-secret" in content
    assert "AI_PPT_API_BASE=https://api.deepseek.com" in content
    assert content.count("MODELSCOPE_API_KEY=") == 1
    assert f"MODELSCOPE_API_KEY={secret}" in content
    assert (
        "MODELSCOPE_BASE_URL=https://api-inference.modelscope.cn/v1/"
        in content
    )
    assert "MODELSCOPE_MODEL=Qwen/Qwen3.5-35B-A3B" in content
    assert (
        "AI_PPT_STORY_MODELS=deepseek-v4-pro,deepseek-v4-flash"
    ) in content
    assert (
        "AI_PPT_VISUAL_MODELS=deepseek-v4-flash,deepseek-v4-pro"
    ) in content
    assert "SLIDE_DECK_V6_ENABLED=true" in content
    assert "SLIDE_DECK_V6_DEFAULT_ENABLED=true" in content
    assert "MODELSCOPE_MODEL_CANDIDATES=" not in content
    assert "MODELSCOPE_MODEL_FAST_CANDIDATES=" not in content
    assert secret not in result.stdout
    assert secret not in result.stderr
    assert "ppt-deepseek-secret" not in result.stdout
    assert "ppt-deepseek-secret" not in result.stderr


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


def test_configure_modelscope_fallback_rejects_untrusted_ppt_endpoint(
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
            "model": "Qwen/Qwen3.5-27B",
            "ppt_api_key": "ppt-secret-value",
            "ppt_api_base": "https://attacker.example/v1",
            "ppt_story_models": "deepseek-v4-pro",
            "ppt_visual_models": "deepseek-v4-flash",
            "slide_deck_v6_enabled": True,
            "slide_deck_v6_default_enabled": True,
        }),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert env_file.read_text(encoding="utf-8") == original


def test_release_workflow_provisions_server_provider_routes_from_secrets():
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "scripts/build-deploy-artifact.sh" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "secrets.LINGZHI_SSH_KEY" in workflow
    assert "secrets.MODELSCOPE_API_KEY" in workflow
    assert "secrets.DEEPSEEK_API_KEY" in workflow
    assert "scripts/configure_modelscope_fallback.py" in workflow


def test_production_diagnostics_can_probe_ppt_story_route_without_content_output():
    workflow = DIAGNOSTICS_WORKFLOW.read_text(encoding="utf-8")

    assert "probe_ai_model:" in workflow
    assert 'AIBase(provider_profile="ppt")' in workflow
    assert 'model_role="ppt_story"' in workflow
    assert 'model_role="ppt_visual"' in workflow
    assert '"model_id"' in workflow
    assert '"status"' in workflow
    assert '"error_code"' in workflow
    assert "full_content" not in workflow
