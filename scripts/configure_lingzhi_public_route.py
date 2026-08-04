#!/usr/bin/env python3

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


LEGACY_MAIN_ROUTE = """\t\t@lingzhi_exact path /lingzhi /lingzhi/
\t\thandle @lingzhi_exact {
\t\t\tredir https://lingzhi.tuotuzju.com/ 302
\t\t}

\t\t@lingzhi_path path_regexp lingzhi_path ^/lingzhi/(.*)$
\t\thandle @lingzhi_path {
\t\t\tredir https://lingzhi.tuotuzju.com/{re.lingzhi_path.1} 302
\t\t}
"""

MAIN_DOMAIN_ROUTE = """\t\t@lingzhi_exact path /lingzhi
\t\thandle @lingzhi_exact {
\t\t\tredir /lingzhi/ 308
\t\t}

\t\t@lingzhi_path path /lingzhi/*
\t\thandle @lingzhi_path {
\t\t\turi strip_prefix /lingzhi
\t\t\theader X-Proxy-Source "Lingzhi-7862"
\t\t\treverse_proxy 127.0.0.1:7862
\t\t}
"""

LEGACY_SUBDOMAIN_ROUTE = """lingzhi.tuotuzju.com {
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

SUBDOMAIN_REDIRECT_ROUTE = """lingzhi.tuotuzju.com {
\tredir https://tuotuzju.com/lingzhi{uri} 308
}
"""


def _replace_route(source: str, legacy: str, desired: str, label: str) -> str:
    if desired in source:
        if legacy in source:
            raise ValueError(f"Lingzhi {label} contains both legacy and desired routes")
        return source

    occurrences = source.count(legacy)
    if occurrences != 1:
        raise ValueError(
            f"Lingzhi {label} legacy route count is {occurrences}; expected exactly one"
        )
    return source.replace(legacy, desired, 1)


def rewrite_caddyfile(source: str) -> str:
    rewritten = _replace_route(
        source,
        LEGACY_MAIN_ROUTE,
        MAIN_DOMAIN_ROUTE,
        "main-domain",
    )
    return _replace_route(
        rewritten,
        LEGACY_SUBDOMAIN_ROUTE,
        SUBDOMAIN_REDIRECT_ROUTE,
        "subdomain",
    )


def _run(command: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def _verify_public_routes() -> None:
    _run(
        [
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--max-time",
            "10",
            "--noproxy",
            "*",
            "--resolve",
            "tuotuzju.com:443:127.0.0.1",
            "https://tuotuzju.com/lingzhi/api/health",
        ]
    )
    redirect = _run(
        [
            "curl",
            "--silent",
            "--show-error",
            "--head",
            "--max-time",
            "10",
            "--noproxy",
            "*",
            "--resolve",
            "lingzhi.tuotuzju.com:443:127.0.0.1",
            "https://lingzhi.tuotuzju.com/",
        ],
        capture_output=True,
    )
    expected_location = "location: https://tuotuzju.com/lingzhi/"
    if expected_location not in redirect.stdout.lower():
        raise RuntimeError("Lingzhi subdomain did not redirect to the canonical /lingzhi/ URL")


def configure_public_route(config_path: Path, caddy_binary: str) -> Path | None:
    original = config_path.read_text(encoding="utf-8")
    rewritten = rewrite_caddyfile(original)

    if rewritten == original:
        _verify_public_routes()
        print("Lingzhi public route is already configured")
        return None

    file_stat = config_path.stat()
    candidate_path: Path | None = None
    backup_path = config_path.with_name(
        f"{config_path.name}.backup-lingzhi-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config_path.parent,
            prefix=f".{config_path.name}.lingzhi-",
            delete=False,
        ) as candidate:
            candidate.write(rewritten)
            candidate_path = Path(candidate.name)

        os.chmod(candidate_path, file_stat.st_mode)
        os.chown(candidate_path, file_stat.st_uid, file_stat.st_gid)
        _run(
            [
                caddy_binary,
                "validate",
                "--config",
                str(candidate_path),
                "--adapter",
                "caddyfile",
            ]
        )

        shutil.copy2(config_path, backup_path)
        os.replace(candidate_path, config_path)
        candidate_path = None

        try:
            _run(
                [
                    caddy_binary,
                    "reload",
                    "--config",
                    str(config_path),
                    "--adapter",
                    "caddyfile",
                ]
            )
            _verify_public_routes()
        except Exception:
            shutil.copy2(backup_path, config_path)
            _run(
                [
                    caddy_binary,
                    "reload",
                    "--config",
                    str(config_path),
                    "--adapter",
                    "caddyfile",
                ]
            )
            raise
    finally:
        if candidate_path is not None:
            candidate_path.unlink(missing_ok=True)

    print(f"Lingzhi public route configured; backup: {backup_path}")
    return backup_path


def main() -> None:
    config_path = Path(os.getenv("LINGZHI_CADDY_CONFIG", "/etc/caddy/Caddyfile"))
    caddy_binary = os.getenv("LINGZHI_CADDY_BINARY") or shutil.which("caddy")
    if not caddy_binary:
        raise RuntimeError("caddy executable was not found")
    configure_public_route(config_path, caddy_binary)


if __name__ == "__main__":
    main()
