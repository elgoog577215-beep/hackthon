"""联网资料语义级内容安全 —— P0 敏感主题标记层。

对应设计文档 `docs/研究/联网资料内容安全最小方案-2026-08-09.md` 第 1 层。

四条设计原则（照搬设计文档，实现时未放宽）：
1. **只标记不审查**：不替教师判断对错，只标出"这条需要你看一眼"。
2. **不阻断生成**：判定本身不抛异常、不拒绝候选，命中只降级为"需确认"。
3. **不引外部依赖**：纯本地词表，无第三方审核 API，无数据出境。
4. **不自动删改内容**：只加标注，不动来源正文。

实现位置说明：设计文档原写在网关 `classify_source()` 里，实际落在我方
`web_material_search.candidate_from_source()`——那里是所有联网来源进入
资料链的必经点，且不与团队的 `web_retrieval.py` 争同一文件。
"""

from __future__ import annotations

import re
from typing import Any

# 初版只覆盖"医学建议"与"未定论科学"两类：这两类在教学场景最常见、
# 也最容易误导学生。其余主题留配置位，等真实误标数据再扩。
SENSITIVE_TOPICS: dict[str, tuple[str, ...]] = {
    # 面向研究者的用药/诊疗细节直接进教学材料风险最高。
    "medical_advice": (
        "剂量", "处方", "禁忌症", "不良反应", "副作用", "诊断标准", "适应症",
        "用药", "疗程", "静脉注射",
        "dosage", "prescription", "contraindication", "adverse effect",
        "side effect", "mg/kg",
    ),
    # 未定论内容被当作定论写进课程，是教育场景最实际的事实风险。
    "unsettled_science": (
        "尚有争议", "存在争议", "有待验证", "尚无定论", "初步研究", "假说",
        "preliminary", "hypothesis", "hypothesized", "not yet established",
        "remains controversial", "further research is needed",
    ),
}

# 命中词最多回传几个——给教师看"为什么被标"，不需要全量。
MAX_MATCHED_TERMS = 5

_WORD_BOUNDARY = re.compile(r"[a-z]")


def _contains(term: str, haystack: str) -> bool:
    """英文词做词边界匹配，中文词直接包含匹配。

    英文若不加边界，"mg/kg" 之类没问题，但 "hypothesis" 会命中
    "hypothesises" 之外的无关词；中文没有空格分词，只能包含匹配。
    """
    if _WORD_BOUNDARY.search(term):
        return re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", haystack) is not None
    return term in haystack


def assess_sensitivity(title: str = "", excerpt: str = "") -> dict[str, Any]:
    """判定来源是否需要教师复核。

    返回 `level` 为 `"none"` 或 `"review_recommended"`——**没有 "blocked"**，
    因为这一层不阻断，只降级。
    """
    text = f"{title or ''}\n{excerpt or ''}"
    haystack = text.lower()
    if not haystack.strip():
        return {"level": "none", "topics": [], "matched_terms": []}

    topics: list[str] = []
    matched: list[str] = []
    for topic, terms in SENSITIVE_TOPICS.items():
        hits = [term for term in terms if _contains(term.lower(), haystack)]
        if hits:
            topics.append(topic)
            matched.extend(hits)

    if not topics:
        return {"level": "none", "topics": [], "matched_terms": []}
    return {
        "level": "review_recommended",
        "topics": sorted(topics),
        "matched_terms": sorted(dict.fromkeys(matched))[:MAX_MATCHED_TERMS],
    }


def needs_teacher_review(sensitivity: dict[str, Any] | None) -> bool:
    return str((sensitivity or {}).get("level") or "none") == "review_recommended"


__all__ = [
    "MAX_MATCHED_TERMS",
    "SENSITIVE_TOPICS",
    "assess_sensitivity",
    "needs_teacher_review",
]
