"""Print a compact narrative audit for a canonical course slide deck."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from course_document import CourseDocument  # noqa: E402
from slide_deck_v3 import (  # noqa: E402
    compile_slide_deck_v3,
    deterministic_slide_allocation,
    fragment_course_document,
)
from slide_deck_renderer import export_structured_slide_deck  # noqa: E402


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("course_file", type=Path)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--export-pptx", type=Path)
    parser.add_argument("--export-slide-limit", type=int, default=0)
    args = parser.parse_args()

    course = json.loads(args.course_file.read_text(encoding="utf-8"))
    document = CourseDocument.model_validate(course["course_document"])
    fragments = fragment_course_document(document)
    plan = deterministic_slide_allocation(
        document,
        fragments,
        mode="teaching",
        theme="qizhi-classroom",
    )
    content = compile_slide_deck_v3(
        document,
        course,
        mode="teaching",
        theme="qizhi-classroom",
        allocation_plan=plan,
    )
    if args.export_pptx:
        export_content = content
        if args.export_slide_limit > 0:
            export_content = {
                **content,
                "slides": content["slides"][: args.export_slide_limit],
            }
        export_structured_slide_deck(
            export_content,
            args.export_pptx,
            theme="qizhi-classroom",
        )
        print("exported", args.export_pptx.resolve())
    print(
        "fragments",
        len(fragments),
        "pages",
        len(plan.pages),
        "main",
        sum(not page.appendix for page in plan.pages),
        "appendix",
        sum(page.appendix for page in plan.pages),
    )
    print("roles", Counter(page.narrative_role for page in plan.pages if not page.appendix))
    print("layouts", Counter(page.layout for page in plan.pages if not page.appendix))
    print("quality", content["quality_summary"])
    print(
        "semantic",
        [
            (issue["code"], issue.get("slide_id"))
            for issue in content["quality_report"]["semantic"]["issues"]
        ],
    )
    print(
        "blockers",
        [
            (issue["code"], issue.get("slide_id"))
            for issue in content["quality_report"]["blockers"][:20]
        ],
    )
    slides_by_id = {
        slide["unit_id"]: slide
        for slide in content["slides"]
    }
    for issue in content["quality_report"]["blockers"][:10]:
        slide = slides_by_id.get(issue.get("slide_id"))
        if slide:
            print(
                "blocker_detail",
                issue["code"],
                slide["unit_id"],
                slide["title"],
                [
                    {
                        "type": block["type"],
                        "content_length": len(block.get("content") or ""),
                        "item_lengths": [
                            len(item) for item in block.get("items") or []
                        ],
                    }
                    for block in slide["blocks"]
                ],
            )
    for index, slide in enumerate(content["slides"][: args.limit], start=1):
        print(
            f"{index:03d} {slide['slide_purpose']} | "
            f"{slide['layout']} | {slide['title']}"
        )


if __name__ == "__main__":
    main()
