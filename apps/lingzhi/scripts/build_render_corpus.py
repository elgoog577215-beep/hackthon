#!/usr/bin/env python3
"""Rebuild the real-course corpus the render-gate measurements are based on.

The courses live in git history, not the working tree: `backend/data/courses/`
holds two hand-authored demos, while 15 real generated courses were deleted in
earlier commits. Those deleted files are the only large body of genuine model
output in the repo — 8 of them give 792 nodes and ~873k characters spanning
mathematics, physics, philosophy, machine learning and programming.

They are read with `git show`, never checked out, so running this cannot disturb
the working tree. Output is a directory of course JSON that
`f1_render_gate_false_positive_probe.py` and `render_gate.mjs` both consume.

    python3 scripts/build_render_corpus.py --out /tmp/corpus
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (commit, filename) pairs. The commit is simply one where the file still
# existed; content is identical wherever it appears.
CORPUS = [
    ("e3a3e4b5", "eb1b58a9-ef99-46d6-8538-daf161e7036b.json"),  # Python 高级编程
    ("4e3b88a9", "8ead44c5-607b-4040-b434-220a357b05db.json"),  # 哲学
    ("182f117e", "8436d166-2710-457e-abf9-9f630ededb87.json"),  # 线性代数
    ("4e3b88a9", "db03dfc5-45bf-4650-b612-fa9dc7235bba.json"),  # 经典力学
    ("4e3b88a9", "b451176e-87d0-495f-8964-293f3701c693.json"),  # 机器学习
    ("4e3b88a9", "cc7aed72-ad8e-48cd-922a-08ed0354b0a7.json"),  # 高等代数
    ("182f117e", "183738db-6fcd-47fd-97d9-938b9e60ebbd.json"),  # 辩论
    ("182f117e", "46d5b522-0121-4058-8752-81d3a6476b78.json"),  # 量子力学
]


def main() -> int:
    parser = argparse.ArgumentParser(description="从 git 历史重建真实课程语料")
    parser.add_argument("--out", required=True, help="语料输出目录")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    total_nodes = 0
    total_chars = 0
    written = 0
    for commit, filename in CORPUS:
        result = subprocess.run(
            ["git", "show", f"{commit}:backend/data/courses/{filename}"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        if result.returncode != 0:
            print(f"跳过 {filename}：{result.stderr.strip()[:120]}", file=sys.stderr)
            continue
        try:
            course = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            print(f"跳过 {filename}：JSON 解析失败 {error}", file=sys.stderr)
            continue
        nodes = [
            node for node in course.get("nodes") or []
            if str(node.get("node_content") or "").strip()
        ]
        chars = sum(len(str(node["node_content"])) for node in nodes)
        (out_dir / filename).write_text(result.stdout, encoding="utf-8")
        written += 1
        total_nodes += len(nodes)
        total_chars += chars
        print(f"{course.get('course_name', filename)[:34]:<36} nodes={len(nodes):>4} chars={chars:>7}")

    print(f"\n共 {written} 门课，{total_nodes} 节正文，{total_chars} 字符 → {out_dir}")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
