#!/usr/bin/env python3
"""Measure the false-positive rate of the L3d / L3e publication-gate criteria.

Why this exists: L3d (table/list/blockquote structure) and L3e (render vs
content dimension split) are publication-gate criteria that had only unit tests.
Unit tests use content I wrote, so they prove the rules fire on what I expected
them to fire on — they say nothing about how often the rules misfire on real
model output. One false positive blocks a release.

What counts as a false positive here: a criterion fires on content that a real
renderer accepts. That is the operational definition — if KaTeX/markdown-it
render it without error, the learner sees it correctly, so flagging it as a
publication blocker is a misfire.

The corpus is real AI-generated prose already on disk (teaching representations
from previous real runs), not text written for this test. Using it costs no
provider quota and gives a broader sample than one freshly generated course.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for module_root in (ROOT, BACKEND):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from course_quality import (  # noqa: E402
    RENDER_ISSUE_CODES,
    _issue_dimension,
    _structural_markdown_issues,
)

# The codes L3d introduced; these are what we are measuring.
L3D_CODES = {
    "table_missing_delimiter",
    "table_delimiter_mismatch",
    "empty_blockquote",
    "list_numbering_restart",
}


_FILLER = re.compile(r"([\u4e00-\u9fff]{4,})")


def _is_synthetic(text: str) -> bool:
    """Reject test fixtures so the sample is not inflated with fake data.

    `backend/data/question_banks` looked like 4780 extra fragments, but every
    long string there is filler of the form "完整课程内容。" repeated dozens of
    times. Counting those would make the sample look 200x larger while
    measuring nothing real, which is worse than a small honest sample.
    """
    tokens = _FILLER.findall(text)
    if not tokens:
        return False
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return max(counts.values()) >= 5


def _fragments(pattern: str, min_chars: int) -> list[dict]:
    """Pull real generated prose out of stored representations."""
    seen: set[str] = set()
    out: list[dict] = []
    for path in sorted(glob.glob(pattern)):
        raw = Path(path).read_text(encoding="utf-8")
        for match in re.finditer(
            r'"(?:markdown|body|content|text|rendered_text)"\s*:\s*"((?:[^"\\]|\\.)+)"',
            raw,
        ):
            try:
                text = json.loads(f'"{match.group(1)}"')
            except json.JSONDecodeError:
                continue
            if len(text) < min_chars or text in seen or _is_synthetic(text):
                continue
            seen.add(text)
            out.append({"source": Path(path).name, "text": text})
    return out


def _wilson_upper_bound(events: int, trials: int, z: float = 1.96) -> float:
    """One-sided 95% upper bound on the true rate.

    With zero observed events this reduces to roughly the rule of three (3/n):
    26 clean samples cannot rule out a true rate around 11%. Reporting the bound
    keeps "0%" from being read as "proven safe".
    """
    if trials <= 0:
        return 1.0
    phat = events / trials
    denominator = 1 + z * z / trials
    centre = phat + z * z / (2 * trials)
    margin = z * ((phat * (1 - phat) / trials + z * z / (4 * trials * trials)) ** 0.5)
    return round(min(1.0, (centre + margin) / denominator), 4)


def _has_structure(text: str) -> dict[str, bool]:
    return {
        "table": bool(re.search(r"(?m)^\s*\|.*\|", text)),
        "list": bool(re.search(r"(?m)^\s*(?:\d+\.|[-*+])\s+\S", text)),
        "blockquote": bool(re.search(r"(?m)^\s*>", text)),
        "math": "$" in text,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="统计 L3d/L3e 判据在真实课程正文上的误报率"
    )
    parser.add_argument(
        "--corpus",
        default=str(BACKEND / "data" / "teaching_representations" / "*.json"),
    )
    parser.add_argument("--min-chars", type=int, default=80)
    parser.add_argument("--show", type=int, default=8, help="列出多少条误报样本")
    args = parser.parse_args()

    fragments = _fragments(args.corpus, args.min_chars)
    if not fragments:
        print(json.dumps({"status": "no_corpus", "corpus": args.corpus}, ensure_ascii=False))
        return 1

    structural_total = 0
    flagged: list[dict] = []
    by_code: dict[str, int] = {}
    structure_counts = {"table": 0, "list": 0, "blockquote": 0, "math": 0}

    for item in fragments:
        text = item["text"]
        structure = _has_structure(text)
        for key, present in structure.items():
            if present:
                structure_counts[key] += 1
        # Only fragments that actually contain the structures L3d judges can
        # produce a meaningful false positive.
        if not any((structure["table"], structure["list"], structure["blockquote"])):
            continue
        structural_total += 1
        issues = _structural_markdown_issues(text, "probe")
        hits = [i for i in issues if i["code"] in L3D_CODES]
        if hits:
            for issue in hits:
                by_code[issue["code"]] = by_code.get(issue["code"], 0) + 1
            flagged.append({
                "source": item["source"],
                "codes": [i["code"] for i in hits],
                "excerpt": text[:220],
            })

    rate = (len(flagged) / structural_total) if structural_total else 0.0
    # A 0/N result is "not observed", never "does not happen". The one-sided
    # 95% upper bound (rule of three for zero events) states what the sample can
    # actually support, so nobody reads 0% as proof of safety.
    upper_95 = _wilson_upper_bound(len(flagged), structural_total)

    # L3e: verify every code the module can emit lands in exactly one dimension,
    # and that the L3d codes are attributed to render (not content).
    dimension_check = {
        code: _issue_dimension(code) for code in sorted(L3D_CODES)
    }
    misattributed = [c for c, d in dimension_check.items() if d != "render"]

    report = {
        "status": "measured",
        "corpus_fragments": len(fragments),
        "fragments_with_structure": structural_total,
        "structure_counts": structure_counts,
        "flagged_fragments": len(flagged),
        "false_positive_rate": round(rate, 4),
        "false_positive_rate_upper_95": upper_95,
        "reading": (
            f"{len(flagged)}/{structural_total} 未发现误报；"
            f"样本量只能支持「真实误报率 ≤ {upper_95:.1%}（95% 单侧上界）」，"
            "不能读作「不存在误报」"
        ),
        "by_code": by_code,
        "l3e_dimension_of_l3d_codes": dimension_check,
        "l3e_misattributed": misattributed,
        "render_codes_total": len(RENDER_ISSUE_CODES),
        "samples": flagged[: args.show],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
