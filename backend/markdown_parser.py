"""
markdown_parser.py — 纯 Python Markdown 解析模块

将 Markdown 文本解析为课程节点列表，无任何 I/O 操作，
不依赖 storage.py 或其他后端模块。
"""

import re
import uuid
from datetime import datetime

# 匹配 Markdown 图片语法: ![alt](url)
IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

def _parse_heading(line: str) -> tuple[int, str] | None:
    """
    解析 ATX 标题行。

    Args:
        line: 单行文本

    Returns:
        (depth, text) 元组，若不是标题则返回 None
    """
    match = re.match(r'^(#{1,6})\s+(.*)', line)
    if match:
        depth = len(match.group(1))
        text = match.group(2).strip()
        return (depth, text)
    return None


def _detect_min_depth(lines: list[str]) -> int:
    """
    扫描所有 ATX 标题，返回最小深度值。
    代码围栏（```或~~~）内的行不计入。

    Args:
        lines: 文档行列表

    Returns:
        最小标题深度（1-6），若无标题则返回 0
    """
    min_depth = 7  # 超出最大深度 6
    in_code_fence = False
    fence_pattern = re.compile(r'^(`{3,}|~{3,})')
    for line in lines:
        m = fence_pattern.match(line)
        if m:
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        result = _parse_heading(line)
        if result is not None:
            depth, _ = result
            if depth < min_depth:
                min_depth = depth
    return min_depth if min_depth <= 6 else 0


def _compute_level(depth: int, min_depth: int) -> int:
    """
    将 ATX 标题深度映射为逻辑层级（1-3）。

    Args:
        depth:     ATX 标题深度
        min_depth: 文档中最小标题深度

    Returns:
        逻辑层级，范围 [1, 3]
    """
    level = depth - min_depth + 1
    return max(1, min(3, level))


def _find_parent(stack: list[dict], level: int) -> str:
    """
    在祖先栈中查找 level-1 层级的最近祖先节点 ID。

    Args:
        stack: 祖先节点栈（按层级排列）
        level: 当前节点的逻辑层级

    Returns:
        父节点的 node_id，若无则返回 "root"
    """
    target_level = level - 1
    # 从栈顶向下查找第一个层级为 target_level 的节点
    for node in reversed(stack):
        if node['node_level'] == target_level:
            return node['node_id']
    return 'root'


def _process_image(match: re.Match) -> str:
    """
    处理图片匹配：外部 URL 保留原样，本地路径替换为占位符。

    Args:
        match: IMAGE_RE 的匹配对象，group(1)=alt, group(2)=url

    Returns:
        处理后的字符串
    """
    alt = match.group(1)
    url = match.group(2)
    is_external = url.startswith('http://') or url.startswith('https://')
    if is_external:
        return f'![{alt}]({url})'
    placeholder = f'[图片: {alt}]' if alt else '[图片]'
    return placeholder


def _process_body(raw: str) -> str:
    """
    对正文内容应用图片替换处理。

    Args:
        raw: 原始正文文本

    Returns:
        处理后的文本
    """
    return IMAGE_RE.sub(_process_image, raw)


# ---------------------------------------------------------------------------
# 主解析函数
# ---------------------------------------------------------------------------

def parse_markdown_to_nodes(text: str, filename: str) -> tuple[list[dict], str]:
    """
    将 Markdown 文本解析为节点列表和课程名称。

    Args:
        text:     原始 UTF-8 Markdown 内容
        filename: 原始文件名（不含扩展名），用作备用课程名称
                  以及前置文本合成根节点的名称

    Returns:
        (nodes, course_name)
        nodes:       符合 Node 模式的字典列表
        course_name: 来自第一个最小层级标题，或 filename

    Raises:
        ValueError: 若文档不含任何 ATX 标题
    """
    lines = text.splitlines()

    # 步骤 1：检测最小标题深度
    min_depth = _detect_min_depth(lines)
    if min_depth == 0:
        raise ValueError('未检测到 Markdown 标题，请确保文件包含至少一个 # 标题')

    nodes: list[dict] = []
    ancestor_stack: list[dict] = []
    current_body: list[str] = []
    pre_heading_lines: list[str] = []
    current_node: dict | None = None
    in_code_fence = False
    fence_re = re.compile(r'^(`{3,}|~{3,})')

    def _finalize_node(node: dict, body_lines: list[str]) -> None:
        """将累积的正文行赋值给节点的 node_content。"""
        raw = '\n'.join(body_lines).strip()
        node['node_content'] = _process_body(raw)

    # 步骤 2：逐行处理
    for line in lines:
        # 追踪代码围栏状态，围栏内的行不解析为标题
        if fence_re.match(line):
            in_code_fence = not in_code_fence
            if current_node is None:
                pre_heading_lines.append(line)
            else:
                current_body.append(line)
            continue

        if in_code_fence:
            if current_node is None:
                pre_heading_lines.append(line)
            else:
                current_body.append(line)
            continue

        heading = _parse_heading(line)
        if heading is not None:
            depth, heading_text = heading
            level = _compute_level(depth, min_depth)

            if current_node is None:
                # 尚未遇到第一个标题，当前行是第一个标题
                pass
            else:
                # 完成上一个节点的正文
                _finalize_node(current_node, current_body)
                current_body = []

            # 更新祖先栈：弹出层级 >= 当前层级的节点
            while ancestor_stack and ancestor_stack[-1]['node_level'] >= level:
                ancestor_stack.pop()

            # 确定父节点 ID
            parent_id = ancestor_stack[-1]['node_id'] if ancestor_stack else 'root'

            # 创建新节点
            new_node: dict = {
                'node_id': str(uuid.uuid4()),
                'parent_node_id': parent_id,
                'node_name': heading_text,
                'node_level': level,
                'node_content': '',
                'node_type': 'original',
                'is_read': False,
                'quiz_score': None,
                'create_time': datetime.utcnow().isoformat(),
            }

            nodes.append(new_node)
            ancestor_stack.append(new_node)
            current_node = new_node

        else:
            # 非标题行
            if current_node is None:
                pre_heading_lines.append(line)
            else:
                current_body.append(line)

    # 步骤 3：完成最后一个节点的正文
    if current_node is not None:
        _finalize_node(current_node, current_body)

    # 步骤 4：若存在前置文本，创建合成根节点并前置
    pre_heading_text = '\n'.join(pre_heading_lines).strip()
    if pre_heading_text:
        synthetic_node: dict = {
            'node_id': str(uuid.uuid4()),
            'parent_node_id': 'root',
            'node_name': filename,
            'node_level': 1,
            'node_content': _process_body(pre_heading_text),
            'node_type': 'original',
            'is_read': False,
            'quiz_score': None,
            'create_time': datetime.utcnow().isoformat(),
        }
        nodes.insert(0, synthetic_node)

    # 步骤 5：确定课程名称
    course_name = filename
    for node in nodes:
        if node['node_level'] == 1:
            course_name = node['node_name']
            break

    return nodes, course_name


# ---------------------------------------------------------------------------
# 美化输出函数
# ---------------------------------------------------------------------------

def pretty_print(nodes: list[dict]) -> str:
    """
    将节点列表序列化回 Markdown 文档。

    node_level 1 → '#', 2 → '##', 3 → '###'
    每个标题后跟空行，然后是 node_content（若非空），再跟空行。

    Args:
        nodes: 节点字典列表

    Returns:
        格式化的 Markdown 字符串（末尾无多余空白）
    """
    parts: list[str] = []
    for node in nodes:
        level = node.get('node_level', 1)
        hashes = '#' * level
        name = node.get('node_name', '')
        content = node.get('node_content', '')

        if content:
            parts.append(f'{hashes} {name}\n\n{content}\n\n')
        else:
            parts.append(f'{hashes} {name}\n\n')

    result = ''.join(parts)
    return result.rstrip()
