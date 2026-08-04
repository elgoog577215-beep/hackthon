import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "configure_lingzhi_public_route.py"

LEGACY_CADDYFILE = """tuotuzju.com, www.tuotuzju.com {
\troute {
\t\t@lingzhi_exact path /lingzhi /lingzhi/
\t\thandle @lingzhi_exact {
\t\t\tredir https://lingzhi.tuotuzju.com/ 302
\t\t}

\t\t@lingzhi_path path_regexp lingzhi_path ^/lingzhi/(.*)$
\t\thandle @lingzhi_path {
\t\t\tredir https://lingzhi.tuotuzju.com/{re.lingzhi_path.1} 302
\t\t}

\t\thandle {
\t\t\trespond "main"
\t\t}
\t}
}

lingzhi.tuotuzju.com {
\troute {
\t\trequest_body {
\t\t\tmax_size 1024MB
\t\t}

\t\thandle {
\t\t\theader X-Proxy-Source "Lingzhi-7862"
\t\t\treverse_proxy 127.0.0.1:7862
\t\t}
\t}
}
"""


def load_route_module():
    assert SCRIPT.exists(), "public-route configurator is missing"
    spec = importlib.util.spec_from_file_location("configure_lingzhi_public_route", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rewrite_keeps_lingzhi_on_the_main_domain() -> None:
    module = load_route_module()

    rewritten = module.rewrite_caddyfile(LEGACY_CADDYFILE)

    assert "@lingzhi_exact path /lingzhi" in rewritten
    assert "redir /lingzhi/ 308" in rewritten
    assert "@lingzhi_path path /lingzhi/*" in rewritten
    assert "uri strip_prefix /lingzhi" in rewritten
    assert "reverse_proxy 127.0.0.1:7862" in rewritten
    assert "redir https://tuotuzju.com/lingzhi{uri} 308" in rewritten
    assert "redir https://lingzhi.tuotuzju.com/" not in rewritten


def test_rewrite_is_idempotent() -> None:
    module = load_route_module()

    rewritten = module.rewrite_caddyfile(LEGACY_CADDYFILE)

    assert module.rewrite_caddyfile(rewritten) == rewritten


def test_rewrite_rejects_an_unknown_route_shape() -> None:
    module = load_route_module()

    with pytest.raises(ValueError, match="Lingzhi"):
        module.rewrite_caddyfile("tuotuzju.com { respond \"main\" }\n")


def test_verify_public_routes_checks_health_and_canonical_redirect(monkeypatch) -> None:
    module = load_route_module()
    commands = []

    def fake_run(command, *, capture_output=False):
        commands.append((command, capture_output))
        if capture_output:
            return SimpleNamespace(
                stdout="HTTP/2 308\r\nlocation: https://tuotuzju.com/lingzhi/\r\n"
            )
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(module, "_run", fake_run)

    module._verify_public_routes()

    assert commands[0][0][-1] == "https://tuotuzju.com/lingzhi/api/health"
    assert commands[1][0][-1] == "https://lingzhi.tuotuzju.com/"
    assert commands[1][1] is True


def test_verify_public_routes_rejects_wrong_subdomain_target(monkeypatch) -> None:
    module = load_route_module()

    monkeypatch.setattr(
        module,
        "_run",
        lambda command, *, capture_output=False: SimpleNamespace(
            stdout="HTTP/2 200\r\n" if capture_output else ""
        ),
    )

    with pytest.raises(RuntimeError, match="canonical"):
        module._verify_public_routes()


def test_configure_public_route_validates_backs_up_and_reloads(tmp_path, monkeypatch) -> None:
    module = load_route_module()
    config_path = tmp_path / "Caddyfile"
    config_path.write_text(LEGACY_CADDYFILE, encoding="utf-8")
    commands = []

    monkeypatch.setattr(module.os, "chown", lambda *args: None, raising=False)
    monkeypatch.setattr(module, "_verify_public_routes", lambda: None)
    monkeypatch.setattr(
        module,
        "_run",
        lambda command, *, capture_output=False: commands.append(command)
        or SimpleNamespace(stdout=""),
    )

    backup_path = module.configure_public_route(config_path, "/usr/bin/caddy")

    assert backup_path is not None
    assert backup_path.read_text(encoding="utf-8") == LEGACY_CADDYFILE
    assert module.MAIN_DOMAIN_ROUTE in config_path.read_text(encoding="utf-8")
    assert commands[0][1] == "validate"
    assert commands[1][1] == "reload"


def test_configure_public_route_is_a_verified_noop_when_already_current(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_route_module()
    config_path = tmp_path / "Caddyfile"
    current = module.rewrite_caddyfile(LEGACY_CADDYFILE)
    config_path.write_text(current, encoding="utf-8")
    verifications = []

    monkeypatch.setattr(module, "_verify_public_routes", lambda: verifications.append(True))

    assert module.configure_public_route(config_path, "/usr/bin/caddy") is None
    assert verifications == [True]
    assert config_path.read_text(encoding="utf-8") == current


def test_configure_public_route_restores_backup_when_reload_fails(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_route_module()
    config_path = tmp_path / "Caddyfile"
    config_path.write_text(LEGACY_CADDYFILE, encoding="utf-8")
    reload_attempts = 0

    def fake_run(command, *, capture_output=False):
        nonlocal reload_attempts
        if command[1] == "reload":
            reload_attempts += 1
            if reload_attempts == 1:
                raise subprocess.CalledProcessError(1, command)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(module.os, "chown", lambda *args: None, raising=False)
    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(module, "_verify_public_routes", lambda: None)

    with pytest.raises(subprocess.CalledProcessError):
        module.configure_public_route(config_path, "/usr/bin/caddy")

    assert reload_attempts == 2
    assert config_path.read_text(encoding="utf-8") == LEGACY_CADDYFILE
