from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_searxng_compose_is_loopback_only_and_pins_the_image() -> None:
    compose = _read("deploy/searxng/compose.yml")

    assert (
        "ghcr.io/searxng/searxng@sha256:"
        "f4c8e59de166ed71f6380c0847c312ca51f0d41996e31d0559163b6b09ecde52"
    ) in compose
    assert '"127.0.0.1:8080:8080"' in compose
    assert "restart: unless-stopped" in compose
    assert "/opt/lingzhi/state/searxng/config:/etc/searxng:ro" in compose
    assert "valkey" not in compose.lower()


def test_searxng_settings_only_enable_approved_keyless_engines() -> None:
    settings = _read("deploy/searxng/settings.yml")
    expected = {
        "duckduckgo",
        "bing",
        "baidu",
        "wikipedia",
        "arxiv",
        "pubmed",
        "openalex",
        "crossref",
    }

    assert "formats:\n      - json" in settings
    assert "safe_search: 2" in settings
    assert "public_instance: false" in settings
    assert "limiter: false" in settings
    assert "image_proxy: false" in settings
    for engine in expected:
        assert f"- {engine}" in settings
    assert "google" not in settings.lower()


def test_provisioning_is_manual_idempotent_and_checks_json_search() -> None:
    workflow = _read(".github/workflows/provision-searxng.yml")
    script = _read("scripts/provision-searxng.sh")

    assert "workflow_dispatch:" in workflow
    assert "push:" not in workflow
    assert "LINGZHI_SSH_HOST" in workflow
    assert "docker compose" in script
    assert "install -m 600" in script
    assert "http://127.0.0.1:8080/config" in script
    assert "http://127.0.0.1:8080/search" in script
    assert "format=json" in script


def test_normal_deploy_preflights_searxng_before_stopping_application() -> None:
    script = _read("scripts/github-action-deploy.sh")

    preflight_definition = script.index("preflight_retrieval_runtime()")
    preflight_call = script.index("\npreflight_retrieval_runtime\n")
    stop_service = script.index('systemctl stop "$SERVICE_NAME"', preflight_call)

    assert preflight_definition < preflight_call < stop_service
    assert "WEB_RETRIEVAL_PROVIDER" in script
    assert "SEARXNG_BASE_URL" in script
    assert "format=json" in script
