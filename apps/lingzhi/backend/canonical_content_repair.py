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

from display_math_repair import repair_display_math_shape, repair_split_display_math

import re

from course_commands import CourseCommandService
from course_document import CourseBlock, stable_hash
from course_errors import CourseDocumentConflict
from course_repository import CourseDocumentRepository

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
