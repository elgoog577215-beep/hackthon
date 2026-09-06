"""One quality decision for manuscript preview, confirmation and export.

Reclassify legacy pacing diagnostics without modifying the confirmed content or
its revision. Source and rendered-scene checks remain the compiler's authority.
"""
from ppt_presentation import PACING_ISSUE_CODES

MANUSCRIPT_QUALITY_VERSION = "teaching_manuscript_quality_v2.6"


def quality_report(manuscript: dict) -> dict:
    teaching = manuscript.get("teaching_content_contract_version") == "page_teaching_v2"
    issues = manuscript.get("quality_issues") or []
    blocking = [issue for issue in issues if not (teaching and issue.get("code") in PACING_ISSUE_CODES)]
    suggestions = list(manuscript.get("quality_suggestions") or [])
    suggestions.extend(issue for issue in issues if teaching and issue.get("code") in PACING_ISSUE_CODES)
    # A blocked result with no diagnostics is still blocked, never guessed safe.
    passed = not blocking and (manuscript.get("quality_status") == "passed" or bool(teaching and issues))
    return {"version": MANUSCRIPT_QUALITY_VERSION, "passed": passed,
            "issues": blocking, "suggestions": suggestions}


def manuscript_quality_passed(manuscript: dict) -> bool:
    return quality_report(manuscript)["passed"]
