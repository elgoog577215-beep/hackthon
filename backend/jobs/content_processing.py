"""Deterministic cleanup applied before generated content is committed."""

from __future__ import annotations

import re
from typing import Any


def _remap_assessment_revision_references(
    assets: dict[str, Any],
    revision_remap: dict[str, str],
) -> None:
    """Keep mastery and final-assessment links aligned after a prompt repair."""
    for asset_type in ("mastery_criteria", "misconceptions"):
        for item in assets.get(asset_type) or []:
            if not isinstance(item, dict):
                continue
            item["assessment_bindings"] = [
                revision_remap.get(str(value), str(value))
                for value in item.get("assessment_bindings") or []
            ]
    for item in assets.get("final_assessment") or []:
        if not isinstance(item, dict):
            continue
        item["question_revision_ids"] = [
            revision_remap.get(str(value), str(value))
            for value in item.get("question_revision_ids") or []
        ]


def fix_latex_content(content: str) -> str:
    """修复 LaTeX 公式格式问题"""
    if not content:
        return content

    def fix_aligned_env(match: re.Match[str]) -> str:
        env_name = match.group(1)
        inner = match.group(2) if match.lastindex and match.lastindex >= 2 else ""

        inner = re.sub(r"\$\s*$", "", inner)
        inner = re.sub(r"^\s*\$", "", inner)
        inner = re.sub(r"\$\$", "", inner)
        inner = re.sub(r"\\\$", r"\\", inner)
        inner = re.sub(r"\\\s*$", r"\\", inner, flags=re.MULTILINE)
        inner = re.sub(r"\\\s*\n", r"\\\n", inner)

        return f"$$\n\\begin{{{env_name}}}\n{inner}\n\\end{{{env_name}}}\n$$"

    content = re.sub(
        r'\\begin\{(aligned|matrix|pmatrix|bmatrix|vmatrix|cases|eqnarray|gather|split)\}(.*?)(?:\\end\{\1\}|$)',
        fix_aligned_env,
        content,
        flags=re.DOTALL,
    )

    content = re.sub(r"\\\[(.+?)\\\]", r"\n$$\n\1\n$$\n", content, flags=re.DOTALL)
    content = re.sub(r"\\\((.+?)\\\)", r"$\1$", content, flags=re.DOTALL)

    content = re.sub(
        r'(?<!\$)\$([^\n$]+?)\$(?!\$)',
        lambda match: f'${match.group(1).strip()}$',
        content,
    )

    # A streamed model can stop after opening a display formula. Repair the
    # smallest deterministic boundary here, before the node is marked complete,
    # while leaving literal dollars inside fenced code untouched.
    lines = content.splitlines()
    in_code_fence = False
    display_fence_count = 0
    for index, line in enumerate(lines):
        if re.match(r"^\s*```", line):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        # Some providers still emit the legacy Markdown display form with a
        # single dollar on its own line. The quality gate correctly rejects
        # that form, so normalize it before a generated node is finalized.
        # Literal dollars inside fenced code were excluded above.
        if re.match(r"^\s*(?<!\\)\$\s*$", line):
            normalized = re.sub(r"\$", "$$", line, count=1)
        else:
            normalized = re.sub(r"(?<!\\)\${3,}", "$$", line)
        lines[index] = normalized
        display_fence_count += len(
            re.findall(r"(?<!\\)\$\$", normalized)
        )
    content = "\n".join(lines)
    if display_fence_count % 2:
        content = f"{content.rstrip()}\n$$\n"

    return content


__all__ = ["fix_latex_content"]
