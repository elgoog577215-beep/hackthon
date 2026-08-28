"""Small Markdown-table parser shared by slide renderers."""

from __future__ import annotations

import re


def parse_markdown_table(value: str) -> tuple[list[str], list[list[str]]]:
    def audience_cell(cell: str) -> str:
        clean = cell.replace(r"\|", "|").strip()
        clean = re.sub(r"(?i)<br\s*/?>", " · ", clean)
        clean = re.sub(r"(?<!\\)(?:\*\*|__|`)", "", clean)
        return clean.strip()

    rows = []
    for line in str(value or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        if re.fullmatch(r"[|:\-\s]+", stripped) and "-" in stripped:
            continue
        cells = [
            audience_cell(cell)
            for cell in re.split(r"(?<!\\)\|", stripped.strip("|"))
        ]
        if cells:
            rows.append(cells)
    return (rows[0], rows[1:]) if rows else ([], [])


__all__ = ["parse_markdown_table"]
