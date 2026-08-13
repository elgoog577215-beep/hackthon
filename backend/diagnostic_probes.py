"""Category-aware diagnostic probes for the error-driven question chain (I0-a).

The diagnosis → probe → remediation chain already existed, but every probe was
built from one template regardless of *what kind* of error was hypothesised, and
it ignored the misconception data the knowledge base already carries
(`error_pattern` / `confused_with` / `discrimination` / `repair_strategy`).

A probe exists to answer one question: **is this hypothesis about the student's
error actually true?**  Different error kinds need different evidence:

- ``concept_gap``        — can they state the conditions the concept requires?
- ``process_error``      — can they redo the failing step and check it?
- ``transfer_gap``       — can they apply it in a situation they have not seen?
- ``boundary_confusion`` — can they tell the concept apart from its neighbour?

**The leak boundary is the subtle part of this file.**  The knowledge base holds
two fields that read as helpful but must never enter a probe:

- ``discrimination`` — *is the answer* to a discrimination probe. Pasting it in
  means the student passes by copying, and the hypothesis gets rejected on
  evidence that proves nothing.
- ``repair_strategy`` — teaching content. It belongs to the remediation step
  *after* the hypothesis is confirmed, not to the test that confirms it.

``confused_with`` and ``error_pattern`` are safe: they frame *what to compare*
without supplying the criterion that decides it.  `probe_leaks_answer` enforces
this, and the tests pin it.

There is a third leak path that no fixture exposes: `build_probe_spec`
interpolates ``hypothesis.claim`` verbatim, and in production that claim is the
live model's own description of the error — which may name the correct answer
while describing it.  `probe_leaks_answer` screens for that too, when the caller
passes the originating task.
"""

from __future__ import annotations

from typing import Any

from hint_leakage import mentions_answer_value


PROBE_CATEGORIES = (
    "concept_gap",
    "process_error",
    "transfer_gap",
    "boundary_confusion",
)

# Fields that answer the probe instead of asking it.  Never interpolate these.
FORBIDDEN_PROBE_FIELDS = ("discrimination", "repair_strategy")


def _clip(value: Any, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def find_misconception(
    course: dict[str, Any],
    mistake_point_ids: list[str],
) -> dict[str, Any]:
    """First knowledge-base misconception matching the hypothesis, or empty."""
    wanted = {str(item) for item in mistake_point_ids or [] if str(item or "")}
    if not wanted:
        return {}
    for item in (course.get("learning_assets") or {}).get("misconceptions") or []:
        if str(item.get("mistake_point_id") or "") in wanted:
            return item
    return {}


def build_probe_spec(
    hypothesis: dict[str, Any],
    *,
    task: dict[str, Any],
    misconception: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile one hypothesis into a category-appropriate probe prompt + rubric.

    Returns ``{"prompt", "criteria", "probe_strategy"}``.  The caller keeps
    ownership of ids, levels and outcome matrix.
    """
    claim = _clip(hypothesis.get("claim"), 200)
    category = str(hypothesis.get("category") or "")
    if category not in PROBE_CATEGORIES:
        category = "process_error"
    mistake = misconception or {}
    # Safe to show: names the thing to compare. Never the criterion that decides.
    confused_with = _clip(mistake.get("confused_with"))
    error_pattern = _clip(mistake.get("error_pattern"))
    objective = _clip(task.get("learning_objective") or task.get("prompt"), 120)

    if category == "concept_gap":
        prompt = (
            f"只回答这一点，不要展开其他内容：{claim}。"
            "请写出这个概念成立需要满足的全部必要条件，并说明少了其中任意一条会怎样。"
        )
        criteria = ["列出全部必要条件", "说明缺少某条件的后果", "不引入题目之外的假设"]
        strategy = "state_conditions"
    elif category == "process_error":
        prompt = (
            f"只重做出问题的那一步，不要重写整题：{claim}。"
            "写出这一步的输入、你做的变换、以及你用什么方法检查这一步没错。"
        )
        criteria = ["指明这一步的输入", "写出变换过程", "给出可执行的自检方法"]
        strategy = "redo_single_step"
    elif category == "transfer_gap":
        prompt = (
            f"换一个和原题不同的情境，重新完成这件事：{objective}。"
            f"针对这一点说明你的判断依据：{claim}。不要复用原题的数据。"
        )
        criteria = ["情境与原题不同", "判断依据完整", "结果可复核"]
        strategy = "new_context_transfer"
    else:  # boundary_confusion
        contrast = confused_with or "与它相近的另一个概念"
        pattern_hint = f"（常见混淆表现：{error_pattern}）" if error_pattern else ""
        prompt = (
            f"请把下面两者区分开：本题涉及的对象 与「{contrast}」{pattern_hint}。"
            f"针对这一点作答：{claim}。"
            "各举一个例子：一个属于前者、一个属于后者，并说明你依据什么把它们分开。"
        )
        criteria = ["两个例子分属不同一侧", "给出可判定的区分依据", "依据能解释所举的例子"]
        strategy = "discriminate_neighbour"

    return {
        "prompt": prompt,
        "criteria": criteria,
        "probe_strategy": strategy,
        "probe_category": category,
    }


def probe_leaks_answer(
    probe: dict[str, Any],
    misconception: dict[str, Any] | None,
    task: dict[str, Any] | None = None,
) -> str:
    """Return the offending source if the probe hands over an answer.

    Two distinct hazards, both fatal to the probe's purpose:

    ``discrimination`` / ``repair_strategy`` — *is the answer* to a discrimination
    probe.  Pasting it in means the student passes by copying, and the hypothesis
    gets rejected on evidence that proves nothing.

    The original question's own answer — reachable because `build_probe_spec`
    interpolates ``hypothesis.claim`` verbatim, and in production that claim is
    lifted from the live model's ``answer_diagnosis``.  Observed with a real model:
    the diagnosis read 「原常数 5 与 -9 相加应得 -4，学生误算为 +4」 and the probe
    handed the student 「-4」 — the answer to the very question they are about to
    re-attempt in the remediation chain.  Hand-written fixtures never show this
    because a human writing a claim does not quote the answer.

    Returns ``"answer_value:<value>"`` for that second case so the caller can tell
    the two apart in logs.
    """
    mistake = misconception or {}
    haystack = "".join(
        str(probe.get(field) or "")
        for field in ("prompt", "probe_strategy")
    )
    haystack += "".join(str(item) for item in probe.get("criteria") or [])
    haystack = "".join(haystack.split())
    for field in FORBIDDEN_PROBE_FIELDS:
        value = "".join(str(mistake.get(field) or "").split())
        # Short values collide with ordinary prose; only act on substantive text.
        if len(value) >= 8 and value in haystack:
            return field
    if task:
        # Same metric K1/K2 use — one implementation, not a third one.
        literal = mentions_answer_value(haystack, task)
        if literal:
            return f"answer_value:{literal}"
    return ""


__all__ = [
    "FORBIDDEN_PROBE_FIELDS",
    "PROBE_CATEGORIES",
    "build_probe_spec",
    "find_misconception",
    "probe_leaks_answer",
]
