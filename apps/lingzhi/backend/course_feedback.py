"""课程检查与参考块的确定性结构编译。"""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any


FEEDBACK_SCHEMA_VERSION = "course_feedback_v1"

_LEGACY_SECTION_TITLE = (
    r"(?:任务\s*\d+[^*\n]*|常见错误(?:反馈)?|典型错误(?:反馈)?|"
    r"评价标准[^*\n]*|评分标准[^*\n]*|参考答案[^*\n]*|答案方向[^*\n]*|核对标准[^*\n]*)"
)
_SECTION_HEADING_RE = re.compile(
    rf"(?m)^(?:###\s+(?P<h3>.+?)|\*\*(?P<strong>{_LEGACY_SECTION_TITLE})\*\*[：:]?)\s*$"
)


def default_block_kind_for_role(role: str) -> str:
    """Return the canonical presentation kind when legacy metadata has none."""
    if role == "feedback":
        return "review_checkpoint"
    if role == "checkpoint":
        return "mastery_check"
    return "rich_text"


def compile_feedback_structure(markdown: str) -> dict[str, Any]:
    """Compile task-level presentation metadata without replacing Markdown truth."""
    text = str(markdown or "").strip()
    matches = list(_SECTION_HEADING_RE.finditer(text))
    raw_sections: list[tuple[str, str]] = []

    if matches:
        preface = _clean_body(text[: matches[0].start()])
        if preface:
            raw_sections.append(("核对说明", preface))
        for index, match in enumerate(matches):
            title = str(match.group("h3") or match.group("strong") or "参考与检查").strip(" ：:")
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = _clean_body(text[match.end():end])
            if body:
                raw_sections.append((title, body))
    elif text:
        raw_sections.append(("参考与检查", _clean_body(text)))

    multiple = len(raw_sections) > 1
    sections: list[dict[str, Any]] = []
    for index, (title, body) in enumerate(raw_sections):
        kind = _section_kind(title)
        sections.append({
            "section_id": _section_id(index, title),
            "title": title,
            "kind": kind,
            "markdown": body,
            "summary": _summary(body),
            "collapsed_by_default": bool(multiple or len(body) >= 700 or kind == "reference_answer"),
        })

    return {
        "schema_version": FEEDBACK_SCHEMA_VERSION,
        "mode": "static_reference",
        "source_fingerprint": _fingerprint(text),
        "sections": sections,
    }


def enrich_feedback_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach a synchronized derived structure to a feedback block payload."""
    enriched = deepcopy(payload)
    markdown = str(enriched.get("markdown") or enriched.get("text") or "")
    current = enriched.get("feedback_structure")
    fingerprint = _fingerprint(markdown.strip())
    if not (
        isinstance(current, dict)
        and current.get("schema_version") == FEEDBACK_SCHEMA_VERSION
        and current.get("source_fingerprint") == fingerprint
    ):
        enriched["feedback_structure"] = compile_feedback_structure(markdown)
    return enriched


def project_feedback_structures(document: Any) -> Any:
    """Return a read projection that enriches old canonical feedback blocks."""
    projected = deepcopy(document)
    for block in projected.blocks:
        if block.role == "feedback" and block.status != "retired":
            block.payload = enrich_feedback_payload(block.payload)
    return projected


def _clean_body(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"(?m)^---\s*$", "", text)
    return text.strip()


def _section_kind(title: str) -> str:
    normalized = re.sub(r"\s+", "", title)
    if any(marker in normalized for marker in ("常见错误", "典型错误", "误区")):
        return "common_errors"
    if any(marker in normalized for marker in ("评价标准", "评分标准", "核对标准")):
        return "rubric"
    if any(marker in normalized for marker in ("答案", "解答", "答案方向")):
        return "reference_answer"
    if "任务" in normalized:
        return "task_review"
    return "guidance"


def _section_id(index: int, title: str) -> str:
    normalized_title = re.sub(r"\s+", " ", title).strip()
    raw = f"{index}:{normalized_title}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"feedback-section-{digest}"


def _fingerprint(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def _summary(markdown: str, limit: int = 96) -> str:
    plain = re.sub(r"```[\s\S]*?```", " ", markdown)
    plain = re.sub(r"[#>*_`$\\-]+", " ", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain[:limit]


__all__ = [
    "FEEDBACK_SCHEMA_VERSION",
    "compile_feedback_structure",
    "default_block_kind_for_role",
    "enrich_feedback_payload",
    "project_feedback_structures",
]
