#!/usr/bin/env python3
"""Check that a plain checkout contains the integrated build sources."""
from pathlib import Path
import json
import subprocess


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    qizhi = root / "apps/qizhi"
    for relative in (
        "apps/lingzhi/Dockerfile", "apps/lingzhi/frontend/package.json", "apps/lingzhi/backend/start.sh",
        "apps/qizhi/server/main.py", "apps/qizhi/client/website/package.json",
        "deploy/zju/docker-compose.yml", "deploy/zju/server/Dockerfile",
        "deploy/zju/website/Dockerfile",
    ):
        if not (root / relative).is_file():
            raise SystemExit(f"Missing build source: {relative}")
    if (qizhi / "services/lingzhi").exists() or (qizhi / ".gitmodules").exists():
        raise SystemExit("Qizhi must use the apps/lingzhi source, without a submodule copy")
    for relative in ("apps/qizhi/client/website/package.json", "apps/qizhi/plugins/essay_check_front/package.json"):
        package = json.loads((root / relative).read_text())
        lock_path = root / relative.replace("package.json", "package-lock.json")
        lock = json.loads(lock_path.read_text())["packages"][""]
        for key in ("dependencies", "devDependencies"):
            if package.get(key, {}) != lock.get(key, {}):
                raise SystemExit(f"Lockfile does not match {relative}: {key}")
    tracked = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "--stage", "apps"], text=True
    )
    if any(line.startswith("160000 ") for line in tracked.splitlines()):
        raise SystemExit("Qizhi contains a Git submodule")
    print("Qizhi source paths and dependency manifests verified.")


if __name__ == "__main__":
    main()
