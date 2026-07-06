"""Lightweight learner context ledger for AI prompts.

This module intentionally stays file-storage based. It only aggregates the
learning signals this app already has: notes, wrong answers, tutor memory and
the latest generated profile snapshot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from storage import storage

DEFAULT_USER_ID = "default_user"
PROFILE_SNAPSHOT_FILE = "learner_profiles.json"


@dataclass
class LearnerContext:
    user_id: str = DEFAULT_USER_ID
    node_id: str | None = None
    course_id: str | None = None
    notes: str = ""
    mistakes: str = ""
    learning_footprint: str = ""
    preferences: str = ""
    persona_summary: str = ""
    weaknesses: list[dict[str, Any]] = field(default_factory=list)
    strengths: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_prompt(self) -> str:
        parts = [
            ("画像摘要", self.persona_summary),
            ("学习偏好", self.preferences),
            ("本节相关笔记", self.notes),
            ("近期错题/薄弱点", self.mistakes),
            ("最近学习足迹", self.learning_footprint),
        ]
        lines = [f"## {title}\n{content}" for title, content in parts if content]
        if self.weaknesses:
            lines.append("## 导师记忆中的薄弱章节\n" + _format_state_items(self.weaknesses))
        if self.strengths:
            lines.append("## 已掌握较好的章节\n" + _format_state_items(self.strengths))
        return "\n\n".join(lines) if lines else "暂无明确学习者上下文。"


def save_profile_snapshot(
    *,
    ai_profile: str,
    persona_summary: str,
    self_evaluation: str = "",
    user_id: str = DEFAULT_USER_ID,
) -> None:
    """Persist the latest AI profile summary for future prompt injection."""
    data = storage.load_data(PROFILE_SNAPSHOT_FILE) or {}
    data[user_id] = {
        "ai_profile": ai_profile,
        "persona_summary": persona_summary,
        "self_evaluation": self_evaluation,
        "updated_at": datetime.now().isoformat(),
    }
    storage.save_data(PROFILE_SNAPSHOT_FILE, data)


def build_learner_context(
    *,
    user_id: str = DEFAULT_USER_ID,
    course_id: str | None = None,
    node_id: str | None = None,
    request_persona: str = "",
) -> LearnerContext:
    annotations = _load_annotations(course_id, node_id)
    profile = _load_profile_snapshot(user_id)
    tutor = _load_tutor_signals(user_id)

    persona_summary = request_persona or profile.get("persona_summary", "")
    preferences = _build_preferences(profile, tutor.get("profile", {}))

    return LearnerContext(
        user_id=user_id,
        node_id=node_id,
        course_id=course_id,
        notes=_format_notes(annotations),
        mistakes=_format_mistakes(annotations, tutor.get("wrong_answers", [])),
        learning_footprint=_format_footprint(annotations),
        preferences=preferences,
        persona_summary=persona_summary,
        weaknesses=tutor.get("weaknesses", []),
        strengths=tutor.get("strengths", []),
    )


def _load_annotations(course_id: str | None, node_id: str | None) -> list[dict[str, Any]]:
    annotations = storage.load_annotations()
    if course_id:
        annotations = [a for a in annotations if not a.get("course_id") or a.get("course_id") == course_id]
    if node_id:
        related = [a for a in annotations if a.get("node_id") == node_id]
        recent = _recent(annotations, limit=5)
        return _dedupe_annotations(related + recent)
    return _recent(annotations, limit=8)


def _load_profile_snapshot(user_id: str) -> dict[str, Any]:
    data = storage.load_data(PROFILE_SNAPSHOT_FILE) or {}
    return data.get(user_id, {})


def _load_tutor_signals(user_id: str) -> dict[str, Any]:
    try:
        from tutor_service import tutor_memory

        return {
            "profile": tutor_memory.get_or_create_profile(user_id),
            "weaknesses": tutor_memory.get_weaknesses(user_id)[:5],
            "strengths": tutor_memory.get_strengths(user_id)[:5],
            "wrong_answers": tutor_memory.get_wrong_answers_for_review(user_id, 5),
        }
    except Exception:
        return {"profile": {}, "weaknesses": [], "strengths": [], "wrong_answers": []}


def _build_preferences(profile: dict[str, Any], tutor_profile: dict[str, Any]) -> str:
    items = []
    if profile.get("self_evaluation"):
        items.append(f"自评：{profile['self_evaluation']}")
    if tutor_profile.get("learning_style"):
        items.append(f"学习风格：{tutor_profile['learning_style']}")
    if tutor_profile.get("preferred_difficulty"):
        items.append(f"偏好难度：{tutor_profile['preferred_difficulty']}")
    if tutor_profile.get("common_mistakes"):
        items.append("常见问题：" + "；".join(tutor_profile["common_mistakes"][:3]))
    return "；".join(items)


def _format_notes(annotations: list[dict[str, Any]]) -> str:
    notes = [
        a for a in annotations
        if a.get("source_type") in {"user", "user_saved", None}
        and (a.get("answer") or a.get("anno_summary"))
    ]
    return "\n".join(
        f"- {a.get('anno_summary') or '学习笔记'}：{_clip(a.get('answer') or a.get('question') or '')}"
        for a in notes[:5]
    )


def _format_mistakes(
    annotations: list[dict[str, Any]],
    wrong_answers: list[dict[str, Any]],
) -> str:
    mistake_annotations = [
        a for a in annotations
        if a.get("source_type") == "wrong"
        or "错" in str(a.get("anno_summary", ""))
        or "mistake" in str(a.get("anno_summary", "")).lower()
    ]
    lines = [
        f"- {a.get('anno_summary') or '错题'}：{_clip(a.get('question') or a.get('answer') or '')}"
        for a in mistake_annotations[:5]
    ]
    lines.extend(
        f"- {w.get('node_title', '未知章节')}：{_clip(w.get('question', ''))}"
        for w in wrong_answers[:5]
    )
    return "\n".join(line for line in lines if line.strip("- ："))


def _format_footprint(annotations: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"- {a.get('anno_summary') or a.get('question') or '学习记录'} ({a.get('node_id', '未知节点')})"
        for a in _recent(annotations, limit=5)
    )


def _format_state_items(items: list[dict[str, Any]]) -> str:
    lines = []
    for item in items[:5]:
        title = item.get("node_title") or item.get("node_name") or item.get("node_id", "未知章节")
        correct_rate = item.get("correct_rate")
        if isinstance(correct_rate, (int, float)):
            lines.append(f"- {title}：正确率 {correct_rate:.0%}")
        else:
            lines.append(f"- {title}")
    return "\n".join(lines)


def _recent(annotations: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return sorted(annotations, key=_annotation_time, reverse=True)[:limit]


def _annotation_time(annotation: dict[str, Any]) -> str:
    return str(annotation.get("timestamp") or annotation.get("create_time") or "")


def _dedupe_annotations(annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for annotation in annotations:
        key = annotation.get("anno_id") or (annotation.get("node_id"), annotation.get("question"), annotation.get("answer"))
        if key in seen:
            continue
        seen.add(key)
        result.append(annotation)
    return result


def _clip(text: str, limit: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit].rstrip() + "..."
