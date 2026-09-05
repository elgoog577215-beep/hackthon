"""Deterministic cleanup applied before generated content is committed."""

from __future__ import annotations

import re
from typing import Any


def _read_balanced_latex_group(
    source: str,
    open_index: int,
) -> tuple[str, int] | None:
    if open_index >= len(source) or source[open_index] != "{":
        return None
    depth = 1
    cursor = open_index + 1
    while cursor < len(source):
        char = source[cursor]
        if char == "\\" and cursor + 1 < len(source):
            cursor += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[open_index + 1:cursor], cursor + 1
        cursor += 1
    return None


def _decode_latex_code_text(source: str) -> str:
    decoded = re.sub(r"\\textbackslash(?:\{\})?", r"\\", source)
    return re.sub(r'\\([_{}#$%&"])', r"\1", decoded)


def _decode_latex_code_expression(
    source: str,
) -> tuple[str, int, bool] | None:
    """Decode a code-only LaTeX fragment without consuming real formulas."""
    result: list[str] = []
    cursor = 0
    macro_count = 0
    recovered_malformed_group = False

    while cursor < len(source):
        if source.startswith("\\texttt{", cursor):
            open_index = cursor + len("\\texttt")
            group = _read_balanced_latex_group(source, open_index)
            macro_count += 1
            if group:
                body, end = group
                result.append(_decode_latex_code_text(body))
                cursor = end
                continue

            # Real provider failure: ``\texttt{if result:\} ...``. Only use
            # the escaped close as a recovery boundary after normal balancing
            # has failed.
            escaped_close = source.find("\\}", open_index + 1)
            if escaped_close < 0:
                return None
            result.append(
                _decode_latex_code_text(
                    source[open_index + 1:escaped_close]
                )
            )
            cursor = escaped_close + 2
            recovered_malformed_group = True
            continue

        if source.startswith("\\dots", cursor):
            result.append("...")
            cursor += len("\\dots")
            continue

        if source[cursor] == "\\" and cursor + 1 < len(source):
            escaped = source[cursor + 1]
            if escaped in '_{}#$%&"':
                result.append(escaped)
                cursor += 2
                continue
            if escaped.isalpha():
                return None

        result.append(source[cursor])
        cursor += 1

    if not macro_count:
        return None
    return " ".join("".join(result).split()), macro_count, recovered_malformed_group


def _is_high_confidence_code_expression(
    decoded: tuple[str, int, bool],
) -> bool:
    value, macro_count, recovered_malformed_group = decoded
    return bool(
        recovered_malformed_group
        or macro_count > 1
        or re.search(r'''[().:=<>"'\[\]]''', value)
        or re.search(
            r"\b(?:if|else|for|while|from|import|class|def|return|print)\b",
            value,
        )
    )


def _markdown_code_span(source: str) -> str:
    longest = max((len(run) for run in re.findall(r"`+", source)), default=0)
    fence = "`" * (longest + 1)
    padding = " " if source.startswith("`") or source.endswith("`") else ""
    return f"{fence}{padding}{source}{padding}{fence}"


def _repair_math_wrapped_latex_code_macros(line: str) -> str:
    r"""Recover high-confidence ``$\texttt{code}$`` near stray dollars."""
    result: list[str] = []
    cursor = 0
    while cursor < len(line):
        if line[cursor] == "`":
            run = re.match(r"`+", line[cursor:])
            fence = run.group(0) if run else "`"
            close = line.find(fence, cursor + len(fence))
            if close < 0:
                result.append(line[cursor:])
                break
            end = close + len(fence)
            result.append(line[cursor:end])
            cursor = end
            continue

        if (
            line[cursor] == "$"
            and not line.startswith("$$", cursor)
            and (cursor == 0 or line[cursor - 1] != "$")
            and (cursor == 0 or line[cursor - 1] != "\\")
        ):
            body_start = cursor + 1
            while body_start < len(line) and line[body_start] in " \t":
                body_start += 1
            if line.startswith("\\texttt{", body_start):
                close = line.find("$", body_start)
                if close >= 0 and not line.startswith("$$", close):
                    decoded = _decode_latex_code_expression(
                        line[body_start:close].strip()
                    )
                    if decoded and _is_high_confidence_code_expression(decoded):
                        result.append(_markdown_code_span(decoded[0]))
                        cursor = close + 1
                        continue

        result.append(line[cursor])
        cursor += 1

    return "".join(result)


def _unwrap_clearly_prose_dollar_lines(content: str) -> str:
    pattern = re.compile(
        r"^(?P<indent>[ \t]*)\$(?!\$)(?P<body>.*?)(?<!\\)\$(?P<trailing>[ \t]*)$",
        flags=re.MULTILINE,
    )

    def unwrap(match: re.Match[str]) -> str:
        body = match.group("body")
        first = body.lstrip()[:1]
        if not first or not re.match(r"[\u3400-\u9fff，。；：！？、]", first):
            return match.group(0)
        return f'{match.group("indent")}{body}{match.group("trailing")}'

    return pattern.sub(unwrap, content)


def _count_unescaped_table_pipes(line: str) -> int:
    count = 0
    index = 0
    while index < len(line):
        char = line[index]
        if char == "`":
            run = re.match(r"`+", line[index:])
            fence = run.group(0) if run else "`"
            close = line.find(fence, index + len(fence))
            if close >= 0:
                index = close + len(fence)
                continue
        if char != "|":
            index += 1
            continue
        slash_count = 0
        slash_cursor = index - 1
        while slash_cursor >= 0 and line[slash_cursor] == "\\":
            slash_count += 1
            slash_cursor -= 1
        if slash_count % 2 == 0:
            count += 1
        index += 1
    return count


def _is_markdown_table_delimiter(line: str) -> bool:
    trimmed = line.strip().removeprefix("|").removesuffix("|")
    cells = [cell.strip() for cell in trimmed.split("|")]
    return len(cells) > 1 and all(
        re.fullmatch(r":?-{3,}:?", cell) for cell in cells
    )


def _repair_broken_markdown_table_rows(content: str) -> str:
    """Join only proven GFM rows whose pipe count was split by streaming."""
    lines = content.splitlines(keepends=True)
    repaired: list[str] = []
    index = 0

    while index < len(lines):
        header = lines[index]
        delimiter = lines[index + 1] if index + 1 < len(lines) else ""
        if (
            not header.lstrip().startswith("|")
            or not _is_markdown_table_delimiter(delimiter)
        ):
            repaired.append(header)
            index += 1
            continue

        expected_pipes = _count_unescaped_table_pipes(header)
        repaired.extend((header, delimiter))
        index += 2

        while index < len(lines) and lines[index].lstrip().startswith("|"):
            row = lines[index]
            pipe_count = _count_unescaped_table_pipes(row)
            while pipe_count < expected_pipes and index + 1 < len(lines):
                continuation = lines[index + 1]
                continuation_pipes = _count_unescaped_table_pipes(continuation)
                if (
                    not continuation.strip()
                    or not continuation_pipes
                    or pipe_count + continuation_pipes > expected_pipes
                ):
                    break
                newline = "\n" if continuation.endswith("\n") else ""
                if continuation.endswith("\r\n"):
                    newline = "\r\n"
                row_body = row.rstrip("\r\n").rstrip()
                row = f"{row_body} {continuation.strip()}{newline}"
                pipe_count += continuation_pipes
                index += 1
            repaired.append(row)
            index += 1

    return "".join(repaired)


def _repair_latex_code_macros_in_line(
    line: str,
    *,
    math_block: str,
) -> tuple[str, str]:
    """Repair prose-only ``\\texttt`` while preserving Markdown regions."""
    if not math_block:
        line = _repair_math_wrapped_latex_code_macros(line)
    result: list[str] = []
    cursor = 0
    while cursor < len(line):
        if math_block:
            close = line.find(math_block, cursor)
            if close < 0:
                result.append(line[cursor:])
                break
            end = close + len(math_block)
            result.append(line[cursor:end])
            cursor = end
            math_block = ""
            continue

        if line[cursor] == "`":
            run = re.match(r"`+", line[cursor:])
            fence = run.group(0) if run else "`"
            close = line.find(fence, cursor + len(fence))
            if close < 0:
                result.append(line[cursor:])
                break
            end = close + len(fence)
            body = line[cursor + len(fence):close]
            decoded = (
                _decode_latex_code_expression(body)
                if body.lstrip().startswith("\\texttt{")
                else None
            )
            result.append(
                _markdown_code_span(decoded[0])
                if decoded
                else line[cursor:end]
            )
            cursor = end
            continue

        if line.startswith("$$", cursor):
            close = line.find("$$", cursor + 2)
            if close < 0:
                result.append(line[cursor:])
                math_block = "$$"
                break
            end = close + 2
            result.append(line[cursor:end])
            cursor = end
            continue

        if line.startswith("\\[", cursor):
            close = line.find("\\]", cursor + 2)
            if close < 0:
                result.append(line[cursor:])
                math_block = "\\]"
                break
            end = close + 2
            result.append(line[cursor:end])
            cursor = end
            continue

        if line.startswith("\\(", cursor):
            close = line.find("\\)", cursor + 2)
            if close >= 0:
                end = close + 2
                result.append(line[cursor:end])
                cursor = end
                continue

        if line[cursor] == "$" and (
            cursor == 0 or line[cursor - 1] != "\\"
        ):
            close = cursor + 1
            while close < len(line):
                close = line.find("$", close)
                if close < 0:
                    break
                if line[close - 1] != "\\":
                    break
                close += 1
            if close >= 0:
                result.append(line[cursor:close + 1])
                cursor = close + 1
                continue

        marker = "\\texttt{"
        if line.startswith(marker, cursor):
            group = _read_balanced_latex_group(
                line,
                cursor + len(marker) - 1,
            )
            if group:
                body, end = group
                result.append(_markdown_code_span(_decode_latex_code_text(body)))
                cursor = end
                continue

        result.append(line[cursor])
        cursor += 1

    return "".join(result), math_block


def repair_latex_code_macros(content: str) -> str:
    """Convert legacy prose ``\\texttt`` to Markdown code before persistence.

    The repair is intentionally syntax-aware: fenced code and genuine math
    keep their original bytes, while high-confidence code disguised as inline
    math is recovered. This avoids the old failure mode where a broad regular
    expression fixed one lesson while corrupting another syntax region.
    """
    lines = str(content or "").splitlines(keepends=True)
    result: list[str] = []
    fence_char = ""
    fence_size = 0
    math_block = ""

    for line in lines:
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            marker = fence.group(1)
            marker_char = marker[0]
            if not fence_char:
                fence_char = marker_char
                fence_size = len(marker)
            elif marker_char == fence_char and len(marker) >= fence_size:
                fence_char = ""
                fence_size = 0
            result.append(line)
            continue
        if fence_char:
            result.append(line)
            continue

        repaired, math_block = _repair_latex_code_macros_in_line(
            line,
            math_block=math_block,
        )
        result.append(repaired)

    repaired = "".join(result)
    repaired = _unwrap_clearly_prose_dollar_lines(repaired)
    return _repair_broken_markdown_table_rows(repaired)


def _remap_assessment_revision_references(
    assets: dict[str, Any],
    revision_remap: dict[str, str],
) -> None:
    """Keep mastery and final-assessment links aligned after a prompt repair."""
    for asset_type in ("mastery_criteria", "misconceptions"):
        for item in assets.get(asset_type) or []:
            if not isinstance(item, dict):
                continue
            item["assessment_bindings"] = [
                revision_remap.get(str(value), str(value))
                for value in item.get("assessment_bindings") or []
            ]
    for item in assets.get("final_assessment") or []:
        if not isinstance(item, dict):
            continue
        item["question_revision_ids"] = [
            revision_remap.get(str(value), str(value))
            for value in item.get("question_revision_ids") or []
        ]


def fix_latex_content(content: str) -> str:
    """修复 LaTeX 公式格式问题"""
    if not content:
        return content

    content = repair_latex_code_macros(content)

    def fix_aligned_env(match: re.Match[str]) -> str:
        env_name = match.group(1)
        inner = match.group(2) if match.lastindex and match.lastindex >= 2 else ""

        inner = re.sub(r"\$\s*$", "", inner)
        inner = re.sub(r"^\s*\$", "", inner)
        inner = re.sub(r"\$\$", "", inner)
        inner = re.sub(r"\\\$", r"\\", inner)
        inner = re.sub(r"\\\s*$", r"\\", inner, flags=re.MULTILINE)
        inner = re.sub(r"\\\s*\n", r"\\\n", inner)

        return f"$$\n\\begin{{{env_name}}}\n{inner}\n\\end{{{env_name}}}\n$$"

    content = re.sub(
        r'\\begin\{(aligned|matrix|pmatrix|bmatrix|vmatrix|cases|eqnarray|gather|split)\}(.*?)(?:\\end\{\1\}|$)',
        fix_aligned_env,
        content,
        flags=re.DOTALL,
    )

    content = re.sub(r"\\\[(.+?)\\\]", r"\n$$\n\1\n$$\n", content, flags=re.DOTALL)
    content = re.sub(r"\\\((.+?)\\\)", r"$\1$", content, flags=re.DOTALL)

    content = re.sub(
        r'(?<!\$)\$([^\n$]+?)\$(?!\$)',
        lambda match: f'${match.group(1).strip()}$',
        content,
    )

    # A streamed model can stop after opening a display formula. Repair the
    # smallest deterministic boundary here, before the node is marked complete,
    # while leaving literal dollars inside fenced code untouched.
    lines = content.splitlines()
    in_code_fence = False
    display_fence_count = 0
    for index, line in enumerate(lines):
        if re.match(r"^\s*```", line):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        # Some providers still emit the legacy Markdown display form with a
        # single dollar on its own line. The quality gate correctly rejects
        # that form, so normalize it before a generated node is finalized.
        # Literal dollars inside fenced code were excluded above.
        if re.match(r"^\s*(?<!\\)\$\s*$", line):
            normalized = re.sub(r"\$", "$$", line, count=1)
        else:
            normalized = re.sub(r"(?<!\\)\${3,}", "$$", line)
        lines[index] = normalized
        display_fence_count += len(
            re.findall(r"(?<!\\)\$\$", normalized)
        )
    content = "\n".join(lines)
    if display_fence_count % 2:
        content = f"{content.rstrip()}\n$$\n"

    return content


__all__ = ["fix_latex_content", "repair_latex_code_macros"]
