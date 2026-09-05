"""Deterministic quality checks for generated course output."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from learning_events import summarize_text


@dataclass(frozen=True)
class AIOutputQualityAssessment:
    output_type: str
    score: float
    passed: bool
    issues: list[str] = field(default_factory=list)
    context_summary: str = ""
    output_summary: str = ""
    output_chars: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_ai_output(
    *,
    output_type: str,
    output_text: str,
    context_text: str = "",
    min_chars: int = 80,
    require_markdown_structure: bool = False,
) -> AIOutputQualityAssessment:
    """Assess an AI output with deterministic, explainable heuristics."""
    text = str(output_text or "").strip()
    issues: list[str] = []
    score = 1.0

    if not text:
        issues.append("输出为空")
        score -= 0.7
    elif len(text) < min_chars:
        issues.append(f"输出偏短，少于 {min_chars} 字符")
        score -= 0.25

    if require_markdown_structure and "##" not in text and "\n-" not in text:
        issues.append("缺少 Markdown 结构")
        score -= 0.2

    if any(marker in text for marker in ["http://", "https://", "论文发表于", "根据某研究"]):
        issues.append("包含需要核验的外部来源表述")
        score -= 0.15

    if "暂无" in text or "生成中" in text:
        issues.append("输出可能是兜底内容")
        score -= 0.2

    score = max(0.0, min(1.0, round(score, 2)))
    return AIOutputQualityAssessment(
        output_type=output_type,
        score=score,
        passed=score >= 0.65,
        issues=issues,
        context_summary=summarize_text(context_text, limit=500),
        output_summary=summarize_text(text, limit=500),
        output_chars=len(text),
    )
