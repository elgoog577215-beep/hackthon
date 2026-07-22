from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_server_activation_script_never_builds_application() -> None:
    script = (ROOT / "scripts" / "github-action-deploy.sh").read_text()

    assert "npm ci" not in script
    assert "npm run build" not in script
    assert "pip install" not in script
    assert "git fetch" not in script
    assert 'HEALTH_ATTEMPTS="${LINGZHI_HEALTH_ATTEMPTS:-60}"' in script
    assert 'HEALTH_INTERVAL_SECONDS="${LINGZHI_HEALTH_INTERVAL_SECONDS:-2}"' in script


def test_workflow_builds_before_uploading_release() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy-lingzhi.yml").read_text()

    build_step = workflow.index("Build release artifact on runner")
    upload_step = workflow.index("Upload release artifact")
    activate_step = workflow.index("Activate release on server")

    assert build_step < upload_step < activate_step
    assert "scripts/build-deploy-artifact.sh" in workflow
