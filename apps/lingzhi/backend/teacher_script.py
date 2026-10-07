"""师生共用的课程讲义结构真源与确定性质量门。

讲义依据当前教案、学科与学习目标自由编排有类型的内容块；常用类型提供写作参考，
自定义类型使用相同的存储与显示结构。整讲一次生成，覆盖知识解释、推导、例题、
练习与参考反馈，不要求内容块与教案环节一一对应。沿用 script 的数据身份和存储接口，不要求课堂话术或模拟师生回应。
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

from course_pedagogy import MODULES, module_block_role
from teacher_visible_language import has_unnatural_system_language


SCRIPT_SCHEMA_VERSION = "teacher_script_v2"
# Historical revisions retain their format identity; generation tasks use a separate contract.
SCRIPT_PIPELINE_VERSION = "direct_teaching_script_v8"
SCRIPT_QUALITY_VERSION = "teacher_script_quality_v13"

HANDOUT_CONTRACT_VERSION = "handout_lecture_v3"

# Writing guidance, not a closed vocabulary or a mandatory lesson sequence.
HANDOUT_CONTENT_TYPES = {
    "introduction": ("引入", "orientation"),
    "definition": ("定义", "concept"),
    "explanation": ("解释", "concept"),
    "comparison": ("对比", "reasoning"),
    "derivation": ("推导", "reasoning"),
    "example": ("例题", "example"),
    "exercise": ("练习", "activity"),
    "answer": ("解答", "feedback"),
    "misconception": ("辨析", "misconception"),
    "summary": ("总结", "summary"),
}


def handout_visible_draft(text: str) -> str:
    """Hide protocol metadata while retaining prose and literal code samples."""
    lines, fence = [], ""
    for line in text.splitlines(keepends=True):
        if not fence and re.match(r"^\s*<!--\s*(?:section|handout|block):", line):
            continue
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        if match:
            token, tail = match.groups()
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not tail.strip():
                fence = ""
        lines.append(line)
    return "".join(lines).strip()


def parse_handout_blocks(content: str, section_id: str, *, identity: str = "",
                         complete: bool = False) -> dict[str, Any]:
    """Parse open-vocabulary blocks locally, including a safe partial preview.

    A marker starts a block; the next marker or enclosing section ends it.
    IDs are scoped to a generation attempt, never reused by ordinal position
    across regenerated revisions. Literal markers in code are ordinary text.
    """
    blocks: list[dict[str, Any]] = []
    body: list[str] = []
    meta: dict[str, Any] | None = None
    fence = ""
    error = ""
    unassigned = ""
    keys: set[str] = set()

    def finish(closed: bool) -> None:
        nonlocal error
        text = "".join(body).strip()
        if meta is None:
            if text:
                error = "block_marker_missing"
            return
        if closed and not handout_structure_closed(text):
            error = "block_incomplete"
        first, _, rest = text.partition("\n")
        if re.fullmatch(r"#{1,6}\s+" + re.escape(meta["title"]), first):
            text = rest.strip()  # A repeated block title is a display duplicate.
            if closed and not text:
                error = "block_incomplete"
        kind = meta["type"]
        kind = next((key for key, (label, _) in HANDOUT_CONTENT_TYPES.items() if label == kind), kind)
        label, role = HANDOUT_CONTENT_TYPES.get(kind, (kind, "concept"))
        key = meta.get("key") or str(len(blocks) + 1)
        if key in keys:
            error = "block_key_duplicate"
        keys.add(key)
        blocks.append({
            "block_id": _stable_block_id(section_id, f"{identity}:{key}", 0),
            "module_id": "handout_content", "role": role,
            "content_type": kind, "type_label": label,
            "title": meta["title"], "content": text,
            "knowledge_names": list(meta.get("knowledge") or []),
            "answer_to": meta.get("answer_to") or "",
            "local_key": key, "generation_source": "model",
        })

    source_lines = content.splitlines(keepends=True)
    for line_index, line in enumerate(source_lines):
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        if match:
            token, tail = match.groups()
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not tail.strip():
                fence = ""
            body.append(line)
            continue
        stripped = line.strip()
        if not fence and stripped.startswith("<!-- block:"):
            # An unfinished metadata line is not rendered as prose.
            if not stripped.endswith("-->"):
                if complete:
                    error = "block_marker_incomplete"
                unassigned = handout_visible_draft("".join(source_lines[line_index + 1:]))
                break
            finish(True)
            if error:
                unassigned = handout_visible_draft("".join(source_lines[line_index:]))
                break
            try:
                value = json.loads(stripped[len("<!-- block:"):-3])
                if not isinstance(value, dict):
                    raise ValueError
                for key, limit in (("type", 40), ("title", 160)):
                    if not isinstance(value.get(key), str) or not value[key].strip() or len(value[key]) > limit or re.search(r"[\r\n<>]", value[key]):
                        raise ValueError
                    value[key] = value[key].strip()
                for key in ("key", "answer_to"):
                    if key in value and (not isinstance(value[key], str) or not re.fullmatch(r"[\w.-]{1,64}", value[key])):
                        raise ValueError
                knowledge = value.get("knowledge", [])
                if isinstance(knowledge, str):
                    knowledge = [knowledge] if knowledge.strip() else []
                    value["knowledge"] = knowledge
                if not isinstance(knowledge, list) or any(not isinstance(name, str) for name in knowledge):
                    raise ValueError
                meta, body = value, []
            except (ValueError, TypeError):
                error = "block_metadata_invalid"
                unassigned = handout_visible_draft("".join(source_lines[line_index + 1:]))
                break
        else:
            # Suppress a split marker prefix while tokens are still arriving.
            if not complete and not fence and "<!-- block:".startswith(stripped) and stripped:
                continue
            body.append(line)
    if not error:
        finish(complete)
    by_key = {block["local_key"]: block for block in blocks}
    for block in blocks:
        target = block["answer_to"]
        if target:
            referenced = by_key.get(target)
            if complete and (not referenced or referenced is block):
                error = "block_answer_reference_invalid"
            block["answer_to"] = referenced["block_id"] if referenced else ""
        block.pop("local_key")
    if error and not blocks:
        unassigned = handout_visible_draft(content)
    return {"blocks": blocks, "error": error, "unassigned_fragment": unassigned,
            "content": teacher_script_blocks_to_markdown(blocks)}


def handout_section_contract(outline: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Keep source scope, but let the model compose its own content blocks."""
    contract = compile_teacher_script_module_contract(outline, plan)
    modules = contract.get("modules") or []
    section_id = str(outline.get("node_id") or "")
    contract["modules"] = [{
        "block_id": _stable_block_id(section_id, "handout_prose", 1),
        "module_id": "handout_prose", "role": "concept",
        "title": str(outline.get("node_name") or plan.get("title") or section_id),
        "required": True,
        "knowledge_names": list(dict.fromkeys(name for m in modules for name in m.get("knowledge_names") or [])),
        "source_plan_context": {"teaching_modules": deepcopy(plan.get("teaching_modules") or [])},
    }]
    contract["flexible_blocks"] = True
    return contract


def script_contract_for_revision(outline: dict[str, Any], plan: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    """Keep historical block identities; new prose revisions use the lecture contract."""
    blocks = existing.get("blocks") or []
    if blocks and any(b.get("module_id") == "handout_content" for b in blocks):
        contract = handout_section_contract(outline, plan)
        contract["modules"] = deepcopy(blocks)
        contract["flexible_blocks"] = False  # Editing preserves the chosen block identities.
        return contract
    if not blocks or all(b.get("module_id") == "handout_prose" for b in blocks):
        contract = handout_section_contract(outline, plan)
        contract["flexible_blocks"] = False
        return contract
    return compile_teacher_script_module_contract(outline, plan)


def handout_structure_closed(content: str) -> bool:
    """Only syntax completeness; never a content/teaching quality gate."""
    fence = ""
    plain = []
    for line in content.splitlines():
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if match:
            token, tail = match.groups()
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not tail.strip():
                fence = ""
            continue
        if not fence:
            plain.append(line)
    text = "\n".join(plain)
    stack = []
    for token in re.findall(r"\\[\[\]()]", text):
        if token in (r"\[", r"\("):
            stack.append(token)
        elif not stack or stack.pop() != (r"\[" if token == r"\]" else r"\("):
            return False
    return bool(content.strip()) and not fence and not stack and text.count("$$") % 2 == 0


def parse_handout_stream(text: str, section_ids: list[str], *, provider_complete: bool = False) -> dict[str, Any]:
    """Parse checkpoints without trusting a model's end marker as provider EOF.

    A previous section is complete only at the next valid section boundary.
    The final one needs normal provider completion and all requested sections.
    An optional end marker never substitutes for either requirement.
    Markers inside fenced code remain literal content.
    """
    completed: dict[str, str] = {}
    fragments: dict[str, str] = {}
    current = ""
    body: list[str] = []
    fence = ""
    index = 0
    ended = False
    error = ""
    if not section_ids or any(not key or re.search(r"[\s<>]", key) for key in section_ids) or len(section_ids) != len(set(section_ids)):
        return {"completed": {}, "fragments": {}, "ended": False, "error": "invalid_section_ids"}
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if ended and stripped:
            error = "trailing_content"
            break
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        if match:
            token, tail = match.groups()
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not tail.strip():
                fence = ""
            body.append(line)
            continue
        marker = re.fullmatch(r"<!-- section:([^<>]+) -->", stripped) if not fence else None
        if marker:
            key = marker.group(1).strip()
            if ended or index >= len(section_ids) or key != section_ids[index]:
                error = "section_order_or_identity"
                break
            if current:
                content = "".join(body).strip()
                if not handout_structure_closed(content):
                    error = "section_incomplete"
                    break
                completed[current] = content
            elif "".join(body).strip():
                error = "unexpected_preamble"
                break
            current, body = key, []
            index += 1
        elif not fence and stripped == "<!-- handout:end -->":
            if ended or not current or index != len(section_ids):
                error = "unexpected_end"
                break
            ended = True
        elif ended and stripped:
            error = "trailing_content"
            break
        elif not ended:
            body.append(line)
    if current:
        fragments[current] = "".join(body).strip()
    if provider_complete and not error and current and index == len(section_ids):
        if handout_structure_closed("".join(body)):
            completed[current] = "".join(body).strip()
        else:
            error = "section_incomplete"
    if provider_complete and index != len(section_ids) and not error:
        error = "missing_sections"
    unassigned = handout_visible_draft(text) if not current else ""
    return {"completed": completed, "fragments": fragments, "ended": ended, "error": error, "unassigned_fragment": unassigned}

_ALLOWED_ROLES = {
    "orientation",
    "prerequisite",
    "objective",
    "concept",
    "reasoning",
    "example",
    "counterexample",
    "application",
    "activity",
    "feedback",
    "misconception",
    "checkpoint",
    "remediation",
    "summary",
    "transfer",
}
_HEADING_PATTERN = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_DELIVERY_CUE_PATTERN = re.compile(
    r"【(?:提问|板书|演示|投影|等待(?:回应)?|巡视|计时|教师活动|学生活动|课堂提示)】"
)
_LESSON_PLAN_VOICE_PATTERN = re.compile(
    r"教师(?:应|需要|可以|负责|讲解|演示|提问|引导|巡视)|"
    r"学生(?:应|需要|负责|完成|讨论|回答|操作|提交)"
)
_DIRECT_TEACHING_PATTERN = re.compile(
    r"我们|大家|同学|你们|请|先看|来看|想一想|试一试|注意|"
    r"接下来|回到|到这里|现在|下面|不妨|可以发现|再看"
)
_INTERNAL_PROCESS_PATTERN = re.compile(
    r"全链路验收|不冒充模型生成|模型生成|内部提示词|"
    r"字数\s*[:：]|补位|重试修复|质量门"
)
_INCOMPLETE_END_PATTERN = re.compile(
    r"(?:因为|所以|因此|并且|以及|那么|例如|包括|从而|"
    r"如果|当|而|或|与|和|的|为|是|在|对|[，、：（(])$"
)
_PLACEHOLDER_PATTERN = re.compile(
    r"本块内容完整|本块用于形成一个完整|已确认的当前知识范围|"
    r"当前教学环节围绕|形式化检查锦标|"
    r"(?:^|[。；\n])(?:内容与方法|展开过程|任务与检验)："
)
_CANNED_DISCOURSE_PATTERN = re.compile(
    r"首先|其次|再次|最后|综上所述|值得注意的是|需要指出的是|"
    r"不难发现|由此可见|显而易见|让我们一起来"
)
_ACTIVITY_TASK_PATTERN = re.compile(r"任务|问题|题目|已知|条件|要求|情境")
_ACTIVITY_RESULT_PATTERN = re.compile(r"输出|结果|答案|解法|标准|步骤|验收|判定")
_FEEDBACK_ERROR_PATTERN = re.compile(r"错误|误区|偏差|遗漏|混淆|不成立")
_FEEDBACK_REPAIR_PATTERN = re.compile(r"标准|核对|检查|修正|原因|再次验证|验收")
_DISPLAY_MATH_ENVIRONMENT_PATTERN = re.compile(
    r"\\begin\{(?:bmatrix|pmatrix|vmatrix|Bmatrix|Vmatrix|matrix|array|"
    r"aligned|split|cases|equation|gather|align)\}"
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.splitlines() if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _stable_block_id(section_id: str, module_id: str, index: int) -> str:
    digest = hashlib.sha256(
        f"{section_id}:{module_id}:{index}".encode("utf-8")
    ).hexdigest()[:12]
    return f"tsb-{digest}"


def _markdown_math_delimiter_state(content: str) -> dict[str, Any]:
    """Inspect math delimiters without counting dollars inside ``$$`` twice.

    The previous quality gate counted every dollar in ``$$`` as an inline
    delimiter too.  A valid display formula could therefore be reported as
    broken, and a single truncated delimiter caused the whole durable script
    job to stop at block one.  Fenced code is excluded because shell examples
    and programming strings may legitimately contain dollar signs.
    """
    segments = re.split(r"(```[\s\S]*?```)", str(content or ""))
    text = "\n".join(
        segment for index, segment in enumerate(segments) if index % 2 == 0
    )
    display_open = False
    inline_open = False
    inline_cross_line = False
    latex_stack: list[str] = []
    unexpected: list[str] = []
    index = 0
    while index < len(text):
        if text[index] == "\\" and index + 1 < len(text):
            token = text[index:index + 2]
            if token in {r"\(", r"\["}:
                latex_stack.append(token)
                index += 2
                continue
            if token in {r"\)", r"\]"}:
                expected = r"\(" if token == r"\)" else r"\["
                if latex_stack and latex_stack[-1] == expected:
                    latex_stack.pop()
                else:
                    unexpected.append(token)
                index += 2
                continue
            index += 2
            continue
        if text.startswith("$$", index):
            display_open = not display_open
            index += 2
            continue
        if text[index] == "\n" and inline_open and not display_open:
            # Inline dollar math cannot cross Markdown block boundaries.  The
            # old even-count gate accepted `$x` on one line and `y$` several
            # lines later, which rendered the literal delimiters seen in the
            # failed PPT manuscript.
            inline_cross_line = True
            inline_open = False
            index += 1
            continue
        if text[index] == "$" and not display_open:
            inline_open = not inline_open
        index += 1
    return {
        "display_open": display_open,
        "inline_open": inline_open,
        "inline_cross_line": inline_cross_line,
        "latex_stack": latex_stack,
        "unexpected": unexpected,
    }


def _has_unwrapped_display_math_environment(content: str) -> bool:
    """Reject legacy split formula shells before they become durable script.

    Counting ``$$`` pairs cannot see a shape such as ``$$\\left[$$`` followed
    by a bare ``\\begin{array}`` environment and a separate ``$$\\right]$$``.
    The learner renderer can repair some of those shapes, but PPT formula
    extraction cannot safely recover the omitted environment after the script
    becomes the current revision. New model output is normalized before this predicate
    runs; this guard primarily invalidates old checkpoints so the model block
    pipeline regenerates them through the same quality gate.
    """

    in_code_fence = False
    in_display_math = False
    for line in str(content or "").splitlines():
        if re.match(r"^\s*```", line):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        for token in re.finditer(
            rf"(?<!\\)\$\$|{_DISPLAY_MATH_ENVIRONMENT_PATTERN.pattern}",
            line,
        ):
            if token.group(0) == "$$":
                in_display_math = not in_display_math
            elif not in_display_math:
                return True
    return False


def _display_math_contains_teaching_prose(content: str) -> bool:
    """Detect a balanced fence that accidentally swallows following prose."""

    for match in re.finditer(r"\$\$([\s\S]*?)\$\$", str(content or "")):
        body = match.group(1)
        cjk_count = len(re.findall(r"[\u3400-\u9fff]", body))
        teaching_label = re.search(
            r"任务条件|输出要求|参考解法|验收标准|核对标准|典型错误|修正原因",
            body,
        )
        sentence_marks = len(re.findall(r"[。！？；]", body))
        if cjk_count >= 40 and sentence_marks >= 2:
            return True
        if teaching_label and cjk_count >= 12:
            return True
    return False


def repair_teacher_script_display_math_prose(
    content: str,
) -> tuple[str, list[str]]:
    """Move accidentally swallowed teaching prose outside a display fence.

    This is a delimiter-boundary repair only: it neither rewrites the formula
    nor invents instructional content.  The two safe shapes are (a) a display
    block containing only prose, whose redundant fences are removed, and (b)
    a valid formula prefix followed by an explicit teaching label, where the
    closing fence is moved immediately before that label.
    """

    repairs: list[str] = []

    def repair_segment(segment: str) -> str:
        def replace(match: re.Match[str]) -> str:
            body = match.group(1)
            wrapped = f"$${body}$$"
            if not _display_math_contains_teaching_prose(wrapped):
                return match.group(0)
            label = re.search(
                r"(?m)^\s*(?:任务条件|输出要求|参考解法|验收标准|核对标准|"
                r"典型错误|修正原因)\s*[:：]",
                body,
            )
            if label:
                prefix = body[:label.start()].strip()
                suffix = body[label.start():].strip()
                repairs.append("normalize:display-math-prose-boundary")
                if prefix and re.search(r"\\begin\{|\\[A-Za-z]+|[=<>]", prefix):
                    return f"$$\n{prefix}\n$$\n\n{suffix}"
                return "\n\n".join(item for item in (prefix, suffix) if item)

            # A balanced pair containing no display environment or relation is
            # a stray prose shell (often one extra ``$$`` after a matrix).
            if not re.search(r"\\begin\{|\\[A-Za-z]+|[=<>]", body):
                repairs.append("normalize:display-math-prose-boundary")
                return body.strip()
            return match.group(0)

        return re.sub(r"\$\$([\s\S]*?)\$\$", replace, segment)

    segments = re.split(r"(```[\s\S]*?```)", str(content or ""))
    repaired = "".join(
        segment if index % 2 else repair_segment(segment)
        for index, segment in enumerate(segments)
    )
    return repaired.strip(), list(dict.fromkeys(repairs))


def repair_teacher_script_math_delimiters(content: str) -> tuple[str, list[str]]:
    """Close only unambiguous trailing math delimiters from a model response."""
    raw_value = str(content or "")
    repaired_lines: list[str] = []
    repairs: list[str] = []
    in_fence = False
    display_open = False
    for raw_line in raw_value.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        ending = raw_line[len(line):]
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            repaired_lines.append(raw_line)
            continue
        if in_fence:
            repaired_lines.append(raw_line)
            continue
        scan = re.sub(r"\\\$", "", line)
        display_count = scan.count("$$")
        single_scan = scan.replace("$$", "")
        single_count = single_scan.count("$") if not display_open else 0
        if not display_open and single_count % 2:
            stripped = line.strip()
            if stripped.endswith("$") and not stripped.startswith("$"):
                indentation = line[:len(line) - len(line.lstrip())]
                line = f"{indentation}${line[len(indentation):]}"
                repairs.append("open:$:line")
            else:
                line = f"{line}$"
                repairs.append("close:$:line")
        if display_count % 2:
            display_open = not display_open
        repaired_lines.append(f"{line}{ending}")

    value = "".join(repaired_lines).rstrip()
    state = _markdown_math_delimiter_state(value)
    if state["unexpected"]:
        return value, []
    suffix = ""
    for token in reversed(state["latex_stack"]):
        closer = r"\)" if token == r"\(" else r"\]"
        suffix += closer
        repairs.append(f"close:{closer}")
    if state["inline_open"]:
        suffix += "$"
        repairs.append("close:$")
    if state["display_open"]:
        suffix += "\n$$"
        repairs.append("close:$$")
    return value + suffix, repairs


def teacher_script_artifact_contract(
    module_id: str,
    role: str,
) -> dict[str, Any]:
    """Translate the shared pedagogy module into a teacher-script artifact rule.

    This deliberately derives from ``MODULES`` instead of adding a second
    discipline registry.  The lesson plan decides the module; the script stage
    only makes its concrete classroom artifact and integrity checks explicit.
    """
    module = _text(module_id)
    discipline = (
        "math" if module.startswith("math_")
        else "engineering" if module.startswith("engineering_")
        else "science" if module.startswith("science_")
        else "life" if module.startswith("life_")
        else "humanities" if module.startswith("humanities_")
        else "language" if module.startswith("language_")
        else "business" if module.startswith("business_")
        else "general"
    )
    hard_artifact = ""
    if module == "engineering_minimal_run":
        hard_artifact = "fenced_code"
    elif module in {"math_formalization", "math_worked_example", "math_proof"}:
        hard_artifact = "formula"
    guidance = {
        "math": "公式、定义、推导步骤与结论必须成对完整；逐步说明前提、依据、边界和结果核验。",
        "engineering": "代码、命令或配置使用完整 Markdown 围栏；写明环境前提、输入、运行方式、预期输出和排错检查。",
        "science": "区分观察、假设、证据、模型和结论；实验写明变量、对照、测量、不确定性与安全边界。",
        "life": "先明确层级与位置，再连接结构、功能和机制；区分正常与异常，不提供个人诊疗建议。",
        "humanities": "区分材料事实、解释与主张；交代来源语境、论证链、替代解释和证据限制。",
        "language": "提供目标语块、使用情境、范例、输出任务与可执行的反馈修正。",
        "business": "写清角色、目标、约束、选项、取舍、交付物和可区分质量的评价标准。",
        "general": "内容必须落到具体情境、操作、产物或可检查判断，不能停留在摘要和口号。",
    }[discipline]
    if role == "activity":
        guidance += " 练习须写清任务情境、已知条件、操作步骤与输出要求，并单列参考解法或验收标准，供学生独立完成和核对。"
    elif role == "feedback":
        guidance += " 辨析必须包含核对标准、典型错误、修正原因和再次验证。"
    elif role in {"reasoning", "example"}:
        guidance += " 推演必须展示关键中间步骤，不能只给结论。"
    return {
        "discipline": discipline,
        "hard_artifact": hard_artifact,
        "guidance": guidance,
    }


def teacher_script_length_contract(
    module_id: str,
    role: str,
    planned_minutes: Any,
) -> dict[str, int]:
    """Keep the existing bounded request budget for each handout module.

    Minutes remain a depth hint, not a speaking-rate limit. Generation and
    editorial advice must preserve necessary explanations and worked solutions.
    """
    compact_roles = {
        "orientation", "prerequisite", "objective", "checkpoint", "summary",
    }
    action_roles = {"activity", "feedback", "remediation"}
    if role in compact_roles:
        target, maximum = 320, 700
        upper_bound = 1000
    elif role in action_roles:
        target, maximum = 650, 1300
        upper_bound = 1800
    else:
        target, maximum = 900, 1800
        upper_bound = 2600
    try:
        minutes = float(planned_minutes)
    except (TypeError, ValueError):
        minutes = 0.0
    if minutes > 0:
        target = max(240, min(int(minutes * 70), upper_bound - 300))
        maximum = min(
            upper_bound,
            max(maximum, target + 300, int(minutes * 105)),
        )
    if module_id == "engineering_minimal_run":
        maximum = max(maximum, 2400)
        target = max(target, 1100)
    return {
        "target_characters": target,
        "max_characters": maximum,
    }


def compile_teacher_script_module_contract(
    outline_section: dict[str, Any],
    current_plan_section: dict[str, Any],
) -> dict[str, Any]:
    """Compile the frozen plan modules into the script's exact block contract."""
    section_id = _text(
        current_plan_section.get("node_id") or outline_section.get("node_id")
    )
    frozen_modules = [
        item
        for item in outline_section.get("module_plan") or []
        if isinstance(item, dict) and item.get("module_id")
    ]
    frozen_by_id = {
        _text(item.get("module_id")): item for item in frozen_modules
    }
    plan_modules = [
        item
        for item in current_plan_section.get("teaching_modules") or []
        if isinstance(item, dict) and item.get("module_id")
    ]
    # The current structurally usable plan owns the actual module order. The frozen outline
    # contract enriches it with labels/roles; it never appends a second module list.
    source_modules = plan_modules or frozen_modules
    modules: list[dict[str, Any]] = []
    for index, actual in enumerate(source_modules, start=1):
        module_id = _text(actual.get("module_id")) or "core_explanation"
        frozen = frozen_by_id.get(module_id) or {}
        registry = MODULES.get(module_id)
        role = _text(
            actual.get("block_role")
            or frozen.get("block_role")
            or module_block_role(module_id)
        )
        if role not in _ALLOWED_ROLES:
            role = "concept"
        label = _text(
            actual.get("label")
            or frozen.get("label")
            or (registry.label if registry else "")
            or module_id
        )
        length_contract = teacher_script_length_contract(
            module_id,
            role,
            actual.get("planned_minutes"),
        )
        modules.append({
            "block_id": _text(actual.get("block_id")) or _stable_block_id(section_id, module_id, index),
            "module_id": module_id,
            "role": role,
            "title": label,
            "required": bool(
                frozen.get("required", True) if frozen else actual.get("required", True)
            ),
            "knowledge_names": _text_list(actual.get("knowledge_names")),
            "planned_minutes": actual.get("planned_minutes"),
            "teaching_purpose": _text(actual.get("teaching_purpose")),
            "teaching_guidance": _text(actual.get("teaching_guidance")),
            "source_plan_context": {
                "teacher_activity": _text(actual.get("teacher_activity")),
                "student_activity": _text(actual.get("student_activity")),
                **({"expected_output": _text(actual.get("expected_output"))} if _text(actual.get("expected_output")) else {}),
                **({"check_method": _text(actual.get("check_method"))} if _text(actual.get("check_method")) else {}),
                **({"feedback_strategy": _text(actual.get("feedback_strategy"))} if _text(actual.get("feedback_strategy")) else {}),
                **({"adaptation_options": _text_list(actual.get("adaptation_options"))} if _text_list(actual.get("adaptation_options")) else {}),
                **({"engagement_mode": _text(actual.get("engagement_mode"))} if _text(actual.get("engagement_mode")) else {}),
                **({"access_support": _text(actual.get("access_support"))} if _text(actual.get("access_support")) else {}),
                **({"grouping": _text(actual.get("grouping"))} if _text(actual.get("grouping")) else {}),
                **({"transition": _text(actual.get("transition"))} if _text(actual.get("transition")) else {}),
            },
            "output_contract": _text(
                frozen.get("output_contract")
                or (registry.output_contract if registry else "")
            ),
            "prompt_instruction": _text(
                frozen.get("prompt_instruction")
                or (registry.prompt_instruction if registry else "")
            ),
            "artifact_contract": teacher_script_artifact_contract(
                module_id,
                role,
            ),
            **length_contract,
        })
    archetype = deepcopy(
        current_plan_section.get("lesson_archetype")
        or outline_section.get("lesson_archetype")
        or {}
    )
    if not archetype and frozen_modules:
        archetype = {
            "archetype_id": _text(frozen_modules[0].get("lesson_archetype_id")),
            "label": _text(frozen_modules[0].get("lesson_archetype_label")),
        }
    return {
        "schema_version": SCRIPT_SCHEMA_VERSION,
        "content_perspective": "teacher_delivery",
        "section_node_id": section_id,
        "title": _text(
            outline_section.get("node_name")
            or current_plan_section.get("title")
        ),
        "lesson_archetype": archetype,
        "learning_objective": _text(
            current_plan_section.get("learning_objective")
            or outline_section.get("learning_objective")
        ),
        "key_points": _text_list(current_plan_section.get("key_points")),
        "key_difficulties": _text_list(
            current_plan_section.get("key_difficulties")
        ),
        "in_class_checks": _text_list(
            current_plan_section.get("in_class_checks")
        ),
        "modules": modules,
    }






def teacher_script_blocks_to_markdown(blocks: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"## {_text(block.get('title'))}\n\n{_text(block.get('content'))}".strip()
        for block in blocks
        if isinstance(block, dict)
        and _text(block.get("title"))
        and _text(block.get("content"))
    )


def _segments(markdown: str) -> list[tuple[str, str]]:
    text = _text(markdown)
    matches = list(_HEADING_PATTERN.finditer(text))
    if not matches:
        return []
    return [
        (
            _text(match.group(1)),
            text[match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(text)].strip(),
        )
        for index, match in enumerate(matches)
    ]


def parse_teacher_script_markdown(
    markdown: str,
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    """Bind model Markdown to the preselected modules without guessing a new template."""
    expected = [item for item in contract.get("modules") or [] if isinstance(item, dict)]
    parsed = _segments(markdown)
    if not parsed and len(expected) == 1 and _text(markdown):
        parsed = [(_text(expected[0].get("title")), _text(markdown))]
    blocks: list[dict[str, Any]] = []
    for index, (title, content) in enumerate(parsed):
        module = expected[index] if index < len(expected) else {}
        if expected and all(item.get("module_id") == "handout_content" for item in expected) and len(expected) > 1:
            matches = [item for item in expected if item.get("title") == title]
            module = matches[0] if len(matches) == 1 else {}
        blocks.append({
            **{key: deepcopy(module[key]) for key in ("content_type", "type_label", "answer_to") if key in module},
            "block_id": _text(module.get("block_id")) or _stable_block_id(
                _text(contract.get("section_node_id")),
                _text(module.get("module_id")) or "extra",
                index + 1,
            ),
            "module_id": _text(module.get("module_id")),
            "role": _text(module.get("role")) or "concept",
            "title": title,
            "content": content,
            "required": bool(module.get("required", True)),
            "knowledge_names": deepcopy(module.get("knowledge_names") or []),
            "planned_minutes": module.get("planned_minutes"),
            "source_plan_context": deepcopy(module.get("source_plan_context") or {}),
        })
    return blocks


def normalize_teacher_script_section(
    section: dict[str, Any],
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize current structured blocks or teacher-authored Markdown."""
    value = deepcopy(section)
    has_contract = contract is not None
    compiled = contract or {
        "section_node_id": _text(value.get("section_node_id")),
        "title": _text(value.get("title")),
        "modules": [],
    }
    raw_blocks = [
        item for item in value.get("blocks") or [] if isinstance(item, dict)
    ]
    if raw_blocks:
        expected = ([] if compiled.get("flexible_blocks") else
                    [item for item in compiled.get("modules") or [] if isinstance(item, dict)])
        blocks: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_blocks, start=1):
            module = expected[index - 1] if index <= len(expected) else {}
            module_id = _text(raw.get("module_id") or module.get("module_id"))
            role = _text(raw.get("role") or module.get("role") or module_block_role(module_id))
            if role not in _ALLOWED_ROLES:
                role = "concept"
            blocks.append({
                **{key: deepcopy(raw.get(key, module.get(key))) for key in ("content_type", "type_label", "answer_to") if key in raw or key in module},
                "block_id": _text(raw.get("block_id") or module.get("block_id"))
                or _stable_block_id(
                    _text(compiled.get("section_node_id")), module_id or "unstructured", index
                ),
                "module_id": module_id,
                "role": role,
                "title": _text(raw.get("title") or module.get("title") or f"教学环节 {index}"),
                "content": _text(raw.get("content")),
                "required": bool(raw.get("required", module.get("required", True))),
                "knowledge_names": _text_list(
                    raw.get("knowledge_names") or module.get("knowledge_names")
                ),
                "planned_minutes": raw.get("planned_minutes", module.get("planned_minutes")),
                "source_plan_context": deepcopy(
                    raw.get("source_plan_context")
                    or module.get("source_plan_context")
                    or {
                        "teacher_activity": _text(raw.get("teacher_activity")),
                        "student_activity": _text(raw.get("student_activity")),
                    }
                ),
                "generation_source": _text(
                    raw.get("generation_source")
                    or module.get("generation_source")
                ),
                **({key: deepcopy(raw[key]) for key in ("ppt_pages", "ppt_errors", "ppt_page_groups", "ppt_page_repair_units", "ppt_repair_attempts", "ppt_recovery_contract_version", "generation_contract_version") if key in raw}
                   if raw.get("generation_contract_version") == "script_ppt_bundle_v1" else {}),
            })
    else:
        content = _text(value.get("content"))
        prose = compiled.get("modules") or []
        blocks = ([{**deepcopy(prose[0]), "content": content}] if len(prose) == 1 and prose[0].get("module_id") == "handout_prose"
                  else parse_teacher_script_markdown(content, compiled) if has_contract else [])
        if not blocks and content:
            blocks = [{
                "block_id": _stable_block_id(
                    _text(compiled.get("section_node_id")), "unstructured", 1
                ),
                "module_id": "unstructured_script",
                "role": "concept",
                "title": _text(value.get("title") or compiled.get("title") or "讲义正文"),
                "content": content,
                "required": True,
                "knowledge_names": [],
                "planned_minutes": None,
                "source_plan_context": {},
                "generation_source": _text(value.get("generation_source")),
            }]
    return {
        "schema_version": SCRIPT_SCHEMA_VERSION,
        "content_perspective": "teacher_delivery",
        "section_node_id": _text(
            value.get("section_node_id") or compiled.get("section_node_id")
        ),
        "title": _text(value.get("title") or compiled.get("title")),
        "lesson_archetype": deepcopy(compiled.get("lesson_archetype") or {}),
        "blocks": blocks,
        "content": teacher_script_blocks_to_markdown(blocks),
    }


def validate_teacher_script_section(
    section: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    normalized = normalize_teacher_script_section(section, contract)
    blocks = normalized["blocks"]
    expected = ([] if contract.get("flexible_blocks") else
                [item for item in contract.get("modules") or [] if isinstance(item, dict)])
    blocking: list[dict[str, str]] = []
    review: list[dict[str, str]] = []

    def add(target: list[dict[str, str]], code: str, message: str) -> None:
        target.append({"code": code, "message": message})

    if not normalized["section_node_id"]:
        add(blocking, "teacher_script:section_identity", "讲义小节缺少稳定标识。")
    if not blocks:
        add(blocking, "teacher_script:blocks_empty", "讲义没有可用的教学环节。")
    if any(not _text(block.get("content")) for block in blocks):
        add(blocking, "teacher_script:block_empty", "讲义仍有空白教学环节。")
    block_ids = [_text(block.get("block_id")) for block in blocks]
    if any(not block_id for block_id in block_ids) or len(block_ids) != len(set(block_ids)):
        add(blocking, "teacher_script:block_identity", "讲义教学环节标识缺失或重复。")
    by_id = {block.get("block_id"): block for block in blocks}
    allowed_knowledge = {name for module in contract.get("modules") or [] for name in module.get("knowledge_names") or []}
    for block in blocks:
        if block.get("module_id") != "handout_content":
            continue
        if not _text(block.get("content_type")) or not _text(block.get("title")):
            add(blocking, "teacher_script:block_type", "讲义内容块缺少类型或标题。")
        target = block.get("answer_to")
        if target and (target not in by_id or target == block.get("block_id")):
            add(blocking, "teacher_script:answer_reference", "解答引用的内容不存在或引用了自身。")
        if contract.get("flexible_blocks") and set(block.get("knowledge_names") or []) - allowed_knowledge:
            add(blocking, "teacher_script:knowledge_scope", "内容块引用了当前教案范围外的知识身份。")
    expected_ids = [_text(item.get("module_id")) for item in expected]
    actual_ids = [_text(item.get("module_id")) for item in blocks]
    if expected_ids and actual_ids != expected_ids:
        add(
            blocking,
            "teacher_script:module_contract",
            "讲义必须按当前可用教案的模块顺序完整覆盖，不能另选通用模板。",
        )
    expected_block_ids = [_text(item.get("block_id")) for item in expected]
    if expected_block_ids and block_ids != expected_block_ids:
        add(
            blocking,
            "teacher_script:block_contract",
            "讲义块身份必须沿用当前可用教案模块，不能重排或替换。",
        )
    expected_titles = [_text(item.get("title")) for item in expected]
    actual_titles = [_text(item.get("title")) for item in blocks]
    if expected_titles and actual_titles != expected_titles and not all(item.get("module_id") == "handout_content" for item in expected):
        add(
            blocking,
            "teacher_script:module_heading",
            "讲义块标题必须与当前教学模块一致。",
        )
    expected_roles = [_text(item.get("role")) for item in expected]
    actual_roles = [_text(item.get("role")) for item in blocks]
    if expected_roles and actual_roles != expected_roles:
        add(
            blocking,
            "teacher_script:role_contract",
            "讲义块角色必须沿用当前教学模块。",
        )
    for block, module in zip(blocks, expected):
        if set(_text_list(block.get("knowledge_names"))) - set(_text_list(module.get("knowledge_names"))):
            add(blocking, "teacher_script:knowledge_scope", "讲义块的知识绑定与当前教案不一致。")
    return {
        "schema_version": SCRIPT_QUALITY_VERSION,
        "pipeline_version": SCRIPT_PIPELINE_VERSION,
        "passed": not blocking,
        "blocking_issues": blocking,
        "review_issues": [],
        "metrics": {
            "block_count": len(blocks), "module_count": len(expected),
            "character_count": sum(len(_text(block.get("content"))) for block in blocks),
        },
    }


def _normalized_repetition_text(value: Any) -> str:
    text = _text(value).lower()
    text = re.sub(
        r"\$\$.+?\$\$|\\\[.+?\\\]",
        "",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(r"\d+(?:\.\d+)*", "#", text)
    text = re.sub(r"[\s`*_#，。；：、！？,.!?;:()（）\[\]{}<>《》]+", "", text)
    return text


def validate_teacher_script_revision(
    sections: list[dict[str, Any]], *, generation_source: str,
) -> dict[str, Any]:
    """Check storage integrity only; content review is no longer a delivery gate."""
    blocking: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    section_ids: set[str] = set()
    for section in sections:
        if not isinstance(section, dict):
            blocking.append({"code": "teacher_script:section_identity", "message": "讲义小节结构无效。"})
            continue
        section_id = _text(section.get("section_node_id"))
        if not section_id or section_id in section_ids:
            blocking.append({"code": "teacher_script:section_identity", "message": "讲义小节标识缺失或重复。"})
        section_ids.add(section_id)
        report = upgrade_script_quality_report(section.get("quality_report") or {})
        # Preserve contract mismatches found by the source-aware section check.
        for issue in report.get("blocking_issues") or []:
            if issue.get("code") in _SCRIPT_STRUCTURE_CODES:
                blocking.append({**deepcopy(issue), "section_node_id": section_id})
        actual = [b for b in section.get("blocks") or [] if isinstance(b, dict)]
        if not actual:
            blocking.append({"code": "teacher_script:blocks_empty", "message": "讲义小节没有正文块。"})
        blocks.extend(actual)
    if not sections:
        blocking.append({"code": "teacher_script:blocks_empty", "message": "讲义没有正文。"})
    ids = [_text(b.get("block_id")) for b in blocks]
    if any(not key for key in ids) or len(ids) != len(set(ids)):
        blocking.append({"code": "teacher_script:block_identity", "message": "讲义块标识缺失或重复。"})
    if any(not _text(b.get("content")) for b in blocks):
        blocking.append({"code": "teacher_script:block_empty", "message": "讲义仍有空白教学环节。"})
    return {
        "schema_version": SCRIPT_QUALITY_VERSION,
        "pipeline_version": SCRIPT_PIPELINE_VERSION,
        "passed": not blocking, "publication_eligible": not blocking,
        "blocking_issues": blocking, "review_issues": [],
        "metrics": {"section_count": len(sections), "block_count": len(blocks),
                    "character_count": sum(len(_text(b.get("content"))) for b in blocks)},
    }


_SCRIPT_STRUCTURE_CODES = {
    "teacher_script:section_identity", "teacher_script:blocks_empty",
    "teacher_script:block_empty", "teacher_script:block_identity",
    "teacher_script:module_contract", "teacher_script:block_contract",
    "teacher_script:module_heading", "teacher_script:role_contract", "teacher_script:knowledge_scope",
    "teacher_script:block_type", "teacher_script:answer_reference",
}


def upgrade_script_quality_report(report: dict[str, Any]) -> dict[str, Any]:
    """Retire old content checks without rewriting stored prose."""
    if report.get("schema_version") not in {
        f"teacher_script_quality_v{version}" for version in range(8, 14)
    } or report.get("pipeline_version") != SCRIPT_PIPELINE_VERSION:
        return report
    result = deepcopy(report)
    result["blocking_issues"] = [item for item in result.get("blocking_issues") or []
                                 if item.get("code") in _SCRIPT_STRUCTURE_CODES]
    result["review_issues"] = []
    result["schema_version"] = SCRIPT_QUALITY_VERSION
    result["passed"] = not result["blocking_issues"]
    if "publication_eligible" in result:
        result["publication_eligible"] = result["passed"]
    return result


def teacher_script_revision_is_publishable(revision: dict[str, Any]) -> bool:
    quality = upgrade_script_quality_report(revision.get("quality_report") or {})
    return bool(
        quality.get("publication_eligible") and quality.get("passed")
        and quality.get("schema_version") == SCRIPT_QUALITY_VERSION
        and quality.get("pipeline_version") == SCRIPT_PIPELINE_VERSION
        and validate_teacher_script_revision(
            revision.get("sections") or [], generation_source=str(revision.get("generation_source") or ""),
        )["passed"]
    )


def compile_teacher_script_section(
    markdown: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    modules = [m for m in contract.get("modules") or [] if isinstance(m, dict)]
    if len(modules) == 1 and markdown.strip():
        markdown = re.sub(r"\A\s*```(?:markdown|md)\s*\n([\s\S]*?)\n```\s*\Z", r"\1", markdown)
        markdown = re.sub(r"\A\s*#{1,2}[^\n]*\n", "", markdown).strip()
        raw = {"section_node_id": contract.get("section_node_id"), "title": contract.get("title"),
               "blocks": [{**deepcopy(modules[0]), "content": markdown}]}
        section = normalize_teacher_script_section(raw, contract)
    else:
        section = normalize_teacher_script_section(
            {
                "section_node_id": contract.get("section_node_id"),
                "title": contract.get("title"),
                "content": markdown,
            },
            contract,
        )
    section = repair_teacher_script_section_formats(section)
    section["quality_report"] = validate_teacher_script_section(section, contract)
    section["pipeline_version"] = SCRIPT_PIPELINE_VERSION
    return section


def repair_teacher_script_section_formats(section: dict[str, Any]) -> dict[str, Any]:
    """Repair delimiters only; never add missing facts or teaching content."""
    section = deepcopy(section)
    format_repairs: list[dict[str, Any]] = []
    for block in section.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        from canonical_content_repair import repair_display_math_shape

        original = str(block.get("content") or "")
        fence = None
        for line in original.splitlines():
            match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
            if match:
                marker, tail = match.groups()
                if fence is None:
                    fence = marker
                elif marker[0] == fence[0] and len(marker) >= len(fence) and not tail.strip():
                    fence = None
        if fence:
            original = original.rstrip() + "\n" + fence
            block["content"] = original
            format_repairs.append({"block_id": str(block.get("block_id") or ""), "repairs": ["close:code-fence"]})
        shape_repaired = repair_display_math_shape(original).strip()
        shape_repairs: list[str] = []
        if shape_repaired != original.strip():
            block["content"] = shape_repaired
            shape_repairs.append("normalize:display-math-shape")
        prose_repaired, prose_repairs = repair_teacher_script_display_math_prose(
            str(block.get("content") or original)
        )
        if prose_repairs:
            block["content"] = prose_repaired
        repaired, repairs = repair_teacher_script_math_delimiters(
            str(block.get("content") or "")
        )
        if shape_repairs or prose_repairs or repairs:
            block["content"] = repaired
            format_repairs.append({
                "block_id": str(block.get("block_id") or ""),
                "repairs": [*shape_repairs, *prose_repairs, *repairs],
            })
    section["content"] = teacher_script_blocks_to_markdown(
        section.get("blocks") or []
    )
    section["format_repairs"] = format_repairs
    return section
