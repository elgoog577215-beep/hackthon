#!/usr/bin/env python3
"""Print the requirements that apply to the running Python interpreter."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

try:
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
except ImportError:  # pip always carries a vendored packaging parser.
    from pip._vendor.packaging.markers import default_environment
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.utils import canonicalize_name


def effective_requirements(path: Path) -> list[str]:
    environment = default_environment()
    result: list[str] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-"):
            raise ValueError(
                f"{path}:{line_number}: unsupported requirements option"
            )
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate(environment):
            continue
        extras = (
            f"[{','.join(sorted(requirement.extras))}]"
            if requirement.extras
            else ""
        )
        target = (
            f" @ {requirement.url}"
            if requirement.url
            else str(requirement.specifier)
        )
        result.append(
            f"{canonicalize_name(requirement.name)}{extras}{target}"
        )
    return sorted(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("requirements", type=Path)
    args = parser.parse_args()
    try:
        for requirement in effective_requirements(args.requirements):
            print(requirement)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
