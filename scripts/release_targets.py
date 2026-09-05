#!/usr/bin/env python3
"""Map a Git diff to application releases; never connect to a server."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def targets(paths):
    tuotu = False
    services = set()
    for path in paths:
        if path.endswith(".md") or path.startswith((".agents/", ".impeccable/")):
            continue
        if path.startswith("apps/lingzhi/"):
            if path.startswith(("apps/lingzhi/docs/", "apps/lingzhi/openspec/", "apps/lingzhi/demo_videos/")):
                continue
            tuotu = True
            services.add("lingzhi")
        elif path.startswith("apps/qizhi/client/"):
            services.add("website")
        elif path.startswith("apps/qizhi/"):
            # Identity/API changes must travel with their consumers in one release.
            services.update(("server", "website", "lingzhi"))
        elif path.startswith("deploy/tuotu/") or path == ".github/workflows/deploy-lingzhi.yml":
            tuotu = True
        elif path.startswith("deploy/zju/") or path == ".github/workflows/zju-release.yml":
            services.update(("server", "website", "lingzhi"))
        elif path in (".gitignore", ".gitattributes", "LICENSE", "dev.sh", "dev.bat"):
            continue
        else:
            # Shared build/release tooling: validate both targets conservatively.
            tuotu = True
            services.update(("server", "website", "lingzhi"))
    return {"tuotu": tuotu, "zju": bool(services), "zju_services": sorted(services)}


def changed_paths(base, head):
    if not base or set(base) == {"0"}:
        args = ["ls-tree", "-r", "--name-only", "-z", head]
    else:
        args = ["diff", "--name-only", "--no-renames", "-z", base, head]
    return subprocess.check_output(["git", "-C", str(ROOT), *args]).decode().rstrip("\0").split("\0")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    result = targets(args.paths or changed_paths(args.base, args.head))
    print(json.dumps(result, ensure_ascii=False))
    if args.github_output:
        with args.github_output.open("a") as out:
            for key, value in result.items():
                out.write(f"{key}={json.dumps(value)}\n")


if __name__ == "__main__":
    main()
