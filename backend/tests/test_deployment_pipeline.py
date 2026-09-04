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
    assert 'LOCALE_ATTEMPTS="${LINGZHI_LOCALE_ATTEMPTS:-12}"' in script
    assert 'LOCALE_INTERVAL_SECONDS="${LINGZHI_LOCALE_INTERVAL_SECONDS:-3}"' in script


def test_server_activation_compares_effective_dependencies_for_current_python() -> None:
    script = (ROOT / "scripts" / "github-action-deploy.sh").read_text()

    assert "verify_backend_requirements_compatibility" in script
    assert "scripts/effective_requirements.py" in script
    assert "后端有实际生效的依赖变化" in script
    assert "pip install" not in script


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


def test_server_activation_sizes_free_space_from_release_backup_and_reserve() -> None:
    script = (ROOT / "scripts" / "github-action-deploy.sh").read_text()

    capacity = script[
        script.index("required_deploy_free_kb()") : script.index("ensure_free_space()")
    ]

    assert 'DEPLOY_SAFETY_RESERVE_MB="${LINGZHI_DEPLOY_SAFETY_RESERVE_MB:-176}"' in script
    assert 'MIN_FREE_MB="${LINGZHI_MIN_FREE_MB:-}"' in script
    assert 'gzip -l "$ARTIFACT_PATH"' in capacity
    assert 'find "$BACKUP_DIR"' in capacity
    assert 'du -sk "$STATE_DIR/backend-data"' in capacity
    assert "backup_required_kb * 5 / 4" in capacity
    assert "DEPLOY_SAFETY_RESERVE_MB * 1024" in capacity
    assert 'required_kb="$(required_deploy_free_kb)"' in script


def test_server_activation_keeps_explicit_free_space_override_as_a_floor() -> None:
    script = (ROOT / "scripts" / "github-action-deploy.sh").read_text()

    capacity = script[
        script.index("required_deploy_free_kb()") : script.index("ensure_free_space()")
    ]

    assert 'if [ -n "$MIN_FREE_MB" ]' in capacity
    assert "explicit_required_kb=$((MIN_FREE_MB * 1024))" in capacity
    assert 'if [ "$explicit_required_kb" -gt "$required_kb" ]' in capacity


def test_server_activation_cache_cleanup_is_scoped_to_regenerable_data() -> None:
    script = (ROOT / "scripts" / "github-action-deploy.sh").read_text()

    cleanup = script[
        script.index("cleanup_regenerable_caches()") : script.index("required_deploy_free_kb()")
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


def test_server_activation_exits_before_stop_for_unsafe_active_tasks() -> None:
    script = (ROOT / "scripts" / "github-action-deploy.sh").read_text()

    preflight = script.index("\npreflight_retrieval_runtime\n")
    safety_gate = script.index("\n    if assert_no_unsafe_active_tasks", preflight)
    stop_service = script.index('systemctl stop "$SERVICE_NAME"', safety_gate)

    assert safety_gate < stop_service
    assert 'exit "$task_safety_status"' in script[safety_gate:stop_service]
    assert "check_deploy_task_safety.py" in script
    assert "继续依赖持久检查点" not in script


def test_server_activation_creates_and_restore_verifies_versioned_backup() -> None:
    script = (ROOT / "scripts" / "github-action-deploy.sh").read_text()

    stop_service = script.index('systemctl stop "$SERVICE_NAME"')
    backup = script.index('create_verified_data_backup "$CURRENT_LINK/backend/data"')
    migrate = script.index('rsync -a "$CURRENT_LINK/backend/data/"')
    switch = script.index('switch_current "$release_path"')

    assert stop_service < backup < migrate < switch
    assert 'create_verified_data_backup "$STATE_DIR/backend-data"' in script
    assert "create_verified_data_backup.py" in script
    assert 'rm -f -- "${backups[index]}.sha256"' in script


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


def test_server_activation_verifies_both_locale_assets_before_completion() -> None:
    script = (ROOT / "scripts" / "github-action-deploy.sh").read_text()

    health_check = script.index("if ! wait_for_health")
    locale_check = script.index("if ! verify_locale_assets", health_check)
    deployment_complete = script.index('log "部署完成：$TARGET_COMMIT"')

    assert 'STATIC_BASE_URL="${LINGZHI_STATIC_BASE_URL:-${HEALTH_URL%/api/health}}"' in script
    assert 'for locale in zh en' in script
    assert 'for attempt in $(seq 1 "$LOCALE_ATTEMPTS")' in script
    assert 'curl --fail --silent --show-error --max-time 10 "$locale_url"' in script
    assert 'sleep "$LOCALE_INTERVAL_SECONDS"' in script
    assert 'payload.get("teacherHome", {}).get("myCalendar")' in script
    assert health_check < locale_check < deployment_complete


def test_server_activation_script_has_valid_bash_syntax() -> None:
    subprocess.run(
        ["bash", "-n", str(ROOT / "scripts" / "github-action-deploy.sh")],
        check=True,
    )


def test_workflow_builds_artifact_before_tuotu_activation() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy-lingzhi.yml").read_text()

    build_step = workflow.index("Build release artifact on runner")
    upload_step = workflow.index("Upload verified release artifact")
    configure_step = workflow.index("Configure deployment SSH")
    activate_step = workflow.index("Activate release on Tuotu server")

    assert build_step < upload_step < configure_step < activate_step
    assert "scripts/build-deploy-artifact.sh" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "secrets.LINGZHI_SSH_HOST" in workflow
    assert "secrets.LINGZHI_SSH_USER" in workflow
    assert "secrets.LINGZHI_SSH_KEY" in workflow
    assert "scripts/github-action-deploy.sh" in workflow
    assert "LINGZHI_DEPLOY_BUSY=true" in workflow
    assert "env.LINGZHI_DEPLOY_BUSY != 'true'" in workflow


def test_server_activation_bootstraps_an_isolated_systemd_runtime() -> None:
    script = (ROOT / "scripts" / "github-action-deploy.sh").read_text()
    unit = (ROOT / "deploy" / "systemd" / "lingzhi.service").read_text()

    bootstrap = script.index("bootstrap_runtime")
    preflight = script.index("preflight_release_runtime", bootstrap)

    assert bootstrap < preflight
    assert 'useradd --system --home-dir "$BASE_DIR"' in script
    assert 'PIP_NO_CACHE_DIR=1 "$VENV/bin/pip" install' in script
    assert 'chmod 755 "$release_path"' in script
    assert "User=lingzhi" in unit
    assert "WorkingDirectory=/opt/lingzhi/hackthon/backend" in unit
    assert "127.0.0.1 --port 7862" in unit


def test_release_artifact_excludes_non_runtime_visual_evidence() -> None:
    script = (ROOT / "scripts" / "build-deploy-artifact.sh").read_text()

    archive = script.index('git -C "$ROOT_DIR" archive "$TARGET_COMMIT"')
    prune_videos = script.index('rm -rf "$STAGING_DIR/demo_videos"')
    prune_design_evidence = script.index("-name 'design-qa-*.png' -delete")
    package = script.index('tar -C "$STAGING_DIR" -czf "$OUTPUT_PATH" .')

    assert archive < prune_videos < package
    assert archive < prune_design_evidence < package


def test_release_artifact_validates_production_i18n_contract() -> None:
    script_path = ROOT / "scripts" / "build-deploy-artifact.sh"
    script = script_path.read_text()

    tests = script.index("src/__tests__/shared/i18n.test.ts")
    build = script.index("VITE_BASE_PATH=/lingzhi/ npm run build")
    locale_validation = script.index("invalid ${locale} teacherHome locale")
    archive = script.index('git -C "$ROOT_DIR" archive "$TARGET_COMMIT"')

    assert tests < build < locale_validation < archive
    subprocess.run(["bash", "-n", str(script_path)], check=True)
