"""确定性的正文形状修复：把被拆开的块级公式围栏合并回一个完整块。

原有内容（`persist_generated_node_content`）负责「把模型输出安全写进空的
canonical 小节」。本模块补的是写进去之前的一步：**把模型写坏的块级公式围栏
形状修回来**——同样是确定性操作，不调用模型，不猜语义。

## 修的是什么

在 8 门真实课程的 792 节正文上实测，渲染失败的 29 节里有 24 节（82.8%）源于
同一种形状：模型想写一个公式 `V(x) = \\begin{cases}...\\end{cases}`，却把它写
成了三段——

    $$
    V(x) =            ← 前缀自己闭合成一个块
    $$
    \\begin{cases}     ← 环境被孤立在下一块
    ...
    \\end{cases}
    $$
                       ← 有时还多出一个空块
    $$

`$$` 总数是偶数，所以任何奇偶校验都看不见它。含此形状的节点渲染失败率
61.5%，不含的只有 0.67%——相差 92 倍。

## 为什么值得在这里做确定性修复

这不只是「公式不好看」。多出来的空 `$$` 对会**开启一个没有闭合的数学块**，
把后续正文连同 `##` 标题一起吸进公式里。受控实验：同一段内容，带空 `$$` 对
的那份标题被摧毁、正文退化成源码；不带的那份完全正常。**它是内容丢失，不是
排版瑕疵。**

前端 `markdown.ts` 的归一化救回了其中 15 个，剩下 24 个是它覆盖不到的变体。
在下游继续加正则是打地鼠——试过一版，8 个节点只有 2 个改善、3 个反而更糟。
所以修复放在内容进入存储之前，一次修干净。

生成侧的提示词约束（「块级环境必须与前缀写在同一组 `$$` 内」）归 lz-course-gen，
本模块不碰；两者是互补关系：提示词减少产生，这里兜住已经产生的。
"""

from __future__ import annotations

import re

from course_commands import CourseCommandService
from course_document import CourseBlock, stable_hash
from course_repository import CourseDocumentConflict, CourseDocumentRepository

# 与 frontend/src/utils/markdown.ts:258 的 DISPLAY_MATH_ENVIRONMENTS 保持一致。
# 这里只列真正会被写成「前缀 + 环境」两段的块级环境。
_DISPLAY_ENVIRONMENTS = (
    "bmatrix|pmatrix|vmatrix|Bmatrix|Vmatrix|matrix|array|aligned|split|cases"
    "|equation|gather|align"
)

_ENV_OPEN = re.compile(rf"\\begin\{{(?:{_DISPLAY_ENVIRONMENTS})\}}")
_ENV_CLOSE = re.compile(rf"\\end\{{(?:{_DISPLAY_ENVIRONMENTS})\}}")
_CODE_FENCE = re.compile(r"^\s*```")


def _segments(text: str) -> list[tuple[str, str]]:
    """把正文按 `$$` 切成交替的「正文段 / 公式段」。

    返回 [(kind, content), ...]，kind 为 "text" 或 "math"。代码块内的 `$$`
    不参与切分——课程正文里到处是代码块，把 Python 字符串里的 `$` 当成公式
    分隔符会毁掉正文（实测踩过一次同类误伤）。
    """
    lines = text.split("\n")
    in_fence = False
    protected: list[str] = []
    for line in lines:
        if _CODE_FENCE.match(line):
            in_fence = not in_fence
            protected.append(line)
            continue
        # 代码块内把 `$$` 换成占位符，切分完再换回来。
        protected.append(line.replace("$$", "\x00DD\x00") if in_fence else line)
    masked = "\n".join(protected)

    parts = masked.split("$$")
    segments: list[tuple[str, str]] = []
    for index, part in enumerate(parts):
        kind = "text" if index % 2 == 0 else "math"
        segments.append((kind, part.replace("\x00DD\x00", "$$")))
    return segments


def _is_orphan_environment(chunk: str) -> bool:
    """这一段是不是一个「孤立的块级环境体」。"""
    body = chunk.strip()
    if not body:
        return False
    return bool(_ENV_OPEN.search(body) and _ENV_CLOSE.search(body))


def _is_join_fragment(chunk: str) -> bool:
    """这一段是不是公式的一部分，而不是真正的正文。

    判据保守：只在整段**没有任何自然语言句子**、且看起来是公式片段时才算。
    典型形态是 `V(x) =`、`, \\quad \\sigma_y =`、`+ t`、`.`，以及空串。
    误判成 True 会把正文吞进公式，所以这里宁可漏修也不多修。
    """
    body = chunk.strip()
    if not body:
        return True
    if len(body) > 80:
        return False
    # 含成句的中文/英文说明就不是公式片段。中文标点是最可靠的信号。
    if re.search(r"[，。；：！？、“”（）]", body):
        return False
    if re.search(r"[\u4e00-\u9fff]{4,}", body):
        return False
    # Markdown 结构（标题、列表、引用）一定是正文。
    if re.match(r"^(#{1,6}\s|[-*+]\s|\d+\.\s|>)", body):
        return False
    # 到这里只剩短片段。要求它像公式：以运算符/关系符收尾或起头，
    # 或整体由 LaTeX 命令与符号组成。
    if re.search(r"(?:=|\\leftrightarrow|\\to|\\Rightarrow|\\sim|\+|-|,|\.)\s*$", body):
        return True
    if re.match(r"^\s*(?:[,.+\-]|\\quad|\\,|\\;)", body):
        return True
    if re.fullmatch(r"[\\A-Za-z0-9_^{}()\[\]\s|/*+\-=.,:]+", body):
        return True
    return False


def repair_split_display_math(markdown: str) -> str:
    """把被 `$$` 拆开的块级公式合并回一个完整块。

    切分后的段序列是交替的 text / math。被拆开的公式呈现为这样一串：

        math: "V(x) ="                 ← 只有前缀的公式段
        text: "\\begin{cases}...\\end{cases}"  ← 环境体落在了正文槽位里
        math: ""                       ← 多出来的空块

    关键在于**环境体出现在 text 槽位**——它本该在公式里。所以合并条件是
    「当前公式段之后，紧跟着一个孤立环境体的 text 段」，把两者并回同一个
    `$$` 块；随后若还跟着空公式段与新的环境体（泡利矩阵那种链式形态），
    继续并下去。

    最初我把方向搞反了（以为环境体在 math 槽位），结果 8 个节点只修好 1 个。
    这是按真实切分结果纠正后的实现。只做形状合并，不改动公式内容。
    """
    text = str(markdown or "")
    if "$$" not in text:
        return text

    segments = _segments(text)
    if len(segments) < 3:
        return text

    result: list[tuple[str, str]] = []
    index = 0
    changed = False
    while index < len(segments):
        kind, chunk = segments[index]
        if kind != "math":
            result.append((kind, chunk))
            index += 1
            continue

        merged = chunk.strip()
        # 只要下一段正文其实是一个孤立的环境体，它就属于当前公式。
        while (
            index + 1 < len(segments)
            and segments[index + 1][0] == "text"
            and _is_orphan_environment(segments[index + 1][1])
        ):
            body = segments[index + 1][1].strip()
            merged = f"{merged}\n{body}" if merged else body
            index += 1
            changed = True
            # 环境体之后往往跟着一个空公式段（多余的空块），以及可能的连接
            # 碎片 + 下一个环境体。空块要丢弃，链式碎片要并进来。
            if index + 1 < len(segments) and segments[index + 1][0] == "math":
                nxt = segments[index + 1][1].strip()
                if not nxt:
                    index += 1  # 丢弃空块
                elif _is_join_fragment(nxt):
                    merged = f"{merged}\n{nxt}"
                    index += 1
                else:
                    break
        result.append(("math", merged))
        index += 1

    if not changed:
        return text

    rebuilt: list[str] = []
    for kind, chunk in result:
        if kind == "text":
            rebuilt.append(chunk)
        else:
            body = chunk.strip()
            rebuilt.append(f"$$\n{body}\n$$" if body else "")
    return "".join(rebuilt)


def _drop_empty_display_blocks(markdown: str) -> str:
    """删掉内容为空的 `$$ ... $$` 块。

    单独一步，因为它可以独立发生：有些节点没有被拆开的公式，只是多了一个空块，
    而空块同样会开启未闭合的数学块、吞掉后文。
    """
    return re.sub(r"\$\$[ \t]*\n?[ \t]*\$\$", "", str(markdown or ""))


def repair_display_math_shape(markdown: str) -> str:
    """对外的确定性形状修复入口。"""
    repaired = repair_split_display_math(markdown)
    repaired = _drop_empty_display_blocks(repaired)
    # 合并后可能留下三个以上连续空行，收敛成两个，避免影响 Markdown 分块。
    return re.sub(r"\n{3,}", "\n\n", repaired)


async def persist_generated_node_content(
    *,
    repository: CourseDocumentRepository,
    course_id: str,
    section_id: str,
    markdown: str,
    actor: str,
) -> dict:
    """Insert model output only when the canonical section has no active block."""
    content = str(markdown or "").strip()
    if (
        len(content) < 40
        or content.startswith("[Error:")
        or content.startswith("[Persistence Error:")
    ):
        raise CourseDocumentConflict(
            "Website generation did not produce content that can be persisted"
        )
    # 在写入存储之前修好围栏形状：坏形状会吞掉后续正文与标题，一旦落库，
    # 后面每一个消费者（渲染、PPT、打印）都得各自去应付同一个坏形状。
    content = repair_display_math_shape(content).strip()

    document, _ = repository.load_document(course_id)
    section = next(
        (
            item
            for item in document.sections
            if item.section_id == section_id
        ),
        None,
    )
    if section is None:
        raise CourseDocumentConflict("Course section not found")
    if any(
        block.section_id == section_id and block.status != "retired"
        for block in document.blocks
    ):
        raise CourseDocumentConflict(
            "Canonical section already has content; use block regeneration"
        )

    identity = {
        "course_id": course_id,
        "section_id": section_id,
        "source_revision": document.document_revision,
        "markdown": content,
    }
    block_id = stable_hash(identity, prefix="cbr_")
    command_id = stable_hash(identity, prefix="cmd_")
    block = CourseBlock(
        block_id=block_id,
        section_id=section_id,
        position=0,
        kind="rich_text",
        role="concept",
        payload={
            "title": section.title,
            "markdown": content,
        },
        objective_refs=(
            [section.objective_id]
            if section.objective_id
            else []
        ),
    )
    return await CourseCommandService(repository).insert_block(
        course_id,
        command_id=command_id,
        expected_document_revision=document.document_revision,
        block=block,
        reason="fill_empty_section_from_website_generation",
        actor=actor,
    )


__all__ = [
    "persist_generated_node_content",
    "repair_display_math_shape",
    "repair_split_display_math",
]
