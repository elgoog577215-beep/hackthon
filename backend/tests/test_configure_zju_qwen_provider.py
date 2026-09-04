from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "configure_zju_qwen_provider.py"
DEPLOY_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "deploy-lingzhi.yml"
DIAGNOSTICS_WORKFLOW = (
    REPOSITORY_ROOT / ".github" / "workflows" / "production-diagnostics.yml"
)


def _payload(**overrides):
    payload = {
        "api_key": "private-placeholder",
        "base_url": "http://qwen.internal.test:30938/v1",
        "model": "qwen3.8-27b",
        "release_sha": "a" * 40,
        "slide_deck_v6_enabled": True,
        "slide_deck_v6_default_enabled": True,
        "teacher_script_animation_enabled": False,
    }
    payload.update(overrides)
    return payload


def _run(env_file: Path, payload: object):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--env-file", str(env_file)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )


def test_configure_zju_qwen_updates_every_text_role_and_removes_modelscope(
    tmp_path,
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AI_API_KEY=old-primary\n"
        "AI_PPT_API_KEY=old-ppt\n"
        "MODELSCOPE_API_KEY=old-fallback\n"
        "MODELSCOPE_BASE_URL=https://api-inference.modelscope.cn/v1\n"
        "MODELSCOPE_MODEL=Qwen/old\n"
        "UNRELATED=value\n",
        encoding="utf-8",
    )

    result = _run(env_file, _payload())

    assert result.returncode == 0, result.stderr
    content = env_file.read_text(encoding="utf-8")
    assert "UNRELATED=value" in content
    assert "MODELSCOPE_" not in content
    for key in (
        "AI_MODEL",
        "AI_MODEL_FAST",
        "AI_MODEL_CANDIDATES",
        "AI_MODEL_FAST_CANDIDATES",
        "AI_ASSESSMENT_GENERATOR_MODELS",
        "AI_ASSESSMENT_SOLVER_MODELS",
        "AI_ASSESSMENT_REVIEWER_MODELS",
        "AI_PPT_STORY_MODELS",
        "AI_PPT_VISUAL_MODELS",
    ):
        assert content.count(f"{key}=") == 1
        assert f"{key}=qwen3.8-27b" in content
    assert "AI_THINKING_ENABLED=false" in content
    assert "AI_LOCAL_PROVIDER=http" in content
    assert f"LINGZHI_RELEASE_SHA={'a' * 40}" in content
    assert "SLIDE_DECK_V6_ENABLED=true" in content
    assert "SLIDE_DECK_V6_DEFAULT_ENABLED=true" in content
    assert "TEACHER_SCRIPT_ANIMATION_ENABLED=false" in content
    assert "private-placeholder" not in result.stdout
    assert "private-placeholder" not in result.stderr
    assert "qwen.internal.test" not in result.stdout
    assert "qwen.internal.test" not in result.stderr


def test_configure_zju_qwen_rejects_wrong_model_atomically(tmp_path):
    env_file = tmp_path / ".env"
    original = "AI_API_KEY=old-primary\n"
    env_file.write_text(original, encoding="utf-8")

    result = _run(env_file, _payload(model="Qwen/Qwen3.5-27B"))

    assert result.returncode != 0
    assert env_file.read_text(encoding="utf-8") == original


def test_configure_zju_qwen_rejects_invalid_endpoint_atomically(tmp_path):
    env_file = tmp_path / ".env"
    original = "AI_API_KEY=old-primary\n"
    env_file.write_text(original, encoding="utf-8")

    result = _run(
        env_file,
        _payload(base_url="https://user:pass@example.test/v1"),
    )

    assert result.returncode != 0
    assert env_file.read_text(encoding="utf-8") == original


def test_configure_zju_qwen_rejects_invalid_release_sha_atomically(tmp_path):
    env_file = tmp_path / ".env"
    original = "LINGZHI_RELEASE_SHA=old\nAI_API_KEY=old-primary\n"
    env_file.write_text(original, encoding="utf-8")

    result = _run(env_file, _payload(release_sha="short"))

    assert result.returncode != 0
    assert env_file.read_text(encoding="utf-8") == original


def test_release_workflow_uses_only_private_zju_qwen_text_secrets():
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "scripts/build-deploy-artifact.sh" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "secrets.LINGZHI_SSH_KEY" in workflow
    assert "secrets.ZJU_QWEN_API_KEY" in workflow
    assert "secrets.ZJU_QWEN_BASE_URL" in workflow
    assert "scripts/configure_zju_qwen_provider.py" in workflow
    assert "qwen3.8-27b" in workflow
    assert "secrets.MODELSCOPE_API_KEY" not in workflow
    assert "secrets.DEEPSEEK_API_KEY" not in workflow
    assert "api-inference.modelscope.cn" not in workflow
    assert "api.deepseek.com" not in workflow
    assert "TEACHER_SCRIPT_ANIMATION_ENABLED: false" in workflow
    assert '"teacher_script_animation_enabled"' in workflow
    assert "LINGZHI_RELEASE_SHA: ${{ github.sha }}" in workflow
    assert '"release_sha": os.environ["LINGZHI_RELEASE_SHA"]' in workflow


def test_production_model_probe_runs_before_independent_retrieval_diagnostics():
    workflow = DIAGNOSTICS_WORKFLOW.read_text(encoding="utf-8")

    probe_position = workflow.index("Probe production ZJU Qwen routes")
    retrieval_position = workflow.index("Inspect retrieval path")
    assert probe_position < retrieval_position
    assert "scripts/probe_zju_qwen_runtime.py" in workflow
    assert "inputs.export_v6_replay || inputs.probe_ai_model" in workflow
    assert "base_url" not in workflow[probe_position:retrieval_position]
    assert "API_KEY" not in workflow[probe_position:retrieval_position]
