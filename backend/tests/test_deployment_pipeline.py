import subprocess
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


def test_server_activation_bounds_backup_and_failed_artifact_retention() -> None:
    script = (ROOT / "scripts" / "github-action-deploy.sh").read_text()

    activation = script.index("\nvalidate_settings\n")
    cleanup_incoming = script.index("\ncleanup_incoming\n", activation)
    ensure_free_space = script.index("\nensure_free_space\n", activation)
    rollback = script.index("rollback()")

    assert 'KEEP_BACKUPS="${LINGZHI_KEEP_BACKUPS:-2}"' in script
    assert cleanup_incoming < ensure_free_space
    assert "'lingzhi-release-*.tgz'" in script
    assert 'rm -f -- "$ARTIFACT_PATH" || true' in script[rollback:]


def test_server_activation_prunes_only_the_older_rollback_when_space_is_still_low() -> None:
    script = (ROOT / "scripts" / "github-action-deploy.sh").read_text()

    ensure_free_space = script[script.index("ensure_free_space()") : script.index("switch_current()")]

    assert "cleanup_backups 1" in ensure_free_space
    assert "cleanup_releases 1" in ensure_free_space
    assert "cleanup_regenerable_caches" in ensure_free_space
    assert ensure_free_space.index("cleanup_backups 1") < ensure_free_space.index("cleanup_releases 1")
    assert ensure_free_space.index("cleanup_releases 1") < ensure_free_space.index(
        "cleanup_regenerable_caches"
    )


def test_server_activation_cache_cleanup_is_scoped_to_regenerable_data() -> None:
    script = (ROOT / "scripts" / "github-action-deploy.sh").read_text()

    cleanup = script[
        script.index("cleanup_regenerable_caches()") : script.index("ensure_free_space()")
    ]

    assert '"${XDG_CACHE_HOME:-$HOME/.cache}/pip"' in cleanup
    assert '"${XDG_CACHE_HOME:-$HOME/.cache}/uv"' in cleanup
    assert '"$HOME/.npm/_cacache"' in cleanup
    assert '"$HOME/.cache/node-gyp"' in cleanup
    assert 'active_path="$(current_release)"' in cleanup
    assert "__pycache__" in cleanup
    assert ".pytest_cache" in cleanup
    assert "STATE_DIR" not in cleanup
    assert "BACKUP_DIR" not in cleanup


def test_server_activation_uses_checkpoint_recovery_for_active_tasks() -> None:
    script = (ROOT / "scripts" / "github-action-deploy.sh").read_text()

    recovery_plan = script.index("log_generation_task_recovery_plan")
    stop_service = script.index('systemctl stop "$SERVICE_NAME"')
    deployment_complete = script.index('log "部署完成：$TARGET_COMMIT"')
    remove_artifact = script.index('rm -f "$ARTIFACT_PATH"')

    assert recovery_plan < stop_service
    assert "exit 75" not in script
    assert "将优雅停止服务，并由新版本从检查点恢复" in script
    assert deployment_complete < remove_artifact


def test_server_activation_preflights_and_recovers_systemd_runtime() -> None:
    script = (ROOT / "scripts" / "github-action-deploy.sh").read_text()

    activation = script.index("\nvalidate_settings\n")
    preflight = script.index("\npreflight_release_runtime\n", activation)
    stop_service = script.index('systemctl stop "$SERVICE_NAME"', preflight)
    rollback = script.index("rollback()")
    health_failure = script.index("if ! wait_for_health")
    diagnostics = script.index("log_service_diagnostics", health_failure)
    fail_activation = script.index("\n    false", health_failure)

    assert '"$VENV/bin/python" -c \'import main\'' in script
    assert preflight < stop_service
    assert diagnostics < fail_activation
    assert 'systemctl reset-failed "$SERVICE_NAME" || true' in script[rollback:]


def test_server_activation_script_has_valid_bash_syntax() -> None:
    subprocess.run(
        ["bash", "-n", str(ROOT / "scripts" / "github-action-deploy.sh")],
        check=True,
    )


def test_workflow_builds_before_uploading_release() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy-lingzhi.yml").read_text()

    build_step = workflow.index("Build release artifact on runner")
    upload_step = workflow.index("Upload release artifact")
    activate_step = workflow.index("Activate release on server")

    assert build_step < upload_step < activate_step
    assert "scripts/build-deploy-artifact.sh" in workflow


def test_production_frontend_builds_for_lingzhi_subpath() -> None:
    for relative_path in (
        "scripts/build-deploy-artifact.sh",
        "scripts/deploy-production.sh",
    ):
        script = (ROOT / relative_path).read_text(encoding="utf-8")

        assert "VITE_BASE_PATH=/lingzhi/ npm run build" in script
