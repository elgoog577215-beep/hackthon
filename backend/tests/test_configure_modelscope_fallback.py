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


def _production_payload(**overrides):
    payload = {
        "primary_api_key": "deepseek-secret-value",
        "primary_base_url": "https://api.deepseek.com",
        "smart_models": "deepseek-v4-pro,deepseek-v4-flash",
        "fast_models": "deepseek-v4-flash,deepseek-v4-pro",
        "assessment_generator_models": "deepseek-v4-pro,deepseek-v4-flash",
        "assessment_solver_models": "deepseek-v4-flash,deepseek-v4-pro",
        "assessment_reviewer_models": "deepseek-v4-pro,deepseek-v4-flash",
        "ppt_story_models": "deepseek-v4-pro,deepseek-v4-flash",
        "ppt_visual_models": "deepseek-v4-flash,deepseek-v4-pro",
        "fallback_api_key": "fallback-secret-value",
        "fallback_base_url": "https://api-inference.modelscope.cn/v1/",
        "fallback_model": "Qwen/Qwen3.5-27B",
        "slide_deck_v6_enabled": True,
        "slide_deck_v6_default_enabled": True,
    }
    payload.update(overrides)
    return payload


def test_configure_production_ai_updates_primary_and_fallback_without_echoing_secrets(
    tmp_path,
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AI_API_KEY=old-primary-key\n"
        "AI_API_BASE=https://api-inference.modelscope.cn/v1\n"
        "AI_MODEL=old-model\n"
        "AI_MODEL_FAST=old-fast-model\n"
        "AI_MODEL_CANDIDATES=old-model,old-backup\n"
        "AI_MODEL_FAST_CANDIDATES=old-fast-model,old-backup\n"
        "AI_ASSESSMENT_GENERATOR_MODELS=old-generator\n"
        "AI_ASSESSMENT_SOLVER_MODELS=old-solver\n"
        "AI_ASSESSMENT_REVIEWER_MODELS=old-reviewer\n"
        "AI_PPT_STORY_MODELS=old-story\n"
        "AI_PPT_VISUAL_MODELS=old-visual\n"
        "MODELSCOPE_API_KEY=old-key\n"
        "UNRELATED=value\n",
        encoding="utf-8",
    )
    primary_secret = "deepseek-secret-value"
    fallback_secret = "fallback-secret-value"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--env-file",
            str(env_file),
        ],
        input=json.dumps(_production_payload()),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    content = env_file.read_text(encoding="utf-8")
    assert "UNRELATED=value" in content
    assert content.count("AI_API_KEY=") == 1
    assert f"AI_API_KEY={primary_secret}" in content
    assert "AI_API_BASE=https://api.deepseek.com" in content
    assert "AI_MODEL=deepseek-v4-pro" in content
    assert "AI_MODEL_FAST=deepseek-v4-flash" in content
    assert (
        "AI_MODEL_CANDIDATES=deepseek-v4-pro,deepseek-v4-flash"
        in content
    )
    assert (
        "AI_MODEL_FAST_CANDIDATES=deepseek-v4-flash,deepseek-v4-pro"
        in content
    )
    assert (
        "AI_ASSESSMENT_GENERATOR_MODELS=deepseek-v4-pro,deepseek-v4-flash"
        in content
    )
    assert (
        "AI_ASSESSMENT_SOLVER_MODELS=deepseek-v4-flash,deepseek-v4-pro"
        in content
    )
    assert (
        "AI_ASSESSMENT_REVIEWER_MODELS=deepseek-v4-pro,deepseek-v4-flash"
        in content
    )
    assert "AI_PPT_STORY_MODELS=deepseek-v4-pro,deepseek-v4-flash" in content
    assert "AI_PPT_VISUAL_MODELS=deepseek-v4-flash,deepseek-v4-pro" in content
    assert content.count("MODELSCOPE_API_KEY=") == 1
    assert f"MODELSCOPE_API_KEY={fallback_secret}" in content
    assert (
        "MODELSCOPE_BASE_URL=https://api-inference.modelscope.cn/v1/"
        in content
    )
    assert "MODELSCOPE_MODEL=Qwen/Qwen3.5-27B" in content
    assert "SLIDE_DECK_V6_ENABLED=true" in content
    assert "SLIDE_DECK_V6_DEFAULT_ENABLED=true" in content
    assert "MODELSCOPE_MODEL_CANDIDATES=" not in content
    assert "MODELSCOPE_MODEL_FAST_CANDIDATES=" not in content
    assert primary_secret not in result.stdout
    assert primary_secret not in result.stderr
    assert fallback_secret not in result.stdout
    assert fallback_secret not in result.stderr


def test_configure_production_ai_rejects_untrusted_primary_endpoint_atomically(
    tmp_path,
):
    env_file = tmp_path / ".env"
    original = "AI_API_KEY=old-primary-key\n"
    env_file.write_text(original, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--env-file", str(env_file)],
        input=json.dumps(
            _production_payload(primary_base_url="https://attacker.example/v1")
        ),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert env_file.read_text(encoding="utf-8") == original


def test_configure_production_ai_rejects_unsupported_deepseek_model_atomically(
    tmp_path,
):
    env_file = tmp_path / ".env"
    original = "AI_API_KEY=old-primary-key\n"
    env_file.write_text(original, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--env-file", str(env_file)],
        input=json.dumps(_production_payload(smart_models="deepseek-chat")),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert env_file.read_text(encoding="utf-8") == original


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
        input=json.dumps(
            _production_payload(
                fallback_base_url="https://attacker.example/v1/",
            )
        ),
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
        input=json.dumps(
            _production_payload(fallback_model="bad model; rm -rf /")
        ),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert env_file.read_text(encoding="utf-8") == original


def test_deploy_workflow_provisions_deepseek_as_primary_and_modelscope_as_fallback():
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}" in workflow
    assert "DEEPSEEK_BASE_URL: https://api.deepseek.com" in workflow
    assert "DEEPSEEK_SMART_MODELS: deepseek-v4-pro,deepseek-v4-flash" in workflow
    assert "DEEPSEEK_FAST_MODELS: deepseek-v4-flash,deepseek-v4-pro" in workflow
    assert "MODELSCOPE_MODEL: Qwen/Qwen3.5-27B" in workflow
    assert (
        "AI_PPT_STORY_MODELS: deepseek-v4-pro,deepseek-v4-flash"
        in workflow
    )
    assert (
        "AI_PPT_VISUAL_MODELS: deepseek-v4-flash,deepseek-v4-pro"
        in workflow
    )
    assert '"primary_api_key": os.environ["DEEPSEEK_API_KEY"]' in workflow
    assert '"primary_base_url": os.environ["DEEPSEEK_BASE_URL"]' in workflow
    assert '"smart_models": os.environ["DEEPSEEK_SMART_MODELS"]' in workflow
    assert '"fast_models": os.environ["DEEPSEEK_FAST_MODELS"]' in workflow
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


def test_production_diagnostics_can_probe_ppt_story_route_without_content_output():
    workflow = DIAGNOSTICS_WORKFLOW.read_text(encoding="utf-8")

    assert "probe_ai_model:" in workflow
    assert 'model_role="ppt_story"' in workflow
    assert 'model_role="ppt_visual"' in workflow
    assert '"model_id"' in workflow
    assert '"status"' in workflow
    assert '"error_code"' in workflow
    assert "full_content" not in workflow
