"""Deterministic, course-native teaching graph for slide-deck V6.

This compiler operates on canonical course blocks and teaching dependencies. It
does not know presentation character budgets; those belong to final page
allocation after story planning.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from course_document import CourseBlock, CourseDocument, stable_hash


ArtifactKind = Literal[
    "code",
    "formula",
    "table",
    "diagram",
    "image",
    "data",
    "experiment",
    "source_excerpt",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CoursePresentationUnitV1(_StrictModel):
    teaching_unit_id: str
    section_id: str
    section_title: str = ""
    source_ordinal: int = Field(ge=0)
    primary_block_ids: list[str] = Field(min_length=1)
    primary_block_kinds: dict[str, str] = Field(default_factory=dict)
    primary_block_roles: dict[str, str] = Field(default_factory=dict)
    primary_block_titles: dict[str, str] = Field(default_factory=dict)
    primary_block_artifacts: dict[str, list[ArtifactKind]] = Field(default_factory=dict)
    primary_block_texts: dict[str, str] = Field(default_factory=dict)
    primary_block_presentation_texts: dict[str, str] = Field(default_factory=dict)
    primary_block_asset_refs: dict[str, list[str]] = Field(default_factory=dict)
    primary_block_evidence_refs: dict[str, list[str]] = Field(default_factory=dict)
    primary_block_evidence_summaries: dict[str, list[str]] = Field(default_factory=dict)
    supporting_block_ids: list[str] = Field(default_factory=list)
    teaching_intent: str
    artifact_kinds: list[ArtifactKind] = Field(default_factory=list)
    source_asset_refs: list[str] = Field(default_factory=list)
    teaching_plan_context: dict[str, Any] = Field(default_factory=dict)
    prerequisite_unit_ids: list[str] = Field(default_factory=list)
    dependent_unit_ids: list[str] = Field(default_factory=list)
    source_text: str
    presentation_text: str = ""


class CoursePresentationGraphV1(_StrictModel):
    schema_version: Literal["course_presentation_graph_v1"] = (
        "course_presentation_graph_v1"
    )
    course_id: str
    source_document_revision: str
    graph_digest: str
    units: list[CoursePresentationUnitV1] = Field(default_factory=list)
    formal_block_ids: list[str] = Field(default_factory=list)
    primary_block_coverage: float = Field(ge=0, le=1)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)


_ANCHOR_ROLES = {"orientation", "prerequisite", "objective", "concept"}
_ARTIFACT_KIND_BY_BLOCK_KIND: dict[str, ArtifactKind] = {
    "code": "code",
    "code_lab": "code",
    "formula": "formula",
    "table": "table",
    "diagram": "diagram",
    "graph_embed": "diagram",
    "image": "image",
    "source_excerpt": "source_excerpt",
}
_CODE_FENCE_RE = re.compile(r"```(?:[A-Za-z0-9_+.#-]+)?\s*\n.+?```", re.S)
_DISPLAY_FORMULA_RE = re.compile(r"\$\$.+?\$\$|\\\[.+?\\\]", re.S)
_INLINE_FORMULA_RE = re.compile(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$(?!\$)", re.S)
_MARKDOWN_TABLE_RE = re.compile(r"(?m)^\s*\|.+\|\s*\n\s*\|\s*:?-{3,}")
_TEACHER_CUE_RE = re.compile(
    r"【(?:板书[^】]*|提问[^】]*|等待回应|演示[^】]*|巡视(?:提示)?|投影|"
    r"典型错误反馈|反馈|收束|"
    r"分发练习单|播放[^】]*|画[^】]*|指令|计时|全链路验收补位[^】]*)】"
)
_INTERNAL_TEACHER_NOTE_RE = re.compile(
    r"(?:教师|老师)(?:展示|强调|说明|引导|巡视|记录|补充)[^。！？；;]*[。！？；;]?"
)
_PRESENTATION_SIGNAL_TERMS = (
    "定义", "定理", "规律", "公式", "结论", "条件", "边界", "原则", "步骤",
    "依据", "标准", "错误", "修正", "已知量", "未知量", "约束", "模型",
    "方向", "分量", "合力", "加速度", "质量", "实验", "观察", "证据",
    "要求", "任务", "完成", "判断", "计算", "核对", "检查", "阶段", "连续",
)
_ROLE_SIGNAL_TERMS: dict[str, tuple[str, ...]] = {
    "objective": ("目标", "任务", "能", "解决", "做到", "完成", "掌握"),
    "concept": ("定义", "规律", "模型", "公式", "条件", "边界", "属性", "方向"),
    "reasoning": ("实验", "观察", "说明", "支持", "证据", "关系", "误差"),
    "activity": ("要求", "任务", "完成", "填写", "画出", "列出", "判断", "计算"),
    "feedback": ("标准", "结论", "错误", "修正", "核对", "检查", "依据"),
    "application": ("情境", "已知", "未知", "约束", "计算", "判断", "结果"),
}
_LOW_VALUE_SPOKEN_LEAD_RE = re.compile(
    r"^(?:好[，,]?|同学们[，,]?|今天[，,]?|现在[，,]?|接下来[，,]?|首先[，,]?|其次[，,]?|"
    r"这节课(?:的)?[，,]?|本节课(?:的)?[，,]?|请(?:大家|同学|一位同学)?|"
    r"我们(?:刚才|现在|接下来|先|来|要)?|谁(?:来|能)?|想一想|"
    r"来看(?:一个|这)?|看(?:这个|这里)?|"
    r"拿出[^，,。；;]{0,28}[，,]|对照(?:标准)?答案[，,]?|"
    r"完成的同学(?:请)?|学生(?:分别|先|再)?|教师(?:先|再)?|"
    r"我把它写在黑板上[：:]?)"
)
_DELIVERY_ONLY_SEGMENT_RE = re.compile(
    r"^(?:展示(?:标准)?(?:答案|解答)|停笔|等待|巡视|我(?:把|只用|来)|"
    r"请(?:一位|两位|大家|同学)?(?:学生|同学)?(?:回答|举手|观察|看|记录)|"
    r"把它写在黑板上|板书|投影)(?:[^。！？；;]{0,80})[。！？；;]?$"
)
_LOW_INFORMATION_LABEL_RE = re.compile(r"^[^:：\n]{1,14}[:：]$")
_PRESENTATION_SECTION_LABEL_RE = re.compile(
    r"^(?:内容与方法|展开过程|任务与检验)\s*[:：]\s*"
)
_PRESENTATION_META_SEGMENT_RE = re.compile(
    r"^(?:本节任务|核心教学|学习者行动|检查与反馈|直觉入口|多重表征|"
    r"正式定义|证明与推导|数学论证|例题推演|策略选择|变式练习)"
    r"围绕.+(?:展开|核心机制展开)[。！？；;]?$|"
    r"^(?:结果需逐项核对条件、过程与结论|若出现错误，依据同一标准修正并再次验证|"
    r"形式化检查锦标|公式中的对象、条件和结论必须与当前知识范围一致)"
)
_PRESENTATION_DELIVERY_SEGMENT_RE = re.compile(
    r"^(?:口头陈述|听讲|抄录|抄写|跟随讲解过程|记录(?:定义|目标|对比表)|"
    r"请\s*\d*\s*名|请学习者|发放|巡视|逐题公布答案|在笔记本|"
    r"对答案|用红笔|观察讲解过程|回答讲解过程提问|"
    r"让学习者|要求学习者|学习者回答答案|系统讲解|选取\s*\d|"
    r"\d+\s*名学习者|"
    r"不要直接|在黑板)"
)
_PRESENTATION_DELIVERY_PREFIX_WITH_COLON_RE = re.compile(
    r"^(?:逐条讲解并板书性质|发放或板书练习题|在黑板完整推演\s*\d*\s*道例题|"
    r"请\s*\d*\s*名学习者[^:：]{0,80}(?:重点演示|重点指出)|"
    r"板书(?:二阶行列式定义|推导|证明)|投影并讲解)[：:]\s*"
)
_ROLE_PRESENTATION_BUDGET: dict[str, tuple[int, int]] = {
    "objective": (3, 120),
    "concept": (5, 280),
    "reasoning": (6, 320),
    "example": (7, 380),
    "application": (7, 380),
    "activity": (9, 420),
    "feedback": (9, 420),
    "misconception": (7, 360),
    "remediation": (7, 360),
    "summary": (6, 320),
    "transfer": (6, 320),
}


def block_source_text(block: CourseBlock) -> str:
    payload = block.payload or {}
    return str(
        payload.get("markdown")
        or payload.get("text")
        or payload.get("content")
        or payload.get("code")
        or payload.get("formula")
        or payload.get("table")
        or payload.get("summary")
        or ""
    ).strip()


def _split_presentation_clauses(line: str) -> list[str]:
    """Split prose without cutting matrices, tuples, or grouped formula text."""

    pairs = {"(": ")", "[": "]", "{": "}", "（": "）", "【": "】"}
    closers = set(pairs.values())
    stack: list[str] = []
    quote: str = ""
    clauses: list[str] = []
    start = 0
    for index, char in enumerate(line):
        if char in {"'", '"', "“", "”", "‘", "’"}:
            if quote:
                if char == quote or (quote == "“" and char == "”") or (
                    quote == "‘" and char == "’"
                ):
                    quote = ""
            elif char in {"'", '"', "“", "‘"}:
                quote = char
            continue
        if char in pairs:
            stack.append(pairs[char])
        elif char in closers and stack and char == stack[-1]:
            stack.pop()
        if char in "。！？；;" and not stack and not quote:
            candidate = line[start:index + 1].strip()
            if candidate:
                clauses.append(candidate)
            start = index + 1
    tail = line[start:].strip()
    if tail:
        clauses.append(tail)
    return clauses


def _presentation_segments(value: str) -> list[str]:
    """Return source-extractive classroom screen candidates in source order."""

    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"```(?:[A-Za-z0-9_+.#-]+)?\s*\n.*?```", "", text, flags=re.S)
    text = text.replace("【学生任务】", "任务：")
    text = _TEACHER_CUE_RE.sub("", text)
    text = _INTERNAL_TEACHER_NOTE_RE.sub("", text)
    text = re.sub(r"(?m)^\s*\*{2,}\s*", "", text)
    text = re.sub(r"(?m)^\s*(?:教师|老师)(?:用|通过)", "", text)
    text = re.sub(r"!\[([^]]*)]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", text)
    text = re.sub(r"(?<!\\)(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<!\\)(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    text = re.sub(r"(?m)^\s*#{1,6}\s+", "", text)

    segments: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or re.fullmatch(r"\|?[|:\-\s]+\|?", line):
            continue
        if line.startswith("|") and line.endswith("|"):
            continue
        line = re.sub(r"^\s*(?:[-+*]\s+|\d+[.)]\s+)", "", line).strip()
        if not line:
            continue
        for segment in _split_presentation_clauses(line):
            clean = segment.strip()
            clean = _PRESENTATION_SECTION_LABEL_RE.sub("", clean).strip()
            clean = _PRESENTATION_DELIVERY_PREFIX_WITH_COLON_RE.sub(
                "", clean
            ).strip()
            example_goal = re.match(
                r"^用.+?呈现(?:学习)?目标\s*[,\uff0c]\s*例如['‘“\"](.+?)['’”\"]\s*[.。]?$",
                clean,
            )
            if example_goal:
                clean = example_goal.group(1).strip()
            clean = re.sub(r"^重点突出\s*[:\uff1a]\s*", "", clean).strip()
            clean = re.sub(r"^(?:给出|提供|展示|选取)\s*", "", clean).strip()
            clean = re.sub(
                r"^在形式化定义之前\s*[,\uff0c]?\s*(?:先)?(?:建立)?\s*",
                "",
                clean,
            ).strip()
            clean = re.sub(
                r"^(?:板书并讲解|板书证明|板书推导|板书|投影并讲解)\s*",
                "",
                clean,
            ).strip()
            clean = clean.replace("板书：", "").replace("板书:", "").strip()
            clean = clean.lstrip("：: ")
            clean = re.sub(r"^\d+[.)]\s*", "", clean).strip()
            clean = re.sub(
                r"^明确本节(?:的)?学习(?:任务与检验标准|目标)，"
                r"让学习者知道",
                "",
                clean,
            ).strip()
            if "常见错误（如" in clean and (
                "请" in clean or "讲解过程" in clean
            ):
                clean = clean[clean.index("常见错误（如"):]
            if _DELIVERY_ONLY_SEGMENT_RE.match(clean):
                continue
            spoken_lead = _LOW_VALUE_SPOKEN_LEAD_RE.match(clean)
            while spoken_lead:
                remainder = clean[spoken_lead.end():].lstrip("，, ：:")
                if remainder:
                    clean = remainder
                    spoken_lead = _LOW_VALUE_SPOKEN_LEAD_RE.match(clean)
                else:
                    break
            if _DELIVERY_ONLY_SEGMENT_RE.match(clean):
                continue
            if clean and not _PRESENTATION_META_SEGMENT_RE.match(clean):
                segments.append(clean)
    return segments


def block_presentation_text(block: CourseBlock) -> str:
    """Project a teacher script block onto what learners should see on screen.

    The complete script remains unchanged in speaker notes.  This projection is
    deliberately extractive: it removes delivery cues and selects only source
    clauses that function as definitions, formulas, steps, tasks, evidence, or
    conclusions.  It never paraphrases or invents teaching content.
    """

    source = block_source_text(block)
    payload = block.payload or {}
    if payload.get("_v6_artifact_only"):
        return ""
    explicit = str(payload.get("slide_visible_text") or "").strip()
    if explicit:
        return explicit
    if not source or not (
        payload.get("module_id")
        or payload.get("module_instance_id")
        or payload.get("teacher_script_block")
    ):
        return source

    candidates = [
        segment
        for segment in _presentation_segments(source)
        if not _LOW_INFORMATION_LABEL_RE.fullmatch(segment)
        and not _PRESENTATION_DELIVERY_SEGMENT_RE.match(segment)
    ]
    if not candidates:
        return source
    role_terms = _ROLE_SIGNAL_TERMS.get(str(block.role or ""), ())
    scored: list[tuple[int, int, str]] = []
    for index, segment in enumerate(candidates):
        score = 0
        if any(term in segment for term in _PRESENTATION_SIGNAL_TERMS):
            score += 3
        if any(term in segment for term in role_terms):
            score += 4
        if _INLINE_FORMULA_RE.search(segment) or _DISPLAY_FORMULA_RE.search(segment):
            score += 4
        if re.search(r"(?:^|[^A-Za-z])\d+(?:\.\d+)?(?:\s|$|[^A-Za-z])", segment):
            score += 1
        if "：" in segment or ":" in segment:
            score += 1
        if segment.endswith(("？", "?")):
            score -= 2
        if _LOW_VALUE_SPOKEN_LEAD_RE.match(segment) and not any(
            term in segment for term in role_terms
        ):
            score -= 3
        if "等待" in segment or "巡视" in segment or "举手" in segment:
            score -= 4
        if _PRESENTATION_DELIVERY_SEGMENT_RE.match(segment):
            score -= 6
        if "讲解过程" in segment or "学习者知道" in segment:
            score -= 3
        if block.role == "objective":
            if any(
                term in segment
                for term in ("学完", "能够", "能做到", "学习目标", "下课前")
            ):
                score += 5
            if any(term in segment for term in ("请带着", "开始", "举手回答")):
                score -= 4
            if segment.startswith("这些就是"):
                score -= 5
        if block.role in {"activity", "feedback"} and re.match(
            r"^(?:【?[第任情]一二三四五六七八九十\d]+|[①-⑳])",
            segment,
        ):
            score += 4
        scored.append((score, index, segment))

    max_segments, max_chars = _ROLE_PRESENTATION_BUDGET.get(
        str(block.role or ""),
        (5, 280),
    )
    if _MARKDOWN_TABLE_RE.search(source):
        max_segments = min(max_segments, 6)
        max_chars = min(
            max_chars,
            220 if block.role == "activity" else 140,
        )
    preferred = sorted(
        (item for item in scored if item[0] > 0),
        key=lambda item: (-item[0], item[1]),
    )[:max_segments]
    if not preferred:
        preferred = [max(scored, key=lambda item: (item[0], -item[1]))]
    selected = sorted(preferred, key=lambda item: item[1])
    accepted: list[str] = []
    for _score, _index, segment in selected:
        candidate = "\n".join([*accepted, segment])
        if accepted and len(candidate) > max_chars:
            continue
        if not accepted and len(segment) > max_chars:
            # Preserve a complete source clause.  Long delivery prose is less
            # harmful in notes than a generated truncation marker on canvas.
            continue
        accepted.append(segment)
    if not accepted:
        accepted.append(max(scored, key=lambda item: (item[0], -item[1]))[2])
    return "\n".join(dict.fromkeys(accepted)).strip()


def _artifact_kinds(block: CourseBlock) -> list[ArtifactKind]:
    kinds: list[ArtifactKind] = []
    explicit = _ARTIFACT_KIND_BY_BLOCK_KIND.get(block.kind)
    text = block_source_text(block)
    if explicit and (explicit not in {"code", "formula", "table"} or text):
        kinds.append(explicit)
    # Structured course blocks can still carry canonical Markdown artifacts.
    # Detect the source expression itself instead of assuming only rich-text
    # blocks can contain code, formulae, or tables.
    if _CODE_FENCE_RE.search(text):
        kinds.append("code")
    if _DISPLAY_FORMULA_RE.search(text):
        kinds.append("formula")
    has_markdown_table = bool(_MARKDOWN_TABLE_RE.search(text))
    inline_formulae = _INLINE_FORMULA_RE.findall(text)
    if (
        (
            (block.payload or {}).get("module_id")
            or (block.payload or {}).get("module_instance_id")
        )
        and len(inline_formulae) >= 2
        and any("=" in formula for formula in inline_formulae)
        and not has_markdown_table
        and block.role in {"concept", "reasoning", "application", "example"}
    ):
        kinds.append("formula")
    if has_markdown_table:
        kinds.append("table")
    payload_kind = str((block.payload or {}).get("artifact_kind") or "").strip()
    if payload_kind in ArtifactKind.__args__:  # type: ignore[attr-defined]
        kinds.append(payload_kind)  # type: ignore[arg-type]
    for payload_item in (
        (block.payload or {}).get("artifact_kinds")
        or (block.payload or {}).get("_v6_artifact_kinds")
        or []
    ):
        normalized = str(payload_item or "").strip()
        if normalized in ArtifactKind.__args__:  # type: ignore[attr-defined]
            kinds.append(normalized)  # type: ignore[arg-type]
    return list(dict.fromkeys(kinds))


def block_artifact_kinds(block: CourseBlock) -> list[ArtifactKind]:
    """Return source-backed characteristic artifacts for one canonical block."""

    return _artifact_kinds(block)


def teaching_intent_for_roles(
    roles: list[str],
    artifacts: set[str] | None = None,
) -> str:
    artifacts = artifacts or set()
    if any(role == "objective" for role in roles) and not artifacts:
        return "orientation"
    if artifacts:
        return "artifact_explanation"
    if any(role in {"activity", "checkpoint", "feedback"} for role in roles):
        return "practice_feedback"
    if any(role in {"misconception", "remediation", "counterexample"} for role in roles):
        return "misconception_repair"
    if any(role in {"reasoning"} for role in roles):
        return "mechanism"
    if any(role in {"example", "application", "transfer"} for role in roles):
        return "worked_example"
    if any(role == "summary" for role in roles):
        return "recap"
    return "concept_explanation"


def _teaching_intent(blocks: list[CourseBlock]) -> str:
    return teaching_intent_for_roles(
        [block.role for block in blocks],
        {kind for block in blocks for kind in _artifact_kinds(block)},
    )


def page_teaching_intent(
    unit: CoursePresentationUnitV1,
    source_block_ids: list[str],
) -> str:
    roles = [
        unit.primary_block_roles.get(block_id, "")
        for block_id in source_block_ids
        if unit.primary_block_roles.get(block_id, "")
    ]
    artifacts = {
        artifact
        for block_id in source_block_ids
        for artifact in unit.primary_block_artifacts.get(block_id, [])
    }
    if not roles and not artifacts:
        return unit.teaching_intent
    return teaching_intent_for_roles(roles, artifacts)


def page_artifact_kinds(
    unit: CoursePresentationUnitV1,
    source_block_ids: list[str],
) -> set[str]:
    return {
        artifact
        for block_id in source_block_ids
        for artifact in unit.primary_block_artifacts.get(block_id, [])
    }


def _ordered_formal_blocks(document: CourseDocument) -> list[CourseBlock]:
    section_order = {
        section.section_id: (section.position, section.level, index)
        for index, section in enumerate(document.sections)
    }
    unknown_base = len(section_order)
    return sorted(
        (block for block in document.blocks if block.status == "final"),
        key=lambda block: (
            section_order.get(block.section_id, (unknown_base, 99, unknown_base)),
            block.position,
            block.block_id,
        ),
    )


def _teaching_plan_context_by_section(
    teaching_plan: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for section in (teaching_plan or {}).get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = str(
            section.get("node_id")
            or section.get("section_id")
            or ""
        ).strip()
        if not section_id:
            continue
        modules = [
            item for item in section.get("teaching_modules") or []
            if isinstance(item, dict)
        ]
        result[section_id] = {
            "key_points": list(dict.fromkeys(
                str(item).strip()
                for item in section.get("key_points") or []
                if str(item).strip()
            )),
            "module_ids": list(dict.fromkeys(
                str(module.get("module_id") or "").strip()
                for module in modules
                if str(module.get("module_id") or "").strip()
            )),
            "teaching_purposes": list(dict.fromkeys(
                str(module.get("teaching_purpose") or "").strip()
                for module in modules
                if str(module.get("teaching_purpose") or "").strip()
            )),
            "knowledge_names": list(dict.fromkeys(
                str(name).strip()
                for module in modules
                for name in module.get("knowledge_names") or []
                if str(name).strip()
            )),
        }
    return result


def _partition_section(blocks: list[CourseBlock]) -> list[list[CourseBlock]]:
    groups: list[list[CourseBlock]] = []
    current: list[CourseBlock] = []
    current_group_id: str | None = None
    for block in blocks:
        starts_new_anchor = (
            bool(current)
            and block.role in _ANCHOR_ROLES
            and any(item.role in _ANCHOR_ROLES for item in current)
            and not (
                block.parent_group_id
                and current_group_id
                and block.parent_group_id == current_group_id
            )
        )
        if starts_new_anchor:
            groups.append(current)
            current = []
            current_group_id = None
        current.append(block)
        current_group_id = current_group_id or block.parent_group_id
    if current:
        groups.append(current)
    return groups


def compile_course_presentation_graph(
    document: CourseDocument,
    *,
    teaching_plan: dict[str, Any] | None = None,
    evidence_catalog: list[dict[str, Any]] | None = None,
) -> CoursePresentationGraphV1:
    """Compile complete source-ordered teaching units without text pagination."""

    ordered = _ordered_formal_blocks(document)
    by_section: dict[str, list[CourseBlock]] = defaultdict(list)
    section_sequence: list[str] = []
    for block in ordered:
        if block.section_id not in by_section:
            section_sequence.append(block.section_id)
        by_section[block.section_id].append(block)

    units: list[CoursePresentationUnitV1] = []
    plan_contexts = _teaching_plan_context_by_section(teaching_plan)
    section_titles = {
        section.section_id: section.title
        for section in document.sections
    }
    evidence_by_id = {
        str(item.get("evidence_id") or item.get("unit_id") or ""): item
        for item in (evidence_catalog or [])
        if isinstance(item, dict)
        and str(item.get("evidence_id") or item.get("unit_id") or "")
    }
    previous_unit_id = ""
    for section_id in section_sequence:
        for blocks in _partition_section(by_section[section_id]):
            ordinal = len(units)
            block_ids = [block.block_id for block in blocks]
            unit_id = stable_hash(
                {
                    "revision": document.document_revision,
                    "section_id": section_id,
                    "block_ids": block_ids,
                    "ordinal": ordinal,
                },
                prefix="cpu_",
            )
            unit = CoursePresentationUnitV1(
                teaching_unit_id=unit_id,
                section_id=section_id,
                section_title=str(section_titles.get(section_id) or "").strip(),
                source_ordinal=ordinal,
                primary_block_ids=block_ids,
                primary_block_kinds={
                    block.block_id: block.kind for block in blocks
                },
                primary_block_roles={
                    block.block_id: block.role for block in blocks
                },
                primary_block_titles={
                    block.block_id: str(
                        block.payload.get("title") or ""
                    ).strip()
                    for block in blocks
                },
                primary_block_artifacts={
                    block.block_id: _artifact_kinds(block) for block in blocks
                },
                primary_block_texts={
                    block.block_id: block_source_text(block) for block in blocks
                },
                primary_block_presentation_texts={
                    block.block_id: block_presentation_text(block)
                    for block in blocks
                },
                primary_block_asset_refs={
                    block.block_id: list(block.asset_refs) for block in blocks
                },
                primary_block_evidence_refs={
                    block.block_id: list(block.evidence_refs) for block in blocks
                },
                primary_block_evidence_summaries={
                    block.block_id: [
                        str(
                            evidence_by_id[evidence_id].get("summary")
                            or evidence_by_id[evidence_id].get("source_text")
                            or evidence_by_id[evidence_id].get("text")
                            or evidence_by_id[evidence_id].get("content")
                            or ""
                        )[:600]
                        for evidence_id in block.evidence_refs
                        if evidence_id in evidence_by_id
                        and str(
                            evidence_by_id[evidence_id].get("summary")
                            or evidence_by_id[evidence_id].get("source_text")
                            or evidence_by_id[evidence_id].get("text")
                            or evidence_by_id[evidence_id].get("content")
                            or ""
                        ).strip()
                    ]
                    for block in blocks
                },
                teaching_intent=_teaching_intent(blocks),
                artifact_kinds=list(
                    dict.fromkeys(
                        kind for block in blocks for kind in _artifact_kinds(block)
                    )
                ),
                source_asset_refs=list(
                    dict.fromkeys(
                        asset_ref
                        for block in blocks
                        for asset_ref in block.asset_refs
                        if asset_ref
                    )
                ),
                teaching_plan_context=dict(plan_contexts.get(section_id) or {}),
                prerequisite_unit_ids=[previous_unit_id] if previous_unit_id else [],
                source_text="\n\n".join(
                    text for block in blocks if (text := block_source_text(block))
                ),
                presentation_text="\n\n".join(
                    text
                    for block in blocks
                    if (text := block_presentation_text(block))
                ),
            )
            if units:
                units[-1].dependent_unit_ids.append(unit_id)
            units.append(unit)
            previous_unit_id = unit_id

    formal_ids = [block.block_id for block in ordered]
    owned_ids = [block_id for unit in units for block_id in unit.primary_block_ids]
    unique_owned = set(owned_ids)
    diagnostics: list[dict[str, Any]] = []
    if len(owned_ids) != len(unique_owned):
        diagnostics.append({"code": "duplicate_primary_block_owner"})
    missing = [block_id for block_id in formal_ids if block_id not in unique_owned]
    if missing:
        diagnostics.append({"code": "formal_blocks_missing", "block_ids": missing})
    coverage = 1.0 if not formal_ids else len(unique_owned.intersection(formal_ids)) / len(formal_ids)
    graph_payload = {
        "course_id": document.course_id,
        "revision": document.document_revision,
        "teaching_plan": teaching_plan or {},
        "units": [unit.model_dump(mode="json") for unit in units],
    }
    return CoursePresentationGraphV1(
        course_id=document.course_id,
        source_document_revision=document.document_revision,
        graph_digest=stable_hash(graph_payload, prefix="cpgraph_"),
        units=units,
        formal_block_ids=formal_ids,
        primary_block_coverage=coverage,
        diagnostics=diagnostics,
    )


__all__ = [
    "ArtifactKind",
    "CoursePresentationGraphV1",
    "CoursePresentationUnitV1",
    "block_artifact_kinds",
    "block_presentation_text",
    "block_source_text",
    "compile_course_presentation_graph",
    "page_artifact_kinds",
    "page_teaching_intent",
    "teaching_intent_for_roles",
]
