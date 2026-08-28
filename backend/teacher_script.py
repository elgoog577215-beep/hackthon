"""可直接讲授的教师讲稿结构真源与确定性质量门。

讲稿不重新选择学科类型、课型或教学模板。它把已确认教案中的教学模块编译为
教师站在讲台上可以自然说出的完整讲述：既讲清知识，也写出过渡、提问、活动指令、
可能回应和反馈。机械舞台标签仍留在教案，真实教师语言进入讲稿。
"""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any

from course_pedagogy import MODULES, module_block_role


SCRIPT_SCHEMA_VERSION = "teacher_script_v2"
SCRIPT_PIPELINE_VERSION = "direct_teaching_script_v8"
SCRIPT_QUALITY_VERSION = "teacher_script_quality_v8"

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
_TRANSITION_PATTERN = re.compile(
    r"接下来|刚才|现在|再看|回到|带着这个|下面|前面|到这里|"
    r"到这一步|最后|因此|接着|由此|进一步"
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
    r"当前教学块围绕|形式化检查锦标|"
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
    has been confirmed.  New model output is normalized before this predicate
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
        guidance += " 练习必须用教师可直接说出的语言写清任务情境、已知条件、输出要求、等待点、可能回应与验收标准。"
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
    """Give every module a complete but bounded direct-teaching budget.

    The script is a polished teacher utterance, not a raw transcript and not a
    short cue card. The minute budget controls depth while leaving room for
    explanation, transitions, questions, likely responses and feedback.
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
    confirmed_plan_section: dict[str, Any],
) -> dict[str, Any]:
    """Compile the frozen plan modules into the script's exact block contract."""
    section_id = _text(
        confirmed_plan_section.get("node_id") or outline_section.get("node_id")
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
        for item in confirmed_plan_section.get("teaching_modules") or []
        if isinstance(item, dict) and item.get("module_id")
    ]
    # A confirmed mature plan owns the actual module order. The frozen outline
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
            "block_id": _stable_block_id(section_id, module_id, index),
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
        confirmed_plan_section.get("lesson_archetype")
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
            or confirmed_plan_section.get("title")
        ),
        "lesson_archetype": archetype,
        "learning_objective": _text(
            confirmed_plan_section.get("learning_objective")
            or outline_section.get("learning_objective")
        ),
        "key_points": _text_list(confirmed_plan_section.get("key_points")),
        "key_difficulties": _text_list(
            confirmed_plan_section.get("key_difficulties")
        ),
        "in_class_checks": _text_list(
            confirmed_plan_section.get("in_class_checks")
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


def compile_teacher_script_fallback_content(
    module: dict[str, Any],
) -> str:
    """Compile an explicit editable baseline when the provider is unavailable.

    The confirmed lesson plan already owns the teaching purpose, knowledge
    scope, guidance and activity contract.  A quota or authentication outage
    should therefore not leave 0/N blank blocks.  This compiler never invents
    a new module or fact; it turns that confirmed contract into an editable
    direct-teaching draft and is always reported as a local fallback.
    """

    def spoken(value: Any) -> str:
        text = _text(value)
        replacements = {
            "教师应": "接下来要",
            "教师需要": "接下来要",
            "学生应": "请大家",
            "学生需要": "请大家",
            "学生完成": "请大家完成",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text

    title = spoken(module.get("title")) or "当前教学块"
    purpose = spoken(module.get("teaching_purpose"))
    guidance = spoken(module.get("teaching_guidance"))
    knowledge = "、".join(_text_list(module.get("knowledge_names")))
    source_context = module.get("source_plan_context") or {}
    activity = spoken(source_context.get("student_activity"))
    explanation = spoken(source_context.get("teacher_activity"))
    expected_output = spoken(source_context.get("expected_output"))
    feedback = spoken(source_context.get("feedback_strategy"))
    role = _text(module.get("role"))
    artifact = module.get("artifact_contract") or {}

    paragraphs = [
        f"现在我们进入{title}。这一段要解决的是{knowledge or '当前核心问题'}。"
        f"{purpose or '到这里，大家需要形成一个可以当场检查的结果'}。",
    ]
    if guidance:
        paragraphs.append(f"先看清这里的方法：{guidance}。")
    if explanation:
        paragraphs.append(f"我们一步一步来看。{explanation}。")
    if activity or role in {"activity", "feedback", "checkpoint"}:
        paragraphs.append(
            f"现在请大家{activity or '根据已知条件完成当前任务'}。"
            f"完成后我们用{expected_output or '条件、过程与结论'}逐项核对。"
            f"如果还没有达到标准，{feedback or '先找出差距，修正后再做一次'}。"
        )
    if _text(artifact.get("hard_artifact")) == "formula":
        paragraphs.append(
            "最后用这个形式化关系检查我们的推理："
            r"\(\mathrm{given}\Rightarrow\mathrm{derivation}"
            r"\Rightarrow\mathrm{verified\ result}\)"
            "。公式中的对象、条件和结论必须与当前知识范围一致。"
        )

    content = "\n\n".join(paragraphs)
    max_characters = int(module.get("max_characters") or 0)
    if max_characters and len(content) > max_characters:
        content = content[: max(20, max_characters - 1)].rstrip("，、：； ") + "。"
    return content


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
        blocks.append({
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
    """Normalize v2 blocks and preserve v1 Markdown through a one-way adapter."""
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
        expected = [item for item in compiled.get("modules") or [] if isinstance(item, dict)]
        blocks: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_blocks, start=1):
            module = expected[index - 1] if index <= len(expected) else {}
            module_id = _text(raw.get("module_id") or module.get("module_id"))
            role = _text(raw.get("role") or module.get("role") or module_block_role(module_id))
            if role not in _ALLOWED_ROLES:
                role = "concept"
            blocks.append({
                "block_id": _text(raw.get("block_id") or module.get("block_id"))
                or _stable_block_id(
                    _text(compiled.get("section_node_id")), module_id or "legacy", index
                ),
                "module_id": module_id,
                "role": role,
                "title": _text(raw.get("title") or module.get("title") or f"教学块 {index}"),
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
            })
    else:
        content = _text(value.get("content"))
        blocks = parse_teacher_script_markdown(content, compiled) if has_contract else []
        if not blocks and content:
            blocks = [{
                "block_id": _stable_block_id(
                    _text(compiled.get("section_node_id")), "legacy", 1
                ),
                "module_id": "legacy_script",
                "role": "concept",
                "title": _text(value.get("title") or compiled.get("title") or "讲稿正文"),
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
    expected = [item for item in contract.get("modules") or [] if isinstance(item, dict)]
    blocking: list[dict[str, str]] = []
    review: list[dict[str, str]] = []

    def add(target: list[dict[str, str]], code: str, message: str) -> None:
        target.append({"code": code, "message": message})

    if not normalized["section_node_id"]:
        add(blocking, "teacher_script:section_identity", "讲稿小节缺少稳定标识。")
    if not blocks:
        add(blocking, "teacher_script:blocks_empty", "讲稿没有可用的教学块。")
    if any(not _text(block.get("content")) for block in blocks):
        add(blocking, "teacher_script:block_empty", "讲稿仍有空白教学块。")
    block_ids = [_text(block.get("block_id")) for block in blocks]
    if any(not block_id for block_id in block_ids) or len(block_ids) != len(set(block_ids)):
        add(blocking, "teacher_script:block_identity", "讲稿教学块标识缺失或重复。")
    expected_ids = [_text(item.get("module_id")) for item in expected]
    actual_ids = [_text(item.get("module_id")) for item in blocks]
    if expected_ids and actual_ids != expected_ids:
        add(
            blocking,
            "teacher_script:module_contract",
            "讲稿必须按已确认教案的模块顺序完整覆盖，不能另选通用模板。",
        )
    expected_block_ids = [_text(item.get("block_id")) for item in expected]
    if expected_block_ids and block_ids != expected_block_ids:
        add(
            blocking,
            "teacher_script:block_contract",
            "讲稿块身份必须沿用已确认教案模块，不能重排或替换。",
        )
    expected_titles = [_text(item.get("title")) for item in expected]
    actual_titles = [_text(item.get("title")) for item in blocks]
    if expected_titles and actual_titles != expected_titles:
        add(
            blocking,
            "teacher_script:module_heading",
            "讲稿块标题必须与已确认教学模块一致。",
        )
    expected_roles = [_text(item.get("role")) for item in expected]
    actual_roles = [_text(item.get("role")) for item in blocks]
    if expected_roles and actual_roles != expected_roles:
        add(
            blocking,
            "teacher_script:role_contract",
            "讲稿块角色必须沿用已确认教学模块。",
        )
    for index, block in enumerate(blocks):
        if index >= len(expected):
            continue
        allowed_knowledge = set(_text_list(expected[index].get("knowledge_names")))
        actual_knowledge = set(_text_list(block.get("knowledge_names")))
        if actual_knowledge - allowed_knowledge:
            add(
                blocking,
                "teacher_script:knowledge_scope",
                f"“{_text(block.get('title'))}”引用了当前教案范围外的知识。",
            )
        content = _text(block.get("content"))
        max_characters = int(expected[index].get("max_characters") or 0)
        if max_characters and len(content) > max_characters:
            add(
                blocking,
                "teacher_script:block_too_long",
                (
                    f"“{_text(block.get('title'))}”过长（{len(content)} 字），"
                    f"讲稿单块上限为 {max_characters} 字。"
                ),
            )
        artifact = expected[index].get("artifact_contract") or {}
        hard_artifact = _text(artifact.get("hard_artifact"))
        if hard_artifact == "fenced_code" and "```" not in content:
            add(
                blocking,
                "teacher_script:required_code_artifact",
                f"“{_text(block.get('title'))}”缺少可直接运行的完整代码围栏。",
            )
        if hard_artifact == "formula" and not re.search(
            r"\$\$|\$[^$\n]+\$|\\\(|\\\[",
            content,
        ):
            add(
                blocking,
                "teacher_script:required_math_artifact",
                f"“{_text(block.get('title'))}”缺少完整公式或形式化表达。",
            )
        role = _text(block.get("role"))
        if role == "activity" and not (
            _ACTIVITY_TASK_PATTERN.search(content)
            and _ACTIVITY_RESULT_PATTERN.search(content)
        ):
            add(
                blocking,
                "teacher_script:practice_not_complete",
                f"“{_text(block.get('title'))}”没有同时写清任务条件与结果、解法或验收标准。",
            )
        if role in {"feedback", "misconception"} and not (
            _FEEDBACK_ERROR_PATTERN.search(content)
            and _FEEDBACK_REPAIR_PATTERN.search(content)
        ):
            add(
                blocking,
                "teacher_script:feedback_not_checkable",
                f"“{_text(block.get('title'))}”没有同时给出典型错误与可执行的修正、核对标准。",
            )
    for block in blocks:
        content = _text(block.get("content"))
        if _DELIVERY_CUE_PATTERN.search(content):
            add(
                blocking,
                "teacher_script:classroom_delivery_cue",
                f"“{_text(block.get('title'))}”仍用机械的提问、板书、巡视或等待标签，没有改写成自然教师语言。",
            )
        if _LESSON_PLAN_VOICE_PATTERN.search(content):
            add(
                blocking,
                "teacher_script:lesson_plan_voice",
                f"“{_text(block.get('title'))}”仍在描述教师或学生应当做什么，没有写成教师可以直接说的话。",
            )
        if _INTERNAL_PROCESS_PATTERN.search(content):
            add(
                blocking,
                "teacher_script:internal_process_leakage",
                f"“{_text(block.get('title'))}”泄露了模型、质量门或内部生成过程语言。",
            )
        if _PLACEHOLDER_PATTERN.search(content):
            add(
                blocking,
                "teacher_script:placeholder_content",
                f"“{_text(block.get('title'))}”仍是恢复模板或占位文字，不是可直接授课的讲稿正文。",
            )
        canned_count = len(_CANNED_DISCOURSE_PATTERN.findall(content))
        if canned_count >= 4:
            add(
                blocking,
                "teacher_script:canned_discourse",
                f"“{_text(block.get('title'))}”连续使用程式化连接词，课堂语言仍有明显模板感。",
            )
        visible_tail = re.sub(r"```\s*$", "", content).rstrip()
        if visible_tail and _INCOMPLETE_END_PATTERN.search(visible_tail):
            add(
                blocking,
                "teacher_script:incomplete_block_ending",
                f"“{_text(block.get('title'))}”结尾似乎被截断，未形成完整语义。",
            )
        if content.count("```") % 2:
            add(
                blocking,
                "teacher_script:unclosed_code_fence",
                f"“{_text(block.get('title'))}”存在未闭合的代码围栏。",
            )
        delimiter_state = _markdown_math_delimiter_state(content)
        if (
            delimiter_state["display_open"]
            or delimiter_state["inline_open"]
            or delimiter_state["inline_cross_line"]
            or delimiter_state["latex_stack"]
            or delimiter_state["unexpected"]
        ):
            add(
                blocking,
                "teacher_script:unclosed_math_delimiter",
                f"“{_text(block.get('title'))}”存在未闭合的公式定界符。",
            )
        if _has_unwrapped_display_math_environment(content):
            add(
                blocking,
                "teacher_script:unwrapped_display_math_environment",
                (
                    f"“{_text(block.get('title'))}”把矩阵或分段公式环境拆在 "
                    "$$ 分隔符之外，无法作为 PPT 的可靠公式真源。"
                ),
            )
        if _display_math_contains_teaching_prose(content):
            add(
                blocking,
                "teacher_script:prose_inside_display_math",
                (
                    f"“{_text(block.get('title'))}”的块级公式分隔符吞入了题目、"
                    "解法或讲解正文，无法可靠渲染或生成 PPT。"
                ),
            )
        table_lines = [line for line in content.splitlines() if "|" in line]
        if table_lines and not any(
            re.match(r"^\s*\|?\s*:?-{3,}", line) for line in table_lines
        ):
            add(
                review,
                "teacher_script:table_not_structured",
                f"“{_text(block.get('title'))}”包含表格式内容，但缺少完整表头分隔行。",
            )
        target_characters = 0
        matching = next(
            (
                item for item in expected
                if _text(item.get("block_id")) == _text(block.get("block_id"))
            ),
            {},
        )
        try:
            target_characters = int(matching.get("target_characters") or 0)
        except (TypeError, ValueError):
            target_characters = 0
        minimum_characters = max(40, min(120, int(target_characters * 0.2)))
        if len(content) < minimum_characters:
            add(
                review,
                "teacher_script:block_too_shallow",
                (
                    f"“{_text(block.get('title'))}”只有 {len(content)} 字，"
                    "不足以形成可直接授课的完整讲解或任务。"
                ),
            )
    combined_content = "\n".join(_text(block.get("content")) for block in blocks)
    if len(combined_content) >= 120 and not _DIRECT_TEACHING_PATTERN.search(combined_content):
        add(
            blocking,
            "teacher_script:not_directly_teachable",
            "整节讲稿缺少自然讲解、提问或引导语言，仍像教材正文，不能直接站在讲台上讲。",
        )
    if len(blocks) > 1 and not any(
        _TRANSITION_PATTERN.search(_text(block.get("content")))
        for block in blocks[1:]
    ):
        add(
            blocking,
            "teacher_script:missing_transition",
            "相邻教学块之间没有自然承接，教师实际讲授时会出现明显跳段。",
        )
    return {
        "schema_version": SCRIPT_QUALITY_VERSION,
        "pipeline_version": SCRIPT_PIPELINE_VERSION,
        "passed": not blocking,
        "blocking_issues": blocking,
        "review_issues": review,
        "metrics": {
            "block_count": len(blocks),
            "module_count": len(expected),
            "character_count": sum(len(_text(block.get("content"))) for block in blocks),
            "code_fence_count": sum(
                _text(block.get("content")).count("```") for block in blocks
            ),
            "formula_block_count": sum(
                1
                for block in blocks
                if re.search(r"\$\$|\$[^$\n]+\$|\\\(|\\\[", _text(block.get("content")))
            ),
            "classroom_delivery_cue_count": sum(
                len(_DELIVERY_CUE_PATTERN.findall(_text(block.get("content"))))
                for block in blocks
            ),
            "lesson_plan_voice_count": sum(
                len(_LESSON_PLAN_VOICE_PATTERN.findall(_text(block.get("content"))))
                for block in blocks
            ),
            "direct_teaching_cue_count": len(_DIRECT_TEACHING_PATTERN.findall(combined_content)),
            "internal_process_leakage_count": sum(
                len(_INTERNAL_PROCESS_PATTERN.findall(_text(block.get("content"))))
                for block in blocks
            ),
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
    sections: list[dict[str, Any]],
    *,
    generation_source: str,
) -> dict[str, Any]:
    """Apply the same publication gate to model, edit, recovery and legacy paths."""
    blocking: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    total_minutes = 0.0

    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("section_node_id"))
        report = section.get("quality_report") or {}
        if (
            report.get("schema_version") != SCRIPT_QUALITY_VERSION
            or report.get("pipeline_version") != SCRIPT_PIPELINE_VERSION
        ):
            blocking.append({
                "code": "teacher_script:quality_contract_stale",
                "message": "讲稿尚未按当前质量规则重新检查，请重新保存或生成。",
                "section_node_id": section_id,
            })
        for issue in report.get("blocking_issues") or []:
            if isinstance(issue, dict):
                blocking.append({**deepcopy(issue), "section_node_id": section_id})
        for issue in report.get("review_issues") or []:
            if isinstance(issue, dict):
                review.append({**deepcopy(issue), "section_node_id": section_id})
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            blocks.append(block)
            try:
                total_minutes += max(0.0, float(block.get("planned_minutes") or 0))
            except (TypeError, ValueError):
                pass

    source = _text(generation_source)
    if "fallback" in source or "recovery" in source:
        blocking.append({
            "code": "teacher_script:recovery_draft_not_publishable",
            "message": "当前稿包含提供方失败后的本地恢复内容，只能继续编辑或重新生成，不能确认或生成 PPT。",
        })
    if source.startswith("legacy"):
        blocking.append({
            "code": "teacher_script:legacy_source_not_revalidated",
            "message": "旧正文没有绑定当前教案质量契约，需重新编辑保存或重新生成后才能发布。",
        })

    normalized_blocks = [
        (_text(block.get("block_id")), _normalized_repetition_text(block.get("content")))
        for block in blocks
        if len(_normalized_repetition_text(block.get("content"))) >= 28
    ]
    duplicate_pairs: list[tuple[str, str]] = []
    repeated_clauses: dict[str, set[str]] = {}
    for block in blocks:
        block_id = _text(block.get("block_id"))
        # Numeric examples commonly reuse the same matrix or cases *shape*
        # while changing coefficients and conclusions.  The repetition
        # normalizer intentionally abstracts numbers for prose boilerplate,
        # so feeding display formulae into it collapses distinct matrices into
        # the same token stream and creates an unrecoverable retry loop.  Whole
        # block duplication still covers copied formula blocks; clause-level
        # repetition is reserved for explanatory prose.
        repetition_prose = re.sub(
            r"\$\$.+?\$\$|\\\[.+?\\\]",
            "",
            _text(block.get("content")),
            flags=re.DOTALL,
        )
        clauses = {
            _normalized_repetition_text(item)
            for item in re.split(r"[。！？!?；;\n]+", repetition_prose)
            if len(_normalized_repetition_text(item)) >= 14
        }
        for clause in clauses:
            repeated_clauses.setdefault(clause, set()).add(block_id)
    for index, (left_id, left) in enumerate(normalized_blocks):
        for right_id, right in normalized_blocks[index + 1:]:
            shorter = min(len(left), len(right))
            if shorter < 28:
                continue
            prefix = 0
            while prefix < shorter and left[prefix] == right[prefix]:
                prefix += 1
            if left == right or prefix / shorter >= 0.82:
                duplicate_pairs.append((left_id, right_id))
    repeated_clause_groups = [
        sorted(block_ids)
        for block_ids in repeated_clauses.values()
        if len(block_ids) >= 3
    ]
    if len(duplicate_pairs) >= 2 or repeated_clause_groups:
        blocking.append({
            "code": "teacher_script:repetitive_blocks",
            "message": "多个教学块高度复读，未形成随知识内容推进的有效讲解。",
            "block_pairs": duplicate_pairs[:8],
            "repeated_clause_groups": repeated_clause_groups[:8],
        })

    canned_phrase_blocks: dict[str, set[str]] = {}
    for block in blocks:
        block_id = _text(block.get("block_id"))
        for phrase in set(_CANNED_DISCOURSE_PATTERN.findall(_text(block.get("content")))):
            canned_phrase_blocks.setdefault(phrase, set()).add(block_id)
    repeated_canned_phrases = {
        phrase: sorted(block_ids)
        for phrase, block_ids in canned_phrase_blocks.items()
        if len(block_ids) >= 4
    }
    if repeated_canned_phrases:
        blocking.append({
            "code": "teacher_script:repetitive_canned_transitions",
            "message": "多个教学块反复使用同一套程式化连接词，讲稿需要改成随内容自然推进的课堂语言。",
            "phrase_blocks": repeated_canned_phrases,
        })

    character_count = sum(len(_text(block.get("content"))) for block in blocks)
    minimum_lesson_characters = int(total_minutes * 55)
    if len(blocks) >= 4 and total_minutes >= 30 and character_count < minimum_lesson_characters:
        blocking.append({
            "code": "teacher_script:lesson_too_shallow",
            "message": (
                f"整讲约 {total_minutes:g} 分钟，但正文只有 {character_count} 字，"
                "不足以支撑完整授课。"
            ),
        })

    unique_blocking: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in blocking:
        key = (
            _text(issue.get("code")),
            _text(issue.get("section_node_id")),
            _text(issue.get("message")),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_blocking.append(issue)
    return {
        "schema_version": SCRIPT_QUALITY_VERSION,
        "pipeline_version": SCRIPT_PIPELINE_VERSION,
        "passed": not unique_blocking,
        "publication_eligible": not unique_blocking,
        "blocking_issues": unique_blocking,
        "review_issues": review,
        "metrics": {
            "section_count": len(sections),
            "block_count": len(blocks),
            "character_count": character_count,
            "planned_minutes": total_minutes,
            "minimum_lesson_characters": minimum_lesson_characters,
            "duplicate_pair_count": len(duplicate_pairs),
            "repeated_clause_group_count": len(repeated_clause_groups),
            "repeated_canned_phrase_count": len(repeated_canned_phrases),
        },
    }


def teacher_script_revision_is_publishable(revision: dict[str, Any]) -> bool:
    quality = revision.get("quality_report") or {}
    return bool(
        revision.get("publication_eligible")
        and quality.get("passed")
        and quality.get("publication_eligible")
        and quality.get("schema_version") == SCRIPT_QUALITY_VERSION
        and quality.get("pipeline_version") == SCRIPT_PIPELINE_VERSION
    )


def compile_teacher_script_section(
    markdown: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    section = normalize_teacher_script_section(
        {
            "section_node_id": contract.get("section_node_id"),
            "title": contract.get("title"),
            "content": markdown,
        },
        contract,
    )
    format_repairs: list[dict[str, Any]] = []
    for block in section.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        from canonical_content_repair import repair_display_math_shape

        original = str(block.get("content") or "")
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
    section["quality_report"] = validate_teacher_script_section(section, contract)
    section["pipeline_version"] = SCRIPT_PIPELINE_VERSION
    return section
