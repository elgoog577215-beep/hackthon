#!/usr/bin/env python3
"""Package one committed source tree for the ZJU Docker build, without private state."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from release_targets import changed_paths, targets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--base", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--verify", args.commit + "^{commit}"], text=True).strip()
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise SystemExit("Invalid commit")
    plan = targets(changed_paths(args.base, sha))
    manifest = {"commit": sha, "target": "zju", "services": plan["zju_services"],
                "format": "source-build-v1", "activation": "not-configured",
                "lingzhi_auth_required": True, "data_included": False}
    source = subprocess.check_output(["git", "-C", str(ROOT), "archive", sha,
                                      "apps/qizhi", "apps/lingzhi", "deploy/zju", "scripts", "LICENSE"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(source)) as src, tarfile.open(args.output, "w:gz") as out:
        for member in src:
            parts = Path(member.name).parts
            if any(part in {"docs", "demo_videos", "output", "openspec"} for part in parts):
                continue
            if Path(member.name).name.startswith("design-qa-"):
                continue
            out.addfile(member, src.extractfile(member) if member.isfile() else None)
        payload = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
        entry = tarfile.TarInfo("release.json"); entry.size = len(payload)
        out.addfile(entry, io.BytesIO(payload))
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(digest + "  " + args.output.name + "\n")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
